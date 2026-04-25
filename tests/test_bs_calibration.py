# -*- coding: utf-8 -*-
"""
test_bs_calibration.py — tests for BS-index calibration and thresholding.

Uses in-memory SQLite. Tests percentile calculation and label assignment.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from callprofiler.db.repository import Repository
from callprofiler.graph.repository import GraphRepository, apply_graph_schema
from callprofiler.graph.calibration import BSCalibrator


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


@pytest.fixture
def setup():
    repo = _make_repo()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    _add_user(repo)
    return repo, conn


# ── calibration tests ────────────────────────────────────────────────────────

def test_calibrator_analyze_empty_user(setup):
    """Analyze on user with no entities returns ok=False."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    result = calibrator.analyze("u1")

    assert result["ok"] is False
    assert result["entity_count"] == 0
    assert result["thresholds"] is None


def test_calibrator_analyze_few_entities(setup):
    """Analyze with < 3 entities returns ok=False."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create 2 entities
    eid1 = grepo.upsert_entity("u1", "person", "Person1", "person1")
    eid2 = grepo.upsert_entity("u1", "person", "Person2", "person2")
    grepo.upsert_entity_metrics(eid1, "u1", total_calls=5, total_promises=2, bs_index=20.0)
    grepo.upsert_entity_metrics(eid2, "u1", total_calls=3, total_promises=1, bs_index=15.0)

    result = calibrator.analyze("u1")

    assert result["ok"] is False
    assert result["entity_count"] == 2


def test_calibrator_analyze_sufficient_entities(setup):
    """Analyze with >= 3 entities returns ok=True and thresholds."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create 5 entities with varied BS-index
    scores = [10.0, 20.0, 30.0, 40.0, 50.0]
    for i, bs in enumerate(scores):
        eid = grepo.upsert_entity("u1", "person", f"Person{i}", f"person{i}")
        grepo.upsert_entity_metrics(eid, "u1", total_calls=5, total_promises=2, bs_index=bs)

    result = calibrator.analyze("u1")

    assert result["ok"] is True
    assert result["entity_count"] == 5
    assert result["thresholds"] is not None
    assert "reliable_max" in result["thresholds"]
    assert "noisy_max" in result["thresholds"]
    assert "risky_max" in result["thresholds"]
    assert "unreliable_max" in result["thresholds"]


def test_calibrator_analyze_computes_percentiles(setup):
    """Analyze computes correct percentiles from scores."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create entities with known BS-index values
    # 10, 20, 30, 40, 50, 60, 70, 80, 90, 100 (10 entities, sorted)
    # With linear interpolation and n=10:
    # p25: rank = 0.25 * 9 = 2.25 → 30 + 0.25*(40-30) = 32.5
    # p50: rank = 0.5 * 9 = 4.5 → 50 + 0.5*(60-50) = 55
    # p75: rank = 0.75 * 9 = 6.75 → 70 + 0.75*(80-70) = 77.5
    # p90: rank = 0.9 * 9 = 8.1 → 90 + 0.1*(100-90) = 91
    for i in range(10):
        bs = (i + 1) * 10.0
        eid = grepo.upsert_entity("u1", "person", f"E{i}", f"e{i}")
        grepo.upsert_entity_metrics(eid, "u1", total_calls=5, total_promises=2, bs_index=bs)

    result = calibrator.analyze("u1")

    assert result["ok"] is True
    percentiles = result["percentiles"]
    # p25 should be ~32.5
    assert 30.0 <= percentiles["p25"] <= 35.0
    # p50 should be ~55 (median)
    assert 50.0 <= percentiles["p50"] <= 60.0
    # p75 should be ~77.5
    assert 75.0 <= percentiles["p75"] <= 80.0
    # p90 should be ~91
    assert 85.0 <= percentiles["p90"] <= 95.0


def test_calibrator_analyze_saves_to_db(setup):
    """Analyze saves thresholds to bs_thresholds table."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create entities
    for i in range(3):
        eid = grepo.upsert_entity("u1", "person", f"E{i}", f"e{i}")
        grepo.upsert_entity_metrics(eid, "u1", total_calls=5, total_promises=2, bs_index=float(i * 20))

    result = calibrator.analyze("u1")

    assert result["ok"] is True

    # Verify row was saved
    saved = grepo.get_latest_bs_thresholds("u1")
    assert saved is not None
    assert saved["user_id"] == "u1"
    assert saved["entity_count"] == 3


