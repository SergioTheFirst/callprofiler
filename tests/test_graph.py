# -*- coding: utf-8 -*-
"""
test_graph.py — tests for the Knowledge Graph module.

Uses in-memory SQLite. No LLM, no filesystem.
"""

import json
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from callprofiler.db.repository import Repository
from callprofiler.graph.repository import GraphRepository, apply_graph_schema
from callprofiler.graph.builder import GraphBuilder, _hash
from callprofiler.graph.aggregator import EntityMetricsAggregator


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def _add_user(repo: Repository, user_id: str = "u1") -> None:
    repo.add_user(
        user_id=user_id,
        display_name="Test",
        telegram_chat_id="0",
        incoming_dir="/tmp/in",
        sync_dir="/tmp/sync",
        ref_audio="/tmp/ref.wav",
    )


def _add_call(repo: Repository, user_id: str = "u1", md5: str = "abc") -> int:
    contact_id = repo.get_or_create_contact(user_id, "+70000000001", "Test")
    return repo.create_call(
        user_id=user_id,
        contact_id=contact_id,
        direction="IN",
        call_datetime="2026-04-01 10:00:00",
        source_filename="t.mp3",
        source_md5=md5,
        audio_path="/tmp/t.mp3",
    )


def _save_v2_analysis(repo: Repository, call_id: int, raw: dict) -> None:
    from callprofiler.models import Analysis

    analysis = Analysis(
        priority=50,
        risk_score=30,
        summary="test",
        action_items=[],
        promises=[],
        flags={},
        key_topics=[],
        raw_response=json.dumps(raw, ensure_ascii=False),
        model="test",
        prompt_version="v2",
        call_type="business",
        hook=None,
    )
    repo.save_analysis(call_id, analysis)
    conn = repo._get_conn()
    conn.execute(
        "UPDATE analyses SET schema_version='v2' WHERE call_id=?", (call_id,)
    )
    conn.commit()


@pytest.fixture
def setup():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo)
    call_id = _add_call(repo)
    return repo, conn, call_id


# ── schema migration tests ────────────────────────────────────────────────────

def test_apply_graph_schema_idempotent():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    apply_graph_schema(conn)  # second call must not raise
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "entities" in tables
    assert "relations" in tables
    assert "entity_metrics" in tables


def test_analyses_schema_version_column():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(analyses)").fetchall()}
    assert "schema_version" in cols


def test_events_graph_columns():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    for col in ("entity_id", "fact_id", "quote", "start_ms", "end_ms", "polarity", "intensity"):
        assert col in cols, f"missing column: {col}"


# ── GraphRepository CRUD tests ────────────────────────────────────────────────

def test_upsert_entity_creates_and_returns_id(setup):
    _, conn, _ = setup
    grepo = GraphRepository(conn)
    eid = grepo.upsert_entity(
        user_id="u1",
        entity_type="person",
        canonical_name="Иван Петров",
        normalized_key="ivan_petrov",
        aliases=["Ваня"],
    )
    assert isinstance(eid, int) and eid > 0


def test_upsert_entity_idempotent(setup):
    _, conn, _ = setup
    grepo = GraphRepository(conn)
    eid1 = grepo.upsert_entity("u1", "person", "Иван", "ivan_petrov")
    eid2 = grepo.upsert_entity("u1", "person", "Иван Петров", "ivan_petrov")
    assert eid1 == eid2  # same normalized_key → same row


def test_upsert_entity_user_isolation(setup):
    repo, conn, _ = setup
    # u2 must exist in users for the FK to succeed
    repo.add_user(
        user_id="u2", display_name="User2", telegram_chat_id="0",
        incoming_dir="/tmp/in2", sync_dir="/tmp/sync2", ref_audio="/tmp/ref2.wav",
    )
    grepo = GraphRepository(conn)
    eid1 = grepo.upsert_entity("u1", "person", "Иван", "ivan")
    eid2 = grepo.upsert_entity("u2", "person", "Иван", "ivan")
    assert eid1 != eid2


