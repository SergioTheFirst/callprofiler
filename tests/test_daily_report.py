# -*- coding: utf-8 -*-
"""test_daily_report.py — F5: вечерний отчёт дня + случайное воспоминание."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from callprofiler.db.repository import Repository
from callprofiler.deliver.daily_report import build_daily_report
from callprofiler.insight.repository import apply_insight_schema, get_report_state, set_report_state
from callprofiler.pipeline.watcher import FileWatcher

DATE = "2026-07-17"


def _repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def _user(repo: Repository, user_id: str = "me", chat_id: str | None = "555") -> None:
    repo.add_user(
        user_id=user_id, display_name="Test", telegram_chat_id=chat_id,
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/ref.wav",
    )


def _call(repo: Repository, user_id, contact_id, dt: datetime, duration=600,
          status="done", error_message=None) -> int:
    call_id = repo.create_call(
        user_id, contact_id, "incoming", dt, f"f{dt.isoformat()}.mp3", f"md5-{dt.isoformat()}",
        f"/audio/{dt.isoformat()}.mp3",
    )
    repo.update_call_paths(user_id, call_id, f"/norm/{call_id}.wav", duration)
    repo.update_call_status(user_id, call_id, status, error_message)
    return call_id


def _event(conn, user_id, contact_id, call_id, event_type, who, what, deadline=None) -> int:
    cur = conn.execute(
        "INSERT INTO events(user_id, contact_id, call_id, event_type, who, payload, "
        "deadline, status) VALUES (?,?,?,?,?,?,?, 'open')",
        (user_id, contact_id, call_id, event_type, who, what, deadline),
    )
    conn.commit()
    return cur.lastrowid


# ── secciones ────────────────────────────────────────────────────────────

def test_section_today_counts_and_top3():
    repo = _repo()
    _user(repo)
    cid = repo.get_or_create_contact("me", "+70000000001", "Вася")
    _call(repo, "me", cid, datetime(2026, 7, 17, 10, 0), duration=1800)
    _call(repo, "me", cid, datetime(2026, 7, 17, 11, 0), duration=600)

    report = build_daily_report(repo._get_conn(), "me", DATE)
    assert "Сегодня" in report
    assert "2 звонков" in report
    assert "40 мин" in report  # (1800+600)/60


def test_new_obligations_confirmed_shown_rejected_hidden():
    repo = _repo()
    _user(repo)
    cid = repo.get_or_create_contact("me", "+70000000001", "Вася")
    call_id = _call(repo, "me", cid, datetime(2026, 7, 17, 10, 0))
    conn = repo._get_conn()
    e_confirmed = _event(conn, "me", cid, call_id, "promise", "OWNER", "перезвонить", "2026-07-20")
    e_rejected = _event(conn, "me", cid, call_id, "promise", "OTHER", "прислать смету", "2026-07-21")

    apply_insight_schema(conn)
    conn.execute(
        "INSERT INTO fact_feedback(user_id,item_kind,item_key,verdict) VALUES (?,?,?,?)",
        ("me", "event", str(e_confirmed), "confirmed"),
    )
    conn.execute(
        "INSERT INTO fact_feedback(user_id,item_kind,item_key,verdict) VALUES (?,?,?,?)",
        ("me", "event", str(e_rejected), "rejected"),
    )
    conn.commit()

    report = build_daily_report(conn, "me", DATE)
    assert "Новое" in report
    assert "✓" in report
    assert "перезвонить" in report
    assert "прислать смету" not in report


def test_tomorrow_shows_reminder_and_overdue():
    repo = _repo()
    _user(repo)
    cid = repo.get_or_create_contact("me", "+70000000001", "Вася")
    call_id = _call(repo, "me", cid, datetime(2026, 7, 10, 10, 0))
    conn = repo._get_conn()
    _event(conn, "me", cid, call_id, "debt", "OTHER", "вернуть долг", "2026-07-15")  # overdue

    apply_insight_schema(conn)
    conn.execute(
        "INSERT INTO reminders(user_id,item_kind,item_key,text,due_at,chat_id) "
        "VALUES ('me','promise','999','напомнить про счёт','2026-07-18 10:00:00',555)"
    )
    conn.commit()

    report = build_daily_report(conn, "me", DATE)
    assert "Завтра" in report
    assert "напомнить про счёт" in report
    assert "вернуть долг" in report
    assert "просрочено" in report


def test_errors_section_lists_error_calls():
    repo = _repo()
    _user(repo)
    cid = repo.get_or_create_contact("me", "+70000000001", "Вася")
    _call(repo, "me", cid, datetime(2026, 7, 17, 9, 0), status="error",
          error_message="ffmpeg упал с кодом 1")

    report = build_daily_report(repo._get_conn(), "me", DATE)
    assert "Ошибки" in report
    assert "ffmpeg упал" in report


def test_memory_only_older_than_180_days():
    repo = _repo()
    _user(repo)
    cid = repo.get_or_create_contact("me", "+70000000001", "Вася")
    conn = repo._get_conn()

    recent_call = _call(repo, "me", cid, datetime(2026, 5, 1, 10, 0))  # ~77 days before DATE
    _event(conn, "me", cid, recent_call, "fact", "OTHER", "недавний факт")
    conn.execute(
        "UPDATE events SET source_quote = ? WHERE call_id = ?",
        ("недавняя цитата", recent_call),
    )
    conn.commit()

    report = build_daily_report(conn, "me", DATE)
    assert "Воспоминание" not in report

    old_call = _call(repo, "me", cid, datetime(2025, 1, 1, 10, 0))  # >180 days before DATE
    old_event = _event(conn, "me", cid, old_call, "fact", "OTHER", "старый факт")
    conn.execute(
        "UPDATE events SET source_quote = ? WHERE id = ?",
        ("старая цитата", old_event),
    )
    conn.commit()

    report2 = build_daily_report(conn, "me", DATE)
    assert "Воспоминание" in report2
    assert "старая цитата" in report2
    assert "недавняя цитата" not in report2


def test_report_capped_at_4096_chars(monkeypatch):
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()

    monkeypatch.setattr(
        "callprofiler.deliver.daily_report._section_today", lambda *a, **k: "X" * 5000
    )
    report = build_daily_report(conn, "me", DATE)
    assert len(report) <= 4096
    assert report.endswith("…")


# ── report_state ─────────────────────────────────────────────────────────

def test_report_state_roundtrip():
    repo = _repo()
    conn = repo._get_conn()
    assert get_report_state(conn, "me") is None
    set_report_state(conn, "me", DATE)
    assert get_report_state(conn, "me") == DATE


# ── watcher trigger ──────────────────────────────────────────────────────

def _watcher(repo: Repository) -> FileWatcher:
    cfg = MagicMock()
    return FileWatcher(cfg, repo, MagicMock(), MagicMock())


def test_watcher_skips_before_2100():
    repo = _repo()
    _user(repo)
    watcher = _watcher(repo)
    fake_now = datetime(2026, 7, 17, 20, 59)

    with patch("callprofiler.pipeline.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now.astimezone()
        with patch("callprofiler.deliver.telegram_sender.send_telegram_message") as sender:
            watcher._maybe_send_daily_report()
    sender.assert_not_called()


def test_watcher_sends_once_and_skips_second_tick():
    repo = _repo()
    _user(repo)
    watcher = _watcher(repo)
    fake_now = datetime(2026, 7, 17, 21, 5).astimezone()

    with patch("callprofiler.pipeline.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        with patch(
            "callprofiler.deliver.telegram_sender.send_telegram_message", return_value=True
        ) as sender:
            watcher._maybe_send_daily_report()
            watcher._maybe_send_daily_report()

    sender.assert_called_once()
    assert get_report_state(repo._get_conn(), "me") == fake_now.date().isoformat()


def test_watcher_no_chat_id_skips_send():
    repo = _repo()
    _user(repo, chat_id=None)
    watcher = _watcher(repo)
    fake_now = datetime(2026, 7, 17, 21, 5).astimezone()

    with patch("callprofiler.pipeline.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        with patch("callprofiler.deliver.telegram_sender.send_telegram_message") as sender:
            watcher._maybe_send_daily_report()

    sender.assert_not_called()


def test_watcher_send_failure_does_not_advance_state():
    repo = _repo()
    _user(repo)
    watcher = _watcher(repo)
    fake_now = datetime(2026, 7, 17, 21, 5).astimezone()

    with patch("callprofiler.pipeline.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        with patch(
            "callprofiler.deliver.telegram_sender.send_telegram_message", return_value=False
        ) as sender:
            watcher._maybe_send_daily_report()
            watcher._maybe_send_daily_report()  # retried, still failing

    assert sender.call_count == 2
    assert get_report_state(repo._get_conn(), "me") is None


def test_watcher_build_failure_is_non_fatal(monkeypatch):
    repo = _repo()
    _user(repo)
    watcher = _watcher(repo)
    fake_now = datetime(2026, 7, 17, 21, 5).astimezone()

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr("callprofiler.deliver.daily_report.build_daily_report", _boom)
    with patch("callprofiler.pipeline.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        watcher._maybe_send_daily_report()  # не должно бросить

    assert get_report_state(repo._get_conn(), "me") is None
