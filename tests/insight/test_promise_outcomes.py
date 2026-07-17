# -*- coding: utf-8 -*-
"""Tests for behavioral promise reliability — det + memoized LLM (B3)."""
from __future__ import annotations

from unittest import mock

from callprofiler.db.repository import Repository
from callprofiler.insight import repository as insight_repo
from callprofiler.insight.promise_outcomes import contact_reliability, run_promise_outcomes


def _db(tmp_path):
    repo = Repository(str(tmp_path / "promout.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    return repo, repo._get_conn()


def _contact(conn, name="Иван", user_id="me"):
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (user_id, f"+7900{ord(name[-1])}", name),
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


def _event(conn, user_id, contact_id, call_id, who, what, deadline, quote="цитата",
          event_type="promise", status="open"):
    conn.execute(
        """INSERT INTO events(user_id, contact_id, call_id, event_type, who, payload,
                               source_quote, deadline, status)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, contact_id, call_id, event_type, who, what, quote, deadline, status),
    )


def _transcript(conn, call_id, speaker, text, start_ms=0):
    conn.execute(
        "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) VALUES (?,?,?,?,?)",
        (call_id, start_ms, start_ms + 3000, text, speaker),
    )


def _resp(content):
    m = mock.MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = {"choices": [{"message": {"content": content}}]}
    return m


def test_det_kept(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call0 = _call(conn, cid, "2026-06-01T10:00:00")
    _event(conn, "me", cid, call0, "OTHER", "привезу документы", None,
           quote="я привезу документы")
    call1 = _call(conn, cid, "2026-06-04T10:00:00")
    _transcript(conn, call1, "OTHER", "привёз документы, всё подписал")
    conn.commit()

    stats = run_promise_outcomes(conn, "me")
    assert stats["kept"] == 1

    row = conn.execute(
        "SELECT status, evidence_quote FROM promise_outcomes WHERE user_id='me' AND contact_id=?",
        (cid,)).fetchone()
    assert row["status"] == "kept"
    assert row["evidence_quote"] == "привёз документы, всё подписал"
    repo.close()


def test_det_late(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call0 = _call(conn, cid, "2026-06-01T10:00:00")
    _event(conn, "me", cid, call0, "OTHER", "привезу документы", "2026-06-02",
           quote="я привезу документы")
    call1 = _call(conn, cid, "2026-06-11T10:00:00")  # +10 дней от обещания
    _transcript(conn, call1, "OTHER", "привёз документы, всё подписал")
    conn.commit()

    run_promise_outcomes(conn, "me")

    row = conn.execute(
        "SELECT status, days_late FROM promise_outcomes WHERE user_id='me' AND contact_id=?",
        (cid,)).fetchone()
    assert row["status"] == "late"
    assert 8 <= row["days_late"] <= 10
    repo.close()


def test_det_broken(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call0 = _call(conn, cid, "2026-06-01T10:00:00")
    _event(conn, "me", cid, call0, "OTHER", "разобраться с документами", None,
           quote="разберусь с документами")
    call1 = _call(conn, cid, "2026-06-04T10:00:00")
    _transcript(conn, call1, "OTHER", "не получилось с документами")
    conn.commit()

    stats = run_promise_outcomes(conn, "me")
    assert stats["broken"] == 1

    row = conn.execute(
        "SELECT status FROM promise_outcomes WHERE user_id='me' AND contact_id=?",
        (cid,)).fetchone()
    assert row["status"] == "broken"
    repo.close()


def test_unknown_speaker_ignored(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call0 = _call(conn, cid, "2026-06-01T10:00:00")
    _event(conn, "me", cid, call0, "OTHER", "разобраться с документами", None,
           quote="разберусь с документами")
    call1 = _call(conn, cid, "2026-06-04T10:00:00")
    _transcript(conn, call1, "UNKNOWN", "не получилось с документами")
    conn.commit()

    stats = run_promise_outcomes(conn, "me")
    assert stats["unknown"] == 1
    assert stats["broken"] == 0
    repo.close()


def test_unknown_goes_llm_memoized(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call0 = _call(conn, cid, "2026-06-01T10:00:00")
    _event(conn, "me", cid, call0, "OTHER", "разобраться с документами", None,
           quote="разберусь с документами")
    call1 = _call(conn, cid, "2026-06-04T10:00:00")
    _transcript(conn, call1, "OTHER", "документы у меня, посмотрим на неделе")
    conn.commit()

    llm_json = '{"status":"kept","quote":"документы у меня, посмотрим на неделе","days_late":null}'
    with mock.patch("requests.post", return_value=_resp(llm_json)) as mp:
        stats1 = run_promise_outcomes(conn, "me", use_llm=True)
        assert stats1["kept"] == 1
        assert mp.call_count == 1

        stats2 = run_promise_outcomes(conn, "me", use_llm=True)
        assert stats2["kept"] == 1
        assert mp.call_count == 1  # не вырос — кэш по llm_prompt_hash

    row = conn.execute(
        "SELECT status, method FROM promise_outcomes WHERE user_id='me' AND contact_id=?",
        (cid,)).fetchone()
    assert row["status"] == "kept"
    assert row["method"] == "llm"
    repo.close()


def test_verbatim_gate(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call0 = _call(conn, cid, "2026-06-01T10:00:00")
    _event(conn, "me", cid, call0, "OTHER", "разобраться с документами", None,
           quote="разберусь с документами")
    call1 = _call(conn, cid, "2026-06-04T10:00:00")
    _transcript(conn, call1, "OTHER", "документы у меня, посмотрим на неделе")
    conn.commit()

    llm_json = '{"status":"kept","quote":"совсем другая цитата, которой не было","days_late":null}'
    with mock.patch("requests.post", return_value=_resp(llm_json)):
        run_promise_outcomes(conn, "me", use_llm=True)

    row = conn.execute(
        "SELECT status, evidence_quote, confidence FROM promise_outcomes "
        "WHERE user_id='me' AND contact_id=?", (cid,)).fetchone()
    assert row["status"] == "kept"
    assert row["evidence_quote"] is None
    assert row["confidence"] < 0.5
    repo.close()


def test_idempotent_rerun(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call0 = _call(conn, cid, "2026-06-01T10:00:00")
    _event(conn, "me", cid, call0, "OTHER", "привезу документы", None,
           quote="я привезу документы")
    call1 = _call(conn, cid, "2026-06-04T10:00:00")
    _transcript(conn, call1, "OTHER", "привёз документы, всё подписал")
    conn.commit()

    run_promise_outcomes(conn, "me")
    n1 = conn.execute("SELECT COUNT(*) FROM promise_outcomes WHERE user_id='me'").fetchone()[0]
    status1 = conn.execute(
        "SELECT status FROM promise_outcomes WHERE user_id='me' AND contact_id=?",
        (cid,)).fetchone()["status"]

    run_promise_outcomes(conn, "me")
    n2 = conn.execute("SELECT COUNT(*) FROM promise_outcomes WHERE user_id='me'").fetchone()[0]
    status2 = conn.execute(
        "SELECT status FROM promise_outcomes WHERE user_id='me' AND contact_id=?",
        (cid,)).fetchone()["status"]

    assert n1 == n2 == 1
    assert status1 == status2 == "kept"
    repo.close()


def test_reliability_phrase_thresholds(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn, "Один")
    call_id = _call(conn, cid, "2026-06-01T10:00:00")
    insight_repo.apply_insight_schema(conn)
    for i, status in enumerate(["kept", "kept", "kept", "kept", "broken"]):
        insight_repo.save_promise_outcome(
            conn, "me", promise_key=f"pk{i}", contact_id=cid, call_id=call_id,
            side="contact", what=f"обещание {i}", due=None, status=status,
            evidence_call_id=None, evidence_date=None, evidence_quote=None,
            days_late=None, method="det", confidence=0.6)
    conn.commit()

    rel = contact_reliability(conn, "me", cid)
    assert rel is not None
    assert rel["kept_ratio"] == 0.8
    assert rel["n"] == 5
    assert rel["phrase"] == "держит слово"

    cid2 = _contact(conn, "Два")
    call_id2 = _call(conn, cid2, "2026-06-01T10:00:00")
    for i, status in enumerate(["kept", "broken"]):
        insight_repo.save_promise_outcome(
            conn, "me", promise_key=f"pk2-{i}", contact_id=cid2, call_id=call_id2,
            side="contact", what=f"о {i}", due=None, status=status,
            evidence_call_id=None, evidence_date=None, evidence_quote=None,
            days_late=None, method="det", confidence=0.6)
    conn.commit()

    assert contact_reliability(conn, "me", cid2) is None
    repo.close()
