# -*- coding: utf-8 -*-
"""test_canary.py — M4: canary json_mode=False vs True, side-effect-free (ozalup2.md §3.4)."""
from __future__ import annotations

import json

from callprofiler.analyze.canary import run_canary
from callprofiler.analyze.llm_client import LLMResult
from callprofiler.config import Config
from callprofiler.db.repository import Repository


def _db(tmp_path):
    repo = Repository(str(tmp_path / "canary.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    return repo, repo._get_conn()


def _seed_calls(conn, n, user_id="me"):
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (user_id, "+79001112233", "Иван"),
    )
    cid = cur.lastrowid
    call_ids = []
    for i in range(n):
        cur = conn.execute(
            "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
            "source_filename, source_md5, status, duration_sec, audio_path) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, cid, "IN", f"2026-01-{i + 1:02d}T10:00:00", f"f{i}.mp3",
             f"md5{i}", "done", 60 + i, f"C:\\calls\\audio\\f{i}.mp3"),
        )
        call_id = cur.lastrowid
        call_ids.append(call_id)
        conn.execute(
            "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) "
            "VALUES (?,0,1000,?,?)",
            (call_id, f"привет это звонок номер {i}", "OWNER"),
        )
        conn.execute(
            "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) "
            "VALUES (?,1000,2000,?,?)",
            (call_id, f"ответ на звонок номер {i}", "OTHER"),
        )
    conn.commit()
    return call_ids


class FakeClient:
    """json_mode=False -> валидный JSON; True -> мусор (симулирует несовместимость)."""

    def __init__(self):
        self.json_modes_seen: list[bool] = []

    def complete(self, messages, temperature, max_tokens, json_mode):
        self.json_modes_seen.append(json_mode)
        if json_mode:
            return LLMResult(text="это не json совсем", finish_reason="stop")
        return LLMResult(
            text=json.dumps({
                "priority": 50, "risk_score": 10, "summary": "s",
                "call_type": "business", "action_items": [], "promises": [],
                "key_topics": [],
            }),
            finish_reason="stop",
        )


def test_canary_reports_both_branches(tmp_path):
    repo, conn = _db(tmp_path)
    _seed_calls(conn, 4)
    report = run_canary(conn, "me", lambda: FakeClient(), Config(), n=4, seed=0)

    assert "Звонков сравнено: 4" in report
    assert "parsed_ok" in report
    assert "parse_failed" in report
    repo.close()


def test_canary_writes_nothing_to_analyses(tmp_path):
    repo, conn = _db(tmp_path)
    _seed_calls(conn, 4)

    before = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    run_canary(conn, "me", lambda: FakeClient(), Config(), n=4, seed=0)
    after = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]

    assert before == 0 and after == 0
    repo.close()


def test_canary_calls_both_json_modes_per_call(tmp_path):
    repo, conn = _db(tmp_path)
    _seed_calls(conn, 4)
    client = FakeClient()

    run_canary(conn, "me", lambda: client, Config(), n=4, seed=0)

    assert client.json_modes_seen.count(False) == 4
    assert client.json_modes_seen.count(True) == 4
    repo.close()
