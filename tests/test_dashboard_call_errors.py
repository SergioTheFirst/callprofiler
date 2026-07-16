# -*- coding: utf-8 -*-
"""test_dashboard_call_errors.py — M7: calls.error_message surfaced in list + detail."""
from __future__ import annotations

from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.db.repository import Repository


def _seed(tmp_path, error_message="ffmpeg: Файл не найден"):
    db_path = tmp_path / "errs.db"
    repo = Repository(str(db_path))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )
    conn = repo._get_conn()
    cur = conn.execute(
        "INSERT INTO calls(user_id, direction, source_filename, source_md5, status, "
        "error_message) VALUES ('me', 'IN', 'bad.mp3', 'md5err', 'error', ?)",
        (error_message,),
    )
    call_id = cur.lastrowid
    conn.commit()
    repo.close()
    return db_path, call_id


def _reader(db_path):
    r = DashboardDBReader(db_path)
    r.connect()
    return r


def test_get_calls_includes_error_message(tmp_path):
    db_path, call_id = _seed(tmp_path)
    r = _reader(db_path)
    calls = r.get_calls("me")
    r.close()

    row = next(c for c in calls if c["call_id"] == call_id)
    assert row["error_message"] == "ffmpeg: Файл не найден"
    assert row["status"] == "error"


def test_get_call_detail_includes_error_message(tmp_path):
    db_path, call_id = _seed(tmp_path)
    r = _reader(db_path)
    detail = r.get_call_detail(call_id, "me")
    r.close()

    assert detail["error_message"] == "ffmpeg: Файл не найден"


def test_get_calls_error_message_none_for_done_call(tmp_path):
    db_path, call_id = _seed(tmp_path, error_message=None)
    repo = Repository(str(db_path))
    conn = repo._get_conn()
    conn.execute("UPDATE calls SET status='done' WHERE call_id=?", (call_id,))
    conn.commit()
    repo.close()

    r = _reader(db_path)
    calls = r.get_calls("me")
    r.close()

    row = next(c for c in calls if c["call_id"] == call_id)
    assert row["error_message"] is None
    assert row["status"] == "done"
