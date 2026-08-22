# -*- coding: utf-8 -*-
"""
test_bs_v2_inputs.py — R-15/R-16: сырой снимок оснований контакта и сборка
входного вектора BS-v2 (offline, без LLM/GPU/сети).
"""

from __future__ import annotations

import sqlite3

from callprofiler.db.repository import Repository
from callprofiler.insight.bs_snapshot import snapshot_contact_evidence


def _seed(tmp_path):
    repo = Repository(str(tmp_path / "snap.db"))
    repo.init_db()
    for uid in ("me", "other"):
        repo.add_user(uid, uid, None, "/in", "/sync", "/ref.wav")
    conn = repo._get_conn()
    mine = repo.get_or_create_contact("me", "+79990001111", "Пётр")
    theirs = repo.get_or_create_contact("other", "+79990002222", "Чужой")

    def _call(user, contact, dt, md5, cid=None):
        return repo.create_call(
            user_id=user, contact_id=contact, direction="IN", call_datetime=dt,
            source_filename=f"{md5}.mp3", source_md5=md5, audio_path=None,
        )

    past = _call("me", mine, "2026-01-10 10:00:00", "md5-past")
    future = _call("me", mine, "2026-03-01 10:00:00", "md5-future")
    alien = _call("other", theirs, "2026-01-10 10:00:00", "md5-alien")

    conn.executemany(
        "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) VALUES (?,?,?,?,?)",
        [
            (past, 0, 1000, "Привезу документы в пятницу", "OTHER"),
            (future, 0, 1000, "это уже за горизонтом", "OTHER"),
            (alien, 0, 1000, "чужая реплика", "OTHER"),
        ],
    )
    conn.executemany(
        "INSERT INTO analyses(call_id, raw_response, canonical_json, schema_version, parse_status)"
        " VALUES (?,?,?,?,?)",
        [
            (past, "{}", '{"bs_score": 40}', "v2", "parsed_ok"),
            (future, "{}", "{}", "v2", "parsed_ok"),
            (alien, "{}", "{}", "v2", "parsed_ok"),
        ],
    )
    repo.save_promises(
        "me", mine, past,
        [{"who": "S2", "what": "Привезу документы в пятницу", "due": "2026-01-16",
          "vague": False}],
        transcript_text="[s2] Привезу документы в пятницу",
    )
    # graph_v2 contradiction (C-кандидат) + legacy contradiction из bulk-пути (НЕ кандидат)
    conn.execute(
        "INSERT INTO events(user_id, contact_id, call_id, event_type, fact_type, who, payload,"
        " quote, quote_match, quote_verified, producer, confidence)"
        " VALUES ('me',?,?,'contradiction','contradiction','OTHER','p','цитата раз',1.0,1,"
        "'graph_v2',0.9)",
        (mine, past),
    )
    conn.execute(
        "INSERT INTO events(user_id, contact_id, call_id, event_type, fact_type, who, payload,"
        " source_quote, producer, confidence)"
        " VALUES ('me',?,?,'contradiction',NULL,'UNKNOWN','p','цитата два','legacy',0.8)",
        (mine, past),
    )
    conn.execute(
        "INSERT INTO events(user_id, contact_id, call_id, event_type, fact_type, who, payload,"
        " quote, producer, confidence)"
        " VALUES ('other',?,?,'contradiction','contradiction','OTHER','p','чужая',"
        "'graph_v2',0.9)",
        (theirs, alien),
    )
    conn.commit()
    return repo, conn, mine, theirs, past, future


def test_raw_contact_evidence_snapshot_is_complete_and_scoped(tmp_path):
    """R-15: снимок полон, детерминирован, не видит будущего и чужого владельца;
    legacy-`contradiction` не становится C-кандидатом (RISK-26)."""
    repo, conn, mine, theirs, past, future = _seed(tmp_path)

    snap = snapshot_contact_evidence(conn, "me", mine, "2026-02-01")

    assert snap["schema"] == "bs-snapshot-1"
    assert snap["call_ids"] == [past]  # будущий звонок исключён ДО расчёта
    assert [a["call_id"] for a in snap["analyses"]] == [past]
    assert all(t["call_id"] == past for t in snap["transcripts"])
    assert snap["callset"] == [("md5-past", "2026-01-10")]

    assert len(snap["promises"]) == 1
    promise = snap["promises"][0]
    assert promise["who"] == "OTHER" and promise["vague"] == 0
    assert promise["quote_match"] == 1.0

    assert len(snap["contradiction_candidates"]) == 1
    assert snap["contradiction_candidates"][0]["quote"] == "цитата раз"
    assert len(snap["legacy_context"]) == 1  # bulk-строка видна как контекст
    assert snap["legacy_context"][0]["producer"] == "legacy"

    # чужой владелец не протекает ни в одну секцию
    flat = repr(snap)
    assert "чужая" not in flat and "md5-alien" not in flat
    alien_snap = snapshot_contact_evidence(conn, "me", theirs, "2026-02-01")
    assert alien_snap["call_ids"] == []

    # каждый выполненный SQL содержит предикат по user_id
    seen: list[str] = []
    conn.set_trace_callback(seen.append)
    try:
        snapshot_contact_evidence(conn, "me", mine, "2026-02-01")
    finally:
        conn.set_trace_callback(None)
    # (запросы к sqlite_master — интроспекция наличия таблиц, не чтение данных)
    selects = [
        s
        for s in seen
        if s.strip().upper().startswith("SELECT") and "sqlite_master" not in s
    ]
    assert selects
    assert all("user_id" in s for s in selects), [s for s in selects if "user_id" not in s]

    # снимок ничего не пишет
    before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    snapshot_contact_evidence(conn, "me", mine, "2026-02-01")
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before

    # горизонт расширили → будущий звонок появляется
    later = snapshot_contact_evidence(conn, "me", mine, "2026-03-31")
    assert later["call_ids"] == [past, future]
    repo.close()


def test_snapshot_survives_missing_optional_tables(tmp_path):
    """Слои insight могут быть не применены — снимок отдаёт пустые секции, не падает."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    repo = Repository(":memory:")
    conn.executescript(
        (
            __import__("pathlib").Path("src/callprofiler/db/schema.sql")
        ).read_text(encoding="utf-8")
    )
    conn.execute(
        "INSERT INTO users(user_id, display_name, incoming_dir, sync_dir, ref_audio)"
        " VALUES ('me','Me','/in','/sync','/r.wav')"
    )
    conn.execute("INSERT INTO contacts(user_id, phone_e164) VALUES ('me','+7999')")
    conn.commit()
    snap = snapshot_contact_evidence(conn, "me", 1, "2026-02-01")
    assert snap["promise_outcomes"] == [] and snap["deep_facts"] == []
    assert snap["contact_features"] == [] and snap["mention_edges"] == []
    conn.close()
    repo.close()
