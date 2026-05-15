# -*- coding: utf-8 -*-
"""test_graph_replay.py — additional tests for GraphReplayer not in test_graph.py."""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from callprofiler.db.repository import Repository
from callprofiler.graph.repository import GraphRepository, apply_graph_schema
from callprofiler.graph.replay import GraphReplayer


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


def _insert_v2_analysis(conn, call_id: int, entities=None, relations=None, facts=None) -> None:
    payload = {
        "entities": entities or [],
        "relations": relations or [],
        "structured_facts": facts or [],
    }
    conn.execute(
        "INSERT INTO analyses (call_id, schema_version, raw_response) VALUES (?, 'v2', ?)",
        (call_id, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def _setup_with_analysis(conn, repo, user_id="u1", md5="abc", entities=None, relations=None, facts=None):
    if user_id not in {"u1"}:
        _add_user(repo, user_id)
    call_id = _add_call(repo, user_id, md5)
    _insert_v2_analysis(conn, call_id, entities=entities, relations=relations, facts=facts)
    return call_id


def test_replay_no_v2_returns_empty():
    repo = _make_repo()
    _add_user(repo)
    conn = repo._get_conn()
    apply_graph_schema(conn)

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1", limit=None)
    assert stats["calls_processed"] == 0


def test_replay_return_keys_complete():
    repo = _make_repo()
    _add_user(repo)
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _setup_with_analysis(conn, repo,
        entities=[{"type": "person", "canonical_name": "Иван", "normalized_key": "ivan",
                    "aliases": [], "attributes": {}}],
        facts=[{"fact_type": "promise", "entity_key": "ivan",
                 "quote": "перезвоню завтра ровно в восемь", "confidence": 0.9}],
    )

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1")
    for key in ("user_id", "calls_processed", "entities_count", "relations_count",
                "facts_count", "facts_total", "facts_inserted", "facts_rejected",
                "rejection_rate", "avg_bs_index", "audit_critical", "audit_result", "warnings"):
        assert key in stats, f"missing key: {key}"


def test_replay_saves_run_record():
    repo = _make_repo()
    _add_user(repo)
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _setup_with_analysis(conn, repo,
        entities=[{"type": "person", "canonical_name": "Иван", "normalized_key": "ivan",
                    "aliases": [], "attributes": {}}],
        facts=[{"fact_type": "promise", "entity_key": "ivan",
                 "quote": "перезвоню завтра в восемь часов", "confidence": 0.9}],
    )

    replayer = GraphReplayer(repo, GraphRepository(conn))
    replayer.replay("u1")

    rows = conn.execute(
        "SELECT COUNT(*) FROM graph_replay_runs WHERE user_id='u1'"
    ).fetchone()
    assert rows[0] >= 1


def test_replay_limit_restricts_calls():
    repo = _make_repo()
    _add_user(repo)
    conn = repo._get_conn()
    apply_graph_schema(conn)
    for i in range(5):
        _setup_with_analysis(conn, repo, md5=f"md5_{i}",
            entities=[{"type": "person", "canonical_name": f"P{i}", "normalized_key": f"p{i}",
                       "aliases": [], "attributes": {}}],
            facts=[{"fact_type": "promise", "entity_key": f"p{i}",
                     "quote": f"перезвоню {i} раз завтра утром", "confidence": 0.9}],
        )

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1", limit=2)
    assert stats["calls_processed"] == 2


def test_replay_rejection_rate():
    repo = _make_repo()
    _add_user(repo)
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _setup_with_analysis(conn, repo,
        entities=[{"type": "person", "canonical_name": "Иван", "normalized_key": "ivan",
                    "aliases": [], "attributes": {}}],
        facts=[{"fact_type": "promise", "entity_key": "ivan",
                 "quote": "перезвоню завтра ровно в восемь утра", "confidence": 0.9}],
    )

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1")
    assert isinstance(stats["rejection_rate"], float)
    assert 0.0 <= stats["rejection_rate"] <= 1.0


def test_replay_warnings_high_rejection():
    repo = _make_repo()
    _add_user(repo)
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _setup_with_analysis(conn, repo,
        entities=[{"type": "person", "canonical_name": "Иван", "normalized_key": "ivan",
                    "aliases": [], "attributes": {}}],
        facts=[],
    )

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1")
    assert any("facts_inserted=0" in w.lower() for w in stats["warnings"])


def test_replay_auditor_integrated():
    repo = _make_repo()
    _add_user(repo)
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _setup_with_analysis(conn, repo,
        entities=[{"type": "person", "canonical_name": "Иван", "normalized_key": "ivan",
                    "aliases": [], "attributes": {}}],
        facts=[{"fact_type": "promise", "entity_key": "ivan",
                 "quote": "перезвоню завтра в восемь ровно", "confidence": 0.9}],
    )

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1")
    assert "audit_result" in stats
    assert "checks" in stats["audit_result"]
    assert isinstance(stats["audit_critical"], int)


def test_replay_multiple_calls_processed():
    repo = _make_repo()
    _add_user(repo)
    conn = repo._get_conn()
    apply_graph_schema(conn)
    for i in range(3):
        _setup_with_analysis(conn, repo, md5=f"md5_{i}",
            entities=[{"type": "person", "canonical_name": f"P{i}", "normalized_key": f"p{i}",
                       "aliases": [], "attributes": {}}],
            facts=[{"fact_type": "promise", "entity_key": f"p{i}",
                     "quote": f"перезвоню завтра в восемь {i}", "confidence": 0.9}],
        )

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1")
    assert stats["calls_processed"] == 3
    assert stats["entities_count"] == 3


def test_replay_avg_bs_index():
    repo = _make_repo()
    _add_user(repo)
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _setup_with_analysis(conn, repo,
        entities=[{"type": "person", "canonical_name": "Иван", "normalized_key": "ivan",
                    "aliases": [], "attributes": {}}],
        facts=[{"fact_type": "promise", "entity_key": "ivan",
                 "quote": "перезвоню завтра в восемь часов ровно", "confidence": 0.9}],
    )

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1")
    assert stats["avg_bs_index"] is None or isinstance(stats["avg_bs_index"], float)


def test_replay_empty_user_warning():
    repo = _make_repo()
    _add_user(repo)
    conn = repo._get_conn()
    apply_graph_schema(conn)

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u_empty", limit=None)
    assert stats["calls_processed"] == 0
    assert stats["entities_count"] == 0
    assert len(stats["warnings"]) > 0
