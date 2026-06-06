from datetime import datetime
from callprofiler.insight.features.temporal import compute_temporal
from callprofiler.insight.features.base import Tier


def _calls(hours, day="2026-03-02"):  # 2026-03-02 = понедельник
    return [{"call_datetime": f"{day} {h:02d}:00:00", "duration_sec": 60} for h in hours]


def test_evening_and_night_ratio():
    f = compute_temporal(_calls([21, 22, 23, 2]))
    assert f["evening_ratio"].value == 0.75
    assert f["night_ratio"].value == 0.25
    assert f["evening_ratio"].tier == Tier.IMMUNE


def test_empty_calls_returns_empty():
    assert compute_temporal([]) == {}


def test_burstiness_needs_three_calls():
    assert "burstiness" not in compute_temporal(_calls([10, 11]))
    assert "burstiness" in compute_temporal(_calls([10, 11, 12]))


def test_recency_from_reference_now():
    calls = [{"call_datetime": "2026-03-01 10:00:00", "duration_sec": 60}]
    f = compute_temporal(calls, reference_now=datetime(2026, 3, 11, 10))
    assert f["recency_days"].value == 10.0
