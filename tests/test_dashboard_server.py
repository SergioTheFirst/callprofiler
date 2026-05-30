"""Tests for callprofiler.dashboard.server — FastAPI endpoints."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create TestClient with mocked DB reader and tools."""
    import callprofiler.dashboard.server as server_mod

    mock_reader = MagicMock()
    mock_tools = MagicMock()
    mock_tools.get_status.return_value = {
        "by_status": {}, "pending": 0, "error": 0, "processed": 0,
    }
    mock_tools.get_history.return_value = []

    saved_reader = server_mod._DB_READER
    saved_tools = server_mod._TOOLS
    saved_user = server_mod._USER_ID

    server_mod._DB_READER = mock_reader
    server_mod._TOOLS = mock_tools
    server_mod._USER_ID = "test_user"

    with TestClient(server_mod.app) as tc:
        yield tc

    server_mod._DB_READER = saved_reader
    server_mod._TOOLS = saved_tools
    server_mod._USER_ID = saved_user


class TestCoreEndpoints:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_favicon(self, client):
        resp = client.get("/favicon.ico")
        assert resp.status_code == 200

    def test_api_stats(self, client):
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.get_stats.return_value = {
            "total_calls": 10, "total_entities": 3, "total_portraits": 2,
            "avg_risk": 35.0, "last_call_datetime": "2024-01-01T00:00:00",
        }
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("total_calls") == 10

    def test_api_history(self, client):
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.get_recent_calls.return_value = []
        resp = client.get("/api/history?limit=10")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestToolsEndpoints:
    def test_tools_status(self, client):
        resp = client.get("/api/tools/status")
        assert resp.status_code == 200

    def test_tools_history(self, client):
        resp = client.get("/api/tools/history")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_tools_reprocess(self, client):
        import callprofiler.dashboard.server as server_mod
        mock_run = MagicMock()
        mock_run.return_value = {"status": "ok", "message": "done", "count": 0}
        server_mod._TOOLS.run_reprocess = mock_run
        resp = client.post("/api/tools/reprocess")
        assert resp.status_code == 200

    def test_tools_extract_names(self, client):
        import callprofiler.dashboard.server as server_mod
        mock_run = MagicMock()
        mock_run.return_value = {"status": "ok", "message": "done", "count": 0}
        server_mod._TOOLS.run_extract_names = mock_run
        resp = client.post("/api/tools/extract-names")
        assert resp.status_code == 200

    def test_tools_rebuild_cards(self, client):
        import callprofiler.dashboard.server as server_mod
        mock_run = MagicMock()
        mock_run.return_value = {"status": "ok", "message": "done", "count": 0}
        server_mod._TOOLS.run_rebuild_cards = mock_run
        resp = client.post("/api/tools/rebuild-cards")
        assert resp.status_code == 200


class TestCharacterEndpoints:
    def test_characters_list(self, client):
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.get_all_characters.return_value = [
            {"entity_id": 1, "canonical_name": "Alice", "entity_type": "PERSON",
             "risk_label": "low", "call_count": 5},
        ]
        resp = client.get("/api/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_character_profile_found(self, client):
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.get_character_profile.return_value = {
            "entity_id": 1, "canonical_name": "Alice", "entity_type": "PERSON",
            "character_summary": "A helpful person", "psychology": {},
            "temperament_label": "Sanguine", "motivation_summary": "",
            "risk_score": 20, "risk_trend": "stable", "contradictions": [],
            "promises": {"open": 0, "total": 0}, "calls": [],
        }
        resp = client.get("/api/character/1")
        assert resp.status_code == 200
        assert resp.json()["canonical_name"] == "Alice"

    def test_character_profile_not_found(self, client):
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.get_character_profile.return_value = None
        resp = client.get("/api/character/999")
        assert resp.status_code == 200
        assert resp.json()["canonical_name"] == "?"


class TestContactEndpoints:
    def test_contact_found(self, client):
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.get_contact_profile.return_value = {
            "contact_id": 1, "display_name": "Bob", "phone_e164": "+123",
            "call_count": 3, "last_call": "2024-01-01",
            "linked_entities": [], "recent_calls": [],
        }
        resp = client.get("/api/contact/1")
        assert resp.status_code == 200

    def test_contact_not_found(self, client):
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.get_contact_profile.return_value = None
        resp = client.get("/api/contact/999")
        assert resp.status_code == 200


class TestAnalytics:
    def test_analytics_returns_dict(self, client):
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.get_analytics.return_value = {"distributions": {}}
        resp = client.get("/api/analytics")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)


