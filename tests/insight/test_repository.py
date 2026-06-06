import sqlite3
from callprofiler.insight.repository import apply_insight_schema


def _tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def test_apply_insight_schema_creates_tables():
    conn = sqlite3.connect(":memory:")
    apply_insight_schema(conn)
    t = _tables(conn)
    assert {"contact_features", "archetype_models", "contact_archetypes"} <= t


def test_apply_insight_schema_idempotent():
    conn = sqlite3.connect(":memory:")
    apply_insight_schema(conn)
    apply_insight_schema(conn)  # second call must not raise
    assert "contact_features" in _tables(conn)
