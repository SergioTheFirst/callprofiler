from datetime import datetime, timedelta
from callprofiler.insight.features.trajectory import compute_trajectory


def _weekly(n_weeks, per_week, start="2026-01-05"):
    base = datetime.fromisoformat(start + " 10:00:00")
    calls = []
    for w in range(n_weeks):
        for _ in range(per_week):
            calls.append({"call_datetime": (base + timedelta(weeks=w)).strftime("%Y-%m-%d %H:%M:%S")})
    return calls


def test_too_few_calls_returns_empty():
    assert compute_trajectory(_weekly(1, 2)) == {}


def test_accelerating_has_positive_slope():
    base = datetime.fromisoformat("2026-01-05 10:00:00")
    counts = [1, 1, 2, 3, 5]  # ускорение
    calls = []
    for w, c in enumerate(counts):
        for _ in range(c):
            calls.append({"call_datetime": (base + timedelta(weeks=w)).strftime("%Y-%m-%d %H:%M:%S")})
    f = compute_trajectory(calls)
    assert f["cadence_slope"].value > 0
