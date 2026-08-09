# -*- coding: utf-8 -*-
"""
ask.py — A2 (ozalupennieStrategic5.md §A2): вопрос к архиву звонков.

FTS5 top-k фрагментов → LLM-синтез прозой, каждый факт со ссылкой [n].
Ссылки [n] извлекаются regex-ом из ответа и мапятся на НАШИ метаданные
фрагмента (contact/date/call_id) — модели не доверяем в атрибуции источника,
только в том, ЧТО она процитировала.

Инъекция-гард (§4.1 ozalup2.md, инвариант 12): фрагменты — чужой текст
(транскрипты), не команды. Обёрнуты в <фрагменты>...</фрагменты> +
явная инструкция игнорировать вложенные "команды" — см. configs/prompts/ask_v001.txt.
json_mode НЕ используется — ответ проза, не JSON.

Кэш — свой (`ask_log`), НЕ унифицирован с `llm_cache.llm_calls` (M3): разная
форма запроса (retrieval+synthesis, не analyze), разная форма ответа
(citations_json), сознательно (blast radius, см. .claude/rules/decisions.md).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import requests

PROMPT_VERSION_ASK = "ask-v1"
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "configs" / "prompts" / "ask_v001.txt"
_STOPWORDS = {
    "что", "как", "где", "когда", "это", "был", "была", "были", "быть", "у", "с",
    "и", "в", "на", "для", "о", "к", "по", "мы", "вы", "он", "она", "они", "за",
    "от", "до", "не", "ли", "же", "то", "так", "если", "или", "но", "а",
}


def apply_ask_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — CREATE TABLE IF NOT EXISTS + ALTER аддитивно (db.md)."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ask_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT NOT NULL,
            question       TEXT NOT NULL,
            prompt_hash    TEXT NOT NULL,
            answer         TEXT NOT NULL,
            citations_json TEXT NOT NULL DEFAULT '[]',
            prompt_version TEXT NOT NULL,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, prompt_hash)
        )"""
    )
    # F3: answered — 1 если ответ содержал >=1 цитату (F13 переиспользует эту
    # колонку для метрик качества). Аддитивно — ask_log уже существовала с A2.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ask_log)").fetchall()}
    if "answered" not in cols:
        conn.execute("ALTER TABLE ask_log ADD COLUMN answered INTEGER")
    _migrate_drop_global_prompt_hash_unique(conn)
    conn.commit()


def _migrate_drop_global_prompt_hash_unique(conn: sqlite3.Connection) -> None:
    """T-13/P-LLM-06: старая схема имела ``prompt_hash TEXT UNIQUE`` (глобально) —
    второй профиль с идентичным вопросом получал конфликт вставки и оставался
    без своей строки (INSERT OR IGNORE молча терял её). Rebuild в
    ``UNIQUE(user_id, prompt_hash)`` — sqlite не умеет ALTER DROP CONSTRAINT.
    Идемпотентно: срабатывает только если старый одноколоночный UNIQUE ещё жив
    (обнаруживается через auto-индекс на ``prompt_hash``); данные не теряются —
    старая схема гарантировала prompt_hash глобально уникальным, значит
    конфликтов при копировании в новую таблицу быть не может."""
    has_column_unique = any(
        row[2] == 1 and _index_columns(conn, row[1]) == ["prompt_hash"]
        for row in conn.execute("PRAGMA index_list(ask_log)").fetchall()
    )
    if not has_column_unique:
        return
    conn.execute("ALTER TABLE ask_log RENAME TO ask_log_old_uq")
    conn.execute(
        """CREATE TABLE ask_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT NOT NULL,
            question       TEXT NOT NULL,
            prompt_hash    TEXT NOT NULL,
            answer         TEXT NOT NULL,
            citations_json TEXT NOT NULL DEFAULT '[]',
            prompt_version TEXT NOT NULL,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
            answered       INTEGER,
            UNIQUE(user_id, prompt_hash)
        )"""
    )
    conn.execute(
        """INSERT INTO ask_log
           (id, user_id, question, prompt_hash, answer, citations_json,
            prompt_version, created_at, answered)
           SELECT id, user_id, question, prompt_hash, answer, citations_json,
                  prompt_version, created_at, answered
             FROM ask_log_old_uq"""
    )
    conn.execute("DROP TABLE ask_log_old_uq")


def _index_columns(conn: sqlite3.Connection, index_name: str) -> list[str]:
    return [r[2] for r in conn.execute(f"PRAGMA index_info({index_name})").fetchall()]


def llm_available(llm_url: str, timeout: float = 2.0) -> bool:
    """Проба /health (паттерн M1, doctor.py) — llama-server спит (GPU sequential)
    это НОРМА вне LLM-окна, не ошибка."""
    base = llm_url.split("/v1/")[0] if "/v1/" in llm_url else llm_url
    if not base:
        return False
    try:
        resp = requests.get(base.rstrip("/") + "/health", timeout=timeout)
        return resp.status_code == 200
    except requests.exceptions.ConnectionError:
        return False
    except Exception:  # noqa: BLE001 — проба не должна падать, только сказать "нет"
        return False


