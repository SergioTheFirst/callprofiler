# -*- coding: utf-8 -*-
"""
test_replay_metrics.py — tests for GraphReplayer stats and metrics.

Validates:
  1. Builder stats accumulate correctly
  2. rejected + inserted == total invariant
  3. graph_replay_runs row is created
"""

import json
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from callprofiler.db.repository import Repository
from callprofiler.graph.repository import GraphRepository, apply_graph_schema
from callprofiler.graph.builder import GraphBuilder
from callprofiler.graph.replay import GraphReplayer


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


# ── Builder stats tests ──────────────────────────────────────────────────────

def test_builder_stats_reset():
    """Builder stats start at zero after reset."""
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    builder = GraphBuilder(conn)

    stats = builder.get_stats()
    assert stats["facts_total"] == 0
    assert stats["facts_inserted"] == 0
    assert stats["facts_rejected"] == 0


def test_builder_stats_accumulate_single_fact(setup):
    """Stats accumulate when processing single fact."""
    repo, conn, call_id = setup

    payload = {
        "entities": [
            {"normalized_key": "vasya", "canonical_name": "Василий", "type": "person", "aliases": [], "attributes": {}}
        ],
        "relations": [],
        "structured_facts": [
            {"entity_key": "vasya", "fact_type": "promise", "quote": "перезвоню завтра",
             "confidence": 0.9, "value": "завтра", "polarity": None, "intensity": 0.8}
        ]
    }
    _save_v2_analysis(repo, call_id, payload)

    builder = GraphBuilder(conn)
    builder.reset_stats()
    builder.update_from_call(call_id)

    stats = builder.get_stats()
    assert stats["facts_total"] == 1
    assert stats["facts_inserted"] == 1
    assert stats["facts_rejected"] == 0


def test_builder_stats_accumulate_multiple_facts(setup):
    """Stats accumulate across multiple facts in single call."""
    repo, conn, call_id = setup

    payload = {
        "entities": [
            {"normalized_key": "vasya", "canonical_name": "Василий", "type": "person", "aliases": [], "attributes": {}},
            {"normalized_key": "ivan", "canonical_name": "Иван", "type": "person", "aliases": [], "attributes": {}}
        ],
        "relations": [],
        "structured_facts": [
            {"entity_key": "vasya", "fact_type": "promise", "quote": "перезвоню завтра",
             "confidence": 0.9, "value": "завтра", "polarity": None, "intensity": 0.8},
            {"entity_key": "ivan", "fact_type": "claim", "quote": "сделаю на следующей неделе",
             "confidence": 0.85, "value": "неделя", "polarity": None, "intensity": 0.7},
            {"entity_key": "vasya", "fact_type": "debt", "quote": "должен денежку",
             "confidence": 0.88, "value": "деньги", "polarity": None, "intensity": 0.9}
        ]
    }
    _save_v2_analysis(repo, call_id, payload)

    builder = GraphBuilder(conn)
    builder.reset_stats()
    builder.update_from_call(call_id)

    stats = builder.get_stats()
    assert stats["facts_total"] == 3
    assert stats["facts_inserted"] == 3
    assert stats["facts_rejected"] == 0


def test_builder_stats_accumulate_across_calls(setup):
    """Stats accumulate across multiple calls."""
    repo, conn, call_id1 = setup

    # Create second call
    call_id2 = _add_call(repo, md5="def")

    # First call: 2 facts
    payload1 = {
        "entities": [{"normalized_key": "vasya", "canonical_name": "Василий", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "vasya", "fact_type": "promise", "quote": "перезвоню завтра", "confidence": 0.9},
            {"entity_key": "vasya", "fact_type": "claim", "quote": "сделаю потом", "confidence": 0.85}
        ]
    }
    _save_v2_analysis(repo, call_id1, payload1)

    # Second call: 3 facts
    payload2 = {
        "entities": [{"normalized_key": "ivan", "canonical_name": "Иван", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "ivan", "fact_type": "promise", "quote": "завтра позвоню точно", "confidence": 0.95},
            {"entity_key": "ivan", "fact_type": "debt", "quote": "должен тебе", "confidence": 0.88},
            {"entity_key": "ivan", "fact_type": "claim", "quote": "буду работать на тебя", "confidence": 0.80}
        ]
    }
    _save_v2_analysis(repo, call_id2, payload2)

    builder = GraphBuilder(conn)
    builder.reset_stats()
    builder.update_from_call(call_id1)
    builder.update_from_call(call_id2)

    stats = builder.get_stats()
    assert stats["facts_total"] == 5
    assert stats["facts_inserted"] == 5
    assert stats["facts_rejected"] == 0