class TestUninitialized:
    def test_characters_empty_when_no_reader(self, client):
        import callprofiler.dashboard.server as server_mod
        saved = server_mod._DB_READER
        server_mod._DB_READER = None
        try:
            resp = client.get("/api/characters")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            server_mod._DB_READER = saved

    def test_tools_status_default_when_no_tools(self, client):
        import callprofiler.dashboard.server as server_mod
        saved = server_mod._TOOLS
        server_mod._TOOLS = None
        try:
            resp = client.get("/api/tools/status")
            assert resp.status_code == 200
        finally:
            server_mod._TOOLS = saved


# ── Dashboard v3 Slice 4: CSV export + audio endpoints (real DB) ───────────
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace


@pytest.fixture
def real_client():
    """TestClient backed by a real temp SQLite DB (for export/audio routes)."""
    import callprofiler.dashboard.server as server_mod

    tmpdir = tempfile.mkdtemp()
    db_dir = Path(tmpdir) / "db"
    db_dir.mkdir()
    db_path = db_dir / "callprofiler.db"

    schema_path = (
        Path(__file__).parents[1] / "src" / "callprofiler" / "db" / "schema.sql"
    )
    audio_file = Path(tmpdir) / "call1.wav"
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")  # tiny stub

    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        # schema_version & graph columns are added by this migration at runtime.
        from callprofiler.graph.repository import apply_graph_schema
        apply_graph_schema(conn)
        # FK enforcement is off by default in sqlite3, so no users row needed.
        # Call 1: has an audio file on disk
        conn.execute(
            """INSERT INTO calls (call_id, user_id, direction, source_filename,
                   source_md5, audio_path, norm_path, duration_sec, status,
                   updated_at)
               VALUES (1,'test_user','incoming','call1.m4a','md5-1',?,?,90,'done',
                   '2026-05-30 10:00:00')""",
            (str(audio_file), str(audio_file)),
        )
        # Call 2: norm_path points to a missing file
        conn.execute(
            """INSERT INTO calls (call_id, user_id, direction, source_filename,
                   source_md5, norm_path, status, updated_at)
               VALUES (2,'test_user','outgoing','call2.m4a','md5-2',
                   '/no/such/file.wav','done','2026-05-30 11:00:00')""",
        )
        conn.execute(
            """INSERT INTO analyses (call_id, risk_score, summary, call_type, flags)
               VALUES (1,42,'Test summary','business','{}')"""
        )
        conn.execute(
            """INSERT INTO transcripts (call_id, start_ms, end_ms, text, speaker)
               VALUES (1,1000,2000,'hello there','OWNER')"""
        )
        conn.commit()

    saved_cfg = server_mod._CONFIG
    saved_user = server_mod._USER_ID
    server_mod._CONFIG = SimpleNamespace(data_dir=str(db_path))
    server_mod._USER_ID = "test_user"

    with TestClient(server_mod.app) as tc:
        yield tc

    server_mod._CONFIG = saved_cfg
    server_mod._USER_ID = saved_user


class TestSlice4Export:
    def test_export_returns_csv(self, real_client):
        resp = real_client.get("/api/calls/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers.get("content-disposition", "")
        body = resp.text
        assert "call_id" in body  # header row
        assert "Test summary" in body  # data row

    def test_export_status_filter(self, real_client):
        resp = real_client.get("/api/calls/export?status=error")
        assert resp.status_code == 200
        # No error-status calls seeded → only the header row remains
        lines = [ln for ln in resp.text.splitlines() if ln.strip()]
        assert len(lines) == 1

    def test_export_no_config(self, client):
        # mocked `client` fixture leaves _CONFIG = None
        resp = client.get("/api/calls/export")
        assert resp.status_code == 200
        assert resp.json() == {"calls": []}


class TestSlice4Audio:
    def test_audio_served_when_file_exists(self, real_client):
        resp = real_client.get("/api/calls/1/audio")
        assert resp.status_code == 200
        assert resp.content.startswith(b"RIFF")

    def test_audio_404_when_file_missing(self, real_client):
        resp = real_client.get("/api/calls/2/audio")
        assert resp.status_code == 404

    def test_audio_404_when_call_missing(self, real_client):
        resp = real_client.get("/api/calls/999/audio")
        assert resp.status_code == 404

    def test_detail_does_not_leak_paths(self, real_client):
        resp = real_client.get("/api/calls/1")
        assert resp.status_code == 200
        data = resp.json()
        assert "norm_path" not in data
        assert "audio_path" not in data
