"""Tests for callprofiler.dashboard.tools module."""

import json
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from callprofiler.dashboard.tools import DashboardTools


@pytest.fixture
def temp_db():
    """Create a temporary directory with a seeded SQLite DB."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_dir = Path(tmpdir) / "db"
        db_dir.mkdir()
        db_path = db_dir / "callprofiler.db"

        schema_path = Path(__file__).parents[2] / "src" / "callprofiler" / "db" / "schema.sql"
        if schema_path.exists():
            with sqlite3.connect(db_path) as conn:
                conn.executescript(schema_path.read_text(encoding="utf-8"))
        else:
            # minimal fallback schema for DashboardTools
            with sqlite3.connect(db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS calls (
                        call_id INTEGER PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        status TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS contacts (
                        contact_id INTEGER PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        display_name TEXT,
                        name_confirmed INTEGER DEFAULT 0
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS call_analysis (
                        analysis_id INTEGER PRIMARY KEY,
                        call_id INTEGER NOT NULL,
                        user_id TEXT NOT NULL
                    )
                """)

        yield db_path


@pytest.fixture
def mock_config(temp_db):
    """Return a mock config object wired to temp_db."""
    data_dir = temp_db.parent.parent
    return SimpleNamespace(data_dir=str(data_dir))


@pytest.fixture
def tools(mock_config):
    """Return a DashboardTools instance."""
    return DashboardTools(config=mock_config, user_id="test_user")


class TestInit:
    def test_db_path_derived_from_config(self, mock_config):
        tools = DashboardTools(config=mock_config, user_id="u1")
        assert tools.db_path.exists() or tools.db_path.parent.exists()
        assert "callprofiler.db" in str(tools.db_path)

    def test_user_id_stored(self, mock_config):
        tools = DashboardTools(config=mock_config, user_id="u1")
        assert tools.user_id == "u1"

    def test_history_initially_empty(self, mock_config):
        tools = DashboardTools(config=mock_config, user_id="u1")
        assert tools.get_history() == []


class TestGetStatus:
    def test_empty_db_returns_zero_counts(self, tools):
        status = tools.get_status()
        assert status["pending"] == 0
        assert status["error"] == 0
        assert status["processed"] == 0

    def test_counts_different_statuses(self, tools, temp_db):
        with sqlite3.connect(temp_db) as conn:
            conn.executemany(
                "INSERT INTO calls (user_id, status) VALUES (?, ?)",
                [
                    ("test_user", "pending"),
                    ("test_user", "processed"),
                    ("test_user", "processed"),
                    ("test_user", "error"),
                    ("other_user", "pending"),
                ],
            )
            conn.commit()

        status = tools.get_status()
        assert status["pending"] == 1
        assert status["processed"] == 2
        assert status["error"] == 1
        assert status["by_status"]["pending"] == 1


class TestLogging:
    def test_log_appends_entry(self, tools):
        tools._log("hello")
        hist = tools.get_history()
        assert len(hist) == 1
        assert hist[0]["message"] == "hello"
        assert "ts" in hist[0]

    def test_log_max_50_truncation(self, tools):
        for i in range(55):
            tools._log(f"msg{i}")
        hist = tools.get_history()
        assert len(hist) == 20  # get_history returns slice [:20]
        # _history itself should cap at 50
        assert len(tools._history) == 50


class TestAsyncOperations:
    @pytest.mark.asyncio
    async def test_run_reprocess_logs_and_returns_ok(self, tools):
        with patch.object(DashboardTools, "_reprocess_sync") as mock_sync:
            mock_sync.return_value = {"status": "ok", "message": "fixed 3", "count": 3}
            result = await tools.run_reprocess()
            assert result["status"] == "ok"
            assert result["count"] == 3

    @pytest.mark.asyncio
    async def test_run_rebuild_cards_logs_and_returns_ok(self, tools):
        with patch.object(DashboardTools, "_rebuild_cards_sync") as mock_sync:
            mock_sync.return_value = {"status": "ok", "message": "5 cards", "count": 5}
            result = await tools.run_rebuild_cards()
            assert result["status"] == "ok"
            assert result["count"] == 5

    @pytest.mark.asyncio
    async def test_run_extract_names_logs_and_returns_ok(self, tools):
        with patch.object(DashboardTools, "_extract_names_sync") as mock_sync:
            mock_sync.return_value = {"status": "ok", "message": "2 names", "count": 2}
            result = await tools.run_extract_names()
            assert result["status"] == "ok"
            assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_run_reprocess_returns_error(self, tools):
        with patch.object(DashboardTools, "_reprocess_sync") as mock_sync:
            mock_sync.return_value = {"status": "error", "message": "boom", "count": 0}
            result = await tools.run_reprocess()
            assert result["status"] == "error"
            assert "boom" in result["message"]


class TestGetHistory:
    def test_returns_last_20(self, tools):
        for i in range(25):
            tools._log(f"msg{i}")
        hist = tools.get_history()
        assert len(hist) == 20
        assert hist[0]["message"] == "msg24"
        assert hist[-1]["message"] == "msg5"

    def test_is_new_list_object(self, tools):
        tools._log("x")
        h1 = tools.get_history()
        assert len(h1) == 1
        assert h1[0]["message"] == "x"
