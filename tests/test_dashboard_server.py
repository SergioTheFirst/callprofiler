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


class TestExport:
    def test_export_calls_csv(self, client):
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.export_calls.return_value = [
            {"call_id": 1, "call_datetime": "2026-05-01 10:00", "direction": "IN",
             "duration_sec": 60, "status": "processed", "contact_label": "Иван",
             "phone_e164": "+700", "call_type": "business", "risk_score": 42,
             "summary": "тест"},
        ]
        resp = client.get("/api/export/calls.csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers.get("content-disposition", "")
        body = resp.text
        assert "call_id" in body      # header row present
        assert "Иван" in body         # data row, Cyrillic preserved
        assert "+700" in body

    def test_export_calls_csv_header_only_when_no_reader(self, client):
        import callprofiler.dashboard.server as server_mod
        saved = server_mod._DB_READER
        server_mod._DB_READER = None
        try:
            resp = client.get("/api/export/calls.csv")
            assert resp.status_code == 200
            assert "call_id" in resp.text  # header still emitted
        finally:
            server_mod._DB_READER = saved

    def test_export_book_md(self, client):
        """Phase 4 F2: /api/export/book.md streams the assembled biography as a
        markdown attachment (Cyrillic preserved)."""
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.export_book_markdown.return_value = (
            "# Жизнь\n\n## Глава 1\n\nтекст главы\n"
        )
        resp = client.get("/api/export/book.md")
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        assert "attachment" in resp.headers.get("content-disposition", "")
        body = resp.text
        assert "Глава 1" in body
        assert "текст главы" in body

    def test_export_book_md_placeholder_when_no_reader(self, client):
        import callprofiler.dashboard.server as server_mod
        saved = server_mod._DB_READER
        server_mod._DB_READER = None
        try:
            resp = client.get("/api/export/book.md")
            assert resp.status_code == 200
            assert resp.text.strip()  # always returns valid markdown
        finally:
            server_mod._DB_READER = saved


class TestEntitiesPersona:
    def test_entities_returns_personas_with_entity_id(self, client):
        """B.1: /api/entities lists graph personas (entity_id space) so the
        entity modal's /api/character/{entity_id} resolves to the same record."""
        import callprofiler.dashboard.server as server_mod
        server_mod._DB_READER.get_all_characters.return_value = [
            {"entity_id": 7, "canonical_name": "Пётр", "entity_type": "person",
             "total_calls": 12, "avg_risk": 55, "bs_index": 33.3,
             "character_label": "Холерик-достиженец", "has_psychology": True},
        ]
        resp = client.get("/api/entities?limit=50")
        assert resp.status_code == 200
        ents = resp.json()["entities"]
        assert len(ents) == 1
        assert ents[0]["entity_id"] == 7          # entity_id space (modal-compatible)
        assert ents[0]["canonical_name"] == "Пётр"
        assert "contact_id" not in ents[0]        # not contact-space anymore

    def test_entities_empty_when_no_reader(self, client):
        import callprofiler.dashboard.server as server_mod
        saved = server_mod._DB_READER
        server_mod._DB_READER = None
        try:
            resp = client.get("/api/entities")
            assert resp.status_code == 200
            assert resp.json()["entities"] == []
        finally:
            server_mod._DB_READER = saved
