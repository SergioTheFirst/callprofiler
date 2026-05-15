# -*- coding: utf-8 -*-
"""test_regressions.py — regression / cross-cutting tests for Phase F."""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from callprofiler.db.repository import Repository
from callprofiler.graph.repository import GraphRepository, apply_graph_schema
from callprofiler.graph.builder import GraphBuilder


def _make_repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def _add_user(repo: Repository, user_id: str = "u1") -> None:
    repo.add_user(
        user_id=user_id, display_name="Test", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/ref.wav",
    )


def _add_call(repo: Repository, user_id: str = "u1", md5: str = "abc") -> int:
    contact_id = repo.get_or_create_contact(user_id, "+70000000001", "Test")
    return repo.create_call(
        user_id=user_id, contact_id=contact_id, direction="IN",
        call_datetime="2026-04-01 10:00:00", source_filename="t.mp3",
        source_md5=md5, audio_path="/tmp/t.mp3",
    )


def _save_v2(repo: Repository, call_id: int, raw: dict) -> None:
    from callprofiler.models import Analysis
    a = Analysis(
        priority=50, risk_score=30, summary="test",
        action_items=[], promises=[], flags={}, key_topics=[],
        raw_response=json.dumps(raw, ensure_ascii=False),
        model="test", prompt_version="v2", call_type="business", hook=None,
    )
    repo.save_analysis(call_id, a)
    conn = repo._get_conn()
    conn.execute("UPDATE analyses SET schema_version='v2' WHERE call_id=?", (call_id,))
    conn.commit()


def _payload(**kw) -> dict:
    return {
        "entities": kw.get("entities", []),
        "relations": kw.get("relations", []),
        "structured_facts": kw.get("facts", []),
    }


def test_duplicate_call_insert_idempotent():
    """call_exists detects existing call by md5, preventing double processing."""
    repo = _make_repo()
    _add_user(repo)
    call_id = _add_call(repo, "u1", "same_md5")

    assert repo.call_exists("u1", "same_md5") is True
    assert repo.call_exists("u1", "nonexistent_md5") is False

    contact_id = repo.get_or_create_contact("u1", "+70000000002", "Test2")
    call_id2 = repo.create_call(
        user_id="u1", contact_id=contact_id, direction="IN",
        call_datetime="2026-04-01 10:00:00", source_filename="t2.mp3",
        source_md5="same_md5", audio_path="/tmp/t2.mp3",
    )
    assert repo.call_exists("u1", "same_md5") is True


def test_cross_user_cannot_read_entities():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo, "uA")
    _add_user(repo, "uB")
    grepo = GraphRepository(conn)

    eid_a = grepo.upsert_entity("uA", "person", "Alice", "alice")
    eid_b = grepo.upsert_entity("uB", "person", "Bob", "bob")

    entities_a = grepo.get_entities("uA", "person")
    assert all(e["id"] != eid_b for e in entities_a)

    entities_b = grepo.get_entities("uB", "person")
    assert all(e["id"] != eid_a for e in entities_b)


def test_entity_with_no_events_metrics_zero():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo)
    grepo = GraphRepository(conn)
    from callprofiler.graph.aggregator import EntityMetricsAggregator

    eid = grepo.upsert_entity("u1", "person", "Nobody", "nobody")
    agg = EntityMetricsAggregator(grepo)
    result = agg.full_recalc_from_events(eid)

    assert result["total_calls"] == 0
    assert result["total_promises"] == 0
    assert result["bs_index"] == 0.0


def test_archived_entity_not_in_merge_candidates():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo)
    grepo = GraphRepository(conn)

    eid = grepo.upsert_entity("u1", "person", "Сергей", "sergei")
    eid2 = grepo.upsert_entity("u1", "person", "Сергей Иванов", "sergei_2")
    conn.execute("UPDATE entities SET archived=1 WHERE id=?", (eid2,))
    conn.commit()

    from callprofiler.graph.resolver import EntityResolver
    resolver = EntityResolver(conn)
    candidates = resolver.find_candidates("u1", "person", min_score=0.5)
    archived = {r[0] for r in conn.execute(
        "SELECT id FROM entities WHERE archived=1"
    ).fetchall()}
    for c in candidates:
        assert c.canonical_id not in archived
        assert c.duplicate_id not in archived


def test_empty_canonical_quotes_audited():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo)
    grepo = GraphRepository(conn)

    eid = grepo.upsert_entity("u1", "person", "Shorty", "shorty")
    call_id = _add_call(repo)
    conn.execute(
        """INSERT INTO events
           (user_id, call_id, event_type, who, payload, status, entity_id, fact_id, quote)
           VALUES ('u1', ?, 'fact', 'UNKNOWN', 'x', 'open', ?, 'f1', 'да')""",
        (call_id, eid),
    )
    conn.commit()

    from callprofiler.graph.auditor import GraphAuditor
    auditor = GraphAuditor(conn)
    result = auditor.run_checks("u1")
    assert "empty_canonical_quotes" in result["checks"]


def test_relation_call_count_multiple_updates():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo)
    grepo = GraphRepository(conn)

    src = grepo.upsert_entity("u1", "person", "Иван", "ivan")
    dst = grepo.upsert_entity("u1", "org", "ООО", "ooo")
    call_id = _add_call(repo)

    grepo.upsert_relation_with_decay("u1", src, dst, "works_for", 0.9, call_id, None)
    grepo.upsert_relation_with_decay("u1", src, dst, "works_for", 0.9, call_id, None)
    rel = grepo.get_relation("u1", src, dst, "works_for")
    assert rel["call_count"] >= 2


def test_fact_dedup_same_call_replayed():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo)
    call_id = _add_call(repo)
    _save_v2(repo, call_id, _payload(
        entities=[{"type": "person", "canonical_name": "Иван", "normalized_key": "ivan",
                    "aliases": [], "attributes": {}}],
        facts=[{"fact_type": "promise", "entity_key": "ivan",
                 "quote": "перезвоню завтра в восемь ровно утра", "confidence": 0.9}],
    ))

    builder = GraphBuilder(conn)
    builder.update_from_call(call_id)
    builder.update_from_call(call_id)

    rows = conn.execute(
        "SELECT COUNT(*) FROM events WHERE fact_id IS NOT NULL"
    ).fetchone()
    assert rows[0] == 1


def test_entity_aliases_saved():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo)
    grepo = GraphRepository(conn)

    eid = grepo.upsert_entity(
        "u1", "person", "Александр", "alexander",
        aliases=["Саша", "Шура"],
    )
    entities = grepo.get_entities("u1", "person")
    found = next(e for e in entities if e["id"] == eid)
    assert found["normalized_key"] == "alexander"


def test_metrics_not_drifted_after_fresh_recalc():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo)
    grepo = GraphRepository(conn)
    from callprofiler.graph.aggregator import EntityMetricsAggregator

    eid = grepo.upsert_entity("u1", "person", "Стас", "stas")
    grepo.upsert_entity_metrics(eid, "u1", total_calls=5, bs_index=20.0)

    agg = EntityMetricsAggregator(grepo)
    result = agg.full_recalc_from_events(eid)
    assert abs(result["bs_index"] - 20.0) <= 20.0


def test_corrupted_analysis_skipped_by_builder():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo)
    call_id = _add_call(repo)

    conn.execute(
        "INSERT INTO analyses (call_id, schema_version, raw_response) VALUES (?, 'v2', ?)",
        (call_id, "not valid json {{{ broken"),
    )
    conn.commit()

    builder = GraphBuilder(conn)
    result = builder.update_from_call(call_id)
    assert result is False
