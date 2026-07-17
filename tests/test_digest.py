# -*- coding: utf-8 -*-
"""test_digest.py — A1: реестр обязательств (ozalupennieStrategic5.md §A1)."""
from __future__ import annotations

from callprofiler.db.repository import Repository
from callprofiler.deliver.digest import build_digest, on_this_day, open_items, overdue_items

TODAY = "2026-07-17"


def _db(tmp_path):
    repo = Repository(str(tmp_path / "digest.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    return repo, repo._get_conn()


def _contact(conn, user_id="me", name="Иван"):
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (user_id, "+79001112233", name),
    )
    return cur.lastrowid


def _call(conn, contact_id, user_id="me", call_datetime="2026-06-01T10:00:00"):
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
        "source_filename, source_md5, status, duration_sec) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (user_id, contact_id, "IN", call_datetime, f"f{contact_id}.mp3",
         f"md5{contact_id}-{call_datetime}", "done", 60),
    )
    return cur.lastrowid


def _event(conn, user_id, contact_id, call_id, who, what, deadline, quote="цитата",
           event_type="promise", status="open"):
    conn.execute(
        """INSERT INTO events(user_id, contact_id, call_id, event_type, who, payload,
                               source_quote, deadline, status)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, contact_id, call_id, event_type, who, what, quote, deadline, status),
    )


def _promise(conn, user_id, contact_id, call_id, who, what, due, status="open"):
    conn.execute(
        """INSERT INTO promises(user_id, contact_id, call_id, who, what, due, status)
           VALUES (?,?,?,?,?,?,?)""",
        (user_id, contact_id, call_id, who, what, due, status),
    )


def test_overdue_bucketing(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id = _call(conn, cid)
    _event(conn, "me", cid, call_id, "OTHER", "прислать смету", "2026-07-01")  # overdue
    _event(conn, "me", cid, call_id, "OTHER", "перезвонить", "2026-07-20")  # not yet
    conn.commit()

    over = overdue_items(conn, "me", today=TODAY)
    assert len(over) == 1
    assert over[0]["what"] == "прислать смету"
    assert over[0]["days_overdue"] == 16
    repo.close()


def test_open_items_within_window(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id = _call(conn, cid)
    _event(conn, "me", cid, call_id, "OWNER", "будущее", "2026-07-25")
    _event(conn, "me", cid, call_id, "OWNER", "прошлое", "2026-07-01")
    conn.commit()

    open_ = open_items(conn, "me", today=TODAY)
    assert len(open_) == 1
    assert open_[0]["what"] == "будущее"
    repo.close()


def test_promises_and_events_dedup(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id = _call(conn, cid)
    _promise(conn, "me", cid, call_id, "OTHER", "прислать смету", "2026-07-01")
    _event(conn, "me", cid, call_id, "OTHER", "прислать смету", "2026-07-01", quote="вот цитата")
    conn.commit()

    over = overdue_items(conn, "me", today=TODAY)
    assert len(over) == 1
    assert over[0]["origin"] == "events"
    assert over[0]["quote"] == "вот цитата"
    repo.close()


def test_side_owner_contact_unknown(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id = _call(conn, cid)
    _event(conn, "me", cid, call_id, "OWNER", "owner item", "2026-07-01")
    _event(conn, "me", cid, call_id, "OTHER", "contact item", "2026-07-02")
    _event(conn, "me", cid, call_id, "UNKNOWN", "unknown item", "2026-07-03")
    conn.commit()

    over = overdue_items(conn, "me", today=TODAY)
    sides = {i["what"]: i["side"] for i in over}
    assert sides["owner item"] == "owner"
    assert sides["contact item"] == "contact"
    assert "unknown item" not in sides
    repo.close()


def test_user_isolation(tmp_path):
    repo, conn = _db(tmp_path)
    repo.add_user(user_id="other", display_name="O", telegram_chat_id="1",
                   incoming_dir="/tmp/in2", sync_dir="/tmp/sync2", ref_audio="/tmp/r2.wav")
    cid_me = _contact(conn, user_id="me")
    cid_other = _contact(conn, user_id="other")
    call_me = _call(conn, cid_me, user_id="me")
    call_other = _call(conn, cid_other, user_id="other")
    _event(conn, "me", cid_me, call_me, "OTHER", "for me", "2026-07-01")
    _event(conn, "other", cid_other, call_other, "OTHER", "for other", "2026-07-01")
    conn.commit()

    over = overdue_items(conn, "me", today=TODAY)
    assert len(over) == 1
    assert over[0]["what"] == "for me"
    repo.close()


def test_digest_contains_quote_and_date(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id = _call(conn, cid, call_datetime="2026-06-15T10:00:00")
    _event(conn, "me", cid, call_id, "OTHER", "прислать смету", "2026-07-01",
           quote="я пришлю смету завтра")
    conn.commit()

    report = build_digest(conn, "me", today=TODAY)
    assert "прислать смету" in report
    assert "я пришлю смету завтра" in report
    assert "2026-06-15" in report
    assert "2026-07-01" in report
    assert "Просрочено ИМИ" in report and "Просрочено ВАМИ" in report
    repo.close()


def test_digest_item_truncated_to_300_chars(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id = _call(conn, cid)
    long_what = "прислать документы " * 30  # far over 300 chars
    _event(conn, "me", cid, call_id, "OTHER", long_what, "2026-07-01")
    conn.commit()

    report = build_digest(conn, "me", today=TODAY)
    for line in report.splitlines():
        assert len(line) <= 300
    repo.close()


def test_overdue_line_gets_amount_suffix(tmp_path):
    """B7: overdue-строки получают сумму из СВОИХ what+quote."""
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id = _call(conn, cid)
    _event(conn, "me", cid, call_id, "OTHER", "прислать 40 тыс руб", "2026-07-01",
           quote="перекину 40 тыс руб завтра")
    conn.commit()

    report = build_digest(conn, "me", today=TODAY)
    assert "~40 тыс ₽" in report
    repo.close()


def test_upcoming_line_has_no_amount_suffix(tmp_path):
    """B7: сумма дописывается ТОЛЬКО к overdue — не-просроченным строкам нет."""
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id = _call(conn, cid)
    _event(conn, "me", cid, call_id, "OWNER", "перевести 40 тыс руб", "2026-07-25",
           quote="переведу 40 тыс руб")
    conn.commit()

    report = build_digest(conn, "me", today=TODAY)
    assert "~40 тыс ₽" not in report
    repo.close()


def _bio_scene(conn, call_id, importance, call_datetime, synopsis="Синопсис сцены",
                key_quote=None, user_id="me"):
    conn.execute(
        "INSERT INTO bio_scenes(user_id, call_id, importance, call_datetime, synopsis, key_quote) "
        "VALUES (?,?,?,?,?,?)",
        (user_id, call_id, importance, call_datetime, synopsis, key_quote),
    )


def test_on_this_day_shows_anniversary_one_year_ago(tmp_path):
    """D1: сцена ровно год назад, importance>70 -> строка «1 год назад»."""
    from callprofiler.biography.schema import apply_biography_schema

    repo, conn = _db(tmp_path)
    apply_biography_schema(conn)
    cid = _contact(conn)
    call_id = _call(conn, cid, call_datetime="2025-07-17T10:00:00")
    _bio_scene(conn, call_id, 80, "2025-07-17T10:00:00", synopsis="Важный разговор",
               key_quote="я тебе перезвоню")
    conn.commit()

    lines = on_this_day(conn, "me", today=TODAY)
    assert len(lines) == 1
    assert lines[0].startswith("1 год назад:")
    assert "Важный разговор" in lines[0]
    assert "я тебе перезвоню" in lines[0]
    repo.close()


def test_on_this_day_low_importance_excluded(tmp_path):
    from callprofiler.biography.schema import apply_biography_schema

    repo, conn = _db(tmp_path)
    apply_biography_schema(conn)
    cid = _contact(conn)
    call_id = _call(conn, cid, call_datetime="2025-07-17T10:00:00")
    _bio_scene(conn, call_id, 50, "2025-07-17T10:00:00")
    conn.commit()

    assert on_this_day(conn, "me", today=TODAY) == []
    repo.close()


def test_on_this_day_without_bio_scenes_table_returns_empty(tmp_path):
    repo, conn = _db(tmp_path)
    assert on_this_day(conn, "me", today=TODAY) == []
    repo.close()


def test_on_this_day_plural_years(tmp_path):
    from callprofiler.biography.schema import apply_biography_schema

    repo, conn = _db(tmp_path)
    apply_biography_schema(conn)
    cid = _contact(conn)
    call_id = _call(conn, cid, call_datetime="2021-07-17T10:00:00")  # 5 лет назад
    _bio_scene(conn, call_id, 90, "2021-07-17T10:00:00")
    conn.commit()

    lines = on_this_day(conn, "me", today=TODAY)
    assert lines[0].startswith("5 лет назад:")
    repo.close()


def test_build_digest_includes_on_this_day_section(tmp_path):
    from callprofiler.biography.schema import apply_biography_schema

    repo, conn = _db(tmp_path)
    apply_biography_schema(conn)
    cid = _contact(conn)
    call_id = _call(conn, cid, call_datetime="2025-07-17T10:00:00")
    _bio_scene(conn, call_id, 80, "2025-07-17T10:00:00", synopsis="Годовщина")
    conn.commit()

    report = build_digest(conn, "me", today=TODAY)
    assert "🗓 В этот день" in report
    assert "1 год назад" in report
    repo.close()
