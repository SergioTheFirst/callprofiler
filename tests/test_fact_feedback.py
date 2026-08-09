# -*- coding: utf-8 -*-
"""test_fact_feedback.py — F1: ✓/✗ пофактовое подтверждение владельцем.

Покрывает: репозиторий (UPSERT-смена вердикта, изоляция user_id), callback-парсер
бота на битых данных, digest (rejected скрыт/confirmed помечен), dashboard tools
+ tools-эндпоинт (400 на невалидный kind/verdict).
"""
from __future__ import annotations

import sqlite3

import pytest

from callprofiler.db.repository import Repository
from callprofiler.deliver.telegram_bot import parse_fv_callback
from callprofiler.insight.repository import (
    FACT_KINDS,
    apply_insight_schema,
    get_verdicts,
    set_fact_verdict,
)


# ── Репозиторий ───────────────────────────────────────────────────────────

def _conn():
    conn = sqlite3.connect(":memory:")
    apply_insight_schema(conn)
    return conn


def test_set_and_get_verdict_round_trip():
    conn = _conn()
    set_fact_verdict(conn, "me", item_kind="event", item_key=5, verdict="confirmed")
    assert get_verdicts(conn, "me", "event", ["5"]) == {"5": "confirmed"}


def test_upsert_changes_verdict_on_second_tap():
    conn = _conn()
    set_fact_verdict(conn, "me", item_kind="event", item_key="5", verdict="confirmed")
    set_fact_verdict(conn, "me", item_kind="event", item_key="5", verdict="rejected")
    assert get_verdicts(conn, "me", "event", ["5"]) == {"5": "rejected"}


def test_user_isolation_same_key_different_verdicts():
    conn = _conn()
    set_fact_verdict(conn, "me", item_kind="event", item_key="5", verdict="confirmed")
    set_fact_verdict(conn, "other", item_kind="event", item_key="5", verdict="rejected")
    assert get_verdicts(conn, "me", "event", ["5"]) == {"5": "confirmed"}
    assert get_verdicts(conn, "other", "event", ["5"]) == {"5": "rejected"}


def test_get_verdicts_empty_keys_returns_empty_dict():
    conn = _conn()
    assert get_verdicts(conn, "me", "event", []) == {}


def test_get_verdicts_missing_key_absent_not_none():
    conn = _conn()
    set_fact_verdict(conn, "me", item_kind="event", item_key="5", verdict="confirmed")
    result = get_verdicts(conn, "me", "event", ["5", "6"])
    assert result == {"5": "confirmed"}
    assert "6" not in result


def test_invalid_item_kind_raises():
    conn = _conn()
    with pytest.raises(ValueError):
        set_fact_verdict(conn, "me", item_kind="bogus", item_key="1", verdict="confirmed")


def test_invalid_verdict_raises():
    conn = _conn()
    with pytest.raises(ValueError):
        set_fact_verdict(conn, "me", item_kind="event", item_key="1", verdict="maybe")


def test_fact_kinds_includes_deep_fact_forward_compat():
    """deep_facts (M8) ещё не реализован — kind уже разрешён схемой заранее."""
    assert FACT_KINDS == ("promise", "event", "deep_fact")


# ── Callback-парсер бота (F1 §2) ──────────────────────────────────────────

def test_parse_fv_callback_valid():
    assert parse_fv_callback("fv|event|123|c") == ("event", "123", "confirmed")
    assert parse_fv_callback("fv|promise|7|r") == ("promise", "7", "rejected")


@pytest.mark.parametrize("data", [
    "garbage", "", None, "feedback_1_ok", "fv|bogus|1|c", "fv|event|1|x",
    "fv|event||c", "fv|event|1", "fv|event|1|c|extra",
])
def test_parse_fv_callback_malformed_returns_none_never_raises(data):
    assert parse_fv_callback(data) is None


# ── Digest — потребитель вердиктов (F1 §4) ────────────────────────────────

@pytest.fixture
def digest_repo(tmp_path):
    db = tmp_path / "digest.db"
    repo = Repository(str(db))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )
    conn = repo._get_conn()
    apply_insight_schema(conn)  # fact_feedback — тест сеет вердикт напрямую, до digest.py
    conn.execute(
        "INSERT INTO calls(call_id, user_id, call_datetime, source_filename, "
        "source_md5, status) VALUES (1, 'me', '2020-01-01', 'a.mp3', 'md5a', 'done')"
    )
    conn.execute(
        "INSERT INTO events(id, user_id, call_id, event_type, who, payload, "
        "deadline, status) VALUES (9, 'me', 1, 'promise', 'OWNER', 'вернуть долг', "
        "'2020-01-05', 'open')"
    )
    conn.commit()
    yield repo, conn
    repo.close()


