"""Tests for financial exposure display axis (B7)."""
from callprofiler.db.repository import Repository
from callprofiler.insight.finance import (
    extract_amounts, finance_exposure, exposure_phrase, format_amount_range,
)


def test_extract_amounts_words_not_caught():
    assert extract_amounts("обещал сорок тысяч рублей") == []


def test_extract_amounts_thousand_ruble():
    assert extract_amounts("перекину 40 тыс руб") == [(40000.0, "RUB")]


def test_extract_amounts_plain_ruble_short_form():
    assert extract_amounts("650 р") == [(650.0, "RUB")]


def test_extract_amounts_k_dollar():
    # "2к $" — множитель к=1000 матчится через \b перед пробелом, затем $ как валюта
    assert extract_amounts("скину 2к $ на днях") == [(2000.0, "USD")]


def test_extract_amounts_no_amount():
    assert extract_amounts("просто текст без денег") == []


def test_extract_amounts_multiple_in_one_text():
    result = extract_amounts("сначала 10 тыс руб потом ещё 5 тыс руб")
    assert result == [(10000.0, "RUB"), (5000.0, "RUB")]


def test_format_amount_range_single_value_no_dash():
    assert format_amount_range(2000, 2000, "USD") == "~2 тыс $"


def test_format_amount_range_range_with_dash():
    assert format_amount_range(40000, 90000, "RUB") == "~40–90 тыс ₽"


def test_exposure_phrase_none_when_no_exposure():
    assert exposure_phrase(None) == ""


# --- finance_exposure (DB-integration) ---

def _db(tmp_path):
    repo = Repository(str(tmp_path / "finance.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    return repo, repo._get_conn()


def _contact(conn, user_id="me"):
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (user_id, "+79001112233", "Иван"),
    )
    return cur.lastrowid


def _call(conn, contact_id, user_id="me", call_datetime="2026-06-01T10:00:00"):
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
        "source_filename, source_md5, status, duration_sec) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, contact_id, "IN", call_datetime, f"f{contact_id}.mp3",
         f"md5{contact_id}-{call_datetime}", "done", 60),
    )
    return cur.lastrowid


def _event(conn, user_id, contact_id, call_id, payload, quote, event_type="promise", status="open"):
    conn.execute(
        """INSERT INTO events(user_id, contact_id, call_id, event_type, who, payload,
                               source_quote, status) VALUES (?,?,?,?,?,?,?,?)""",
        (user_id, contact_id, call_id, event_type, "OTHER", payload, quote, status),
    )


def test_finance_exposure_none_without_events(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    conn.commit()
    assert finance_exposure(conn, "me", cid) is None
    repo.close()


def test_finance_exposure_aggregates_low_high(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id1 = _call(conn, cid, call_datetime="2026-06-01T10:00:00")
    _event(conn, "me", cid, call_id1, "обещал 40 тыс руб", "перекину 40 тыс руб")
    call_id2 = _call(conn, cid, call_datetime="2026-06-02T10:00:00")
    _event(conn, "me", cid, call_id2, "должен 50 тыс руб", "верну 50 тыс руб", event_type="debt")
    conn.commit()

    exp = finance_exposure(conn, "me", cid)
    assert exp == {"RUB": [50000.0, 90000.0]}  # low=крупнейшая разовая, high=сумма
    assert exposure_phrase(exp) == "на нём завязано ~50–90 тыс ₽"
    repo.close()


def test_duplicate_mention_within_event_not_doubled(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id = _call(conn, cid)
    _event(conn, "me", cid, call_id, "обещал перевести 40 тыс руб",
           "точно переведу 40 тысяч рублей завтра")
    conn.commit()

    exp = finance_exposure(conn, "me", cid)
    assert exp == {"RUB": [40000.0, 40000.0]}  # одно событие — не 80000
    repo.close()


def test_finance_exposure_ignores_closed_events(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_id = _call(conn, cid)
    _event(conn, "me", cid, call_id, "перевёл 40 тыс руб", "готово, перевёл 40 тыс руб",
           status="fulfilled")
    conn.commit()
    assert finance_exposure(conn, "me", cid) is None
    repo.close()