def test_upsert_relation_with_decay_creates(setup):
    _, conn, call_id = setup
    grepo = GraphRepository(conn)
    src = grepo.upsert_entity("u1", "person", "Иван", "ivan")
    dst = grepo.upsert_entity("u1", "org", "ООО Рога", "ooo_roga")
    grepo.upsert_relation_with_decay(
        user_id="u1", src_id=src, dst_id=dst,
        relation_type="works_for", confidence=0.9,
        call_id=call_id, call_datetime="2026-04-01 10:00:00",
    )
    rel = grepo.get_relation("u1", src, dst, "works_for")
    assert rel is not None
    assert rel["call_count"] == 1
    assert abs(rel["weight"] - 0.9) < 1e-6


def test_upsert_relation_increments_call_count(setup):
    _, conn, call_id = setup
    grepo = GraphRepository(conn)
    src = grepo.upsert_entity("u1", "person", "Иван", "ivan")
    dst = grepo.upsert_entity("u1", "org", "ООО", "ooo")
    for _ in range(3):
        grepo.upsert_relation_with_decay("u1", src, dst, "works_for", 0.8, call_id, None)
    rel = grepo.get_relation("u1", src, dst, "works_for")
    assert rel["call_count"] == 3


def test_upsert_fact_inserts_into_events(setup):
    _, conn, call_id = setup
    grepo = GraphRepository(conn)
    grepo.upsert_fact(
        user_id="u1", call_id=call_id, contact_id=None, entity_id=None,
        fact_id="test1234", event_type="promise",
        quote="перезвоню завтра до шести",
        value="перезвонит", confidence=0.85,
    )
    rows = conn.execute(
        "SELECT * FROM events WHERE fact_id='test1234'"
    ).fetchall()
    assert len(rows) == 1


def test_upsert_fact_dedup(setup):
    _, conn, call_id = setup
    grepo = GraphRepository(conn)
    for _ in range(3):
        grepo.upsert_fact(
            user_id="u1", call_id=call_id, contact_id=None, entity_id=None,
            fact_id="dedup_abc", event_type="promise",
            quote="одна цитата для дедупа", confidence=0.9,
        )
    rows = conn.execute("SELECT COUNT(*) as n FROM events WHERE fact_id='dedup_abc'").fetchone()
    assert rows[0] == 1


def test_upsert_entity_metrics(setup):
    _, conn, _ = setup
    grepo = GraphRepository(conn)
    eid = grepo.upsert_entity("u1", "person", "Вася", "vasya")
    grepo.upsert_entity_metrics(
        entity_id=eid, user_id="u1",
        total_calls=5, total_promises=3, broken_promises=1,
        bs_index=25.0, bs_formula_version="v1_linear",
    )
    m = grepo.get_entity_metrics(eid)
    assert m is not None
    assert m["total_calls"] == 5
    assert abs(m["bs_index"] - 25.0) < 1e-6

    # idempotent update
    grepo.upsert_entity_metrics(entity_id=eid, user_id="u1", total_calls=10, bs_index=30.0)
    m2 = grepo.get_entity_metrics(eid)
    assert m2["total_calls"] == 10


# ── GraphBuilder tests ────────────────────────────────────────────────────────

def _v2_payload(entities=None, relations=None, facts=None) -> dict:
    return {
        "schema_version": "v2",
        "summary": "test",
        "category": "рабочий",
        "priority": 40,
        "risk_score": 20,
        "sentiment": "нейтральный",
        "action_items": [],
        "promises": [],
        "key_topics": [],
        "people": [],
        "companies": [],
        "amounts": [],
        "contact_name_guess": None,
        "bs_score": 0,
        "bs_evidence": [],
        "flags": {"urgent": False, "conflict": False, "money": False, "legal_risk": False},
        "call_type": "business",
        "hook": None,
        "entities": entities or [],
        "relations": relations or [],
        "structured_facts": facts or [],
    }


