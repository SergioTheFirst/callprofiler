# -*- coding: utf-8 -*-
"""test_digest.py — A1: реестр обязательств (ozalupennieStrategic5.md §A1)."""
from __future__ import annotations

from callprofiler.db.repository import Repository
from callprofiler.deliver.digest import build_digest, open_items, overdue_items

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
