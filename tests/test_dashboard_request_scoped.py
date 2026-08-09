# -*- coding: utf-8 -*-
"""test_dashboard_request_scoped.py — T-18: request-scoped loopback dashboard.

Covers the P-TEN-05 / P-WEB-01..03 fixes:
  - profile resolution is per-request (cookie), no shared mutable global
  - loopback-only startup enforcement
  - CSRF (double-submit cookie + Origin check) on mutating endpoints
  - streaming upload enforces the size cap while reading (no full buffering)
  - lifespan poller task is tracked and cancelled on shutdown
"""
from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from callprofiler.dashboard import assert_loopback_host
from callprofiler.dashboard.tools import DashboardTools
from callprofiler.db.repository import Repository


# ── P-TEN-05: profile is per-request, not a mutated global ────────────────

def test_no_mutable_global_profile_state():
    """Grep-level introspection: the only ``global _USER_ID`` statements left
    are in the two startup-configuration functions (_build_app/get_app) —
    no request handler assigns to it anymore."""
    src_path = Path(__file__).parent.parent / "src" / "callprofiler" / "dashboard" / "server.py"
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    allowed = {"_build_app", "get_app"}
    offenders = []

    def _walk(node, func_name):
        for child in ast.walk(node):
            if isinstance(child, ast.Global) and "_USER_ID" in child.names:
                if func_name not in allowed:
                    offenders.append(func_name)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _walk(node, node.name)

    assert offenders == [], f"unexpected mutation of _USER_ID in: {offenders}"


def test_users_select_sets_cookie_not_global():
    import callprofiler.dashboard.server as server_mod

    saved_user = server_mod._USER_ID
    server_mod._USER_ID = "default_profile"
    try:
        with TestClient(server_mod.app) as tc:
            resp = tc.post("/api/users/select?user=profile_b",
                            headers={"X-CSRF-Token": tc.get("/").cookies.get("cp_csrf") or ""})
        assert resp.status_code == 200
        assert resp.json() == {"active": "profile_b"}
        assert "cp_profile" in resp.cookies
        # the process-wide default must be untouched — no cross-tab leak
        assert server_mod._USER_ID == "default_profile"
    finally:
        server_mod._USER_ID = saved_user


def test_forged_profile_cookie_is_rejected(tmp_path):
    """Cookie приходит от клиента — доверять ей нельзя.

    Без валидации браузер (или любая страница, дотянувшаяся до loopback)
    назначал бы себе tenant-идентичность произвольной строкой. Неизвестный
    профиль обязан откатываться на стартовый дефолт, а /api/users/select —
    отказывать, а не выдавать cookie на несуществующий профиль.
    """
    import callprofiler.dashboard.server as server_mod

    db = tmp_path / "db" / "callprofiler.db"
    repo = Repository(str(db))
    repo.init_db()
    repo.add_user(user_id="alice", display_name="A", telegram_chat_id="0",
                   incoming_dir=str(tmp_path / "in_a"), sync_dir=str(tmp_path / "sync_a"),
                   ref_audio=str(tmp_path / "ref_a.wav"))
    conn = repo._get_conn()
    conn.execute(
        "INSERT INTO calls(user_id, direction, call_datetime, source_filename, "
        "source_md5, status) VALUES ('alice','IN','2026-01-01T00:00:00','a.mp3','md5a','done')"
    )
    conn.commit()
    repo.close()

    cfg = SimpleNamespace(data_dir=str(tmp_path))
    saved = (server_mod._DB_READER, server_mod._TOOLS, server_mod._CONFIG,
             server_mod._USER_ID, server_mod.app, server_mod._APP)
    server_mod._DB_READER = None
    server_mod._TOOLS = None
    try:
        app = server_mod.get_app("alice", cfg)
        with TestClient(app) as tc:
            # подделанный профиль -> откат на стартовый (alice), не на "mallory"
            tc.cookies.set("cp_profile", "mallory")
            assert tc.get("/api/overview").json()["calls_total"] == 1
            # путь-обход в cookie тоже не принимается
            tc.cookies.set("cp_profile", "../../etc")
            assert tc.get("/api/overview").json()["calls_total"] == 1
            # выбрать несуществующий профиль нельзя
            tc.cookies.clear()
            token = tc.get("/").cookies.get("cp_csrf") or ""
            assert tc.post("/api/users/select?user=mallory",
                           headers={"X-CSRF-Token": token}).status_code == 404
    finally:
        (server_mod._DB_READER, server_mod._TOOLS, server_mod._CONFIG,
         server_mod._USER_ID, server_mod.app, server_mod._APP) = saved


