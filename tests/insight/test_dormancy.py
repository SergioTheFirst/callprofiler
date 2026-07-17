"""Tests for dormancy alerts for valuable ties (C3)."""
from datetime import date, timedelta

from callprofiler.db.repository import Repository
from callprofiler.insight.dormancy import dormant_valuable


def _db(tmp_path):
    repo = Repository(str(tmp_path / "dormancy.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    return repo, repo._get_conn()


def _contact(conn, name, phone, user_id="me"):
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (user_id, phone, name),
    )
    return cur.lastrowid


def _call(conn, contact_id, call_dt, duration_sec=60, user_id="me"):
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
        "source_filename, source_md5, status, duration_sec) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, contact_id, "IN", call_dt.isoformat(),
         f"f{contact_id}-{call_dt.isoformat()}.mp3",
         f"md5{contact_id}-{call_dt.isoformat()}", "done", duration_sec),
    )
    return cur.lastrowid


def test_weekly_caller_with_long_silence_is_flagged(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn, "Часто", "+79001110001")
    start = date(2024, 1, 1)
    for i in range(30):
        _call(conn, cid, start + timedelta(days=7 * i))
    conn.commit()

    last_date = start + timedelta(days=7 * 29)
    today = last_date + timedelta(days=240)  # ~8 месяцев тишины

    result = dormant_valuable(conn, "me", today=today)
    hit = next((d for d in result if d["contact_id"] == cid), None)
    assert hit is not None
    assert hit["why"] == "раньше вы говорили почти каждую неделю"
    assert hit["last_date"] == last_date.isoformat()
    repo.close()


def test_regular_monthly_caller_within_own_rhythm_not_flagged(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn, "Ежемесячно", "+79001110002")
    start = date(2023, 1, 1)
    for i in range(12):
        _call(conn, cid, start + timedelta(days=30 * i))
    conn.commit()

    last_date = start + timedelta(days=30 * 11)
    today = last_date + timedelta(days=45)  # пауза 45 < 3x30=90 -> НЕ дремлющий

    result = dormant_valuable(conn, "me", today=today)
    assert not any(d["contact_id"] == cid for d in result)
    repo.close()


def test_small_contact_not_valuable_excluded(tmp_path):
    repo, conn = _db(tmp_path)
    small_cid = _contact(conn, "Мелкий", "+79001110003")
    big_cid = _contact(conn, "Крупный", "+79001110004")

    start = date(2023, 1, 1)
    for i in range(5):
        _call(conn, small_cid, start + timedelta(days=10 * i), duration_sec=60)
    for i in range(10):
        _call(conn, big_cid, start + timedelta(days=10 * i), duration_sec=3600)
    conn.commit()

    today = start + timedelta(days=200)
    result = dormant_valuable(conn, "me", today=today)
    assert not any(d["contact_id"] == small_cid for d in result)
    repo.close()


def test_no_calls_returns_empty(tmp_path):
    repo, conn = _db(tmp_path)
    assert dormant_valuable(conn, "me") == []
    repo.close()


def test_single_call_contact_excluded_no_gap_to_measure(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn, "Один раз", "+79001110005")
    _call(conn, cid, date(2024, 1, 1))
    conn.commit()
    assert not any(d["contact_id"] == cid for d in dormant_valuable(conn, "me"))
    repo.close()


def test_top_caps_result_length(tmp_path):
    repo, conn = _db(tmp_path)
    start = date(2023, 1, 1)
    for c in range(3):
        cid = _contact(conn, f"К{c}", f"+7900111001{c}")
        for i in range(30):
            _call(conn, cid, start + timedelta(days=7 * i))
    conn.commit()
    today = start + timedelta(days=7 * 29 + 240)

    result = dormant_valuable(conn, "me", today=today, top=2)
    assert len(result) == 2
    repo.close()
