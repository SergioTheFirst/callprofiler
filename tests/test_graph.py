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


# ── full_recalc_from_events tests ─────────────────────────────────────────────

def test_full_recalc_returns_dict_for_empty_entity(setup):
    _, conn, _ = setup
    grepo = GraphRepository(conn)
    agg = EntityMetricsAggregator(grepo)

    eid = grepo.upsert_entity("u1", "person", "Иван", "ivan")
    result = agg.full_recalc_from_events(eid)

    assert result["entity_id"] == eid
    assert result["total_calls"] == 0
    assert result["bs_index"] == 0.0
    assert result["bs_formula_version"] == "v1_linear"


def test_full_recalc_entity_not_found_raises(setup):
    _, conn, _ = setup
    grepo = GraphRepository(conn)
    agg = EntityMetricsAggregator(grepo)

    import pytest
    with pytest.raises(ValueError, match="not found"):
        agg.full_recalc_from_events(99999)


def test_full_recalc_idempotent(setup):
    repo, conn, call_id = setup
    payload = _v2_payload(
        entities=[{"type": "person", "canonical_name": "Вася", "normalized_key": "vasya"}],
        facts=[
            {"fact_type": "promise", "entity_key": "vasya",
             "quote": "сделаю завтра утром точно", "confidence": 0.9},
        ],
    )
    _save_v2_analysis(repo, call_id, payload)
    GraphBuilder(conn).update_from_call(call_id)

    grepo = GraphRepository(conn)
    agg = EntityMetricsAggregator(grepo)
    eid = next(e["id"] for e in grepo.get_entities("u1", "person")
               if e["normalized_key"] == "vasya")

    r1 = agg.full_recalc_from_events(eid)
    r2 = agg.full_recalc_from_events(eid)  # second call must produce identical result

    assert r1["total_calls"] == r2["total_calls"]
    assert abs(r1["bs_index"] - r2["bs_index"]) < 1e-6
    assert r1["total_promises"] == r2["total_promises"]


def test_full_recalc_counts_facts_correctly(setup):
    repo, conn, call_id = setup
    payload = _v2_payload(
        entities=[{"type": "person", "canonical_name": "Вася", "normalized_key": "vasya"}],
        facts=[
            {"fact_type": "promise", "entity_key": "vasya",
             "quote": "перезвоню завтра рано утром", "confidence": 0.9},
            {"fact_type": "contradiction", "entity_key": "vasya",
             "quote": "вчера говорил другое совсем", "confidence": 0.8},
        ],
    )
    _save_v2_analysis(repo, call_id, payload)
    GraphBuilder(conn).update_from_call(call_id)

    grepo = GraphRepository(conn)
    agg = EntityMetricsAggregator(grepo)
    eid = next(e["id"] for e in grepo.get_entities("u1", "person")
               if e["normalized_key"] == "vasya")

    result = agg.full_recalc_from_events(eid)
    assert result["total_calls"] == 1
    assert result["total_promises"] == 1

    # Verify entity_metrics row was written
    m = grepo.get_entity_metrics(eid)
    assert m is not None
    assert m["total_calls"] == 1


# ── is_owner migration test ───────────────────────────────────────────────────

def test_is_owner_column_exists_after_migration():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entities)").fetchall()}
    assert "is_owner" in cols


def test_is_owner_index_exists():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    idx = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_entities_owner'"
    ).fetchone()
    assert idx is not None


# ── EntityResolver tests ──────────────────────────────────────────────────────

def test_resolver_find_candidates_excludes_owner(setup):
    _, conn, _ = setup
    from callprofiler.graph.resolver import EntityResolver

    grepo = GraphRepository(conn)
    # Create two entities with same name; mark one as owner
    eid_owner = grepo.upsert_entity("u1", "person", "Сергей Медведев", "sergei_medvedev")
    conn.execute("UPDATE entities SET is_owner=1 WHERE id=?", (eid_owner,))
    conn.commit()
    _eid_other = grepo.upsert_entity("u1", "person", "Сергей Медведев", "sergei_medvedev_2")

    resolver = EntityResolver(conn)
    candidates = resolver.find_candidates("u1", "person", min_score=0.5)
    ids = {c.canonical_id for c in candidates} | {c.duplicate_id for c in candidates}
    assert eid_owner not in ids, "Owner entity must never appear in merge candidates"