def test_digest_overdue_excludes_rejected(digest_repo):
    from callprofiler.deliver.digest import overdue_items

    repo, conn = digest_repo
    set_fact_verdict(conn, "me", item_kind="event", item_key="9", verdict="rejected")
    assert overdue_items(conn, "me", today="2020-02-01") == []


def test_digest_overdue_marks_confirmed(digest_repo):
    from callprofiler.deliver.digest import overdue_items

    repo, conn = digest_repo
    set_fact_verdict(conn, "me", item_kind="event", item_key="9", verdict="confirmed")
    items = overdue_items(conn, "me", today="2020-02-01")
    assert len(items) == 1
    assert items[0]["confirmed"] is True


def test_digest_overdue_no_verdict_confirmed_false(digest_repo):
    from callprofiler.deliver.digest import overdue_items

    repo, conn = digest_repo
    items = overdue_items(conn, "me", today="2020-02-01")
    assert len(items) == 1
    assert items[0]["confirmed"] is False


def test_build_digest_marks_confirmed_item_with_checkmark(digest_repo):
    from callprofiler.deliver.digest import build_digest

    repo, conn = digest_repo
    set_fact_verdict(conn, "me", item_kind="event", item_key="9", verdict="confirmed")
    text = build_digest(conn, "me", today="2020-02-01")
    assert "✓ **" in text


# ── Dashboard tools (F1 §3) ────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    db = tmp_path / "verdict.db"
    repo = Repository(str(db))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )
    repo.close()
    return str(db)


def test_tools_set_fact_verdict_persists(db_path):
    from callprofiler.dashboard.tools import set_fact_verdict as tools_set_fact_verdict

    result = tools_set_fact_verdict(db_path, "me", "event", "9", "confirmed")
    assert result == {"item_kind": "event", "item_key": "9", "verdict": "confirmed"}

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT verdict FROM fact_feedback WHERE user_id='me' AND item_kind='event' AND item_key='9'"
    ).fetchone()
    conn.close()
    assert row[0] == "confirmed"


def test_tools_set_fact_verdict_invalid_kind_returns_error(db_path):
    from callprofiler.dashboard.tools import set_fact_verdict as tools_set_fact_verdict

    result = tools_set_fact_verdict(db_path, "me", "bogus", "9", "confirmed")
    assert "error" in result


def test_tools_set_fact_verdict_invalid_verdict_returns_error(db_path):
    from callprofiler.dashboard.tools import set_fact_verdict as tools_set_fact_verdict

    result = tools_set_fact_verdict(db_path, "me", "event", "9", "maybe")
    assert "error" in result


class TestFactVerdictEndpoint:
    @pytest.fixture
    def client(self):
        import callprofiler.dashboard.server as server_mod
        from unittest.mock import MagicMock
        from fastapi.testclient import TestClient

        mock_tools = MagicMock()
        saved_tools = server_mod._TOOLS
        saved_user = server_mod._USER_ID
        server_mod._TOOLS = mock_tools
        server_mod._USER_ID = "test_user"

        with TestClient(server_mod.app) as tc:
            tc.headers.update({"X-CSRF-Token": tc.get("/").cookies.get("cp_csrf") or ""})
            yield tc, mock_tools

        server_mod._TOOLS = saved_tools
        server_mod._USER_ID = saved_user

    def test_valid_verdict_saved(self, client):
        tc, mock_tools = client
        mock_tools.run_fact_verdict.return_value = {
            "item_kind": "event", "item_key": "9", "verdict": "confirmed",
        }

        resp = tc.post("/api/tools/fact-verdict",
                        json={"item_kind": "event", "item_key": "9", "verdict": "confirmed"})

        assert resp.status_code == 200
        assert resp.json()["verdict"] == "confirmed"
        mock_tools.run_fact_verdict.assert_called_once_with("event", "9", "confirmed")

    def test_missing_field_returns_400(self, client):
        tc, _ = client
        resp = tc.post("/api/tools/fact-verdict", json={"item_kind": "event", "item_key": "9"})
        assert resp.status_code == 400

    def test_invalid_verdict_value_returns_400(self, client):
        tc, _ = client
        resp = tc.post("/api/tools/fact-verdict",
                        json={"item_kind": "event", "item_key": "9", "verdict": "maybe"})
        assert resp.status_code == 400

    def test_error_result_returns_400(self, client):
        tc, mock_tools = client
        mock_tools.run_fact_verdict.return_value = {"error": "invalid item_kind"}

        resp = tc.post("/api/tools/fact-verdict",
                        json={"item_kind": "bogus", "item_key": "9", "verdict": "confirmed"})

        assert resp.status_code == 400