def test_builder_stats_track_rejections(setup):
    """Stats track facts rejected due to validator (after confidence check)."""
    repo, conn, call_id = setup

    # Create a transcript so validator can check quotes
    transcript = "[me]: перезвоню завтра\n[s2]: спасибо"

    payload = {
        "entities": [{"normalized_key": "vasya", "canonical_name": "Василий", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "vasya", "fact_type": "promise", "quote": "перезвоню завтра",
             "confidence": 0.9},  # High confidence, valid quote
            {"entity_key": "vasya", "fact_type": "claim", "quote": "да",
             "confidence": 0.8}  # High confidence but too short (< 8 chars)
        ]
    }
    _save_v2_analysis(repo, call_id, payload)

    builder = GraphBuilder(conn)
    builder.reset_stats()
    builder.update_from_call(call_id, transcript_text=transcript)

    stats = builder.get_stats()
    assert stats["facts_total"] == 2
    assert stats["facts_inserted"] == 1
    assert stats["facts_rejected"] == 1  # Rejected due to validator (short quote)


# ── Invariant tests (rejected + inserted == total) ────────────────────────

def test_builder_invariant_rejected_plus_inserted_equals_total(setup):
    """Core invariant: rejected + inserted == total."""
    repo, conn, call_id = setup

    # Mixed high/low confidence facts
    payload = {
        "entities": [{"normalized_key": "v", "canonical_name": "V", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "v", "fact_type": "promise", "quote": "перезвоню завтра", "confidence": 0.9},
            {"entity_key": "v", "fact_type": "claim", "quote": "может быть", "confidence": 0.4},
            {"entity_key": "v", "fact_type": "debt", "quote": "должен деньги", "confidence": 0.85},
            {"entity_key": "v", "fact_type": "fact", "quote": "это факт", "confidence": 0.3}
        ]
    }
    _save_v2_analysis(repo, call_id, payload)

    builder = GraphBuilder(conn)
    builder.reset_stats()
    builder.update_from_call(call_id)

    stats = builder.get_stats()
    # INVARIANT: rejected + inserted MUST equal total
    assert stats["facts_rejected"] + stats["facts_inserted"] == stats["facts_total"]


def test_builder_invariant_multiple_calls(setup):
    """Invariant holds across multiple calls."""
    repo, conn, call_id1 = setup
    call_id2 = _add_call(repo, md5="xyz")

    payload1 = {
        "entities": [{"normalized_key": "v1", "canonical_name": "V1", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "v1", "fact_type": "promise", "quote": "завтра позвоню", "confidence": 0.95},
            {"entity_key": "v1", "fact_type": "claim", "quote": "может", "confidence": 0.45}
        ]
    }
    payload2 = {
        "entities": [{"normalized_key": "v2", "canonical_name": "V2", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "v2", "fact_type": "debt", "quote": "должен денег", "confidence": 0.80},
            {"entity_key": "v2", "fact_type": "fact", "quote": "слишком неясно", "confidence": 0.25}
        ]
    }
    _save_v2_analysis(repo, call_id1, payload1)
    _save_v2_analysis(repo, call_id2, payload2)

    builder = GraphBuilder(conn)
    builder.reset_stats()
    builder.update_from_call(call_id1)
    builder.update_from_call(call_id2)

    stats = builder.get_stats()
    assert stats["facts_rejected"] + stats["facts_inserted"] == stats["facts_total"]


# ── graph_replay_runs table tests ────────────────────────────────────────────

