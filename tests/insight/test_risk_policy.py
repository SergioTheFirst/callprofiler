# -*- coding: utf-8 -*-
"""Test risk_band and risk_emoji unified risk policy."""

import sqlite3
import tempfile
from pathlib import Path

from callprofiler.insight.risk_calibration import (
    FALLBACK_GREEN_MAX,
    FALLBACK_YELLOW_MAX,
    RISK_POLICY_VERSION,
    apply_risk_schema,
    calibrate_risk,
    risk_band,
    risk_emoji,
)


def test_risk_policy_version():
    """Verify RISK_POLICY_VERSION constant exists."""
    assert RISK_POLICY_VERSION == "risk-v1"


def test_risk_band_with_none_score():
    """risk_band(None, ...) returns 'none'."""
    assert risk_band(None, None) == "none"
    assert risk_band(None, {"green_max": 30, "yellow_max": 70}) == "none"


def test_risk_band_fallback_thresholds():
    """risk_band uses fallback 30/70 when thresholds=None."""
    assert risk_band(0, None) == "low"
    assert risk_band(29, None) == "low"
    assert risk_band(30, None) == "mid"
    assert risk_band(69, None) == "mid"
    assert risk_band(70, None) == "high"
    assert risk_band(71, None) == "high"
    assert risk_band(100, None) == "high"


def test_risk_band_custom_thresholds():
    """risk_band respects custom thresholds."""
    thresholds = {"green_max": 40, "yellow_max": 80}
    assert risk_band(39, thresholds) == "low"
    assert risk_band(40, thresholds) == "mid"
    assert risk_band(79, thresholds) == "mid"
    assert risk_band(80, thresholds) == "high"
    assert risk_band(81, thresholds) == "high"


def test_risk_emoji_with_none():
    """risk_emoji returns ⚪ for 'none' band."""
    assert risk_emoji(None, None) == "⚪"


def test_risk_emoji_fallback():
    """risk_emoji uses fallback 30/70 policy."""
    assert risk_emoji(0, None) == "🟢"
    assert risk_emoji(29, None) == "🟢"
    assert risk_emoji(30, None) == "🟡"
    assert risk_emoji(69, None) == "🟡"
    assert risk_emoji(70, None) == "🔴"
    assert risk_emoji(71, None) == "🔴"
    assert risk_emoji(100, None) == "🔴"


def test_risk_emoji_custom_thresholds():
    """risk_emoji uses custom thresholds."""
    thresholds = {"green_max": 25, "yellow_max": 75}
    assert risk_emoji(24, thresholds) == "🟢"
    assert risk_emoji(25, thresholds) == "🟡"
    assert risk_emoji(74, thresholds) == "🟡"
    assert risk_emoji(76, thresholds) == "🔴"


def test_calibrate_risk_too_few():
    """calibrate_risk returns error when < min_analyses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        try:
            # Create minimal schema
            conn.execute(
                "CREATE TABLE IF NOT EXISTS calls (call_id INTEGER PRIMARY KEY, user_id TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS analyses (call_id INTEGER, risk_score REAL, feedback TEXT)"
            )
            conn.commit()

            # Add only 2 analyses (below min of 50)
            conn.execute("INSERT INTO calls VALUES (1, 'test_user')")
            conn.execute("INSERT INTO analyses VALUES (1, 50.0, NULL)")
            conn.commit()

            result = calibrate_risk(conn, "test_user")
            assert result["ok"] is False
            assert result["reason"] == "too_few"
            assert result["count"] == 1
        finally:
            conn.close()


def test_calibrate_risk_success():
    """calibrate_risk calculates percentiles and stores them."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        try:
            # Create schema
            conn.execute(
                "CREATE TABLE IF NOT EXISTS calls (call_id INTEGER PRIMARY KEY, user_id TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS analyses (call_id INTEGER, risk_score REAL, feedback TEXT)"
            )
            conn.commit()

            # Insert 100 analyses with scores 1-100 (risk_score > 0 is required)
            for i in range(1, 101):
                conn.execute("INSERT INTO calls VALUES (?, ?)", (i, "test_user"))
                conn.execute("INSERT INTO analyses VALUES (?, ?, ?)", (i, float(i), None))
            conn.commit()

            result = calibrate_risk(conn, "test_user", min_analyses=50)
            assert result["ok"] is True
            assert result["count"] == 100
            # p50 of 1..100 should be ~50.5, p85 should be ~85.5
            assert 48 < result["green_max"] < 53
            assert 83 < result["yellow_max"] < 88

            # Verify stored in table
            row = conn.execute(
                "SELECT * FROM risk_thresholds WHERE user_id = 'test_user'"
            ).fetchone()
            assert row is not None
            assert row["green_max"] == result["green_max"]
            assert row["yellow_max"] == result["yellow_max"]
        finally:
            conn.close()
