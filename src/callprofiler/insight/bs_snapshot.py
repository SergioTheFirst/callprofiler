# -*- coding: utf-8 -*-
"""
insight/bs_snapshot.py — сырой снимок оснований контакта (R-15).

Ровно один READ-ONLY слой между БД и чистой математикой BS-v2: собирает всё,
что вообще может быть основанием (§2 плана), сохраняя provenance и пропуски
как есть — интерпретация (что годно, что нет) живёт в ``bs_inputs.py``.

Инварианты:
* каждый запрос содержит предикат по ``user_id`` (в т.ч. в join'ах);
* строки с ``source_date > as_of`` не попадают в снимок ВООБЩЕ (RISK-17:
  ретроспективный расчёт не должен видеть будущее);
* порядок детерминирован — ``(source_date, table_rank, pk)``;
* C-кандидаты (§4.2) — только ``producer='graph_v2' AND fact_type='contradiction'
  AND who='OTHER'``; legacy-события ``contradiction`` (их пишет bulk-путь из
  ``bs_evidence`` без provenance) попадают в ``legacy_context`` и на C не влияют
  (RISK-26);
* ничего не пишет и не создаёт схему.
"""

from __future__ import annotations

import sqlite3
from typing import Any

SNAPSHOT_SCHEMA = "bs-snapshot-1"

# Ранги таблиц для детерминированного порядка внутри одной даты.
_TABLE_RANK = {
    "calls": 0,
    "analyses": 1,
    "transcripts": 2,
    "promises": 3,
    "events": 4,
    "promise_outcomes": 5,
    "deep_facts": 6,
    "contact_features": 7,
    "mention_edges": 8,
}


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return column in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _rows(conn: sqlite3.Connection, sql: str, params: tuple) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _domain_date(row: dict) -> str:
    return str(row.get("source_date") or "")