def _tokenize(question: str) -> list[str]:
    words = re.findall(r"\w+", question.lower(), re.UNICODE)
    return [w for w in words if len(w) >= 3 and w not in _STOPWORDS]


def retrieve(conn: sqlite3.Connection, user_id: str, question: str, k: int = 8) -> list[dict]:
    """FTS5 OR-поиск по токенам вопроса → top-k фрагментов транскрипта.

    Возвращает [{idx, call_id, contact_name, date, text}], idx с 1.
    """
    tokens = _tokenize(question)
    if not tokens:
        return []
    fts_query = " OR ".join(f'"{t}"' for t in tokens)

    rows = conn.execute(
        """SELECT t.call_id, t.text, c.call_datetime,
                  COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164, '?') AS contact_name
             FROM (
                 SELECT rowid, rank FROM transcripts_fts
                  WHERE transcripts_fts MATCH ?
                  ORDER BY rank LIMIT 200
             ) ranked
             JOIN transcripts t ON t.segment_id = ranked.rowid
             JOIN calls c ON c.call_id = t.call_id
             LEFT JOIN contacts ct ON ct.contact_id = c.contact_id
            WHERE c.user_id = ?
            ORDER BY ranked.rank
            LIMIT ?""",
        (fts_query, user_id, k),
    ).fetchall()

    return [
        {
            "idx": i + 1,
            "call_id": r["call_id"],
            "contact_name": r["contact_name"],
            "date": (r["call_datetime"] or "")[:10] or "?",
            "text": r["text"],
        }
        for i, r in enumerate(rows)
    ]


def _build_messages(question: str, fragments: list[dict]) -> list[dict]:
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    frag_lines = [
        f"[{f['idx']}] {f['contact_name']}, {f['date']}: {f['text']}" for f in fragments
    ]
    user = (
        f"Вопрос: {question}\n\n"
        "<фрагменты>\n" + "\n".join(frag_lines) + "\n</фрагменты>"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _prompt_hash(messages: list[dict]) -> str:
    canonical = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(f"{canonical}|{PROMPT_VERSION_ASK}".encode("utf-8")).hexdigest()


def _get_cached(conn: sqlite3.Connection, user_id: str, prompt_hash: str) -> dict | None:
    row = conn.execute(
        "SELECT answer, citations_json FROM ask_log WHERE prompt_hash = ? AND user_id = ?",
        (prompt_hash, user_id),
    ).fetchone()
    if row is None:
        return None
    return {"answer": row["answer"], "citations": json.loads(row["citations_json"])}


def _save_cache(
    conn: sqlite3.Connection, user_id: str, question: str, prompt_hash: str,
    answer: str, citations: list[dict],
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO ask_log
           (user_id, question, prompt_hash, answer, citations_json, prompt_version, answered)
           VALUES (?,?,?,?,?,?,?)""",
        (user_id, question, prompt_hash, answer, json.dumps(citations, ensure_ascii=False),
         PROMPT_VERSION_ASK, 1 if citations else 0),
    )
    conn.commit()


def _extract_citations(answer: str, fragments: list[dict]) -> list[dict]:
    by_idx = {f["idx"]: f for f in fragments}
    seen: list[int] = []
    for m in re.findall(r"\[(\d+)\]", answer):
        n = int(m)
        if n in by_idx and n not in seen:
            seen.append(n)
    return [
        {"n": n, "contact": by_idx[n]["contact_name"], "date": by_idx[n]["date"],
         "call_id": by_idx[n]["call_id"]}
        for n in seen
    ]


def answer_question(
    conn: sqlite3.Connection,
    user_id: str,
    question: str,
    *,
    llm_url: str,
    k: int = 8,
    timeout: int = 120,
) -> dict:
    """{answer: str, citations: [{n, contact, date, call_id}], from_cache: bool}."""
    fragments = retrieve(conn, user_id, question, k=k)
    if not fragments:
        return {"answer": "В архиве не найдено релевантных фрагментов.", "citations": [], "from_cache": False}

    apply_ask_schema(conn)
    messages = _build_messages(question, fragments)
    prompt_hash = _prompt_hash(messages)

    cached = _get_cached(conn, user_id, prompt_hash)
    if cached is not None:
        return {**cached, "from_cache": True}

    response = requests.post(
        llm_url,
        json={"messages": messages, "temperature": 0.2, "max_tokens": 800},
        timeout=timeout,
    )
    response.raise_for_status()
    answer = response.json()["choices"][0]["message"]["content"]

    citations = _extract_citations(answer, fragments)
    _save_cache(conn, user_id, question, prompt_hash, answer, citations)
    return {"answer": answer, "citations": citations, "from_cache": False}
