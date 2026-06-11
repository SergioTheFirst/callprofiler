# -*- coding: utf-8 -*-
"""person_link.py — связка graph-entity ↔ contact (Ф1 плана досье).

Три id-пространства проекта (contact / graph entity / архетип) сшиваются
МЯГКИМИ ссылками в ``entity_contact_map``:

  1. name-match (confidence 0.95, любой entity_type): нормализованное имя
     entity (canonical или alias) совпало с display_name/guessed_name контакта;
  2. co-occurrence (только PERSON, confidence 0.6+0.3*share): доля звонков
     entity, пришедшихся на контакта, >= 0.6 при >= 3 звонках.

Карта — DERIVED-данные (как graph из events): полный rebuild per user,
идемпотентно; entity_id пересоздаются graph-replay'ем → replay перестраивает
карту. Никакого слияния contacts/entities (Prohibited: auto-merge).
"""
from __future__ import annotations

import json
import logging
import sqlite3

from . import repository as repo

logger = logging.getLogger(__name__)

NAME_CONFIDENCE = 0.95
COOCCUR_MIN_SHARE = 0.6
COOCCUR_MIN_EVENTS = 3


def _norm(value) -> str:
    """lower + ё→е + collapse spaces. Пустое/None → ''."""
    if not value:
        return ""
    return " ".join(str(value).lower().replace("ё", "е").split())


def _entity_names(row) -> set[str]:
    names = {_norm(row["canonical_name"])}
    try:
        for alias in json.loads(row["aliases"] or "[]"):
            names.add(_norm(alias))
    except (json.JSONDecodeError, TypeError):
        pass
    names.discard("")
    return names


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def build_entity_contact_map(
    conn: sqlite3.Connection, user_id: str, dry_run: bool = False
) -> dict:
    """Полный rebuild карты entity↔contact пользователя.

    Возвращает {"links": n, "name": n, "cooccur": n}. dry_run — посчитать
    без записи (preview для CLI person-link --dry-run).
    """
    repo.apply_insight_schema(conn)

    # Graph-слой может отсутствовать (entities создаёт apply_graph_schema,
    # не schema.sql) — тогда карта пуста, не ошибка.
    if not _table_exists(conn, "entities"):
        if not dry_run:
            conn.execute("DELETE FROM entity_contact_map WHERE user_id = ?", (user_id,))
            conn.commit()
        return {"links": 0, "name": 0, "cooccur": 0}

    contacts = conn.execute(
        "SELECT contact_id, display_name, guessed_name FROM contacts "
        "WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    # Базовая entities из schema.sql не имеет is_owner (его добавляет
    # apply_graph_schema-миграция) — фильтры собираем по фактическим колонкам.
    ecols = _columns(conn, "entities")
    where = ["user_id = ?"]
    if "archived" in ecols:
        where.append("archived = 0")
    if "is_owner" in ecols:
        where.append("COALESCE(is_owner, 0) = 0")
    entities = conn.execute(
        "SELECT id, entity_type, canonical_name, aliases FROM entities "
        "WHERE " + " AND ".join(where),
        (user_id,),
    ).fetchall()

    # нормализованное имя контакта → contact_ids
    by_name: dict[str, list[int]] = {}
    for c in contacts:
        for raw in (c["display_name"], c["guessed_name"]):
            key = _norm(raw)
            if key:
                by_name.setdefault(key, []).append(c["contact_id"])

    links: dict[tuple[int, int], tuple[str, float]] = {}

    # 1) name-match — приоритетный сигнал, любой entity_type
    for e in entities:
        for name in _entity_names(e):
            for cid in by_name.get(name, []):
                links.setdefault((e["id"], cid), ("name", NAME_CONFIDENCE))

    # 2) co-occurrence — только PERSON, по концентрации упоминаний.
    # events.entity_id добавляет graph-миграция — без неё cooccur пропускаем.
    if "entity_id" in _columns(conn, "events"):
        pair_rows = conn.execute(
            """SELECT ev.entity_id AS entity_id, c.contact_id AS contact_id,
                      COUNT(DISTINCT ev.call_id) AS n_ec
                 FROM events ev
                 JOIN calls c ON c.call_id = ev.call_id AND c.user_id = ev.user_id
                WHERE ev.user_id = ? AND ev.entity_id IS NOT NULL
                  AND c.contact_id IS NOT NULL
                GROUP BY ev.entity_id, c.contact_id""",
            (user_id,),
        ).fetchall()
        totals = {
            r["entity_id"]: r["n"]
            for r in conn.execute(
                "SELECT entity_id, COUNT(DISTINCT call_id) AS n FROM events "
                "WHERE user_id = ? AND entity_id IS NOT NULL GROUP BY entity_id",
                (user_id,),
            ).fetchall()
        }
    else:
        pair_rows, totals = [], {}
    person_ids = {
        e["id"] for e in entities if (e["entity_type"] or "").upper() == "PERSON"
    }
    for r in pair_rows:
        eid, cid, n_ec = r["entity_id"], r["contact_id"], r["n_ec"]
        if eid not in person_ids or (eid, cid) in links:
            continue
        total = totals.get(eid, 0)
        if n_ec < COOCCUR_MIN_EVENTS or not total:
            continue
        share = n_ec / total
        if share >= COOCCUR_MIN_SHARE:
            links[(eid, cid)] = ("cooccur", round(0.6 + 0.3 * share, 3))

    n_name = sum(1 for method, _ in links.values() if method == "name")
    stats = {"links": len(links), "name": n_name, "cooccur": len(links) - n_name}
    if dry_run:
        return stats

    conn.execute("DELETE FROM entity_contact_map WHERE user_id = ?", (user_id,))
    for (eid, cid), (method, conf) in links.items():
        conn.execute(
            "INSERT INTO entity_contact_map(user_id, entity_id, contact_id, "
            "method, confidence) VALUES (?,?,?,?,?)",
            (user_id, eid, cid, method, conf),
        )
    conn.commit()
    logger.info(
        "entity_contact_map user=%s: links=%d (name=%d, cooccur=%d)",
        user_id, stats["links"], stats["name"], stats["cooccur"],
    )
    return stats
