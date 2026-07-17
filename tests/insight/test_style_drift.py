"""Tests for style drift over years, FRAGILE-gated (B8)."""
from callprofiler.db.repository import Repository
from callprofiler.insight.age_style.drift import style_drift


def _db(tmp_path):
    repo = Repository(str(tmp_path / "drift.db"))
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


def _call(conn, contact_id, call_datetime, user_id="me"):
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
        "source_filename, source_md5, status, duration_sec) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, contact_id, "IN", call_datetime, f"f{contact_id}-{call_datetime}.mp3",
         f"md5{contact_id}-{call_datetime}", "done", 60),
    )
    return cur.lastrowid


def _segment(conn, call_id, speaker, text, start_ms=0, end_ms=1000):
    conn.execute(
        "INSERT INTO transcripts(call_id, speaker, text, start_ms, end_ms) VALUES (?,?,?,?,?)",
        (call_id, speaker, text, start_ms, end_ms),
    )


def test_detects_formalization_trend(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)

    call_2021 = _call(conn, cid, "2021-03-01T10:00:00")
    informal = " ".join(["кринж"] * 5 + ["рофл"] * 5 + ["ты"] * 5)
    _segment(conn, call_2021, "OTHER", informal)

    call_2024 = _call(conn, cid, "2024-03-01T10:00:00")
    formal = " ".join(
        ["уважаемый"] * 3 + ["непосредственно"] * 3 + ["впоследствии"] * 3 + ["вы"] * 6
    )
    _segment(conn, call_2024, "OTHER", formal)
    conn.commit()

    phrases = style_drift(conn, "me", cid, min_tokens_per_year=5, min_years=2)
    assert phrases
    assert len(phrases) <= 2
    assert all("осторожная оценка по стилю" in p for p in phrases)
    repo.close()


def test_below_min_years_returns_empty(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_2021 = _call(conn, cid, "2021-03-01T10:00:00")
    _segment(conn, call_2021, "OTHER", " ".join(["кринж"] * 10))
    call_2024 = _call(conn, cid, "2024-03-01T10:00:00")
    _segment(conn, call_2024, "OTHER", " ".join(["вы"] * 10))
    conn.commit()

    # min_years=3 (дефолт), а качественных лет только 2 -> []
    assert style_drift(conn, "me", cid, min_tokens_per_year=5) == []
    repo.close()


def test_unknown_share_over_40_percent_returns_empty(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_2021 = _call(conn, cid, "2021-03-01T10:00:00")
    _segment(conn, call_2021, "OTHER", " ".join(["кринж"] * 10))
    call_2022 = _call(conn, cid, "2022-03-01T10:00:00")
    _segment(conn, call_2022, "OTHER", " ".join(["слово"] * 10))
    call_2024 = _call(conn, cid, "2024-03-01T10:00:00")
    _segment(conn, call_2024, "OTHER", " ".join(["вы"] * 10))
    for call_id in (call_2021, call_2022, call_2024):
        _segment(conn, call_id, "UNKNOWN", "невнятно")
    conn.commit()

    # 3 UNKNOWN vs 6 всего -> 50% > 40%
    assert style_drift(conn, "me", cid, min_tokens_per_year=5, min_years=2) == []
    repo.close()


def test_no_calls_returns_empty(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    conn.commit()
    assert style_drift(conn, "me", cid) == []
    repo.close()


def test_stable_style_returns_empty(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call_2021 = _call(conn, cid, "2021-03-01T10:00:00")
    _segment(conn, call_2021, "OTHER", " ".join(["слово"] * 10))
    call_2022 = _call(conn, cid, "2022-03-01T10:00:00")
    _segment(conn, call_2022, "OTHER", " ".join(["слово"] * 10))
    conn.commit()

    assert style_drift(conn, "me", cid, min_tokens_per_year=5, min_years=2) == []
    repo.close()
