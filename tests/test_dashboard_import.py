# -*- coding: utf-8 -*-
"""test_dashboard_import.py — M5: drag&drop audio import (security-sensitive)."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from callprofiler.dashboard.tools import save_incoming_audio


def _seed_user(db_path: Path, user_id: str, incoming_dir: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO users(user_id, display_name, telegram_chat_id, incoming_dir, "
        "sync_dir, ref_audio) VALUES (?,?,?,?,?,?)",
        (user_id, "T", "0", incoming_dir, "/tmp/sync", "/tmp/r.wav"),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def db_and_incoming(tmp_path):
    schema_path = Path(__file__).parent.parent / "src" / "callprofiler" / "db" / "schema.sql"
    db_path = tmp_path / "cp.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.close()

    incoming = tmp_path / "in"
    incoming.mkdir()
    _seed_user(db_path, "me", str(incoming))
    return str(db_path), incoming


class TestSaveIncomingAudio:
    def test_saves_valid_file(self, db_and_incoming):
        db_path, incoming = db_and_incoming
        result = save_incoming_audio(db_path, "me", "call.mp3", b"fake audio bytes")

        assert result == {"saved": "call.mp3", "bytes": 16}
        assert (incoming / "call.mp3").read_bytes() == b"fake audio bytes"
        assert not (incoming / "call.mp3.part").exists()

    def test_path_traversal_confined_to_incoming_dir(self, db_and_incoming):
        db_path, incoming = db_and_incoming
        result = save_incoming_audio(db_path, "me", "..\\..\\evil.mp3", b"x")

        assert result["saved"] == "evil.mp3"
        saved_file = incoming / "evil.mp3"
        assert saved_file.exists()
        assert saved_file.resolve().parent == incoming.resolve()

    def test_path_traversal_unix_style(self, db_and_incoming):
        db_path, incoming = db_and_incoming
        result = save_incoming_audio(db_path, "me", "../../etc/evil.mp3", b"x")

        assert result["saved"] == "evil.mp3"
        assert (incoming / "evil.mp3").exists()

    @pytest.mark.parametrize("name", ["CON.mp3", "nul.wav", "com1.mp3", "Lpt3.flac"])
    def test_windows_reserved_device_name_rejected(self, db_and_incoming, name):
        db_path, incoming = db_and_incoming
        result = save_incoming_audio(db_path, "me", name, b"x")

        assert result == {"error": "reserved filename"}
        assert list(incoming.iterdir()) == []

    def test_unsupported_extension_rejected(self, db_and_incoming):
        db_path, incoming = db_and_incoming
        result = save_incoming_audio(db_path, "me", "malware.exe", b"x")

        assert result == {"error": "unsupported type"}
        assert list(incoming.iterdir()) == []

    def test_empty_body_rejected(self, db_and_incoming):
        db_path, _ = db_and_incoming
        result = save_incoming_audio(db_path, "me", "call.mp3", b"")

        assert result == {"error": "empty file"}

    def test_oversized_file_rejected(self, db_and_incoming):
        db_path, incoming = db_and_incoming
        result = save_incoming_audio(db_path, "me", "call.mp3", b"x" * (513 * 1024 * 1024))

        assert result == {"error": "file too large"}
        assert list(incoming.iterdir()) == []

    def test_name_collision_gets_suffix(self, db_and_incoming):
        db_path, incoming = db_and_incoming
        (incoming / "call.mp3").write_bytes(b"existing")

        result = save_incoming_audio(db_path, "me", "call.mp3", b"new bytes")

        assert result["saved"] == "call-1.mp3"
        assert (incoming / "call.mp3").read_bytes() == b"existing"
        assert (incoming / "call-1.mp3").read_bytes() == b"new bytes"

    def test_unknown_user_rejected(self, db_and_incoming):
        db_path, _ = db_and_incoming
        result = save_incoming_audio(db_path, "ghost", "call.mp3", b"x")

        assert result == {"error": "unknown user or incoming_dir not configured"}

    def test_no_part_file_left_behind(self, db_and_incoming):
        db_path, incoming = db_and_incoming
        save_incoming_audio(db_path, "me", "call.wav", b"data")

        leftovers = [f for f in incoming.iterdir() if f.suffix == ".part"]
        assert leftovers == []


@pytest.fixture
def client():
    import callprofiler.dashboard.server as server_mod

    mock_tools = MagicMock()
    saved_tools = server_mod._TOOLS
    saved_user = server_mod._USER_ID
    server_mod._TOOLS = mock_tools
    server_mod._USER_ID = "test_user"

    from fastapi.testclient import TestClient

    with TestClient(server_mod.app) as tc:
        tc.headers.update({"X-CSRF-Token": tc.get("/").cookies.get("cp_csrf") or ""})
        yield tc, mock_tools

    server_mod._TOOLS = saved_tools
    server_mod._USER_ID = saved_user


class TestImportAudioEndpoint:
    def test_valid_upload_returns_saved(self, client):
        tc, mock_tools = client
        mock_tools.run_import_audio_stream.return_value = {"saved": "call.mp3", "bytes": 4}

        resp = tc.post("/api/tools/import-audio?name=call.mp3", content=b"data")

        assert resp.status_code == 200
        assert resp.json() == {"saved": "call.mp3", "bytes": 4}
        mock_tools.run_import_audio_stream.assert_called_once()
        args = mock_tools.run_import_audio_stream.call_args[0]
        assert args[0] == "call.mp3"
        # 2nd arg is Request.stream() — an async chunk iterator, not raw bytes
        # (P-WEB-02: body must never be buffered in memory before the check).

    def test_error_result_returns_400(self, client):
        tc, mock_tools = client
        mock_tools.run_import_audio_stream.return_value = {"error": "unsupported type"}

        resp = tc.post("/api/tools/import-audio?name=evil.exe", content=b"data")

        assert resp.status_code == 400
        assert resp.json() == {"error": "unsupported type"}

    def test_missing_run_import_audio_stream_falls_back(self, client):
        tc, mock_tools = client
        del mock_tools.run_import_audio_stream

        resp = tc.post("/api/tools/import-audio?name=call.mp3", content=b"data")

        assert resp.status_code == 200
