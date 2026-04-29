# -*- coding: utf-8 -*-
"""Tests for biography ↔ graph bridge helpers used by chapter generation."""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from callprofiler.db.repository import Repository
from callprofiler.graph.repository import apply_graph_schema
from callprofiler.biography.p6_chapters import _resolve_graph_entity_id


def _make_conn(user_id: str = "u1") -> sqlite3.Connection:
    repo = Repository(":memory:")
    repo.init_db()
    repo.add_user(
        user_id=user_id,
        display_name="Test",
        telegram_chat_id="0",
        incoming_dir="/tmp/in",
        sync_dir="/tmp/sync",
        ref_audio="/tmp/ref.wav",
    )
    conn = repo._get_conn()
    apply_graph_schema(conn)
    conn.row_factory = sqlite3.Row
    return conn


def test_resolve_graph_entity_by_contact_id():
    conn = _make_conn()
    conn.execute(
        """INSERT INTO contacts
           (user_id, phone_e164, display_name, guessed_name, name_confirmed)
           VALUES ('u1', '+70000000001', 'Вася', NULL, 1)"""
    )
    contact_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO entities (user_id, canonical_name, normalized_key, entity_type, aliases, archived)
           VALUES ('u1', 'Вася', 'vasya', 'PERSON', '[]', 0)"""
    )
    entity_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO calls
           (user_id, contact_id, direction, call_datetime, source_filename, source_md5, status)
           VALUES ('u1', ?, 'IN', '2026-01-01 10:00:00', 'f.mp3', 'md5-a', 'enriched')""",
        (contact_id,),
    )
    call_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO events
           (user_id, call_id, contact_id, entity_id, event_type, payload, confidence)
           VALUES ('u1', ?, ?, ?, 'fact', 'payload', 0.9)""",
        (call_id, contact_id, entity_id),
    )
    conn.commit()

    portrait = {
        "user_id": "u1",
        "entity_type": "PERSON",
        "canonical_name": "Вася",
        "contact_id": contact_id,
    }
    assert _resolve_graph_entity_id(portrait, conn) == entity_id


def test_resolve_graph_entity_by_alias_name():
    conn = _make_conn()
    conn.execute(
        """INSERT INTO entities (user_id, canonical_name, normalized_key, entity_type, aliases, archived)
           VALUES ('u1', 'Василий', 'vasiliy', 'PERSON', '["Вася"]', 0)"""
    )
    entity_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    portrait = {
        "user_id": "u1",
        "entity_type": "PERSON",
        "canonical_name": "Вася",
        "contact_id": None,
    }
    assert _resolve_graph_entity_id(portrait, conn) == entity_id
