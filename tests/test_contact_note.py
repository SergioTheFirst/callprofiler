# -*- coding: utf-8 -*-
"""test_contact_note.py — M6: заметка владельца на контакте (tools-канал)."""
from __future__ import annotations

import sqlite3

import pytest

from callprofiler.dashboard.tools import set_contact_note
from callprofiler.db.repository import Repository


@pytest.fixture
def db_with_contact(tmp_path):
    db_path = tmp_path / "notes.db"
    repo = Repository(str(db_path))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )
    contact_id = repo.get_or_create_contact("me", "+79161234567", "Иванов")
    repo.close()
    return str(db_path), contact_id


def _read_note(db_path, contact_id):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT note FROM contact_notes WHERE contact_id = ?", (contact_id,)
    ).fetchone()
    conn.close()
    return row["note"] if row else None


def test_set_note_creates_row(db_with_contact):
    db_path, contact_id = db_with_contact
    result = set_contact_note(db_path, "me", contact_id, "любит поговорить о рыбалке")

    assert result == {"note": "любит поговорить о рыбалке"}
    assert _read_note(db_path, contact_id) == "любит поговорить о рыбалке"


def test_set_note_overwrites_existing(db_with_contact):
    db_path, contact_id = db_with_contact
    set_contact_note(db_path, "me", contact_id, "первая заметка")
    result = set_contact_note(db_path, "me", contact_id, "вторая заметка")

    assert result == {"note": "вторая заметка"}
    assert _read_note(db_path, contact_id) == "вторая заметка"


def test_empty_note_deletes_row(db_with_contact):
    db_path, contact_id = db_with_contact
    set_contact_note(db_path, "me", contact_id, "будет удалено")
    result = set_contact_note(db_path, "me", contact_id, "")

    assert result == {"note": None}
    assert _read_note(db_path, contact_id) is None


def test_whitespace_only_note_deletes_row(db_with_contact):
    db_path, contact_id = db_with_contact
    set_contact_note(db_path, "me", contact_id, "заметка")
    result = set_contact_note(db_path, "me", contact_id, "   \n  ")

    assert result == {"note": None}
    assert _read_note(db_path, contact_id) is None


def test_note_stripped_and_capped_at_2000_chars(db_with_contact):
    db_path, contact_id = db_with_contact
    long_note = "  " + ("а" * 2500) + "  "
    result = set_contact_note(db_path, "me", contact_id, long_note)

    assert len(result["note"]) == 2000
    assert result["note"] == "а" * 2000


def test_ensures_schema_without_prior_insight_call(db_with_contact):
    """Таблица contact_notes НЕ создаётся init_db() — set_contact_note обязана
    сама её обеспечить (apply_insight_schema), не полагаясь на другие insight-команды."""
    db_path, contact_id = db_with_contact
    conn = sqlite3.connect(db_path)
    has_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='contact_notes'"
    ).fetchone()
    conn.close()
    assert has_table is None  # предпосылка: свежая core-схема без insight-таблиц

    result = set_contact_note(db_path, "me", contact_id, "проверка авто-схемы")
    assert result == {"note": "проверка авто-схемы"}


def test_user_isolation_other_user_cannot_overwrite(db_with_contact):
    """Guard `WHERE contact_notes.user_id = excluded.user_id` — чужой user_id
    не перезаписывает существующую заметку (contact_id глобально уникален)."""
    db_path, contact_id = db_with_contact
    set_contact_note(db_path, "me", contact_id, "заметка me")
    set_contact_note(db_path, "someone_else", contact_id, "заметка чужого")

    assert _read_note(db_path, contact_id) == "заметка me"


class TestContactNoteEndpoint:
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

    def test_valid_note_saved(self, client):
        tc, mock_tools = client
        mock_tools.run_contact_note.return_value = {"note": "saved text"}

        resp = tc.post("/api/tools/contact-note", json={"contact_id": 7, "note": "saved text"})

        assert resp.status_code == 200
        assert resp.json() == {"note": "saved text"}
        mock_tools.run_contact_note.assert_called_once_with(7, "saved text")

    def test_missing_contact_id_returns_400(self, client):
        tc, _ = client
        resp = tc.post("/api/tools/contact-note", json={"note": "x"})
        assert resp.status_code == 400

    def test_error_result_returns_400(self, client):
        tc, mock_tools = client
        mock_tools.run_contact_note.return_value = {"error": "boom"}

        resp = tc.post("/api/tools/contact-note", json={"contact_id": 1, "note": "x"})

        assert resp.status_code == 400
