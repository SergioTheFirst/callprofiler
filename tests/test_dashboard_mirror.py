# -*- coding: utf-8 -*-
"""test_dashboard_mirror.py — A3: dashboard get_mirror + GET /api/mirror."""
from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.db.repository import Repository
from callprofiler.insight import repository as insight_repo
from callprofiler.insight.mirror import build_mirror, save_mirror


def test_get_mirror_none_without_table(tmp_path):
    db = tmp_path / "nomirror.db"
    repo = Repository(str(db))
    repo.init_db()  # core schema only — no owner_mirror
    repo.close()

    r = DashboardDBReader(db)
    r.connect()
    result = r.get_mirror("me")
    r.close()

    assert result is None


def test_get_mirror_returns_payload_when_present(tmp_path):
    db = tmp_path / "mirror.db"
    repo = Repository(str(db))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    conn = repo._get_conn()
    insight_repo.apply_insight_schema(conn)
    payload = build_mirror(conn, "me")
    save_mirror(conn, "me", payload)
    repo.close()

    r = DashboardDBReader(db)
    r.connect()
    result = r.get_mirror("me")
    r.close()

    assert result is not None
    assert result["promises"]["phrase"] == "за вами долгов нет"
    assert "computed_at" in result


def test_endpoint_returns_empty_dict_without_mirror():
    import callprofiler.dashboard.server as server_mod

    saved_reader, saved_user = server_mod._DB_READER, server_mod._USER_ID
    server_mod._DB_READER = MagicMock()
    server_mod._DB_READER.get_mirror.return_value = None
    server_mod._USER_ID = "me"
    try:
        with TestClient(server_mod.app) as tc:
            resp = tc.get("/api/mirror")
            assert resp.status_code == 200
            assert resp.json() == {}
    finally:
        server_mod._DB_READER = saved_reader
        server_mod._USER_ID = saved_user


def test_endpoint_returns_payload_when_present():
    import callprofiler.dashboard.server as server_mod

    saved_reader, saved_user = server_mod._DB_READER, server_mod._USER_ID
    server_mod._DB_READER = MagicMock()
    server_mod._DB_READER.get_mirror.return_value = {
        "promises": {"phrase": "за вами долгов нет"},
    }
    server_mod._USER_ID = "me"
    try:
        with TestClient(server_mod.app) as tc:
            resp = tc.get("/api/mirror")
            assert resp.status_code == 200
            assert resp.json()["promises"]["phrase"] == "за вами долгов нет"
    finally:
        server_mod._DB_READER = saved_reader
        server_mod._USER_ID = saved_user