def test_calibrator_get_label_uncalibrated(setup):
    """Get label without thresholds returns 'uncalibrated' with white circle."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    label, emoji = calibrator.get_label(50.0, "u1")

    assert label == "uncalibrated"
    assert emoji == "⚪"


def test_calibrator_get_label_reliable(setup):
    """BS-index <= p25 returns 'reliable' with green circle."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create entities to calibrate: 0, 10, 20, 30, 40, 50
    for i in range(6):
        eid = grepo.upsert_entity("u1", "person", f"E{i}", f"e{i}")
        grepo.upsert_entity_metrics(eid, "u1", total_calls=5, total_promises=2, bs_index=float(i * 10))

    calibrator.analyze("u1")

    # bs_index=5.0 should be < p25 (~12.5)
    label, emoji = calibrator.get_label(5.0, "u1")
    assert label == "reliable"
    assert emoji == "🟢"


def test_calibrator_get_label_noisy(setup):
    """BS-index between p25 and p50 returns 'noisy' with yellow circle."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create entities: 0, 10, 20, 30, 40, 50
    for i in range(6):
        eid = grepo.upsert_entity("u1", "person", f"E{i}", f"e{i}")
        grepo.upsert_entity_metrics(eid, "u1", total_calls=5, total_promises=2, bs_index=float(i * 10))

    calibrator.analyze("u1")

    # bs_index=20.0 should be between p25 (~12.5) and p50 (~25)
    label, emoji = calibrator.get_label(20.0, "u1")
    assert label == "noisy"
    assert emoji == "🟡"


def test_calibrator_get_label_risky(setup):
    """BS-index between p50 and p75 returns 'risky' with red circle."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create entities: 0, 10, 20, 30, 40, 50
    for i in range(6):
        eid = grepo.upsert_entity("u1", "person", f"E{i}", f"e{i}")
        grepo.upsert_entity_metrics(eid, "u1", total_calls=5, total_promises=2, bs_index=float(i * 10))

    calibrator.analyze("u1")

    # bs_index=35.0 should be between p50 (~25) and p75 (~37.5)
    label, emoji = calibrator.get_label(35.0, "u1")
    assert label == "risky"
    assert emoji == "🔴"


def test_calibrator_get_label_unreliable(setup):
    """BS-index between p75 and p90 returns 'unreliable' with red circle."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create entities: 0, 10, 20, 30, 40, 50
    for i in range(6):
        eid = grepo.upsert_entity("u1", "person", f"E{i}", f"e{i}")
        grepo.upsert_entity_metrics(eid, "u1", total_calls=5, total_promises=2, bs_index=float(i * 10))

    calibrator.analyze("u1")

    # bs_index=42.0 should be between p75 (~37.5) and p90 (~45)
    label, emoji = calibrator.get_label(42.0, "u1")
    assert label == "unreliable"
    assert emoji == "🔴"


def test_calibrator_get_label_critical(setup):
    """BS-index >= p90 returns 'critical' with black circle."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create entities: 0, 10, 20, 30, 40, 50
    for i in range(6):
        eid = grepo.upsert_entity("u1", "person", f"E{i}", f"e{i}")
        grepo.upsert_entity_metrics(eid, "u1", total_calls=5, total_promises=2, bs_index=float(i * 10))

    calibrator.analyze("u1")

    # bs_index=48.0 should be >= p90 (~45)
    label, emoji = calibrator.get_label(48.0, "u1")
    assert label == "critical"
    assert emoji == "⚫"


def test_calibrator_percentile_calculation():
    """Test static percentile method."""
    scores = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

    p25 = BSCalibrator._percentile(scores, 25)
    p50 = BSCalibrator._percentile(scores, 50)
    p75 = BSCalibrator._percentile(scores, 75)

    # With linear interpolation on n=10:
    # p25: rank = 2.25 → 30 + 0.25*10 = 32.5
    # p50: rank = 4.5 → 50 + 0.5*10 = 55
    # p75: rank = 6.75 → 70 + 0.75*10 = 77.5
    assert 30.0 <= p25 <= 35.0
    assert 50.0 <= p50 <= 60.0
    assert 75.0 <= p75 <= 80.0


