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
from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.config import load_config
from callprofiler.db.repository import Repository
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
    - promises → 'promise' events
    - action_items → 'task' events
    - risks/contradictions → 'risk'/'contradiction' events
    - debts/amounts → 'debt' events
    - smalltalk facts → 'smalltalk' events
    """
    events = []

    # Promises → event type 'promise'
    if hasattr(analysis, "promises") and analysis.promises:
        for p in analysis.promises:
            if isinstance(p, dict):
                events.append({
                    "user_id": user_id,
                    "contact_id": contact_id,
                    "call_id": call_id,
                    "event_type": "promise",
                    "who": p.get("who", "UNKNOWN"),
                    "payload": p.get("what", ""),
                    "deadline": p.get("due"),
                    "confidence": 0.9,
                    "status": "open",
                })

    # Action items → event type 'task'
    if hasattr(analysis, "action_items") and analysis.action_items:
        for item in analysis.action_items:
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

    # Risk/contradiction flags and evidence (from raw_response if available)
    flags = getattr(analysis, "flags", {}) or {}
    if isinstance(flags, dict):
        if flags.get("conflict"):
            events.append({
                "user_id": user_id,
                "contact_id": contact_id,
                "call_id": call_id,
                "event_type": "contradiction",
                "who": "UNKNOWN",
                "payload": "Конфликт/противоречие обнаружено",
                "confidence": 0.8,
                "status": "open",
            })

        if flags.get("legal_risk") or flags.get("urgent"):
            events.append({
                "user_id": user_id,
                "contact_id": contact_id,
                "call_id": call_id,
                "event_type": "risk",
                "who": "UNKNOWN",
                "payload": "Юридический или срочный риск",
                "confidence": 0.85,
                "status": "open",
            })

    # Key topics → 'fact' events for high-confidence smalltalk
    if hasattr(analysis, "key_topics") and analysis.key_topics:
        for topic in analysis.key_topics:
            if isinstance(topic, str) and len(topic) > 0:
                # Check if this looks like a personal fact (lowercase heuristic)
                if topic[0].islower() or " " in topic:
                    events.append({
                        "user_id": user_id,
                        "contact_id": contact_id,
                        "call_id": call_id,
                        "event_type": "smalltalk",
                        "who": "UNKNOWN",
                        "payload": topic,
                        "confidence": 0.7,
                        "status": "open",
                    })

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
                log.error("[enricher] ✗ call_id=%d: ошибка записи: %s", item["call_id"], ie)
                failed += 1
        return failed


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

                # Короткий звонок — не отправлять в LLM
                if len(transcript_text) < _SHORT_CALL_THRESHOLD:
                    log.info(
                        "[enricher] %d/%d call_id=%d | короткий (%d симв) — stub | %.1fс",
                        idx, total, call_id, len(transcript_text), time.time() - call_start,
                    )
                    analysis = _stub_analysis()
                    is_partial = True
                else:
                    user_message = (
                        f"Метаданные звонка:\n"
                        f"Контакт: {name} ({phone})\n"
                        f"Дата: {call.get('call_datetime', 'unknown')}\n"
                        f"Направление: {call.get('direction', 'UNKNOWN')}\n\n"
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
                        log.error("[enricher] ✗ call_id=%d: LLM вернул None (ошибка/timeout)", call_id)
                        stats["failed"] += 1
                        continue

                    llm_times.append(llm_elapsed)
                    est_tokens = max(1, len(llm_response) // 4)
                    tokens_total += est_tokens
                    tps = est_tokens / llm_elapsed if llm_elapsed > 0 else 0

                    analysis = parse_llm_response(llm_response)
                    is_partial = not analysis.summary  # Если summary пусто — парсинг частичный

                    # ETA по всем завершённым (включая skipped/failed)
                    completed = stats["processed"] + stats["partial"] + stats["skipped"] + stats["failed"]
                    elapsed_total = time.time() - global_start
                    rate = completed / elapsed_total if elapsed_total > 0 and completed > 0 else 0
                    eta = (total - idx) / rate if rate > 0 else 0

                    status = "[partial]" if is_partial else "✓"
                    log.info(
                        "[enricher] %d/%d call_id=%d | %s | %.1fс/файл | ~%.0f tok/с | ETA %.0fс",
                        idx, total, call_id, status,
                        time.time() - call_start, tps, eta,
                    )

                # Счётчик partial успехов
                if is_partial:
                    stats["partial"] += 1
                else:
                    stats["processed"] += 1

                # Extract events from analysis
                events = _extract_events_from_analysis(
                    analysis, user_id, call.get("contact_id"), call_id
                )

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
                log.error("[enricher] ✗ call_id=%d: ошибка обработки: %s", call_id, e)
                stats["failed"] += 1
                # Продолжаем, несмотря на ошибку одного звонка

            # Батчевая запись каждые BATCH_SIZE файлов
            if len(pending_batch) >= _BATCH_SIZE:
                stats["failed"] += _flush_batch(repo, pending_batch)
                pending_batch.clear()

    except KeyboardInterrupt:
        log.info("[enricher] Прервано пользователем (обработано: %d)", stats["processed"])
        if pending_batch:
            _flush_batch(repo, pending_batch)
        return stats

    # Дозаписать остаток
    if pending_batch:
        stats["failed"] += _flush_batch(repo, pending_batch)

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