def test_two_profiles_do_not_contaminate_each_other(tmp_path):
    """Two 'browser tabs' (independent cookie jars) on different profiles
    must see only their own data — the exact P-TEN-05 scenario."""
    import callprofiler.dashboard.server as server_mod

    db = tmp_path / "db" / "callprofiler.db"
    repo = Repository(str(db))
    repo.init_db()
    repo.add_user(user_id="alice", display_name="A", telegram_chat_id="0",
                   incoming_dir=str(tmp_path / "in_a"), sync_dir=str(tmp_path / "sync_a"),
                   ref_audio=str(tmp_path / "ref_a.wav"))
    repo.add_user(user_id="bob", display_name="B", telegram_chat_id="0",
                   incoming_dir=str(tmp_path / "in_b"), sync_dir=str(tmp_path / "sync_b"),
                   ref_audio=str(tmp_path / "ref_b.wav"))
    conn = repo._get_conn()
    conn.execute(
        "INSERT INTO calls(user_id, direction, call_datetime, source_filename, "
        "source_md5, status) VALUES ('alice','IN','2026-01-01T00:00:00','a.mp3','md5a','done')"
    )
    conn.commit()
    repo.close()

    cfg = SimpleNamespace(data_dir=str(tmp_path))
    saved_reader, saved_tools, saved_config, saved_user, saved_app, saved_app_obj = (
        server_mod._DB_READER, server_mod._TOOLS, server_mod._CONFIG, server_mod._USER_ID,
        server_mod.app, server_mod._APP,
    )
    server_mod._DB_READER = None
    server_mod._TOOLS = None
    try:
        app = server_mod.get_app("alice", cfg)
        with TestClient(app) as tc:
            tc.cookies.set("cp_profile", "alice")
            r_alice = tc.get("/api/overview").json()
            tc.cookies.set("cp_profile", "bob")
            r_bob = tc.get("/api/overview").json()

        assert r_alice["calls_total"] == 1
        assert r_bob["calls_total"] == 0
    finally:
        server_mod._DB_READER, server_mod._TOOLS, server_mod._CONFIG, server_mod._USER_ID = (
            saved_reader, saved_tools, saved_config, saved_user,
        )
        server_mod.app, server_mod._APP = saved_app, saved_app_obj


# ── P-WEB-01: loopback-only startup ────────────────────────────────────────

@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "127.5.5.5"])
def test_loopback_hosts_accepted(host):
    assert_loopback_host(host)  # must not raise


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "::", "example.com", ""])
def test_non_loopback_hosts_rejected(host):
    with pytest.raises(RuntimeError):
        assert_loopback_host(host)


# ── CSRF (Origin + double-submit token) ────────────────────────────────────

@pytest.fixture
def csrf_client():
    import callprofiler.dashboard.server as server_mod
    with TestClient(server_mod.app) as tc:
        yield tc


