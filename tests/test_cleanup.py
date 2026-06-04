# -*- coding: utf-8 -*-
"""
test_cleanup.py — деструктивная чистка: delete_calls / purge_user.

Проверяет: dry-run (apply=False) ничего не трогает; apply=True удаляет звонок и
все зависимые строки; FTS5-индекс остаётся консистентным (поиск не находит
удалённое); идемпотентность; изоляция по user_id; путь TEMP-таблицы при числе
id > лимита параметров SQLite.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from callprofiler.db.repository import Repository
from callprofiler.models import Analysis, Segment


@pytest.fixture
def repo():
    r = Repository(":memory:")
    r.init_db()
    return r


def _add_user(repo, user_id="user1"):
    repo.add_user(
        user_id=user_id,
        display_name="Тест",
        telegram_chat_id="1",
        incoming_dir="/tmp/in",
        sync_dir="/tmp/sync",
        ref_audio="/tmp/ref.wav",
    )


def _add_call(repo, user_id="user1", md5="m", text="уникальноеслово", with_analysis=True):
    contact_id = repo.get_or_create_contact(user_id, "+79160000000", "Контакт")
    call_id = repo.create_call(
        user_id=user_id,
        contact_id=contact_id,
        direction="IN",
        call_datetime="2026-03-28 10:00:00",
        source_filename=f"{md5}.mp3",
        source_md5=md5,
        audio_path=f"/tmp/{md5}.mp3",
    )
    repo.save_transcripts(
        call_id, [Segment(start_ms=0, end_ms=500, text=text, speaker="OWNER")]
    )
    if with_analysis:
        repo.save_analysis(call_id, Analysis(priority=10, risk_score=5, summary="ok"))
    return call_id, contact_id


# ── delete_calls ───────────────────────────────────────────────────────────

def test_delete_calls_dryrun_changes_nothing(repo):
    _add_user(repo)
    call_id, _ = _add_call(repo)
    counts = repo.delete_calls([call_id], apply=False)
    assert counts["calls"] == 1
    assert counts["transcripts"] == 1
    assert counts["analyses"] == 1
    # Ничего не удалено
    assert repo.get_transcript(call_id)
    assert repo.search_transcripts("user1", "уникальноеслово")


def test_delete_calls_apply_removes_all_and_fts(repo):
    _add_user(repo)
    call_id, _ = _add_call(repo)
    repo.delete_calls([call_id], apply=True)
    assert repo.get_transcript(call_id) == []
    assert repo.get_analysis("user1", call_id) is None
    # FTS пересобран → удалённый текст не находится
    assert repo.search_transcripts("user1", "уникальноеслово") == []


def test_delete_calls_idempotent(repo):
    _add_user(repo)
    call_id, _ = _add_call(repo)
    repo.delete_calls([call_id], apply=True)
    counts = repo.delete_calls([call_id], apply=True)
    assert counts["calls"] == 0  # уже удалён — второй проход = 0


def test_delete_calls_keeps_other_calls_fts(repo):
    _add_user(repo)
    keep_id, _ = _add_call(repo, md5="keep", text="остаётсятекст")
    drop_id, _ = _add_call(repo, md5="drop", text="удаляемыйтекст")
    repo.delete_calls([drop_id], apply=True)
    # Оставшийся звонок ищется, удалённый — нет
    assert repo.search_transcripts("user1", "остаётсятекст")
    assert repo.search_transcripts("user1", "удаляемыйтекст") == []


def test_delete_calls_handles_many_ids_no_param_limit(repo):
    """>999 id не должны падать с 'too many SQL variables' (TEMP-таблица)."""
    _add_user(repo)
    call_id, _ = _add_call(repo)
    ids = list(range(5000)) + [call_id]  # 5001 id, реальный один
    counts = repo.delete_calls(ids, apply=True)
    assert counts["calls"] == 1
    assert repo.get_transcript(call_id) == []


def test_delete_calls_empty_noop(repo):
    counts = repo.delete_calls([], apply=True)
    assert counts == {"calls": 0, "transcripts": 0, "analyses": 0, "events": 0, "promises": 0}


# ── purge_user ─────────────────────────────────────────────────────────────

def test_purge_user_dryrun_changes_nothing(repo):
    _add_user(repo)
    _add_call(repo)
    counts = repo.purge_user("user1", apply=False)
    assert counts["users"] == 1
    assert counts["calls"] == 1
    assert repo.get_user("user1") is not None


def test_purge_user_apply_removes_everything(repo):
    _add_user(repo)
    call_id, _ = _add_call(repo)
    repo.purge_user("user1", apply=True)
    assert repo.get_user("user1") is None
    assert repo.get_transcript(call_id) == []
    assert repo.search_transcripts("user1", "уникальноеслово") == []


def test_purge_user_isolated(repo):
    _add_user(repo, "u1")
    _add_user(repo, "u2")
    c1, _ = _add_call(repo, user_id="u1", md5="a", text="первыйюзер")
    c2, _ = _add_call(repo, user_id="u2", md5="b", text="второйюзер")
    repo.purge_user("u1", apply=True)
    # u1 снесён, u2 цел (включая FTS)
    assert repo.get_user("u1") is None
    assert repo.get_user("u2") is not None
    assert repo.get_transcript(c2)
    assert repo.search_transcripts("u2", "второйюзер")
    assert repo.search_transcripts("u1", "первыйюзер") == []
