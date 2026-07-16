# -*- coding: utf-8 -*-
"""test_card_v2.py — A6: карточка v2 — due:/grade:/call: строки, graceful degradation."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

from callprofiler.db.repository import Repository
from callprofiler.deliver.card_generator import MAX_CARD_BYTES, CardGenerator


def _repo(tmp_path, db_name="cardv2.db"):
    repo = Repository(str(tmp_path / db_name))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )
    return repo


def _empty_summary(repo, contact_id):
    repo.save_contact_summary(
        contact_id=contact_id, user_id="me", global_risk=40, contact_role="",
        top_hook="", open_promises=json.dumps([]), open_debts=json.dumps([]),
        personal_facts=json.dumps([]), advice="",
    )


def test_card_v2_shows_due_line_for_overdue_promise(tmp_path):
    repo = _repo(tmp_path)
    contact_id = repo.get_or_create_contact("me", "+79161234567", "Иванов")
    _empty_summary(repo, contact_id)

    conn = repo._get_conn()
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, source_filename, "
        "source_md5, status, duration_sec) VALUES (?,?,?,?,?,?,?,?)",
        ("me", contact_id, "IN", "2026-01-01T10:00:00", "f.mp3", "md5x", "done", 60),
    )
    call_id = cur.lastrowid
    conn.execute(
        "INSERT INTO events(user_id, contact_id, call_id, event_type, who, payload, "
        "deadline, status) VALUES (?,?,?,?,?,?,?,?)",
        ("me", contact_id, call_id, "promise", "OTHER", "Прислать документы", "2026-01-05", "open"),
    )
    conn.commit()

    gen = CardGenerator(repo)
    card = gen.generate_card("me", contact_id, now=datetime(2026, 1, 20, 9, 0))

    assert "due: Прислать документы (просрочено 15 дн.)" in card
    assert "grade:" in card
    assert len(card.encode("utf-8")) <= MAX_CARD_BYTES


def test_card_v2_no_due_line_when_nothing_overdue(tmp_path):
    repo = _repo(tmp_path)
    contact_id = repo.get_or_create_contact("me", "+79161234567", "Иванов")
    _empty_summary(repo, contact_id)

    gen = CardGenerator(repo)
    card = gen.generate_card("me", contact_id)

    assert "due:" not in card
    assert "grade:" in card


def test_card_v2_degrades_gracefully_without_insight_schema(tmp_path):
    """Только core-схема (нет entity_contact_map из insight-схемы) -> не падает, grade: F."""
    repo = _repo(tmp_path)
    contact_id = repo.get_or_create_contact("me", "+79161234567", "Иванов")
    _empty_summary(repo, contact_id)

    gen = CardGenerator(repo)
    card = gen.generate_card("me", contact_id)

    assert card != ""
    assert "grade: F" in card
    assert len(card.encode("utf-8")) <= MAX_CARD_BYTES


def test_card_v2_filename_canon_strips_plus_and_normalizes_leading_eight(tmp_path):
    repo = _repo(tmp_path, "canon.db")
    contact_id = repo.get_or_create_contact("me", "89161234567", "Петров")
    _empty_summary(repo, contact_id)

    gen = CardGenerator(repo)
    with tempfile.TemporaryDirectory() as tmpdir:
        gen.write_card("me", contact_id, tmpdir)
        assert (Path(tmpdir) / "79161234567.txt").exists()
