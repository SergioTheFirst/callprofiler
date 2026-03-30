# -*- coding: utf-8 -*-
"""
test_repository.py — тесты Repository с in-memory SQLite.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from callprofiler.db.repository import Repository
from callprofiler.models import Analysis, Segment


@pytest.fixture
def repo(tmp_path):
    r = Repository(":memory:")
    r.init_db()
    return r


def add_user(repo, user_id="user1"):
    repo.add_user(
        user_id=user_id,
        display_name="Тест",
        telegram_chat_id="123",
        incoming_dir="/tmp/in",
        sync_dir="/tmp/sync",
        ref_audio="/tmp/ref.wav",
    )


def add_call(repo, user_id="user1", md5="abc123"):
    contact_id = repo.get_or_create_contact(user_id, "+79161234567", "Иванов")
    call_id = repo.create_call(
        user_id=user_id,
        contact_id=contact_id,
        direction="IN",
        call_datetime="2026-03-28 14:30:00",
        source_filename="test.mp3",
        source_md5=md5,
        audio_path="/tmp/test.mp3",
    )
    return call_id, contact_id


# ---- Users ----

def test_add_and_get_user(repo):
    add_user(repo)
    u = repo.get_user("user1")
    assert u is not None
    assert u["display_name"] == "Тест"
    assert u["telegram_chat_id"] == "123"


def test_get_all_users(repo):
    add_user(repo, "u1")
    add_user(repo, "u2")
    users = repo.get_all_users()
    assert len(users) == 2


def test_get_nonexistent_user(repo):
    assert repo.get_user("nobody") is None


# ---- Contacts ----

def test_get_or_create_contact_idempotent(repo):
    add_user(repo)
    id1 = repo.get_or_create_contact("user1", "+79161234567", "Иванов")
    id2 = repo.get_or_create_contact("user1", "+79161234567", "Иванов")
    assert id1 == id2


def test_contact_isolation_by_user(repo):
    add_user(repo, "u1")
    add_user(repo, "u2")
    id1 = repo.get_or_create_contact("u1", "+79161234567")
    id2 = repo.get_or_create_contact("u2", "+79161234567")
    # Разные пользователи — разные строки контактов
    assert id1 != id2


def test_get_contact_by_phone(repo):
    add_user(repo)
    repo.get_or_create_contact("user1", "+79161234567", "Иванов")
    c = repo.get_contact_by_phone("user1", "+79161234567")
    assert c is not None
    assert c["display_name"] == "Иванов"


def test_get_contact_by_phone_wrong_user(repo):
    add_user(repo, "u1")
    add_user(repo, "u2")
    repo.get_or_create_contact("u1", "+79161234567")
    assert repo.get_contact_by_phone("u2", "+79161234567") is None


# ---- Calls ----

def test_create_and_get_call(repo):
    add_user(repo)
    call_id, _ = add_call(repo)
    calls = repo.get_calls_for_user("user1")
    assert len(calls) == 1
    assert calls[0]["call_id"] == call_id
    assert calls[0]["direction"] == "IN"


def test_call_exists(repo):
    add_user(repo)
    add_call(repo, md5="md5_1")
    assert repo.call_exists("user1", "md5_1") is True
    assert repo.call_exists("user1", "md5_other") is False


def test_call_exists_isolation(repo):
    add_user(repo, "u1")
    add_user(repo, "u2")
    add_call(repo, user_id="u1", md5="same_md5")
    assert repo.call_exists("u2", "same_md5") is False


def test_update_call_status(repo):
    add_user(repo)
    call_id, _ = add_call(repo)
    repo.update_call_status(call_id, "transcribing")
    calls = repo.get_calls_for_user("user1")
    assert calls[0]["status"] == "transcribing"


def test_update_call_status_error_increments_retry(repo):
    add_user(repo)
    call_id, _ = add_call(repo)
    repo.update_call_status(call_id, "error", error_message="что-то сломалось")
    calls = repo.get_calls_for_user("user1")
    assert calls[0]["retry_count"] == 1
    assert calls[0]["error_message"] == "что-то сломалось"


def test_get_pending_calls(repo):
    add_user(repo)
    add_call(repo, md5="m1")
    add_call(repo, md5="m2")
    pending = repo.get_pending_calls()
    assert len(pending) == 2


def test_get_error_calls(repo):
    add_user(repo)
    call_id, _ = add_call(repo)
    repo.update_call_status(call_id, "error", "ошибка")
    errors = repo.get_error_calls(max_retries=3)
    assert len(errors) == 1
    # После max_retries попыток — не возвращать
    for _ in range(3):
        repo.update_call_status(call_id, "error", "снова")
    errors = repo.get_error_calls(max_retries=3)
    assert len(errors) == 0


# ---- Transcripts ----

def test_save_and_get_transcript(repo):
    add_user(repo)
    call_id, _ = add_call(repo)
    segs = [
        Segment(start_ms=0, end_ms=1000, text="Привет", speaker="OWNER"),
        Segment(start_ms=1000, end_ms=2000, text="Здравствуйте", speaker="OTHER"),
    ]
    repo.save_transcripts(call_id, segs)
    result = repo.get_transcript(call_id)
    assert len(result) == 2
    assert result[0]["text"] == "Привет"
    assert result[1]["speaker"] == "OTHER"


def test_search_transcripts(repo):
    add_user(repo)
    call_id, _ = add_call(repo)
    segs = [
        Segment(start_ms=0, end_ms=1000, text="цена договора", speaker="OWNER"),
        Segment(start_ms=1000, end_ms=2000, text="доставка завтра", speaker="OTHER"),
    ]
    repo.save_transcripts(call_id, segs)
    hits = repo.search_transcripts("user1", "цена")
    assert len(hits) == 1
    assert "цена" in hits[0]["text"]


def test_search_transcripts_isolation(repo):
    add_user(repo, "u1")
    add_user(repo, "u2")
    call_id, _ = add_call(repo, user_id="u1")
    segs = [Segment(start_ms=0, end_ms=500, text="секрет", speaker="OWNER")]
    repo.save_transcripts(call_id, segs)
    assert repo.search_transcripts("u2", "секрет") == []


# ---- Analyses ----

def test_save_and_get_analysis(repo):
    add_user(repo)
    call_id, _ = add_call(repo)
    a = Analysis(
        priority=70, risk_score=30, summary="Хороший звонок",
        action_items=["Отправить КП"],
        flags={"urgent": True},
        key_topics=["цена", "сроки"],
        model="qwen", prompt_version="v001",
    )
    repo.save_analysis(call_id, a)
    result = repo.get_analysis(call_id)
    assert result is not None
    assert result["priority"] == 70
    assert result["action_items"] == ["Отправить КП"]
    assert result["flags"]["urgent"] is True


def test_set_feedback(repo):
    add_user(repo)
    call_id, _ = add_call(repo)
    a = Analysis(priority=50, risk_score=10, summary="ok")
    repo.save_analysis(call_id, a)
    analysis = repo.get_analysis(call_id)
    repo.set_feedback(analysis["analysis_id"], "good")
    result = repo.get_analysis(call_id)
    assert result["feedback"] == "good"


# ---- Promises ----

def test_save_and_get_promises(repo):
    add_user(repo)
    call_id, contact_id = add_call(repo)
    promises = [
        {"who": "OWNER", "what": "Отправить договор", "due": "2026-04-01"},
        {"who": "OTHER", "what": "Подтвердить получение", "due": None},
    ]
    repo.save_promises("user1", contact_id, call_id, promises)
    result = repo.get_open_promises("user1")
    assert len(result) == 2
    whats = {r["what"] for r in result}
    assert "Отправить договор" in whats
    assert "Подтвердить получение" in whats


def test_get_contact_promises(repo):
    add_user(repo)
    call_id, contact_id = add_call(repo)
    repo.save_promises("user1", contact_id, call_id, [
        {"who": "OWNER", "what": "дело1", "due": None}
    ])
    result = repo.get_contact_promises("user1", contact_id)
    assert len(result) == 1


def test_promises_isolation(repo):
    add_user(repo, "u1")
    add_user(repo, "u2")
    call_id, contact_id = add_call(repo, user_id="u1")
    repo.save_promises("u1", contact_id, call_id, [
        {"who": "OWNER", "what": "u1 дело", "due": None}
    ])
    assert repo.get_open_promises("u2") == []