class TestCsrf:
    def test_mutation_without_token_rejected(self, csrf_client):
        resp = csrf_client.post("/api/tools/reprocess")
        assert resp.status_code == 403

    def test_mutation_with_wrong_token_rejected(self, csrf_client):
        csrf_client.get("/")  # seed real cookie
        resp = csrf_client.post("/api/tools/reprocess", headers={"X-CSRF-Token": "forged"})
        assert resp.status_code == 403

    def test_mutation_with_mismatched_origin_rejected(self, csrf_client):
        token = csrf_client.get("/").cookies.get("cp_csrf")
        resp = csrf_client.post(
            "/api/tools/reprocess",
            headers={"X-CSRF-Token": token, "Origin": "http://evil.example"},
        )
        assert resp.status_code == 403

    def test_mutation_with_valid_token_accepted(self, csrf_client):
        token = csrf_client.get("/").cookies.get("cp_csrf")
        resp = csrf_client.post("/api/tools/reprocess", headers={"X-CSRF-Token": token})
        assert resp.status_code == 200

    def test_get_requests_never_require_csrf(self, csrf_client):
        resp = csrf_client.get("/api/overview")
        assert resp.status_code == 200


# ── P-WEB-02: streaming upload, size cap enforced while reading ───────────

class TestStreamingUpload:
    @pytest.mark.asyncio
    async def test_oversized_upload_aborts_without_reading_everything(self, tmp_path, monkeypatch):
        import callprofiler.dashboard.tools as tools_mod

        monkeypatch.setattr(tools_mod, "_IMPORT_MAX_BYTES", 100)
        db = tmp_path / "db" / "callprofiler.db"
        repo = Repository(str(db))
        repo.init_db()
        repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                       incoming_dir=str(tmp_path / "in"), sync_dir=str(tmp_path / "sync"),
                       ref_audio=str(tmp_path / "r.wav"))
        repo.close()

        chunks_seen = []

        async def body():
            # 20 chunks of 20 bytes = 400 bytes total, way over the 100-byte cap.
            for _ in range(20):
                chunks_seen.append(1)
                yield b"x" * 20

        cfg = SimpleNamespace(data_dir=str(tmp_path))
        dt = DashboardTools(cfg, "me")
        result = await dt.run_import_audio_stream("call.mp3", body())

        assert result == {"error": "file too large"}
        # aborted well before exhausting the generator — proves the cap is
        # enforced WHILE reading, not after buffering the full body.
        assert len(chunks_seen) < 20
        assert not list((tmp_path / "in").glob("*.part"))

    @pytest.mark.asyncio
    async def test_valid_stream_saves_file(self, tmp_path):
        db = tmp_path / "db" / "callprofiler.db"
        repo = Repository(str(db))
        repo.init_db()
        repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                       incoming_dir=str(tmp_path / "in"), sync_dir=str(tmp_path / "sync"),
                       ref_audio=str(tmp_path / "r.wav"))
        repo.close()

        async def body():
            yield b"hello "
            yield b"world"

        cfg = SimpleNamespace(data_dir=str(tmp_path))
        dt = DashboardTools(cfg, "me")
        result = await dt.run_import_audio_stream("call.mp3", body())

        assert result == {"saved": "call.mp3", "bytes": 11}
        assert (tmp_path / "in" / "call.mp3").read_bytes() == b"hello world"


# ── P-WEB-03: lifespan tracks + cancels the poller task ────────────────────

def test_lifespan_cancels_poller_task_on_shutdown(monkeypatch, tmp_path):
    import callprofiler.dashboard.server as server_mod

    created = []
    real_create_task = asyncio.create_task

    def _spy_create_task(coro, *a, **kw):
        t = real_create_task(coro, *a, **kw)
        created.append(t)
        return t

    monkeypatch.setattr(server_mod.asyncio, "create_task", _spy_create_task)

    cfg = SimpleNamespace(data_dir=str(tmp_path))
    saved_config, saved_app, saved_app_obj = server_mod._CONFIG, server_mod.app, server_mod._APP
    try:
        app = server_mod.get_app("me", cfg)
        with TestClient(app):
            assert len(created) == 1
            assert not created[0].done()
        # after the lifespan context manager exits, the poller task must be
        # cancelled — not leaked to run forever creating new DB connections.
        assert created[0].done()
    finally:
        server_mod._CONFIG = saved_config
        server_mod.app, server_mod._APP = saved_app, saved_app_obj
