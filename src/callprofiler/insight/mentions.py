# -*- coding: utf-8 -*-
"""mentions.py — граф упоминаний contact->contact через entity_contact_map (C1).

DERIVED, как entity_contact_map (person_link.py): полный rebuild per user,
источник — events.entity_id (graph-схема) JOIN entity_contact_map (entity к
dst-контакту, PERSON-only, confidence>=0.6) JOIN calls (src-контакт разговора,
где сущность упомянута). Владелец-entity рёбра не строит (is_owner-фильтр,
PRAGMA-guarded — колонка приходит из graph-схемы, как в person_link.py).
"""
from __future__ import annotations

import sqlite3

from . import repository as repo

MIN_CONFIDENCE = 0.6
MAX_QUOTE_CHARS = 200


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def build_mention_edges(conn: sqlite3.Connection, user_id: str) -> dict:
    """Полный rebuild mention_edges юзера. Возвращает {"edges": n}.

    Graph-слой отсутствует (нет `entities`/`events.entity_id`) -> пусто, не ошибка
    (тот же паттерн, что build_entity_contact_map).
    """
    repo.apply_insight_schema(conn)

    if not _table_exists(conn, "entities") or "entity_id" not in _columns(conn, "events"):
        conn.execute("DELETE FROM mention_edges WHERE user_id = ?", (user_id,))
        conn.commit()
        return {"edges": 0}

    owner_filter = ""
    if "is_owner" in _columns(conn, "entities"):
        owner_filter = " AND COALESCE(e.is_owner, 0) = 0"

    rows = conn.execute(
        f"""SELECT c.contact_id AS src, ecm.contact_id AS dst,
                   c.call_datetime AS call_datetime, ev.source_quote AS quote
              FROM events ev
              JOIN calls c ON c.call_id = ev.call_id AND c.user_id = ev.user_id
              JOIN entity_contact_map ecm ON ecm.entity_id = ev.entity_id AND ecm.user_id = ev.user_id
              JOIN entities e ON e.id = ev.entity_id AND e.user_id = ev.user_id
             WHERE ev.user_id = ? AND ev.entity_id IS NOT NULL
               AND ecm.confidence >= ? AND UPPER(e.entity_type) = 'PERSON'
               {owner_filter}
               AND c.contact_id IS NOT NULL AND c.contact_id != ecm.contact_id""",
        (user_id, MIN_CONFIDENCE),
    ).fetchall()

    edges: dict[tuple[int, int], dict] = {}
    for r in rows:
        key = (r["src"], r["dst"])
        e = edges.setdefault(key, {"mention_count": 0, "last_date": None, "sample_quote": None})
        e["mention_count"] += 1
        cd = r["call_datetime"]
        if cd and (e["last_date"] is None or cd > e["last_date"]):
            e["last_date"] = cd
        if e["sample_quote"] is None and r["quote"]:
            e["sample_quote"] = r["quote"][:MAX_QUOTE_CHARS]

    conn.execute("DELETE FROM mention_edges WHERE user_id = ?", (user_id,))
    for (src, dst), data in edges.items():
        conn.execute(
            """INSERT INTO mention_edges(user_id, src_contact_id, dst_contact_id,
                       mention_count, last_date, sample_quote) VALUES (?,?,?,?,?,?)""",
            (user_id, src, dst, data["mention_count"], data["last_date"], data["sample_quote"]),
        )
    conn.commit()
    return {"edges": len(edges)}


def mentioned_by(conn: sqlite3.Connection, user_id: str, contact_id: int, top: int = 3) -> list[dict]:
    """Top-N контактов, которые упоминали этого контакта («о нём говорят»)."""
    rows = conn.execute(
        """SELECT me.src_contact_id AS contact_id, me.mention_count, me.last_date,
                  me.sample_quote,
                  COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164, '?') AS name
             FROM mention_edges me
             JOIN contacts ct ON ct.contact_id = me.src_contact_id AND ct.user_id = me.user_id
            WHERE me.user_id = ? AND me.dst_contact_id = ?
            ORDER BY me.mention_count DESC LIMIT ?""",
        (user_id, contact_id, top),
    ).fetchall()
    return [
        {"contact_id": r["contact_id"], "name": r["name"], "mention_count": r["mention_count"],
         "last_date": r["last_date"], "sample_quote": r["sample_quote"]}
        for r in rows
    ]


def outgoing_count(conn: sqlite3.Connection, user_id: str, contact_id: int) -> int:
    """Скольких РАЗНЫХ ваших контактов сам упоминает этот контакт."""
    row = conn.execute(
        """SELECT COUNT(DISTINCT dst_contact_id) AS n FROM mention_edges
            WHERE user_id = ? AND src_contact_id = ?""",
        (user_id, contact_id),
    ).fetchone()
    return int(row["n"] or 0) if row else 0
