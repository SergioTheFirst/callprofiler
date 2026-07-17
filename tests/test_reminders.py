# -*- coding: utf-8 -*-
"""test_reminders.py — F2: напоминания по подтверждённым обещаниям."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from callprofiler.db.repository import Repository
from callprofiler.deliver.reminders import (
    MAX_CONSECUTIVE_ERRORS,
    close_item,
    create_reminder,
    due_reminders,
    mark_error,
    mark_sent,
    parse_due_ru,
    snooze_reminder,
)
from callprofiler.insight.repository import apply_insight_schema

TZ = timezone(timedelta(hours=3))


# ── parse_due_ru ────────────────────────────────────────────────────────

def test_today():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)  # Wednesday
    assert parse_due_ru("сегодня", now) == datetime(2020, 6, 10, 10, 0, tzinfo=TZ)


def test_tomorrow():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)
    assert parse_due_ru("завтра", now) == datetime(2020, 6, 11, 10, 0, tzinfo=TZ)


def test_day_after_tomorrow():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)
    assert parse_due_ru("послезавтра", now) == datetime(2020, 6, 12, 10, 0, tzinfo=TZ)


def test_weekday_in_future_this_week():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)  # Wednesday
    assert parse_due_ru("в пятницу", now) == datetime(2020, 6, 12, 10, 0, tzinfo=TZ)


def test_weekday_wraps_to_next_week_when_earlier_in_week():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)  # Wednesday
    assert parse_due_ru("в понедельник", now) == datetime(2020, 6, 15, 10, 0, tzinfo=TZ)


def test_weekday_today_means_next_week_not_today():
    """«ближайший будущий» — сегодняшний день недели не считается «будущим»."""
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)  # Wednesday
    assert parse_due_ru("в среду", now) == datetime(2020, 6, 17, 10, 0, tzinfo=TZ)


def test_vo_prefix_for_tuesday():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)  # Wednesday
    assert parse_due_ru("во вторник", now) == datetime(2020, 6, 16, 10, 0, tzinfo=TZ)


def test_through_n_days():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)
    assert parse_due_ru("через 3 дня", now) == datetime(2020, 6, 13, 10, 0, tzinfo=TZ)
    assert parse_due_ru("через 10 дней", now) == datetime(2020, 6, 20, 10, 0, tzinfo=TZ)


def test_dd_mm_future_this_year():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)
    assert parse_due_ru("15.07", now) == datetime(2020, 7, 15, 10, 0, tzinfo=TZ)


def test_dd_mm_already_passed_rolls_to_next_year():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)
    assert parse_due_ru("01.01", now) == datetime(2021, 1, 1, 10, 0, tzinfo=TZ)


def test_dd_mm_yyyy_exact():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)
    assert parse_due_ru("15.07.2030", now) == datetime(2030, 7, 15, 10, 0, tzinfo=TZ)


def test_time_tail_hour_and_minute():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)
    assert parse_due_ru("завтра в 15:30", now) == datetime(2020, 6, 11, 15, 30, tzinfo=TZ)


def test_time_tail_hour_only():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)
    assert parse_due_ru("15.07 в 9", now) == datetime(2020, 7, 15, 9, 0, tzinfo=TZ)


@pytest.mark.parametrize("text", [
    "какая-то фигня", "", "в 15:30", "в 25:00 завтра", "31.02", "через дней",
    "в понедельникы", "завтра завтра",
])
def test_garbage_returns_none(text):
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)
    assert parse_due_ru(text, now) is None


def test_none_and_empty_input():
    now = datetime(2020, 6, 10, 9, 0, tzinfo=TZ)
    assert parse_due_ru(None, now) is None
    assert parse_due_ru("", now) is None


def test_naive_now_gets_localized():
    now = datetime(2020, 6, 10, 9, 0)  # без tzinfo
    result = parse_due_ru("завтра", now)
    assert result is not None
    assert result.tzinfo is not None


# ── repository helpers ────────────────────────────────────────────────────

@pytest.fixture
def repo(tmp_path):
    db = tmp_path / "reminders.db"
    r = Repository(str(db))
    r.init_db()
    r.add_user(user_id="me", display_name="T", telegram_chat_id="555",
               incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    conn = r._get_conn()
    apply_insight_schema(conn)
    conn.execute(
        "INSERT INTO calls(call_id, user_id, call_datetime, source_filename, "
        "source_md5, status) VALUES (1, 'me', '2020-06-01', 'a.mp3', 'md5a', 'done')"
    )
    conn.execute(
        "INSERT INTO events(id, user_id, call_id, event_type, who, payload, "
        "deadline, status) VALUES (9, 'me', 1, 'promise', 'OWNER', 'вернуть долг', "
        "'2020-06-15', 'open')"
    )
    conn.commit()
    yield r
    r.close()


def test_create_and_due_reminders(repo):
    conn = repo._get_conn()
    past = datetime(2020, 1, 1, 10, 0, tzinfo=TZ)
    rid = create_reminder(conn, "me", item_kind="event", item_key="9",
                           text="обещал вернуть долг", due_at=past, chat_id=555)
    assert isinstance(rid, int)

    due = due_reminders(conn, datetime(2020, 1, 2, tzinfo=TZ))
    assert len(due) == 1
    assert due[0]["reminder_id"] == rid
    assert due[0]["text"] == "обещал вернуть долг"


def test_due_reminders_excludes_future(repo):
    conn = repo._get_conn()
    future = datetime(2099, 1, 1, 10, 0, tzinfo=TZ)
    create_reminder(conn, "me", item_kind="event", item_key="9", text="x",
                     due_at=future, chat_id=555)
    assert due_reminders(conn, datetime(2020, 1, 1, tzinfo=TZ)) == []


def test_due_reminders_excludes_already_sent(repo):
    conn = repo._get_conn()
    past = datetime(2020, 1, 1, 10, 0, tzinfo=TZ)
    rid = create_reminder(conn, "me", item_kind="event", item_key="9", text="x",
                           due_at=past, chat_id=555)
    mark_sent(conn, rid)
    assert due_reminders(conn, datetime(2020, 1, 2, tzinfo=TZ)) == []


def test_due_reminders_excludes_disabled(repo):
    conn = repo._get_conn()
    past = datetime(2020, 1, 1, 10, 0, tzinfo=TZ)
    rid = create_reminder(conn, "me", item_kind="event", item_key="9", text="x",
                           due_at=past, chat_id=555)
    conn.execute("UPDATE reminders SET enabled = 0 WHERE reminder_id = ?", (rid,))
    conn.commit()
    assert due_reminders(conn, datetime(2020, 1, 2, tzinfo=TZ)) == []


def test_due_reminders_user_isolation(repo):
    conn = repo._get_conn()
    repo.add_user(user_id="other", display_name="O", telegram_chat_id="777",
                   incoming_dir="/tmp/in2", sync_dir="/tmp/sync2", ref_audio="/tmp/r2.wav")
    past = datetime(2020, 1, 1, 10, 0, tzinfo=TZ)
    create_reminder(conn, "me", item_kind="event", item_key="9", text="mine",
                     due_at=past, chat_id=555)
    create_reminder(conn, "other", item_kind="event", item_key="9", text="theirs",
                     due_at=past, chat_id=777)
    all_due = due_reminders(conn, datetime(2020, 1, 2, tzinfo=TZ))
    assert {d["user_id"] for d in all_due} == {"me", "other"}
    assert {d["text"] for d in all_due} == {"mine", "theirs"}


def test_mark_error_disables_after_max_consecutive(repo):
    conn = repo._get_conn()
    past = datetime(2020, 1, 1, 10, 0, tzinfo=TZ)
    rid = create_reminder(conn, "me", item_kind="event", item_key="9", text="x",
                           due_at=past, chat_id=555)
    disabled = False
    for _ in range(MAX_CONSECUTIVE_ERRORS):
        disabled = mark_error(conn, rid)
    assert disabled is True
    row = conn.execute("SELECT enabled FROM reminders WHERE reminder_id = ?", (rid,)).fetchone()
    assert row[0] == 0


def test_mark_error_not_yet_disabled_below_threshold(repo):
    conn = repo._get_conn()
    past = datetime(2020, 1, 1, 10, 0, tzinfo=TZ)
    rid = create_reminder(conn, "me", item_kind="event", item_key="9", text="x",
                           due_at=past, chat_id=555)
    disabled = mark_error(conn, rid)
    assert disabled is False
    row = conn.execute("SELECT enabled FROM reminders WHERE reminder_id = ?", (rid,)).fetchone()
    assert row[0] == 1


def test_mark_sent_resets_error_counter(repo):
    conn = repo._get_conn()
    past = datetime(2020, 1, 1, 10, 0, tzinfo=TZ)
    rid = create_reminder(conn, "me", item_kind="event", item_key="9", text="x",
                           due_at=past, chat_id=555)
    mark_error(conn, rid)
    mark_error(conn, rid)
    mark_sent(conn, rid)
    row = conn.execute(
        "SELECT consecutive_errors, sent_at FROM reminders WHERE reminder_id = ?", (rid,)
    ).fetchone()
    assert row[0] == 0
    assert row[1] is not None


def test_snooze_moves_due_at_forward_and_clears_sent(repo):
    conn = repo._get_conn()
    due_at = datetime(2020, 1, 1, 10, 0, tzinfo=TZ)
    rid = create_reminder(conn, "me", item_kind="event", item_key="9", text="x",
                           due_at=due_at, chat_id=555)
    mark_sent(conn, rid)
    snooze_reminder(conn, rid, "me")
    row = conn.execute(
        "SELECT due_at, sent_at FROM reminders WHERE reminder_id = ?", (rid,)
    ).fetchone()
    assert row[1] is None
    assert row[0].startswith("2020-01-02")


def test_snooze_wrong_user_id_does_not_modify_row(repo):
    """Regress (CRITICAL, security-review 2026-07-17 до коммита): snooze_reminder
    без user_id-фильтра позволял перенести ЧУЖОЕ напоминание по угаданному id."""
    conn = repo._get_conn()
    due_at = datetime(2020, 1, 1, 10, 0, tzinfo=TZ)
    rid = create_reminder(conn, "me", item_kind="event", item_key="9", text="x",
                           due_at=due_at, chat_id=555)
    mark_sent(conn, rid)
    snooze_reminder(conn, rid, "someone_else")
    row = conn.execute(
        "SELECT due_at, sent_at FROM reminders WHERE reminder_id = ?", (rid,)
    ).fetchone()
    assert row[1] is not None  # sent_at НЕ сброшен — чужой user_id не подошёл
    assert row[0].startswith("2020-01-01")  # due_at НЕ сдвинут


def test_close_item_event_marks_fulfilled(repo):
    close_item(repo, "me", "event", "9")
    conn = repo._get_conn()
    status = conn.execute("SELECT status FROM events WHERE id = 9").fetchone()[0]
    assert status == "fulfilled"


def test_close_item_promise_marks_fulfilled(repo):
    conn = repo._get_conn()
    conn.execute(
        "INSERT INTO promises(promise_id, user_id, call_id, who, what, due, status) "
        "VALUES (7, 'me', 1, 'OTHER', 'прислать документы', '2020-06-20', 'open')"
    )
    conn.commit()
    close_item(repo, "me", "promise", "7")
    status = conn.execute("SELECT status FROM promises WHERE promise_id = 7").fetchone()[0]
    assert status == "fulfilled"


def test_close_item_deep_fact_is_noop_no_crash(repo):
    close_item(repo, "me", "deep_fact", "abc123")  # таблицы нет — не должно упасть