def test_replay_creates_graph_replay_runs_row(setup):
    """Replay creates a row in graph_replay_runs table."""
    repo, conn, call_id = setup

    payload = {
        "entities": [{"normalized_key": "v", "canonical_name": "V", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "v", "fact_type": "promise", "quote": "перезвоню завтра", "confidence": 0.9}
        ]
    }
    _save_v2_analysis(repo, call_id, payload)

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1")

    # Check that row was created in graph_replay_runs
    row = conn.execute(
        "SELECT * FROM graph_replay_runs WHERE user_id='u1' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    row_dict = dict(row)
    assert row_dict["user_id"] == "u1"
    assert row_dict["calls_processed"] == 1
    assert row_dict["facts_inserted"] == 1


def test_replay_runs_contains_stats(setup):
    """graph_replay_runs row contains correct stats from builder."""
    repo, conn, call_id = setup

    payload = {
        "entities": [{"normalized_key": "v", "canonical_name": "V", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "v", "fact_type": "promise", "quote": "перезвоню завтра", "confidence": 0.9},
            {"entity_key": "v", "fact_type": "claim", "quote": "может быть", "confidence": 0.4}  # rejected
        ]
    }
    _save_v2_analysis(repo, call_id, payload)

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1")

    # Get the saved row
    row = conn.execute(
        "SELECT * FROM graph_replay_runs WHERE user_id='u1' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    row_dict = dict(row)

    assert row_dict["facts_total"] == stats["facts_total"]
    assert row_dict["facts_inserted"] == stats["facts_inserted"]
    assert row_dict["facts_rejected"] == stats["facts_rejected"]
    assert row_dict["rejection_rate"] == stats["rejection_rate"]


def test_replay_runs_multiple_runs(setup):
    """Multiple replay runs on same data create separate rows."""
    repo, conn, call_id1 = setup
    call_id2 = _add_call(repo, md5="xyz")

    payload1 = {
        "entities": [{"normalized_key": "v1", "canonical_name": "V1", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "v1", "fact_type": "promise", "quote": "перезвоню завтра", "confidence": 0.9}
        ]
    }
    payload2 = {
        "entities": [{"normalized_key": "v2", "canonical_name": "V2", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "v2", "fact_type": "promise", "quote": "обещаю завтра позвонить", "confidence": 0.85}
        ]
    }
    _save_v2_analysis(repo, call_id1, payload1)
    _save_v2_analysis(repo, call_id2, payload2)

    replayer = GraphReplayer(repo, GraphRepository(conn))

    # First replay with call_id1
    stats1 = replayer.replay("u1", limit=1)
    assert stats1["calls_processed"] == 1

    # Second full replay (should process both calls and create a new row)
    # Note: Replay clears graph tables, so second run starts fresh
    stats2 = replayer.replay("u1")
    assert stats2["calls_processed"] == 2

    # Both runs should create rows
    rows = conn.execute(
        "SELECT COUNT(*) FROM graph_replay_runs WHERE user_id='u1'"
    ).fetchone()[0]
    assert rows == 2


def test_replay_rejection_rate_calculation(setup):
    """Rejection rate is correctly calculated and stored."""
    repo, conn, call_id = setup

    # Facts with high confidence but varying lengths for validator checks
    payload = {
        "entities": [{"normalized_key": "v", "canonical_name": "V", "type": "person", "aliases": [], "attributes": {}}],
        "relations": [],
        "structured_facts": [
            {"entity_key": "v", "fact_type": "promise", "quote": "обещаю завтра утром", "confidence": 0.9},  # OK
            {"entity_key": "v", "fact_type": "claim", "quote": "да", "confidence": 0.8},  # Too short (< 8 chars)
            {"entity_key": "v", "fact_type": "debt", "quote": "должен деньги тебе", "confidence": 0.85}  # OK
        ]
    }
    _save_v2_analysis(repo, call_id, payload)

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1")

    # Should have 3 total (all passed confidence), but 1 rejected for short quote
    # Expected: 3 total, 2 inserted, 1 rejected → 1/3 = 0.3333
    assert stats["facts_total"] == 3
    assert stats["facts_inserted"] == 2
    assert stats["facts_rejected"] == 1
    expected_rate = 1 / 3
    assert abs(stats["rejection_rate"] - expected_rate) < 0.01

    # Check it's in the DB row too
    row = conn.execute(
        "SELECT rejection_rate FROM graph_replay_runs WHERE user_id='u1' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert abs(row[0] - expected_rate) < 0.01


# ── Edge cases ───────────────────────────────────────────────────────────────

def test_replay_no_facts_creates_row_with_zeros(setup):
    """Replay with no facts creates row with 0 counts."""
    repo, conn, call_id = setup

    payload = {
        "entities": [],
        "relations": [],
        "structured_facts": []
    }
    _save_v2_analysis(repo, call_id, payload)

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u1")

    # Should still create a row
    row = conn.execute(
        "SELECT * FROM graph_replay_runs WHERE user_id='u1' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    row_dict = dict(row)
    assert row_dict["facts_total"] == 0
    assert row_dict["facts_inserted"] == 0
    assert row_dict["facts_rejected"] == 0


def test_replay_empty_user_warning(setup):
    """Replay on user with no v2 analyses returns warning."""
    repo, conn, _ = setup

    replayer = GraphReplayer(repo, GraphRepository(conn))
    stats = replayer.replay("u_nonexistent")

    assert stats["calls_processed"] == 0
    assert len(stats["warnings"]) > 0
