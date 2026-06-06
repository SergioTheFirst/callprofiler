from callprofiler.insight.features.reciprocity import compute_reciprocity


def test_outgoing_ratio_ignores_unknown_direction():
    calls = [
        {"direction": "OUT", "duration_sec": 100, "call_datetime": "2026-03-01 10:00:00"},
        {"direction": "IN", "duration_sec": 200, "call_datetime": "2026-03-08 10:00:00"},
        {"direction": "UNKNOWN", "duration_sec": 50, "call_datetime": "2026-03-09 10:00:00"},
    ]
    f = compute_reciprocity(calls)
    assert f["outgoing_ratio"].value == 0.5
    assert f["outgoing_ratio"].support_n == 2  # UNKNOWN не считается


def test_total_calls_and_mean_duration():
    calls = [
        {"direction": "OUT", "duration_sec": 100, "call_datetime": "2026-03-01 10:00:00"},
        {"direction": "OUT", "duration_sec": 300, "call_datetime": "2026-03-15 10:00:00"},
    ]
    f = compute_reciprocity(calls)
    assert f["total_calls"].value == 2.0
    assert f["mean_duration_sec"].value == 200.0
    assert round(f["calls_per_week"].value, 2) == 1.0  # 2 звонка за 2 недели


def test_empty_returns_empty():
    assert compute_reciprocity([]) == {}