def test_calibrator_percentile_empty_data():
    """Percentile of empty list returns 0.0."""
    p = BSCalibrator._percentile([], 50)
    assert p == 0.0


def test_calibrator_percentile_single_value():
    """Percentile of single value returns that value."""
    p = BSCalibrator._percentile([42.0], 50)
    assert p == 42.0


def test_calibrator_analyze_filters_by_min_calls(setup):
    """Analyze filters entities with total_calls < min_calls."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create 2 entities: one with calls >= 3, one with calls < 3
    eid1 = grepo.upsert_entity("u1", "person", "Good", "good")
    eid2 = grepo.upsert_entity("u1", "person", "Bad", "bad")
    grepo.upsert_entity_metrics(eid1, "u1", total_calls=5, total_promises=2, bs_index=20.0)
    grepo.upsert_entity_metrics(eid2, "u1", total_calls=1, total_promises=1, bs_index=50.0)

    # Need 3+ entities with min_calls >= 3
    eid3 = grepo.upsert_entity("u1", "person", "Good2", "good2")
    grepo.upsert_entity_metrics(eid3, "u1", total_calls=4, total_promises=1, bs_index=30.0)

    result = calibrator.analyze("u1", min_calls=3)

    # Should only count entities with total_calls >= 3 (eid1 and eid3)
    assert result["entity_count"] == 2
    assert result["ok"] is False  # Only 2 entities, need >= 3


def test_calibrator_analyze_filters_by_min_promises(setup):
    """Analyze filters entities with total_promises < min_promises."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create entities with varying promises
    for i in range(3):
        eid = grepo.upsert_entity("u1", "person", f"E{i}", f"e{i}")
        promises = i + 1  # 1, 2, 3
        grepo.upsert_entity_metrics(eid, "u1", total_calls=5, total_promises=promises, bs_index=float(i * 20))

    result = calibrator.analyze("u1", min_promises=2)

    # Should only count entities with total_promises >= 2 (E1 and E2)
    assert result["entity_count"] == 2
    assert result["ok"] is False  # Only 2 entities, need >= 3


def test_calibrator_analyze_excludes_owner(setup):
    """Analyze excludes owner entity even if it has enough metrics."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create owner entity
    owner_id = grepo.upsert_entity("u1", "person", "Owner", "owner")
    conn.execute("UPDATE entities SET is_owner=1 WHERE id=?", (owner_id,))
    conn.commit()

    # Create 2 regular entities
    for i in range(2):
        eid = grepo.upsert_entity("u1", "person", f"E{i}", f"e{i}")
        grepo.upsert_entity_metrics(eid, "u1", total_calls=5, total_promises=2, bs_index=float(i * 20))

    # Add metrics to owner (should be ignored)
    grepo.upsert_entity_metrics(owner_id, "u1", total_calls=5, total_promises=2, bs_index=50.0)

    result = calibrator.analyze("u1")

    # Should only count non-owner entities (2)
    assert result["entity_count"] == 2
    assert result["ok"] is False  # Only 2 entities, need >= 3


def test_calibrator_analyze_excludes_archived(setup):
    """Analyze excludes archived entities."""
    _, conn = setup
    grepo = GraphRepository(conn)
    calibrator = BSCalibrator(grepo)

    # Create 2 regular entities
    eid1 = grepo.upsert_entity("u1", "person", "E1", "e1")
    eid2 = grepo.upsert_entity("u1", "person", "E2", "e2")
    grepo.upsert_entity_metrics(eid1, "u1", total_calls=5, total_promises=2, bs_index=20.0)
    grepo.upsert_entity_metrics(eid2, "u1", total_calls=5, total_promises=2, bs_index=30.0)

    # Archive one
    conn.execute("UPDATE entities SET archived=1 WHERE id=?", (eid2,))
    conn.commit()

    result = calibrator.analyze("u1")

    # Should only count non-archived (1)
    assert result["entity_count"] == 1
    assert result["ok"] is False  # Only 1 entity, need >= 3
