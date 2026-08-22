# -*- coding: utf-8 -*-
"""
analyze/payload_reader.py — один читатель JSON-анализа звонка (R-04).

``response_parser`` чинит ответ модели и кладёт починенный вариант в
``analyses.canonical_json``; ``raw_response`` остаётся как есть, для аудита.
Графовый билдер обещал в комментарии читать canonical, но его SELECT этой
колонки не запрашивал — то есть чинёный payload не использовался НИКОГДА, а
replay парсил `raw_response` своей копией кода. Теперь путь один.
"""

from __future__ import annotations

import json
import logging
import sqlite3

log = logging.getLogger(__name__)

CANONICAL = "canonical"
RAW = "raw"
INVALID = "invalid"


def _loads_object(text: object) -> dict | None:
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) and parsed else None


def parse_analysis_payload(canonical_json: object, raw_response: object) -> tuple[dict | None, str]:
    """Чистая часть: canonical → raw → invalid. Без БД (тестируется отдельно)."""
    payload = _loads_object(canonical_json)
    if payload is not None:
        return payload, CANONICAL
    payload = _loads_object(raw_response)
    if payload is not None:
        return payload, RAW
    return None, INVALID


def load_analysis_payload(
    conn: sqlite3.Connection, call_id: int
) -> tuple[dict | None, str]:
    """Вернуть ``(payload, reason)`` для звонка; ``reason ∈ canonical|raw|invalid``."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(analyses)")}
    canonical_expr = "canonical_json" if "canonical_json" in cols else "'' AS canonical_json"
    row = conn.execute(
        f"SELECT raw_response, {canonical_expr} FROM analyses WHERE call_id = ?",
        (call_id,),
    ).fetchone()
    if row is None:
        return None, INVALID
    payload, reason = parse_analysis_payload(row["canonical_json"], row["raw_response"])
    if payload is None:
        log.warning("[payload] call_id=%s: неразбираемый анализ (canonical и raw)", call_id)
    return payload, reason
