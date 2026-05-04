# -*- coding: utf-8 -*-
"""
enricher.py — массовый LLM-анализ звонков без анализа.

Функция bulk_enrich() обрабатывает все звонки которым не хватает Analysis,
отправляет их на анализ через LLM (llama.cpp), и сохраняет результаты.

CLI: python -m callprofiler bulk-enrich --user <user_id> [--limit 100]
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from callprofiler.analyze.llm_client import LLMClient
from callprofiler.analyze.profanity_detector import count_profanity
from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.config import load_config
from callprofiler.db.repository import Repository
from callprofiler.events import emit_event_sync
from callprofiler.models import Analysis

log = logging.getLogger(__name__)

# Сегменты короче этого (в символах) убираются из транскрипта,
# кроме специально сохраняемых коротких слов.
_MIN_SEG_CHARS = 3
_KEEP_SHORT_SEGS = {"да", "ну", "угу"}

# Если суммарный текст транскрипта короче — пропустить LLM.
_SHORT_CALL_THRESHOLD = 50

# Кол-во звонков, накапливаемых перед записью одной транзакцией.
_BATCH_SIZE = 5


def _extract_events_from_analysis(
    analysis: Analysis,
    user_id: str,
    contact_id: int | None,
    call_id: int,
) -> list[dict]:
    """Extract structured events from LLM analysis result.

    Converts analysis fields into event records:
    - promises → 'promise' events (who: Me→OWNER, S2→OTHER)
    - action_items → 'task' events
    - bs_evidence → 'contradiction' events
    - amounts → 'debt' events
    - Handles role mapping and graceful error handling.

    If extraction fails for any field, log and continue (don't fail the enrichment).
    """
    events = []

    try:
        # Promises → event type 'promise'
        if hasattr(analysis, "promises") and analysis.promises:
            for p in analysis.promises:
                try:
                    if isinstance(p, dict):
                        who_raw = p.get("who", "UNKNOWN")
                        # Map Me→OWNER, S2→OTHER
                        who_mapped = "OWNER" if who_raw == "Me" else (
                            "OTHER" if who_raw == "S2" else "UNKNOWN"
                        )
                        events.append({
                            "user_id": user_id,
                            "contact_id": contact_id,
                            "call_id": call_id,
                            "event_type": "promise",
                            "who": who_mapped,
                            "payload": p.get("what", ""),
                            "deadline": p.get("due"),
                            "confidence": 0.9,
                            "status": "open",
                        })
                except Exception as e:
                    log.warning("[enricher] Ошибка при извлечении promise: %s", e)
                    continue

        # Action items → event type 'task'
        if hasattr(analysis, "action_items") and analysis.action_items:
            for item in analysis.action_items:
                try:
                    if isinstance(item, str):
                        events.append({
                            "user_id": user_id,
                            "contact_id": contact_id,
                            "call_id": call_id,
                            "event_type": "task",
                            "who": "OWNER",  # Actions are for owner
                            "payload": item,
                            "confidence": 0.85,
                            "status": "open",
                        })
                except Exception as e:
                    log.warning("[enricher] Ошибка при извлечении action_item: %s", e)
                    continue

        # bs_evidence → 'contradiction' events
        try:
            raw_resp = getattr(analysis, "raw_response", "") or ""
            if raw_resp:
                # Try to extract bs_evidence from raw JSON response
                import json
                try:
                    parsed = json.loads(raw_resp)
                    bs_evidence = parsed.get("bs_evidence", [])
                    if bs_evidence and isinstance(bs_evidence, list):
                        for evidence in bs_evidence:
                            if isinstance(evidence, str) and len(evidence) > 0:
                                events.append({
                                    "user_id": user_id,
                                    "contact_id": contact_id,
                                    "call_id": call_id,
                                    "event_type": "contradiction",
                                    "who": "UNKNOWN",
                                    "payload": evidence,
                                    "source_quote": evidence[:100],  # First 100 chars as quote
                                    "confidence": 0.8,
                                    "status": "open",
                                })
                except (json.JSONDecodeError, TypeError):
                    pass  # raw_response не распарсился или не JSON
        except Exception as e:
            log.warning("[enricher] Ошибка при извлечении bs_evidence: %s", e)

        # Amounts → 'debt' events
        try:
            raw_resp = getattr(analysis, "raw_response", "") or ""
            if raw_resp:
                import json
                try:
                    parsed = json.loads(raw_resp)
                    amounts = parsed.get("amounts", [])
                    if amounts and isinstance(amounts, list):
                        for amount in amounts:
                            if isinstance(amount, str) and len(amount) > 0:
                                events.append({
                                    "user_id": user_id,
                                    "contact_id": contact_id,
                                    "call_id": call_id,
                                    "event_type": "debt",
                                    "who": "UNKNOWN",
                                    "payload": f"Сумма упомянута: {amount}",
                                    "source_quote": amount[:100],
                                    "confidence": 0.75,
                                    "status": "open",
                                })
                except (json.JSONDecodeError, TypeError):
                    pass
        except Exception as e:
            log.warning("[enricher] Ошибка при извлечении amounts: %s", e)

    except Exception as e:
        log.error("[enricher] Неожиданная ошибка при извлечении events: %s", e)
        # Don't fail enrichment, just skip events for this call

    return events


def _format_transcript(segments: list[dict]) -> str:
    """Форматировать и сжать транскрипт для промпта.

    Убирает пустые и очень короткие сегменты (< 3 символов),
    оставляя исключения: "да", "ну", "угу".
    """
    lines = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        if len(text) < _MIN_SEG_CHARS and text.lower() not in _KEEP_SHORT_SEGS:
            continue
        role = "[Я]" if seg.get("speaker") == "OWNER" else "[Собеседник]"
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _load_prompt_template(prompts_dir: str) -> str:
    """Загрузить шаблон промпта для анализа."""
    prompt_file = Path(prompts_dir) / "analyze_v001.txt"
    if not prompt_file.exists():
        log.warning("Файл промпта не найден: %s, используется встроенный шаблон", prompt_file)
        return """Проанализируй стенограмму разговора и верни ТОЛЬКО валидный JSON:
{
  "priority": <0-100>,
  "risk_score": <0-100>,
  "summary": "<краткое резюме>",
  "action_items": ["<действие1>", ...],
  "promises": [{"who": "OWNER|OTHER", "what": "<обещание>", "due": null}],
  "flags": {"urgent": <bool>, "follow_up_needed": <bool>},
  "key_topics": ["<тема>", ...]
}"""
    return prompt_file.read_text(encoding="utf-8")


def _stub_analysis() -> Analysis:
    """Заглушка для короткого звонка без содержания."""
    return Analysis(
        priority=0,
        risk_score=0,
        summary="Короткий звонок без содержания",
        action_items=[],
        promises=[],
        flags={},
        key_topics=[],
        raw_response="",
        model="stub",
        prompt_version="v001",
        call_type="short",
        hook=None,
    )


def _flush_batch(repo: Repository, batch: list[dict]) -> int:
    """Записать батч в БД одной транзакцией. Возвращает кол-во ошибок."""
    if not batch:
        return 0
    try:
        repo.save_batch(batch)
        log.debug("[enricher] Батч записан (%d элементов)", len(batch))
        # Сохранить события отдельно (save_batch их не трогает)
        for item in batch:
            if item.get("events"):
                repo.save_events(item["call_id"], item["events"])
        return 0
    except Exception as e:
        log.error("[enricher] Ошибка batch-записи: %s — пробуем по одному", e)
        failed = 0
        for item in batch:
            try:
                repo.save_analysis(item["call_id"], item["analysis"])
                if item.get("promises") and item.get("contact_id") is not None:
                    repo.save_promises(
                        item["user_id"], item["contact_id"],
                        item["call_id"], item["promises"],
                    )
                if item.get("events"):
                    repo.save_events(item["call_id"], item["events"])
            except Exception as ie:
                log.error("[enricher] ERR call_id=%d: ошибка записи: %s", item["call_id"], ie)
                failed += 1
        return failed


def _update_graph(repo: Repository, call_ids: list[int]) -> None:
    """Update Knowledge Graph for a list of call_ids (only v2 analyses).

    Lazily imported to avoid circular dependency and to keep graph module optional.
    """
    try:
        from callprofiler.graph.builder import GraphBuilder
        from callprofiler.graph.repository import apply_graph_schema

        conn = repo._get_conn()
        apply_graph_schema(conn)
        builder = GraphBuilder(conn)
        for call_id in call_ids:
            builder.update_from_call(call_id)
    except Exception as e:
        log.warning("[enricher] graph update failed (non-fatal): %s", e)


def bulk_enrich(
    user_id: str,
    db_path: str,
    config_path: str = "configs/base.yaml",
    limit: int = 0,
) -> dict[str, int]:
    """
    Массовый LLM-анализ для всех звонков без анализа.

    Параметры:
        user_id      — ID пользователя
        db_path      — путь к БД
        config_path  — путь к конфигу (для LLM URL и промпта)
        limit        — максимум файлов (0 = все)

    Возвращает:
        {"processed": N, "failed": N, "skipped": N, "total": N}
    """
    cfg = load_config(config_path)
    repo = Repository(db_path)
    repo.init_db()

    user = repo.get_user(user_id)
    if not user:
        log.error("[enricher] Пользователь '%s' не найден", user_id)
        return {"processed": 0, "failed": 0, "skipped": 0, "total": 0}

    try:
        llm = LLMClient(base_url=cfg.models.llm_url, timeout=300)
    except ConnectionError as e:
        log.error("[enricher] Ошибка подключения к LLM: %s", e)
        return {"processed": 0, "failed": 0, "skipped": 0, "total": 0}

    prompts_dir = Path(cfg.data_dir).parent / "configs" / "prompts"
    if not prompts_dir.exists():
        prompts_dir = Path("configs") / "prompts"
    prompt_template = _load_prompt_template(str(prompts_dir))

    conn = repo._get_conn()
    rows = conn.execute(
        """SELECT c.call_id, c.user_id, c.contact_id, c.call_datetime,
                  c.source_filename, c.direction, cnt.phone_e164, cnt.display_name
           FROM calls c
           LEFT JOIN contacts cnt ON c.contact_id = cnt.contact_id
           LEFT JOIN analyses a ON c.call_id = a.call_id
           WHERE c.user_id = ? AND a.analysis_id IS NULL
           ORDER BY c.call_datetime""",
        (user_id,),
    ).fetchall()

    calls = [dict(row) for row in rows]
    if limit > 0:
        calls = calls[:limit]

    total = len(calls)
    log.info("[enricher] Найдено %d звонков для анализа (пользователь: %s)", total, user_id)

    stats = {"processed": 0, "partial": 0, "failed": 0, "skipped": 0, "total": total}
    pending_batch: list[dict] = []
    llm_times: list[float] = []
    tokens_total = 0
    global_start = time.time()

    try:
        for idx, call in enumerate(calls, 1):
            call_id = call["call_id"]
            phone = call.get("phone_e164") or "unknown"
            name = call.get("display_name") or "?"
            call_start = time.time()

            try:
                segments = repo.get_transcript(call_id)
                if not segments:
                    log.warning("[enricher] call_id=%d: транскрипт пустой, пропускаем", call_id)
                    stats["skipped"] += 1
                    continue

                transcript_text = _format_transcript(segments)
                is_partial = False  # По умолчанию полный успех

                # Словарный детектор мата (без LLM, дешёвый): считаем
                # ДО разветвления, чтобы и stub-путь, и LLM-путь сохраняли метрику.
                # Feature flag: можно полностью отключить (например, на анонимизированных
                # данных или если результат не используется).
                if cfg.features.enable_profanity_detection:
                    profanity = count_profanity(transcript_text)
                else:
                    profanity = {"count": 0, "unique": 0, "density": 0.0}

                # Короткий звонок — не отправлять в LLM
                if len(transcript_text) < _SHORT_CALL_THRESHOLD:
                    log.info(
                        "[enricher] %d/%d call_id=%d | короткий (%d симв) — stub | %.1fс",
                        idx, total, call_id, len(transcript_text), time.time() - call_start,
                    )
                    analysis = _stub_analysis()
                    is_partial = True
                else:
                    # Подсказка LLM: метрика мата как доп. сигнал для bs_score / call_type.
                    # Модель всё ещё может игнорировать, но в JSON-ответе обычно
                    # повышает risk/bs при высокой плотности.
                    profanity_hint = (
                        f"Сигнал детектора (не LLM): "
                        f"мат={profanity['count']} ("
                        f"уникальных={profanity['unique']}, "
                        f"плотность={profanity['density']}/100слов). "
                        f"Учти при оценке bs_score и call_type."
                    )
                    user_message = (
                        f"Метаданные звонка:\n"
                        f"Контакт: {name} ({phone})\n"
                        f"Дата: {call.get('call_datetime', 'unknown')}\n"
                        f"Направление: {call.get('direction', 'UNKNOWN')}\n"
                        f"{profanity_hint}\n\n"
                        f"Стенограмма:\n{transcript_text}"
                    )

                    llm_start = time.time()
                    llm_response = llm.generate(
                        messages=[
                            {"role": "system", "content": prompt_template},
                            {"role": "user", "content": user_message},
                        ],
                        temperature=0.3,
                        max_tokens=1500,
                    )
                    llm_elapsed = time.time() - llm_start

                    # Если LLM вернул None — ошибка подключения/timeout
                    if llm_response is None:
                        log.error("[enricher] ERR call_id=%d: LLM вернул None (ошибка/timeout)", call_id)
                        stats["failed"] += 1
                        continue

                    llm_times.append(llm_elapsed)
                    est_tokens = max(1, len(llm_response) // 4)
                    tokens_total += est_tokens
                    tps = est_tokens / llm_elapsed if llm_elapsed > 0 else 0

                    analysis = parse_llm_response(llm_response)
                    is_partial = not analysis.summary  # Если summary пусто — парсинг частичный
                    parse_status = getattr(analysis, "parse_status", "unknown")

                    # ETA по всем завершённым (включая skipped/failed)
                    completed = stats["processed"] + stats["partial"] + stats["skipped"] + stats["failed"]
                    elapsed_total = time.time() - global_start
                    rate = completed / elapsed_total if elapsed_total > 0 and completed > 0 else 0
                    eta = (total - idx) / rate if rate > 0 else 0

                    status = "[partial]" if is_partial else "OK"
                    log.info(
                        "[enricher] %d/%d call_id=%d | %s | parse_status=%s | %.1fс/файл | ~%.0f tok/с | ETA %.0fс",
                        idx, total, call_id, status, parse_status,
                        time.time() - call_start, tps, eta,
                    )

                # Прикрепить метрику мата к анализу (сохраняется в БД)
                analysis.profanity_count = profanity["count"]
                analysis.profanity_density = profanity["density"]

                # Счётчик partial успехов
                if is_partial:
                    stats["partial"] += 1
                else:
                    stats["processed"] += 1

                # Extract events from analysis (feature-gated)
                if cfg.features.enable_event_extraction:
                    events = _extract_events_from_analysis(
                        analysis, user_id, call.get("contact_id"), call_id
                    )
                else:
                    events = []

                pending_batch.append({
                    "call_id": call_id,
                    "analysis": analysis,
                    "user_id": user_id,
                    "contact_id": call.get("contact_id"),
                    "promises": getattr(analysis, "promises", []),
                    "events": events,
                })

                # Промежуточная статистика каждые 50 файлов
                completed = stats["processed"] + stats["partial"] + stats["skipped"] + stats["failed"]
                if completed % 50 == 0 and completed > 0:
                    elapsed = time.time() - global_start
                    rate = completed / elapsed if elapsed > 0 else 0
                    log.info(
                        "[enricher] промежуточная статистика (%d/%d): успешно %d, частичных %d, "
                        "пропущено %d, ошибок %d (%.1f файлов/сек)",
                        completed, total, stats["processed"], stats["partial"],
                        stats["skipped"], stats["failed"], rate,
                    )

            except Exception as e:
                log.error("[enricher] ERR call_id=%d: ошибка обработки: %s", call_id, e)
                stats["failed"] += 1
                # Продолжаем, несмотря на ошибку одного звонка

            # Батчевая запись каждые BATCH_SIZE файлов
            if len(pending_batch) >= _BATCH_SIZE:
                stats["failed"] += _flush_batch(repo, pending_batch)
                if cfg.features.enable_graph_update:
                    _update_graph(repo, [it["call_id"] for it in pending_batch])

                # Emit real-time events to dashboard
                for item in pending_batch:
                    try:
                        emit_event_sync("analysis_complete", {
                            "call_id": item["call_id"],
                            "contact_label": call.get("display_name") or call.get("source_filename", "Unknown"),
                            "risk_score": item["analysis"].risk_score,
                            "call_type": item["analysis"].call_type,
                            "summary": item["analysis"].summary,
                        })
                    except Exception as e:
                        log.warning("[enricher] Failed to emit event for call_id=%d: %s", item["call_id"], e)

                pending_batch.clear()

    except KeyboardInterrupt:
        log.info("[enricher] Прервано пользователем (обработано: %d)", stats["processed"])
        if pending_batch:
            _flush_batch(repo, pending_batch)
        return stats

    # Дозаписать остаток
    if pending_batch:
        stats["failed"] += _flush_batch(repo, pending_batch)
        if cfg.features.enable_graph_update:
            _update_graph(repo, [it["call_id"] for it in pending_batch])

        # Emit real-time events to dashboard
        for item in pending_batch:
            call = repo.get_call_by_id(item["call_id"])
            if not call:
                continue
            try:
                emit_event_sync("analysis_complete", {
                    "call_id": item["call_id"],
                    "contact_label": call.get("display_name") or call.get("source_filename", "Unknown"),
                    "risk_score": item["analysis"].risk_score,
                    "call_type": item["analysis"].call_type,
                    "summary": item["analysis"].summary,
                })
            except Exception as e:
                log.warning("[enricher] Failed to emit event for call_id=%d: %s", item["call_id"], e)

    elapsed_total = time.time() - global_start
    avg_tps = tokens_total / sum(llm_times) if llm_times else 0
    total_done = stats["processed"] + stats["partial"] + stats["skipped"] + stats["failed"]

    log.info(
        "\n[enricher] ✅ Завершено!\n"
        "  Успешных: %d | Частичных: %d | Пропущено: %d | Ошибок: %d | Всего: %d\n"
        "  Время: %.1fс (%.1f файлов/сек) | Средняя скорость LLM: ~%.0f tok/с",
        stats["processed"], stats["partial"], stats["skipped"], stats["failed"], stats["total"],
        elapsed_total, total_done / elapsed_total if elapsed_total > 0 else 0, avg_tps,
    )

    # Вернуть совместимые со старым кодом stats
    return {
        "processed": stats["processed"] + stats["partial"],  # total successful + partial
        "failed": stats["failed"],
        "skipped": stats["skipped"],
        "total": stats["total"],
    }