def test_builder_skips_v1(setup):
    repo, conn, call_id = setup
    from callprofiler.models import Analysis
    a = Analysis(
        priority=0, risk_score=0, summary="",
        action_items=[], promises=[], flags={},
        key_topics=[], raw_response=json.dumps(_v2_payload()),
        model="t", prompt_version="v1", call_type="short", hook=None,
    )
    repo.save_analysis(call_id, a)
    # schema_version defaults to 'v1' — builder must skip

    builder = GraphBuilder(conn)
    result = builder.update_from_call(call_id)
    assert result is False


def test_builder_processes_v2(setup):
    repo, conn, call_id = setup
    payload = _v2_payload(
        entities=[
            {"type": "person", "canonical_name": "Иван Петров",
             "normalized_key": "ivan_petrov", "aliases": ["Ваня"], "attributes": {}},
        ],
        facts=[
            {"fact_type": "promise", "entity_key": "ivan_petrov",
             "value": "перезвонит", "quote": "перезвоню завтра", "confidence": 0.9,
             "polarity": 1, "intensity": 0.7},
        ],
    )
    _save_v2_analysis(repo, call_id, payload)
    builder = GraphBuilder(conn)
    result = builder.update_from_call(call_id)
    assert result is True

    grepo = GraphRepository(conn)
    entities = grepo.get_entities("u1", "person")
    assert any(e["normalized_key"] == "ivan_petrov" for e in entities)


def test_builder_relation_links_entities(setup):
    repo, conn, call_id = setup
    payload = _v2_payload(
        entities=[
            {"type": "person", "canonical_name": "Иван", "normalized_key": "ivan"},
            {"type": "org", "canonical_name": "ООО Рога", "normalized_key": "ooo_roga"},
        ],
        relations=[
            {"src_key": "ivan", "dst_key": "ooo_roga",
             "relation_type": "works_for", "confidence": 0.85},
        ],
    )
    _save_v2_analysis(repo, call_id, payload)
    GraphBuilder(conn).update_from_call(call_id)

    grepo = GraphRepository(conn)
    entities = {e["normalized_key"]: e["id"] for e in grepo.get_entities("u1")}
    rel = grepo.get_relation("u1", entities["ivan"], entities["ooo_roga"], "works_for")
    assert rel is not None


def test_builder_filters_low_confidence_facts(setup):
    repo, conn, call_id = setup
    payload = _v2_payload(
        entities=[{"type": "person", "canonical_name": "Вася", "normalized_key": "vasya"}],
        facts=[
            {"fact_type": "claim", "entity_key": "vasya",
             "quote": "скоро сделаю", "confidence": 0.3},  # below 0.6 threshold
        ],
    )
    _save_v2_analysis(repo, call_id, payload)
    GraphBuilder(conn).update_from_call(call_id)

    rows = conn.execute("SELECT COUNT(*) FROM events WHERE fact_id IS NOT NULL").fetchone()
    assert rows[0] == 0


def test_builder_filters_short_quote_facts(setup):
    repo, conn, call_id = setup
    payload = _v2_payload(
        entities=[{"type": "person", "canonical_name": "Вася", "normalized_key": "vasya"}],
        facts=[
            {"fact_type": "promise", "entity_key": "vasya",
             "quote": "да", "confidence": 0.9},  # too short (< MIN_QUOTE_LENGTH=5)
        ],
    )
    _save_v2_analysis(repo, call_id, payload)
    GraphBuilder(conn).update_from_call(call_id)

    rows = conn.execute("SELECT COUNT(*) FROM events WHERE fact_id IS NOT NULL").fetchone()
    assert rows[0] == 0


