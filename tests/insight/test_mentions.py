# -*- coding: utf-8 -*-
"""test_mentions.py — граф упоминаний contact->contact через entity_contact_map (C1)."""
import json
import sqlite3
from pathlib import Path

import callprofiler.db as db_pkg
from callprofiler.graph.repository import apply_graph_schema
from callprofiler.insight import repository as insight_repo
from callprofiler.insight.mentions import build_mention_edges, mentioned_by, outgoing_count

_SEQ = {"n": 0}


def _db(with_graph=True):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = Path(db_pkg.__file__).parent / "schema.sql"
    conn.executescript(schema.read_text(encoding="utf-8"))
    if with_graph:
        apply_graph_schema(conn)
    insight_repo.apply_insight_schema(conn)
    return conn


def _contact(conn, uid, name):
    _SEQ["n"] += 1
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (uid, f"+79{_SEQ['n']:09d}", name),
    )
    return cur.lastrowid


def _call(conn, uid, contact_id, call_datetime="2026-06-01T10:00:00"):
    _SEQ["n"] += 1
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, source_filename, source_md5, call_datetime) "
        "VALUES (?,?,?,?,?)",
        (uid, contact_id, f"f{_SEQ['n']}.mp3", f"md5-{_SEQ['n']}", call_datetime),
    )
    return cur.lastrowid


def _entity(conn, uid, name, etype="PERSON", is_owner=0):
    cur = conn.execute(
        "INSERT INTO entities(user_id, entity_type, canonical_name, normalized_key, "
        "aliases, is_owner) VALUES (?,?,?,?,?,?)",
        (uid, etype, name, name.lower(), json.dumps([], ensure_ascii=False), is_owner),
    )
    return cur.lastrowid


def _event(conn, uid, call_id, entity_id, quote="цитата"):
    conn.execute(
        "INSERT INTO events(user_id, call_id, event_type, payload, entity_id, source_quote) "
        "VALUES (?,?,?,?,?,?)",
        (uid, call_id, "fact", "{}", entity_id, quote),
    )


def _map(conn, uid, entity_id, contact_id, confidence, method="name"):
    conn.execute(
        "INSERT INTO entity_contact_map(user_id, entity_id, contact_id, method, confidence) "
        "VALUES (?,?,?,?,?)",
        (uid, entity_id, contact_id, method, confidence),
    )


def _edges(conn, uid):
    rows = conn.execute(
        "SELECT src_contact_id, dst_contact_id, mention_count, last_date, sample_quote "
        "FROM mention_edges WHERE user_id = ? ORDER BY src_contact_id, dst_contact_id",
        (uid,),
    ).fetchall()
    return [dict(r) for r in rows]


def test_mention_twice_creates_edge_with_count_and_quote():
    conn = _db()
    x = _contact(conn, "me", "X")
    z = _contact(conn, "me", "Z")
    ivan = _entity(conn, "me", "Иван")
    _map(conn, "me", ivan, z, confidence=0.9)

    c1 = _call(conn, "me", x, call_datetime="2026-06-01T10:00:00")
    c2 = _call(conn, "me", x, call_datetime="2026-06-15T10:00:00")
    _event(conn, "me", c1, ivan, quote="Иван говорил про проект")
    _event(conn, "me", c2, ivan, quote="Иван снова звонил")

    stats = build_mention_edges(conn, "me")
    assert stats == {"edges": 1}

    edges = _edges(conn, "me")
    assert len(edges) == 1
    assert edges[0]["src_contact_id"] == x
    assert edges[0]["dst_contact_id"] == z
    assert edges[0]["mention_count"] == 2
    assert edges[0]["last_date"] == "2026-06-15T10:00:00"
    assert edges[0]["sample_quote"] in ("Иван говорил про проект", "Иван снова звонил")


def test_low_confidence_map_produces_no_edge():
    conn = _db()
    x = _contact(conn, "me", "X")
    z = _contact(conn, "me", "Z")
    ivan = _entity(conn, "me", "Иван")
    _map(conn, "me", ivan, z, confidence=0.5)

    c1 = _call(conn, "me", x)
    _event(conn, "me", c1, ivan)

    build_mention_edges(conn, "me")
    assert _edges(conn, "me") == []


def test_rebuild_is_idempotent():
    conn = _db()
    x = _contact(conn, "me", "X")
    z = _contact(conn, "me", "Z")
    ivan = _entity(conn, "me", "Иван")
    _map(conn, "me", ivan, z, confidence=0.9)
    c1 = _call(conn, "me", x)
    _event(conn, "me", c1, ivan, quote="раз")

    build_mention_edges(conn, "me")
    first = _edges(conn, "me")
    build_mention_edges(conn, "me")
    second = _edges(conn, "me")
    assert first == second


def test_dossier_mentioned_by_shows_source_contact():
    conn = _db()
    x = _contact(conn, "me", "X")
    z = _contact(conn, "me", "Z")
    ivan = _entity(conn, "me", "Иван")
    _map(conn, "me", ivan, z, confidence=0.9)
    c1 = _call(conn, "me", x)
    _event(conn, "me", c1, ivan, quote="про Ивана")

    build_mention_edges(conn, "me")
    by = mentioned_by(conn, "me", z, top=3)
    names = [b["name"] for b in by]
    assert "X" in names


def test_outgoing_count_counts_distinct_mentioned_contacts():
    conn = _db()
    x = _contact(conn, "me", "X")
    z1 = _contact(conn, "me", "Z1")
    z2 = _contact(conn, "me", "Z2")
    e1 = _entity(conn, "me", "Иван")
    e2 = _entity(conn, "me", "Пётр")
    _map(conn, "me", e1, z1, confidence=0.9)
    _map(conn, "me", e2, z2, confidence=0.9)
    c1 = _call(conn, "me", x)
    _event(conn, "me", c1, e1)
    _event(conn, "me", c1, e2)

    build_mention_edges(conn, "me")
    assert outgoing_count(conn, "me", x) == 2


def test_self_mention_excluded():
    conn = _db()
    x = _contact(conn, "me", "X")
    ivan = _entity(conn, "me", "Иван")
    _map(conn, "me", ivan, x, confidence=0.9)  # entity maps to the SAME contact as the call
    c1 = _call(conn, "me", x)
    _event(conn, "me", c1, ivan)

    build_mention_edges(conn, "me")
    assert _edges(conn, "me") == []


def test_non_person_entity_excluded():
    conn = _db()
    x = _contact(conn, "me", "X")
    z = _contact(conn, "me", "Z")
    company = _entity(conn, "me", "ООО Ромашка", etype="COMPANY")
    _map(conn, "me", company, z, confidence=0.9)
    c1 = _call(conn, "me", x)
    _event(conn, "me", c1, company)

    build_mention_edges(conn, "me")
    assert _edges(conn, "me") == []


def test_owner_entity_excluded():
    conn = _db()
    x = _contact(conn, "me", "X")
    z = _contact(conn, "me", "Z")
    owner_ent = _entity(conn, "me", "Владелец", is_owner=1)
    _map(conn, "me", owner_ent, z, confidence=0.9)
    c1 = _call(conn, "me", x)
    _event(conn, "me", c1, owner_ent)

    build_mention_edges(conn, "me")
    assert _edges(conn, "me") == []


def test_no_graph_schema_returns_zero_edges_gracefully():
    conn = _db(with_graph=False)
    assert build_mention_edges(conn, "me") == {"edges": 0}
