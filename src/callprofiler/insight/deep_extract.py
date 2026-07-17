# -*- coding: utf-8 -*-
"""
deep_extract.py — M8: map-reduce по ПОЛНОМУ транскрипту длинных звонков.

Снимает слепоту head+tail-клипа основного analyze-промпта (llm.md: >3000 символов
клипается до 1500+1500): длинный звонок режется на перекрывающиеся чанки, каждый
чанк прогоняется отдельным LLM-вызовом, извлечённые обязательства/факты дедупятся.

Границы (ozalup2.md §3.8, НЕ нарушать): результат — СВОЯ таблица `deep_facts`,
НЕ events/graph (граф derived только из analyses.raw_response, replay-инвариант,
graph.md layer contract). Это дисплей-слой + материал для digest (A1).

Инъекция-гард (инвариант 12): фрагмент — чужой текст (транскрипт), не команды;
промпт (deep_extract_v001.txt) явно требует его игнорировать.
"""

from __future__ import annotations

import json
import re
import sqlite3
from hashlib import sha1
from pathlib import Path

from callprofiler.analyze.llm_client import LLMClient

PROMPT_VERSION_DEEP = "deep-v1"
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "configs" / "prompts" / "deep_extract_v001.txt"

_ITEM_TYPES = {"promise", "debt", "fact", "date"}
_WHO_VALUES = {"OWNER", "OTHER"}
_WHAT_MAX_CHARS = 200


def chunk_text(text: str, size: int = 9000, overlap: int = 800) -> list[str]:
    """Символьные чанки с overlap; разрез назад до ближайшего пробела/переноса
    (не рвать слово). Короче size -> один чанк без разбиения."""
    text = text or ""
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    n = len(text)
    chunks: list[str] = []
    start = 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            cut = text.rfind(" ", start, end)
            if cut == -1:
                cut = text.rfind("\n", start, end)
            if cut > start:
                end = cut
        chunks.append(text[start:end])
        if end >= n:
            break
        start += step
    return chunks


def _parse_llm_json(raw: str) -> dict | None:
    """llm.md repair-парсер: strip fences → extract {...} → fix truncated. + <think>."""
    s = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)
    s = re.sub(r"```[a-zA-Z]*", "", s).replace("```", "")
    i, j = s.find("{"), s.rfind("}")
    if i < 0:
        return None
    frag = s[i:j + 1] if j > i else s[i:]
    for cand in (frag, frag + "}", frag + "]}", frag + '"}]}'):
        try:
            d = json.loads(cand)
            if isinstance(d, dict):
                return d
        except json.JSONDecodeError:
            continue
    return None


def _parse_items(raw: str | None) -> list[dict]:
    parsed = _parse_llm_json(raw or "")
    if not parsed:
        return []
    items = parsed.get("items")
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


