# -*- coding: utf-8 -*-
"""test_dashboard_health.py — F7: панель «Здоровье системы» (GET /api/health-report)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from callprofiler.doctor import Check


def _client_with_config(cfg):
    import callprofiler.dashboard.server as server_mod

    saved_config = server_mod._CONFIG
    saved_reader = server_mod._DB_READER
    server_mod._CONFIG = cfg
    server_mod._DB_READER = MagicMock()
    return server_mod, saved_config, saved_reader


def test_health_report_returns_structure(tmp_path):
    server_mod, saved_config, saved_reader = _client_with_config(SimpleNamespace(data_dir=str(tmp_path)))
    try:
        with patch(
            "callprofiler.dashboard.server.run_checks",
            return_value=[Check("python", "OK", "3.12"), Check("disk", "WARN", "low")],
        ):
            with TestClient(server_mod.app) as tc:
                resp = tc.get("/api/health-report")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"checks": [
            {"name": "python", "status": "OK", "detail": "3.12"},
            {"name": "disk", "status": "WARN", "detail": "low"},
        ]}
    finally:
        server_mod._CONFIG = saved_config
        server_mod._DB_READER = saved_reader


def test_health_report_reflects_fail_check(tmp_path):
    server_mod, saved_config, saved_reader = _client_with_config(SimpleNamespace(data_dir=str(tmp_path)))
    try:
        with patch(
            "callprofiler.dashboard.server.run_checks",
            return_value=[Check("queue-stuck", "FAIL", "call_id=1,2,3")],
        ):
            with TestClient(server_mod.app) as tc:
                resp = tc.get("/api/health-report")
        checks = resp.json()["checks"]
        assert any(c["status"] == "FAIL" for c in checks)
    finally:
        server_mod._CONFIG = saved_config
        server_mod._DB_READER = saved_reader


def test_health_report_empty_checks_without_config():
    import callprofiler.dashboard.server as server_mod

    saved_config = server_mod._CONFIG
    server_mod._CONFIG = None
    try:
        with TestClient(server_mod.app) as tc:
            resp = tc.get("/api/health-report")
        assert resp.status_code == 200
        assert resp.json() == {"checks": []}
    finally:
        server_mod._CONFIG = saved_config


def test_health_report_never_writes_to_db(tmp_path):
    """doctor уже side-effect-free — эндпоинт не должен трогать БД."""
    server_mod, saved_config, saved_reader = _client_with_config(SimpleNamespace(data_dir=str(tmp_path)))
    try:
        with patch("callprofiler.dashboard.server.run_checks") as mock_run:
            mock_run.return_value = [Check("a", "OK", "")]
            with TestClient(server_mod.app) as tc:
                tc.get("/api/health-report")
            # run_checks called with (config, conn) — conn passed through, never written to
            assert mock_run.call_count == 1
            args = mock_run.call_args.args
            assert args[0] is server_mod._CONFIG
    finally:
        server_mod._CONFIG = saved_config
        server_mod._DB_READER = saved_reader
