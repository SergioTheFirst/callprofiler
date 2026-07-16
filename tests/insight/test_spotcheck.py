# -*- coding: utf-8 -*-
"""test_spotcheck.py — задача 0.3: спот-чек-сэмплер (ozalupennieStrategic5.md §Ф0)."""
from callprofiler.db.repository import Repository
from callprofiler.insight.spotcheck import build_spotcheck


def _db(tmp_path):
    repo = Repository(str(tmp_path / "spotcheck.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    return repo, repo._get_conn()


def _seed_calls(conn, durations, user_id="me"):
    """durations: список длительностей (сек) -> сеет по звонку на каждую с транскриптом."""
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (user_id, "+79001112233", "Иван"),
    )
    cid = cur.lastrowid
    call_ids = []
    for i, dur in enumerate(durations):
        cur = conn.execute(
            "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
            "source_filename, source_md5, status, duration_sec, audio_path) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, cid, "IN", f"2026-01-{i + 1:02d}T10:00:00", f"f{i}.mp3",
             f"md5{i}", "done", dur, f"C:\\calls\\audio\\f{i}.mp3"),
        )
        call_id = cur.lastrowid
        call_ids.append(call_id)
        conn.execute(
            "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) "
            "VALUES (?,0,1000,?,?)",
            (call_id, f"привет это звонок {i}", "OWNER"),
        )
        conn.execute(
            "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) "
            "VALUES (?,1000,2000,?,?)",
            (call_id, f"ответ на звонок {i}", "OTHER"),
        )
        conn.execute(
            "INSERT INTO analyses(call_id, prompt_version, summary, risk_score) "
            "VALUES (?, 'v1', ?, ?)",
            (call_id, f"саммари {i}", 10 * i),
        )
    conn.commit()
    return call_ids


def test_spotcheck_nine_calls_three_strata(tmp_path):
    repo, conn = _db(tmp_path)
    # 3 короткие(<60s) + 3 средние(60-600s) + 3 длинные(>600s)
    durations = [10, 20, 30, 100, 200, 300, 700, 800, 900]
    _seed_calls(conn, durations)

    report = build_spotcheck(conn, "me", n=9, seed=0)

    assert report.count("## call_id=") == 9
    assert report.count("- [ ] текст верен") == 9
    assert report.count("- [ ] роли верны") == 9
    assert report.count("- [ ] обещания верны") == 9
    assert "[me]:" in report and "[s2]:" in report
    assert "audio:" in report
    repo.close()


def test_spotcheck_deterministic_same_seed(tmp_path):
    repo, conn = _db(tmp_path)
    durations = [10, 20, 30, 100, 200, 300, 700, 800, 900]
    _seed_calls(conn, durations)

    r1 = build_spotcheck(conn, "me", n=9, seed=42)
    r2 = build_spotcheck(conn, "me", n=9, seed=42)
    assert r1 == r2
    repo.close()


def test_spotcheck_respects_user_isolation(tmp_path):
    repo, conn = _db(tmp_path)
    repo.add_user(user_id="other", display_name="O", telegram_chat_id="1",
                   incoming_dir="/tmp/in2", sync_dir="/tmp/sync2", ref_audio="/tmp/r2.wav")
    _seed_calls(conn, [10, 20, 30], user_id="me")
    _seed_calls(conn, [10, 20, 30], user_id="other")

    report = build_spotcheck(conn, "me", n=25, seed=0)
    assert report.count("## call_id=") == 3
    repo.close()


def test_spotcheck_shows_promises(tmp_path):
    repo, conn = _db(tmp_path)
    call_ids = _seed_calls(conn, [10])
    conn.execute(
        "INSERT INTO promises(user_id, contact_id, call_id, who, what, due, status) "
        "SELECT 'me', contact_id, call_id, 'OWNER', 'перезвонить', '2026-02-01', 'open' "
        "FROM calls WHERE call_id = ?",
        (call_ids[0],),
    )
    conn.commit()

    report = build_spotcheck(conn, "me", n=1, seed=0)
    assert "перезвонить" in report
    repo.close()
