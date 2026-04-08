# -*- coding: utf-8 -*-
"""
enricher.py — массовый LLM-анализ звонков без анализа.

Функция bulk_enrich() обрабатывает все звонки которым не хватает Analysis,
отправляет их на анализ через LLM (llama.cpp), и сохраняет результаты.

CLI: python -m callprofiler bulk-enrich --user <user_id> [--limit 100]
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from callprofiler.analyze.llm_client import LLMClient
from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.config import load_config
from callprofiler.db.repository import Repository

log = logging.getLogger(__name__)

# Паттерн для извлечения JSON из markdown кода
_JSON_MD_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _format_transcript(segments: list[dict]) -> str:
    """Форматировать транскрипт для промпта."""
    lines = []
    for seg in segments:
        speaker = seg.get("speaker", "UNKNOWN")
        text = seg.get("text", "")
        role = "[Я]" if speaker == "OWNER" else "[Собеседник]"
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
    # Загрузить конфиг
    cfg = load_config(config_path)
    repo = Repository(db_path)
    repo.init_db()

    # Проверить пользователя
    user = repo.get_user(user_id)
    if not user:
        log.error("[enricher] Пользователь '%s' не найден", user_id)
        return {"processed": 0, "failed": 0, "skipped": 0, "total": 0}

    # Инициализировать LLM клиент
    try:
        llm = LLMClient(base_url=cfg.models.llm_url, timeout=300)
    except ConnectionError as e:
        log.error("[enricher] Ошибка подключения к LLM: %s", e)
        return {"processed": 0, "failed": 0, "skipped": 0, "total": 0}

    # Загрузить шаблон промпта
    prompts_dir = Path(cfg.data_dir).parent / "configs" / "prompts"
    if not prompts_dir.exists():
        prompts_dir = Path("configs") / "prompts"
    prompt_template = _load_prompt_template(str(prompts_dir))

    # Выбрать звонки без анализа
    conn = repo._get_conn()
    rows = conn.execute(
        """SELECT c.call_id, c.user_id, c.contact_id, c.call_datetime,
                  c.source_filename, cnt.phone_e164, cnt.display_name
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

    log.info("[enricher] Найдено %d звонков для анализа (пользователь: %s)", len(calls), user_id)

    stats = {
        "processed": 0,
        "failed": 0,
        "skipped": 0,
        "total": len(calls),
    }

    start_time = time.time()

    try:
        for idx, call in enumerate(calls, 1):
            call_id = call["call_id"]
            phone = call.get("phone_e164", "unknown")
            name = call.get("display_name", "?")

            log.info(
                "[enricher] Обработка %d/%d: call_id=%d (%s, %s)",
                idx, len(calls), call_id, phone, name,
            )

            try:
                # Получить транскрипт
                segments = repo.get_transcript(call_id)
                if not segments:
                    log.warning("[enricher] call_id=%d: транскрипт пустой", call_id)
                    stats["skipped"] += 1
                    continue

                # Форматировать промпт
                transcript_text = _format_transcript(segments)
                call_datetime = call.get("call_datetime", "unknown")
                direction = call.get("direction", "UNKNOWN")

                user_message = f"""Метаданные звонка:
Контакт: {name} ({phone})
Дата: {call_datetime}
Направление: {direction}

Стенограмма:
{transcript_text}"""

                # Отправить на анализ
                llm_response = llm.generate(
                    messages=[
                        {"role": "system", "content": prompt_template},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.3,
                    max_tokens=2048,
                )

                # Распарсить ответ
                analysis = parse_llm_response(llm_response)

                # Сохранить анализ
                repo.save_analysis(call_id, analysis)

                # Сохранить promises если были найдены
                if analysis.promises:
                    repo.save_promises(user_id, call["contact_id"] or 0, call_id, analysis.promises)

                # Обновить контакт если был найден guessed_name
                # (в данном случае игнорируем, т.к. это из LLM, а не из имён в транскрипте)

                stats["processed"] += 1
                elapsed = time.time() - start_time
                rate = stats["processed"] / elapsed if elapsed > 0 else 0
                eta = (len(calls) - idx) / rate if rate > 0 else 0

                log.debug(
                    "[enricher] ✓ call_id=%d (%.1f сек/файл, ETA: %.0f сек)",
                    call_id, 1 / rate if rate > 0 else 0, eta,
                )

            except Exception as e:
                log.error("[enricher] ✗ call_id=%d: ошибка при обработке: %s", call_id, e)
                stats["failed"] += 1

    except KeyboardInterrupt:
        log.info("[enricher] Прервано пользователем (обработано: %d)", stats["processed"])
        return stats

    # Итоговая статистика
    elapsed_total = time.time() - start_time
    log.info(
        "\n[enricher] ✅ Завершено!\n"
        "  Обработано файлов: %d\n"
        "  Ошибок: %d\n"
        "  Пропущено: %d\n"
        "  Всего: %d\n"
        "  Время: %.1f сек (%.1f сек/файл)",
        stats["processed"],
        stats["failed"],
        stats["skipped"],
        stats["total"],
        elapsed_total,
        elapsed_total / stats["processed"] if stats["processed"] > 0 else 0,
    )

    return stats
