# -*- coding: utf-8 -*-
"""test_person_link.py — связка graph-entity ↔ contact (Ф1 плана досье).

Мягкие перестраиваемые ссылки: name-match (0.95) + co-occurrence
(share>=0.6, n>=3, только PERSON). Никакого слияния контактов.
"""
import json
import sqlite3
from pathlib import Path

import callprofiler.db as db_pkg
from callprofiler.graph.repository import apply_graph_schema
from callprofiler.insight import repository as insight_repo
from callprofiler.insight.person_link import build_entity_contact_map

_SEQ = {"n": 0}


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = Path(db_pkg.__file__).parent / "schema.sql"
    conn.executescript(schema.read_text(encoding="utf-8"))
    apply_graph_schema(conn)
    insight_repo.apply_insight_schema(conn)
    return conn


def _contact(conn, uid, name, guessed=None):
    _SEQ["n"] += 1
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name, guessed_name) "
        "VALUES (?,?,?,?)",
        (uid, f"+79{_SEQ['n']:09d}", name, guessed),
    )
    return cur.lastrowid


def _call(conn, uid, contact_id):
    _SEQ["n"] += 1
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, source_filename, source_md5) "
        "VALUES (?,?,?,?)",
        (uid, contact_id, f"f{_SEQ['n']}.mp3", f"md5-{_SEQ['n']}"),
    )
    return cur.lastrowid


def _entity(conn, uid, name, etype="PERSON", aliases=(), is_owner=0):
    cur = conn.execute(
        "INSERT INTO entities(user_id, entity_type, canonical_name, normalized_key, "
        "aliases, is_owner) VALUES (?,?,?,?,?,?)",
        (uid, etype, name, name.lower(), json.dumps(list(aliases), ensure_ascii=False),
         is_owner),
    )
    return cur.lastrowid


def _event(conn, uid, call_id, entity_id):
    conn.execute(
        "INSERT INTO events(user_id, call_id, event_type, payload, entity_id) "
        "VALUES (?,?,?,?,?)",
        (uid, call_id, "fact", "{}", entity_id),
    )


def _links(conn, uid):
    rows = conn.execute(
        "SELECT entity_id, contact_id, method, confidence FROM entity_contact_map "
        "WHERE user_id = ? ORDER BY entity_id, contact_id",
        (uid,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── name-match ──────────────────────────────────────────────────────────

def test_name_match_by_alias():
    conn = _db()
    cid = _contact(conn, "me", "Дмитрий Бердников")
    eid = _entity(conn, "me", "Димон Бердников", aliases=["Дмитрий Бердников", "Димон"])

    build_entity_contact_map(conn, "me")

    links = _links(conn, "me")
    assert links == [
        {"entity_id": eid, "contact_id": cid, "method": "name", "confidence": 0.95}
    ]


def test_name_match_normalizes_yo_case_spaces():
    conn = _db()
    cid = _contact(conn, "me", "  пётр  СЕМЁНОВ ")
    eid = _entity(conn, "me", "Петр Семенов")

    build_entity_contact_map(conn, "me")

    links = _links(conn, "me")
    assert [(l["entity_id"], l["contact_id"], l["method"]) for l in links] == [
        (eid, cid, "name")
    ]


def test_name_match_uses_guessed_name_and_any_type():
    conn = _db()
    cid = _contact(conn, "me", None, guessed="ООО Ромашка")
    eid = _entity(conn, "me", "ООО Ромашка", etype="COMPANY")

    build_entity_contact_map(conn, "me")

    links = _links(conn, "me")
    assert len(links) == 1
    assert (links[0]["entity_id"], links[0]["contact_id"]) == (eid, cid)
    assert links[0]["method"] == "name"


# ── co-occurrence ───────────────────────────────────────────────────────

def test_cooccur_links_dominant_person():
    conn = _db()
    cid_a = _contact(conn, "me", "А")
    cid_b = _contact(conn, "me", "Б")
    eid = _entity(conn, "me", "Вася Упомянутый")  # имя ни с кем не совпадает

    for _ in range(3):  # 3 звонка контакта А с упоминанием
        _event(conn, "me", _call(conn, "me", cid_a), eid)
    _event(conn, "me", _call(conn, "me", cid_b), eid)  # 1 звонок Б

    build_entity_contact_map(conn, "me")

    links = _links(conn, "me")
    assert len(links) == 1
    link = links[0]
    assert (link["entity_id"], link["contact_id"], link["method"]) == (eid, cid_a, "cooccur")
    assert abs(link["confidence"] - (0.6 + 0.3 * 0.75)) < 1e-6  # share=3/4


def test_cooccur_below_min_events_not_linked():
    conn = _db()
    cid = _contact(conn, "me", "А")
    eid = _entity(conn, "me", "Редкий")
    for _ in range(2):  # n=2 < 3
        _event(conn, "me", _call(conn, "me", cid), eid)

    build_entity_contact_map(conn, "me")

    assert _links(conn, "me") == []


def test_cooccur_company_not_linked():
    conn = _db()
    cid = _contact(conn, "me", "А")
    eid = _entity(conn, "me", "ЗАО Вектор", etype="COMPANY")
    for _ in range(5):
        _event(conn, "me", _call(conn, "me", cid), eid)

    build_entity_contact_map(conn, "me")

    assert _links(conn, "me") == []  # cooccur — только PERSON


# ── защиты и инварианты ─────────────────────────────────────────────────

def test_owner_never_linked():
    conn = _db()
    cid = _contact(conn, "me", "Сергей Медведев")
    eid = _entity(conn, "me", "Сергей Медведев", is_owner=1)
    for _ in range(5):
        _event(conn, "me", _call(conn, "me", cid), eid)

    build_entity_contact_map(conn, "me")

    assert _links(conn, "me") == []


def test_rebuild_idempotent():
    conn = _db()
    cid = _contact(conn, "me", "Дмитрий")
    _entity(conn, "me", "Дмитрий")
    for _ in range(3):
        _event(conn, "me", _call(conn, "me", cid), 1)

    s1 = build_entity_contact_map(conn, "me")
    s2 = build_entity_contact_map(conn, "me")

    assert s1["links"] == s2["links"] == len(_links(conn, "me")) == 1


def test_user_isolation():
    conn = _db()
    cid_me = _contact(conn, "me", "Иван")
    _entity(conn, "me", "Иван")
    cid_other = _contact(conn, "other", "Иван")
    _entity(conn, "other", "Иван")

    build_entity_contact_map(conn, "me")

    assert _links(conn, "other") == []          # чужого пользователя не трогали
    me_links = _links(conn, "me")
    assert len(me_links) == 1
    assert me_links[0]["contact_id"] == cid_me  # и не прилинковали чужой контакт
    assert me_links[0]["contact_id"] != cid_other


def test_dry_run_writes_nothing():
    conn = _db()
    _contact(conn, "me", "Дмитрий")
    _entity(conn, "me", "Дмитрий")

    stats = build_entity_contact_map(conn, "me", dry_run=True)

    assert stats["links"] == 1
    assert _links(conn, "me") == []