def test_builder_fact_dedup(setup):
    repo, conn, call_id = setup
    payload = _v2_payload(
        entities=[{"type": "person", "canonical_name": "Иван", "normalized_key": "ivan"}],
        facts=[
            {"fact_type": "promise", "entity_key": "ivan",
             "quote": "перезвоню завтра ровно", "confidence": 0.9},
        ],
    )
    _save_v2_analysis(repo, call_id, payload)
    builder = GraphBuilder(conn)
    builder.update_from_call(call_id)
    builder.update_from_call(call_id)  # second run — must not duplicate

    rows = conn.execute("SELECT COUNT(*) FROM events WHERE fact_id IS NOT NULL").fetchone()
    assert rows[0] == 1


# ── EntityMetricsAggregator tests ─────────────────────────────────────────────

def test_aggregator_bs_zero_for_clean_entity(setup):
    _, conn, _ = setup
    grepo = GraphRepository(conn)
    agg = EntityMetricsAggregator(grepo)

    bs = EntityMetricsAggregator._bs_v1_linear(
        total_promises=0, broken=0, total_calls=10,
        contradictions=0, vagueness=0, blame_shifts=0, emotional_spikes=0,
    )
    assert bs == 0.0


def test_aggregator_bs_max_for_all_broken(setup):
    _, conn, _ = setup
    bs = EntityMetricsAggregator._bs_v1_linear(
        total_promises=5, broken=5, total_calls=5,
        contradictions=5, vagueness=5, blame_shifts=5, emotional_spikes=5,
    )
    assert bs == 100.0


def test_aggregator_bs_partial():
    bs = EntityMetricsAggregator._bs_v1_linear(
        total_promises=10, broken=4, total_calls=10,
        contradictions=2, vagueness=1, blame_shifts=1, emotional_spikes=1,
    )
    # broken_ratio = 0.4, contradiction_dens = 0.2, vagueness_dens = 0.1,
    # blame = 0.1, emotional = 0.1
    # bs_raw = 0.40*0.4 + 0.20*0.2 + 0.15*0.1 + 0.15*0.1 + 0.10*0.1
    # = 0.16 + 0.04 + 0.015 + 0.015 + 0.01 = 0.24 → 24.0
    assert abs(bs - 24.0) < 0.01


def test_aggregator_recalc_persists_metrics(setup):
    repo, conn, call_id = setup
    grepo = GraphRepository(conn)
    agg = EntityMetricsAggregator(grepo)

    eid = grepo.upsert_entity("u1", "person", "Вася", "vasya")
    agg.recalc_for_entities([eid], "u1")

    m = grepo.get_entity_metrics(eid)
    assert m is not None
    assert m["bs_formula_version"] == "v1_linear"


# ── hash helper ───────────────────────────────────────────────────────────────

def test_hash_deterministic():
    h1 = _hash("promise|42|перезвоню завтра")
    h2 = _hash("promise|42|перезвоню завтра")
    assert h1 == h2
    assert len(h1) == 16


def test_hash_different_inputs():
    assert _hash("a") != _hash("b")


# ── graph stats ───────────────────────────────────────────────────────────────

def test_graph_stats_empty(setup):
    _, conn, _ = setup
    grepo = GraphRepository(conn)
    stats = grepo.stats("u1")
    assert stats["entities"] == {}
    assert stats["relations"] == {}
    assert stats["facts"] == {}


def test_graph_stats_counts(setup):
    repo, conn, call_id = setup
    payload = _v2_payload(
        entities=[
            {"type": "person", "canonical_name": "Иван", "normalized_key": "ivan"},
            {"type": "org", "canonical_name": "ООО", "normalized_key": "ooo"},
        ],
        relations=[
            {"src_key": "ivan", "dst_key": "ooo", "relation_type": "works_for", "confidence": 0.9},
        ],
        facts=[
            {"fact_type": "promise", "entity_key": "ivan",
             "quote": "перезвоню завтра в восемь", "confidence": 0.85},
        ],
    )
    _save_v2_analysis(repo, call_id, payload)
    GraphBuilder(conn).update_from_call(call_id)
    stats = GraphRepository(conn).stats("u1")

    assert stats["entities"].get("person", 0) == 1
    assert stats["entities"].get("org", 0) == 1
    assert stats["relations"].get("works_for", 0) == 1
