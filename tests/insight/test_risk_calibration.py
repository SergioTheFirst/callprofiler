# -*- coding: utf-8 -*-
"""test_risk_calibration.py — A4: перцентильные пороги risk_score, отдельно от BS-index."""
from __future__ import annotations

from callprofiler.db.repository import Repository
from callprofiler.insight.risk_calibration import (
    calibrate_risk, get_latest_risk_thresholds, risk_emoji,
)


def _db(tmp_path):
    repo = Repository(str(tmp_path / "risk.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    return repo, repo._get_conn()


def _call_with_analysis(conn, user_id, risk_score, feedback=None, i=0):
    cur = conn.execute(
        "INSERT INTO calls(user_id, direction, call_datetime, source_filename, "
        "source_md5, status, duration_sec) VALUES (?,?,?,?,?,?,?)",
        (user_id, "IN", f"2026-01-{(i % 28) + 1:02d}T10:00:00", f"f{i}.mp3",
         f"md5{i}", "done", 60),
    )
    call_id = cur.lastrowid
    conn.execute(
        "INSERT INTO analyses(call_id, prompt_version, risk_score, feedback) VALUES (?,?,?,?)",
        (call_id, "v001", risk_score, feedback),
    )
    return call_id


def test_too_few_analyses_no_write(tmp_path):
    repo, conn = _db(tmp_path)
    for i in range(10):
        _call_with_analysis(conn, "me", risk_score=50, i=i)
    conn.commit()

    res = calibrate_risk(conn, "me")
    assert res["ok"] is False
    assert res["reason"] == "too_few"
    n = conn.execute("SELECT COUNT(*) FROM risk_thresholds").fetchone()[0]
    assert n == 0
    repo.close()


def test_calibrate_computes_percentiles(tmp_path):
    repo, conn = _db(tmp_path)
    for i, score in enumerate(range(1, 101)):  # 1..100, 100 values
        _call_with_analysis(conn, "me", risk_score=score, i=i)
    conn.commit()

    res = calibrate_risk(conn, "me")
    assert res["ok"] is True
    assert res["count"] == 100
    assert 45 <= res["green_max"] <= 55  # ~p50
    assert 80 <= res["yellow_max"] <= 90  # ~p85
    assert res["green_max"] < res["yellow_max"]
    repo.close()


def test_calibrate_excludes_inaccurate_feedback_and_zero_risk(tmp_path):
    repo, conn = _db(tmp_path)
    for i in range(60):
        _call_with_analysis(conn, "me", risk_score=50, i=i)
    # шум, который НЕ должен попасть в выборку
    for i in range(60, 70):
        _call_with_analysis(conn, "me", risk_score=99, feedback="inaccurate", i=i)
    for i in range(70, 80):
        _call_with_analysis(conn, "me", risk_score=0, i=i)  # заглушка коротких звонков
    conn.commit()

    res = calibrate_risk(conn, "me")
    assert res["ok"] is True
    assert res["count"] == 60  # только чистые 50-е
    repo.close()


def test_calibrate_respects_user_isolation(tmp_path):
    repo, conn = _db(tmp_path)
    repo.add_user(user_id="other", display_name="O", telegram_chat_id="1",
                   incoming_dir="/tmp/in2", sync_dir="/tmp/sync2", ref_audio="/tmp/r2.wav")
    for i in range(60):
        _call_with_analysis(conn, "me", risk_score=50, i=i)
    for i in range(60, 120):
        _call_with_analysis(conn, "other", risk_score=90, i=i)
    conn.commit()

    res = calibrate_risk(conn, "me")
    assert res["ok"] is True
    assert res["count"] == 60
    repo.close()


def test_get_latest_thresholds_none_before_calibration(tmp_path):
    repo, conn = _db(tmp_path)
    assert get_latest_risk_thresholds(conn, "me") is None
    repo.close()


def test_get_latest_thresholds_after_calibration(tmp_path):
    repo, conn = _db(tmp_path)
    for i in range(60):
        _call_with_analysis(conn, "me", risk_score=50, i=i)
    conn.commit()
    calibrate_risk(conn, "me")

    thresholds = get_latest_risk_thresholds(conn, "me")
    assert thresholds is not None
    assert thresholds["green_max"] == 50.0
    assert thresholds["yellow_max"] == 50.0
    repo.close()


def test_risk_emoji_fallback_matches_old_thresholds():
    assert risk_emoji(10, None) == "🟢"
    assert risk_emoji(50, None) == "🟡"
    assert risk_emoji(90, None) == "🔴"
    assert risk_emoji(30, None) == "🟡"  # boundary: >=30 → yellow
    assert risk_emoji(70, None) == "🔴"  # boundary: >=70 → red


def test_risk_emoji_uses_calibrated_thresholds():
    thresholds = {"green_max": 5.0, "yellow_max": 8.0}
    assert risk_emoji(3, thresholds) == "🟢"
    assert risk_emoji(6, thresholds) == "🟡"
    assert risk_emoji(9, thresholds) == "🔴"