def _item_key(call_id: int, item_type: str, what: str) -> str:
    raw = f"{call_id}|{item_type}|{(what or '').strip().lower()[:60]}"
    return sha1(raw.encode("utf-8")).hexdigest()[:16]


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _load_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _select_calls(
    conn: sqlite3.Connection, user_id: str, min_duration: int, min_priority: int | None, limit: int,
) -> list[dict]:
    """status IN (done,transcribed), достаточно длинные, НЕ голосовые заметки (F4:
    call_type='note' — самозаметка владельца, не разговор с контактом).

    min_priority задан -> INNER JOIN analyses: звонки без анализа (bare transcribed)
    не проходят фильтр (нечего сравнивать с порогом)."""
    if min_priority is not None:
        sql = (
            "SELECT c.call_id, c.contact_id, c.call_datetime FROM calls c "
            "JOIN analyses a ON a.call_id = c.call_id "
            "WHERE c.user_id = ? AND c.status IN ('done','transcribed') "
            "AND c.duration_sec >= ? AND c.call_type IS NULL AND a.priority >= ? "
            "ORDER BY c.call_datetime DESC LIMIT ?"
        )
        params = (user_id, min_duration, min_priority, limit)
    else:
        sql = (
            "SELECT c.call_id, c.contact_id, c.call_datetime FROM calls c "
            "WHERE c.user_id = ? AND c.status IN ('done','transcribed') "
            "AND c.duration_sec >= ? AND c.call_type IS NULL "
            "ORDER BY c.call_datetime DESC LIMIT ?"
        )
        params = (user_id, min_duration, limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _call_transcript_text(conn: sqlite3.Connection, call_id: int, user_id: str) -> str:
    """[me]/[s2]/[?] префиксы — тот же канон, что analyze/service.py и p1_scene.py."""
    rows = conn.execute(
        """SELECT t.speaker, t.text FROM transcripts t
             JOIN calls c ON c.call_id = t.call_id
            WHERE t.call_id = ? AND c.user_id = ?
            ORDER BY t.start_ms""",
        (call_id, user_id),
    ).fetchall()
    lines = []
    for r in rows:
        text = (r["text"] or "").strip()
        if not text:
            continue
        role = "[me]" if r["speaker"] == "OWNER" else ("[s2]" if r["speaker"] == "OTHER" else "[?]")
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _already_scanned(conn: sqlite3.Connection, user_id: str, call_id: int, prompt_version: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM deep_scans WHERE user_id = ? AND call_id = ? AND prompt_version = ?",
        (user_id, call_id, prompt_version),
    ).fetchone() is not None


def _mark_scanned(conn: sqlite3.Connection, user_id: str, call_id: int, prompt_version: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO deep_scans(user_id, call_id, prompt_version) VALUES (?,?,?)",
        (user_id, call_id, prompt_version),
    )


def _save_item(
    conn: sqlite3.Connection, user_id: str, call_id: int, contact_id: int | None,
    chunk_idx: int, chunk: str, item: dict, prompt_version: str,
) -> bool:
    """Гейты (инварианты 5/6): who не в {OWNER,OTHER} -> дроп; what пустой -> дроп;
    quote не substring чанка -> дроп ЦЕЛИКОМ (факту без цитаты веры нет). item_key PK
    дедупит перекрытия чанков (INSERT OR IGNORE)."""
    item_type = item.get("type")
    who = item.get("who")
    what = str(item.get("what") or "").strip()
    quote = str(item.get("quote") or "").strip()
    if item_type not in _ITEM_TYPES or who not in _WHO_VALUES or not what:
        return False
    if not quote or quote not in chunk:
        return False
    deadline_raw = item.get("deadline")
    if not isinstance(deadline_raw, str) or not deadline_raw.strip():
        deadline_raw = None
    key = _item_key(call_id, item_type, what)
    cur = conn.execute(
        """INSERT OR IGNORE INTO deep_facts
           (user_id, item_key, call_id, contact_id, type, who, what, quote,
            deadline_raw, chunk_idx, prompt_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, key, call_id, contact_id, item_type, who, what[:_WHAT_MAX_CHARS],
         quote, deadline_raw, chunk_idx, prompt_version),
    )
    return cur.rowcount > 0


def run_deep_extract(
    conn: sqlite3.Connection, user_id: str, *, llm_url: str, min_duration: int = 600,
    min_priority: int | None = None, limit: int = 100, force: bool = False, timeout: int = 120,
) -> dict:
    """Map-reduce деep-extract по звонкам user_id. LLMClient поднимает ConnectionError
    при недоступном llama-server (инвариант 4) — только на ПЕРВОМ реальном чанке
    (пустая выборка не трогает сеть вообще)."""
    from callprofiler.insight.repository import apply_insight_schema

    apply_insight_schema(conn)

    calls = _select_calls(conn, user_id, min_duration, min_priority, limit)
    if not force:
        calls = [c for c in calls if not _already_scanned(conn, user_id, c["call_id"], PROMPT_VERSION_DEEP)]

    stats = {"calls_seen": len(calls), "calls_scanned": 0, "chunks": 0,
              "items_saved": 0, "items_dropped": 0}
    if not calls:
        return stats

    template = _load_prompt_template()
    client: LLMClient | None = None

    for call in calls:
        text = _call_transcript_text(conn, call["call_id"], user_id)
        if not text:
            _mark_scanned(conn, user_id, call["call_id"], PROMPT_VERSION_DEEP)
            continue
        for idx, chunk in enumerate(chunk_text(text)):
            if client is None:
                client = LLMClient(
                    llm_url, timeout=timeout, cache_conn=conn,
                    cache_user_id=user_id, prompt_version=PROMPT_VERSION_DEEP,
                )
            prompt = template.replace("{chunk}", chunk)
            result = client.complete(
                [{"role": "user", "content": prompt}],
                temperature=0.1, max_tokens=900, json_mode=True,
            )
            stats["chunks"] += 1
            for item in _parse_items(result.text):
                saved = _save_item(conn, user_id, call["call_id"], call["contact_id"],
                                    idx, chunk, item, PROMPT_VERSION_DEEP)
                stats["items_saved" if saved else "items_dropped"] += 1
        _mark_scanned(conn, user_id, call["call_id"], PROMPT_VERSION_DEEP)
        stats["calls_scanned"] += 1

    conn.commit()
    return stats


def recent_deep_lines(conn: sqlite3.Connection, user_id: str, days: int = 7, top: int = 5) -> list[str]:
    """Строки для digest (A1 extra_sections) — только promise/debt, ≤300 симв/строка."""
    if not _has_table(conn, "deep_facts"):
        return []
    rows = conn.execute(
        """SELECT df.who, df.what, date(c.call_datetime) AS call_date,
                  COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164, '?') AS contact_name
             FROM deep_facts df
             JOIN calls c ON c.call_id = df.call_id
             LEFT JOIN contacts ct ON ct.contact_id = df.contact_id
            WHERE df.user_id = ? AND df.type IN ('promise','debt')
              AND df.created_at >= datetime('now', ?)
            ORDER BY df.created_at DESC LIMIT ?""",
        (user_id, f"-{int(days)} days", top),
    ).fetchall()
    lines = []
    for r in rows:
        line = f"- **{r['contact_name']}** ({r['who']}): {r['what']} — {r['call_date'] or '?'}"
        lines.append(line if len(line) <= 300 else line[:299] + "…")
    return lines
