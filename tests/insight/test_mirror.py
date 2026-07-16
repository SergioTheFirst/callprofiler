# -*- coding: utf-8 -*-
"""test_mirror.py — A3: «Зеркало» владельца (self-dossier aggregates)."""
from __future__ import annotations

from callprofiler.db.repository import Repository
from callprofiler.insight import repository as insight_repo
from callprofiler.insight.mirror import build_mirror, save_mirror


def _db(tmp_path):
    repo = Repository(str(tmp_path / "mirror.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    conn = repo._get_conn()
    insight_repo.apply_insight_schema(conn)
    return repo, conn


def _contact(conn, phone, name):
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES ('me', ?, ?)",
        (phone, name),
    )
    return cur.lastrowid


def _call(conn, contact_id, dt, duration_sec=60):
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, source_filename, "
        "source_md5, status, duration_sec) VALUES ('me', ?, 'IN', ?, ?, ?, 'done', ?)",
        (contact_id, dt, f"f{dt}-{contact_id}.mp3", f"md5-{dt}-{contact_id}", duration_sec),
    )
    return cur.lastrowid


def _analysis(conn, call_id, risk_score):
    conn.execute(
        "INSERT INTO analyses(call_id, prompt_version, risk_score) VALUES (?, 'v001', ?)",
        (call_id, risk_score),
    )


def _owner_event(conn, call_id, contact_id, deadline, status="open"):
    conn.execute(
        "INSERT INTO events(user_id, contact_id, call_id, event_type, who, payload, "
        "deadline, status) VALUES ('me', ?, ?, 'promise', 'OWNER', 'отправить документы', ?, ?)",
        (contact_id, call_id, deadline, status),
    )


def _segments(conn, call_id, speaker, text):
    conn.execute(
        "INSERT INTO transcripts(call_id, speaker, text, start_ms, end_ms) "
        "VALUES (?, ?, ?, 0, 60000)",
        (call_id, speaker, text),
    )


def test_promises_block_owner_overdue(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn, "+79160000001", "Иван")
    call_id = _call(conn, cid, "2026-01-01T10:00:00")
    _owner_event(conn, call_id, cid, "2026-01-05")  # давно просрочено
    conn.commit()

    m = build_mirror(conn, "me", today="2026-07-01")
    repo.close()

    assert m["promises"]["open_n"] == 1
    assert m["promises"]["overdue_n"] == 1
    assert "просрочено" in m["promises"]["phrase"]


def test_promises_block_no_debts(tmp_path):
    repo, conn = _db(tmp_path)
    conn.commit()

    m = build_mirror(conn, "me")
    repo.close()

    assert m["promises"]["open_n"] == 0
    assert m["promises"]["phrase"] == "за вами долгов нет"


def test_risk_trend_increasing(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn, "+79160000002", "Пётр")
    for i, risk in enumerate([10, 20, 30, 40, 50, 60]):
        call_id = _call(conn, cid, f"2026-{i + 1:02d}-10T10:00:00")
        _analysis(conn, call_id, risk)
    conn.commit()

    m = build_mirror(conn, "me", today="2026-07-15")
    repo.close()

    assert m["risk_trend"]["slope"] > 1.0
    assert m["risk_trend"]["phrase"] == "фон ваших разговоров становится напряжённее"


def test_dependency_concentration(tmp_path):
    repo, conn = _db(tmp_path)
    a = _contact(conn, "+79160000003", "Алиса")
    b = _contact(conn, "+79160000004", "Борис")
    c = _contact(conn, "+79160000005", "Вера")
    for cid in (a, b, c):
        _call(conn, cid, "2026-06-15T10:00:00", duration_sec=1000)
    conn.commit()

    m = build_mirror(conn, "me", today="2026-07-01")
    repo.close()

    assert m["dependency"]["share"] > 0.6
    assert "Алиса" in m["dependency"]["phrase"]
    assert "сконцентрировано" in m["dependency"]["phrase"]


def test_register_formal_and_informal_contacts(tmp_path):
    repo, conn = _db(tmp_path)
    formal_cid = _contact(conn, "+79160000006", "Формальный")
    informal_cid = _contact(conn, "+79160000007", "Свойский")

    call_a = _call(conn, formal_cid, "2026-06-01T10:00:00")
    _segments(conn, call_a, "OWNER", " ".join(["вы"] * 45))
    call_b = _call(conn, informal_cid, "2026-06-01T10:00:00")
    _segments(conn, call_b, "OWNER", " ".join(["ты"] * 45))
    conn.commit()

    m = build_mirror(conn, "me")
    repo.close()

    assert "Формальный" in m["register"]["formal_top"]
    assert "Свойский" in m["register"]["informal_top"]
    assert "вы" in m["register"]["phrase"]


def test_register_gated_by_min_owner_tokens(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn, "+79160000008", "Малоговорящий")
    call_id = _call(conn, cid, "2026-06-01T10:00:00")
    _segments(conn, call_id, "OWNER", " ".join(["вы"] * 5))  # < 40
    conn.commit()

    m = build_mirror(conn, "me")
    repo.close()

    assert m["register"]["formal_top"] == []
    assert m["register"]["phrase"] == "недостаточно данных"


def test_save_mirror_idempotent_upsert(tmp_path):
    repo, conn = _db(tmp_path)
    save_mirror(conn, "me", {"a": 1})
    save_mirror(conn, "me", {"a": 2})

    row = conn.execute("SELECT payload FROM owner_mirror WHERE user_id='me'").fetchall()
    repo.close()

    assert len(row) == 1
    assert row[0]["payload"] == '{"a": 2}'


def test_user_isolation(tmp_path):
    repo, conn = _db(tmp_path)
    repo.add_user(user_id="other", display_name="O", telegram_chat_id="1",
                  incoming_dir="/tmp/in2", sync_dir="/tmp/sync2", ref_audio="/tmp/r2.wav")
    cid_me = _contact(conn, "+79160000009", "Мой контакт")
    call_me = _call(conn, cid_me, "2026-01-01T10:00:00")
    _owner_event(conn, call_me, cid_me, "2026-01-05")
    conn.commit()

    m_me = build_mirror(conn, "me", today="2026-07-01")
    m_other = build_mirror(conn, "other", today="2026-07-01")
    repo.close()

    assert m_me["promises"]["open_n"] == 1
    assert m_other["promises"]["open_n"] == 0