def test_resolver_execute_merge_basic(setup):
    _, conn, _ = setup
    from callprofiler.graph.resolver import EntityResolver

    grepo = GraphRepository(conn)
    canonical_id = grepo.upsert_entity("u1", "person", "Иван Петров", "ivan_petrov")
    duplicate_id = grepo.upsert_entity("u1", "person", "Ваня Петров", "vanya_petrov")

    resolver = EntityResolver(conn)
    resolver.execute_merge(
        canonical_id=canonical_id,
        duplicate_id=duplicate_id,
        signals={"score": 0.80, "name_similarity": 0.75},
        merged_by="test",
    )

    # Duplicate must be archived
    dup_row = conn.execute(
        "SELECT archived, merged_into_id FROM entities WHERE id=?", (duplicate_id,)
    ).fetchone()
    assert dup_row[0] == 1, "duplicate must be archived"
    assert dup_row[1] == canonical_id, "merged_into_id must point to canonical"

    # Merge log must have a row
    log_row = conn.execute(
        "SELECT * FROM entity_merges_log WHERE canonical_id=? AND duplicate_id=?",
        (canonical_id, duplicate_id),
    ).fetchone()
    assert log_row is not None

    # Canonical metrics must be computed
    m = grepo.get_entity_metrics(canonical_id)
    assert m is not None


def test_resolver_execute_merge_owner_blocked(setup):
    _, conn, _ = setup
    from callprofiler.graph.resolver import EntityResolver
    import pytest

    grepo = GraphRepository(conn)
    owner_id = grepo.upsert_entity("u1", "person", "Сергей", "sergei")
    conn.execute("UPDATE entities SET is_owner=1 WHERE id=?", (owner_id,))
    conn.commit()
    other_id = grepo.upsert_entity("u1", "person", "Сергей Иванов", "sergei_ivanov")

    resolver = EntityResolver(conn)
    with pytest.raises(ValueError, match="owner"):
        resolver.execute_merge(owner_id, other_id, {})


# ── GraphAuditor tests ────────────────────────────────────────────────────────

def test_auditor_clean_graph_all_ok(setup):
    _, conn, _ = setup
    from callprofiler.graph.auditor import GraphAuditor

    auditor = GraphAuditor(conn)
    result = auditor.run_checks("u1")

    assert "checks" in result
    assert result["has_critical"] is False
    # All checks should pass on empty graph except possibly merge_candidates_residual
    # (no entities = no candidates = ok)


def test_auditor_detects_orphan_events(setup):
    repo, conn, call_id = setup
    from callprofiler.graph.auditor import GraphAuditor

    # Create entity, insert event linked to it, then archive entity → orphan event
    grepo = GraphRepository(conn)
    phantom_id = grepo.upsert_entity("u1", "person", "Призрак", "prizrak")
    conn.execute(
        """INSERT INTO events (user_id, call_id, event_type, who, payload, status, entity_id)
           VALUES ('u1', ?, 'fact', 'UNKNOWN', 'x', 'open', ?)""",
        (call_id, phantom_id),
    )
    # Archive the entity — now event's entity_id points to archived entity → orphan
    conn.execute("UPDATE entities SET archived=1 WHERE id=?", (phantom_id,))
    conn.commit()

    auditor = GraphAuditor(conn)
    result = auditor.run_checks("u1")

    assert result["has_critical"] is True
    assert result["checks"]["orphan_events"]["ok"] is False
    assert result["checks"]["orphan_events"]["count"] >= 1


def test_auditor_detects_owner_contamination(setup):
    repo, conn, call_id = setup
    from callprofiler.graph.auditor import GraphAuditor

    grepo = GraphRepository(conn)
    owner_id = grepo.upsert_entity("u1", "person", "Сергей", "sergei")
    conn.execute("UPDATE entities SET is_owner=1 WHERE id=?", (owner_id,))
    # Insert a fact event for the owner
    conn.execute(
        """INSERT INTO events
           (user_id, call_id, event_type, who, payload, status, entity_id, fact_id, quote)
           VALUES ('u1', ?, 'fact', 'UNKNOWN', 'x', 'open', ?, 'abc123', 'некая цитата')""",
        (call_id, owner_id),
    )
    conn.commit()

    auditor = GraphAuditor(conn)
    result = auditor.run_checks("u1")

    assert result["has_critical"] is True
    assert result["checks"]["owner_contamination"]["ok"] is False