def snapshot_contact_evidence(
    conn: sqlite3.Connection, user_id: str, contact_id: int, as_of: str
) -> dict[str, Any]:
    """Собрать все строки-основания контакта, видимые на дату ``as_of`` (YYYY-MM-DD)."""
    as_of_day = str(as_of)[:10]
    key = (user_id, contact_id, as_of_day)

    calls = _rows(
        conn,
        """SELECT call_id, contact_id, call_datetime, created_at, status, call_type,
                  role_fragile, source_md5, duration_sec, asr_coverage,
                  substr(COALESCE(call_datetime, created_at), 1, 10) AS source_date
             FROM calls
            WHERE user_id = ? AND contact_id = ?
              AND substr(COALESCE(call_datetime, created_at), 1, 10) <= ?
            ORDER BY source_date, call_id""",
        key,
    )
    call_ids = [c["call_id"] for c in calls]

    analyses = _rows(
        conn,
        """SELECT a.call_id, a.parse_status, a.schema_version, a.risk_score, a.call_type,
                  a.prompt_version, a.raw_response, a.canonical_json,
                  substr(COALESCE(c.call_datetime, c.created_at), 1, 10) AS source_date
             FROM analyses a
             JOIN calls c ON c.call_id = a.call_id
            WHERE c.user_id = ? AND c.contact_id = ?
              AND substr(COALESCE(c.call_datetime, c.created_at), 1, 10) <= ?
            ORDER BY source_date, a.call_id""",
        key,
    )

    transcripts = _rows(
        conn,
        """SELECT t.call_id, t.segment_id, t.start_ms, t.end_ms, t.text, t.speaker,
                  substr(COALESCE(c.call_datetime, c.created_at), 1, 10) AS source_date
             FROM transcripts t
             JOIN calls c ON c.call_id = t.call_id
            WHERE c.user_id = ? AND c.contact_id = ?
              AND substr(COALESCE(c.call_datetime, c.created_at), 1, 10) <= ?
            ORDER BY source_date, t.call_id, t.start_ms, t.segment_id""",
        key,
    )

    promises = _rows(
        conn,
        """SELECT p.promise_id, p.call_id, p.who, p.what, p.due, p.status,
                  p.vague, p.source_quote, p.quote_match, p.status_updated_at, p.status_method,
                  substr(COALESCE(c.call_datetime, c.created_at), 1, 10) AS source_date
             FROM promises p
             JOIN calls c ON c.call_id = p.call_id AND c.user_id = p.user_id
            WHERE p.user_id = ? AND p.contact_id = ?
              AND substr(COALESCE(c.call_datetime, c.created_at), 1, 10) <= ?
            ORDER BY source_date, p.promise_id""",
        key,
    )

    events = _rows(
        conn,
        """SELECT e.id, e.call_id, e.event_type, e.fact_type, e.who, e.payload,
                  e.source_quote, e.quote, e.quote_match, e.quote_verified, e.producer,
                  e.confidence, e.status, e.deadline, e.entity_id, e.normalized_entity_key,
                  substr(COALESCE(c.call_datetime, c.created_at), 1, 10) AS source_date
             FROM events e
             JOIN calls c ON c.call_id = e.call_id AND c.user_id = e.user_id
            WHERE e.user_id = ? AND e.contact_id = ?
              AND substr(COALESCE(c.call_datetime, c.created_at), 1, 10) <= ?
            ORDER BY source_date, e.id""",
        key,
    )

    outcomes: list[dict[str, Any]] = []
    if _has_table(conn, "promise_outcomes"):
        outcomes = _rows(
            conn,
            """SELECT promise_key, contact_id, call_id, side, what, due, status,
                      evidence_call_id, evidence_date, evidence_quote, days_late, method,
                      confidence, prompt_version,
                      substr(evidence_date, 1, 10) AS source_date
                 FROM promise_outcomes
                WHERE user_id = ? AND contact_id = ?
                  AND (evidence_date IS NULL OR substr(evidence_date, 1, 10) <= ?)
                ORDER BY source_date, promise_key""",
            key,
        )

    deep_facts: list[dict[str, Any]] = []
    if _has_table(conn, "deep_facts"):
        deep_facts = _rows(
            conn,
            """SELECT d.item_key, d.call_id, d.type, d.who, d.what, d.quote, d.prompt_version,
                      substr(COALESCE(c.call_datetime, c.created_at), 1, 10) AS source_date
                 FROM deep_facts d
                 JOIN calls c ON c.call_id = d.call_id AND c.user_id = d.user_id
                WHERE d.user_id = ? AND d.contact_id = ?
                  AND substr(COALESCE(c.call_datetime, c.created_at), 1, 10) <= ?
                ORDER BY source_date, d.item_key""",
            key,
        )

    features: list[dict[str, Any]] = []
    if _has_table(conn, "contact_features"):
        features = _rows(
            conn,
            """SELECT feature_set, feature_name, value, support_n, tier
                 FROM contact_features
                WHERE user_id = ? AND contact_id = ?
                ORDER BY feature_set, feature_name""",
            (user_id, contact_id),
        )

    mentions: list[dict[str, Any]] = []
    if _has_table(conn, "mention_edges"):
        mentions = _rows(
            conn,
            """SELECT src_contact_id, dst_contact_id, mention_count, last_date
                 FROM mention_edges
                WHERE user_id = ? AND (src_contact_id = ? OR dst_contact_id = ?)
                ORDER BY src_contact_id, dst_contact_id""",
            (user_id, contact_id, contact_id),
        )

    # C-кандидаты и legacy-контекст разводятся ЗДЕСЬ, а не в потребителе: иначе
    # bulk-события 'contradiction' без provenance (bs_evidence, §0.1 п.11) молча
    # попадали бы в числитель C.
    contradiction_candidates = [
        e
        for e in events
        if e.get("producer") == "graph_v2"
        and (e.get("fact_type") or "") == "contradiction"
        and e.get("who") == "OTHER"
    ]
    legacy_context = [
        e
        for e in events
        if e.get("producer") != "graph_v2"
        and (e.get("fact_type") or e.get("event_type")) == "contradiction"
    ]

    return {
        "schema": SNAPSHOT_SCHEMA,
        "user_id": user_id,
        "contact_id": contact_id,
        "as_of": as_of_day,
        "calls": calls,
        "call_ids": call_ids,
        "analyses": analyses,
        "transcripts": transcripts,
        "promises": promises,
        "events": events,
        "contradiction_candidates": contradiction_candidates,
        "legacy_context": legacy_context,
        "promise_outcomes": outcomes,
        "deep_facts": deep_facts,
        "contact_features": features,
        "mention_edges": mentions,
        "callset": [
            (str(c.get("source_md5") or ""), _domain_date(c)) for c in calls
        ],
    }
