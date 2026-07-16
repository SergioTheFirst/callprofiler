# -*- coding: utf-8 -*-
"""
llm_cache.py — мемоизация LLM-вызовов по fingerprint (M3, decisions.md 2026-06-04 #1).

Retry уже есть в `analyze/llm_client.py` (backoff 2/4/8s) — этот модуль НЕ дублирует
его, только кэширует успешные (и явно неуспешные, но НЕ отказные) ответы по
sha1(messages+temperature+max_tokens+prompt_version). Перезапуски/reprocess/replay
не платят повторную LLM-стоимость; крэш посреди батча дорезюмируется бесплатно.

Biography (`bio_llm_calls`) и per-row кэши insight (age/ask/promise) СВОИ — не
унифицированы сюда (blast radius; см. decisions.md).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from callprofiler.analyze.llm_client import LLMResult


def apply_llm_cache_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — CREATE TABLE IF NOT EXISTS, безопасно звать на каждый старт клиента."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS llm_calls (
            cache_key      TEXT PRIMARY KEY,
            user_id        TEXT NOT NULL DEFAULT '',
            prompt_version TEXT NOT NULL DEFAULT '',
            response       TEXT NOT NULL,
            finish_reason  TEXT,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()


def make_key(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    prompt_version: str,
    json_mode: bool = False,
) -> str:
    """Fingerprint запроса — детерминированный, порядок ключей сообщений не важен
    (``sort_keys=True``): один и тот же запрос всегда даёт один и тот же ключ.

    ``json_mode`` входит в ключ (M4): ``response_format`` меняет форму ответа модели —
    без этого json_mode=True/False на одних messages читали бы чужой кэш друг у друга.
    """
    canonical = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    payload = f"{canonical}|{temperature}|{max_tokens}|{prompt_version}|{json_mode}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def get(conn: sqlite3.Connection, key: str) -> LLMResult | None:
    row = conn.execute(
        "SELECT response, finish_reason FROM llm_calls WHERE cache_key = ?", (key,)
    ).fetchone()
    if row is None:
        return None
    # Индексный доступ — не полагаемся на row_factory=sqlite3.Row у переданного conn.
    return LLMResult(text=row[0], finish_reason=row[1])


def put(
    conn: sqlite3.Connection,
    key: str,
    user_id: str,
    prompt_version: str,
    result: LLMResult,
) -> None:
    """``result.text is None`` (сбой подключения/парсинга) -> НЕ кэшировать,
    иначе временный отказ llama-server залип бы в кэше навсегда."""
    if result.text is None:
        return
    conn.execute(
        """INSERT OR IGNORE INTO llm_calls (cache_key, user_id, prompt_version, response, finish_reason)
           VALUES (?, ?, ?, ?, ?)""",
        (key, user_id, prompt_version, result.text, result.finish_reason),
    )
    conn.commit()
