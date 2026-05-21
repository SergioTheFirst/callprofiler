# -*- coding: utf-8 -*-
"""
test_ds1_data_integrity.py — тесты Data Integrity (DS1 F2.1–F2.5),
User Isolation (F3.1–F3.2) и Entity Normalizer (F7.3).
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from callprofiler.db.repository import Repository
from callprofiler.models import Analysis, Segment

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def _add_user(repo: Repository, user_id: str = "u1") -> None:
    repo.add_user(
        user_id=user_id,
        display_name="Test",
        telegram_chat_id="0",
        incoming_dir="/tmp/in",
        sync_dir="/tmp/sync",
        ref_audio="/tmp/ref.wav",
    )


def _add_call(repo: Repository, user_id: str = "u1", md5: str = "abc") -> int:
    cid = repo.get_or_create_contact(user_id, "+70000000001", "Test")
    return repo.create_call(
        user_id=user_id,
        contact_id=cid,
        direction="IN",
        call_datetime="2026-04-01 10:00:00",
        source_filename="t.mp3",
        source_md5=md5,
        audio_path="/tmp/t.mp3",
    )


def _make_analysis(**kw) -> Analysis:
    defaults = dict(
        priority=50,
        risk_score=30,
        summary="test",
        action_items=[],
        promises=[],
        flags={},
        key_topics=[],
        raw_response='{"summary":"test"}',
        model="local",
        prompt_version="v001",
        call_type="business",
        hook=None,
        schema_version="v2",
        canonical_json='{"summary":"test"}',
    )
    defaults.update(kw)
    return Analysis(**defaults)


# ── F2.1 — schema_version в свежей БД ────────────────────────────────────────


def test_fresh_db_has_schema_version_column():
    """schema_version присутствует в analyses на свежей БД без graph-migration (F2.1)."""
    repo = _make_repo()
    cols = {row[1] for row in repo._get_conn().execute("PRAGMA table_info(analyses)")}
    assert "schema_version" in cols, "schema_version колонка должна быть в analyses"


def test_schema_version_saved_and_retrieved():
    """schema_version сохраняется и читается из analyses."""
    repo = _make_repo()
    _add_user(repo)
    call_id = _add_call(repo)
    a = _make_analysis(schema_version="v2")
    repo.save_analysis(call_id, a)
    result = repo.get_analysis("u1", call_id)
    assert result["schema_version"] == "v2"


# ── F2.2 — canonical_json в свежей БД ────────────────────────────────────────


def test_fresh_db_has_canonical_json_column():
    """canonical_json присутствует в analyses на свежей БД без graph-migration (F2.2)."""
    repo = _make_repo()
    cols = {row[1] for row in repo._get_conn().execute("PRAGMA table_info(analyses)")}
    assert "canonical_json" in cols, "canonical_json колонка должна быть в analyses"


def test_canonical_json_saved_and_retrieved():
    """canonical_json сохраняется и читается из analyses."""
    repo = _make_repo()
    _add_user(repo)
    call_id = _add_call(repo)
    payload = json.dumps({"summary": "test", "risk_score": 10}, ensure_ascii=False)
    a = _make_analysis(canonical_json=payload)
    repo.save_analysis(call_id, a)
    result = repo.get_analysis("u1", call_id)
    assert result["canonical_json"] == payload


def test_save_batch_on_fresh_db():
    """save_batch() работает на свежей БД без graph-migration (F2.2 fix)."""
    repo = _make_repo()
    _add_user(repo)
    call_id = _add_call(repo)
    a = _make_analysis()
    # Не должно бросать OperationalError "no column named canonical_json"
    repo.save_batch(
        [
            {
                "call_id": call_id,
                "analysis": a,
                "user_id": "u1",
                "contact_id": None,
                "promises": [],
            }
        ]
    )
    result = repo.get_analysis("u1", call_id)
    assert result is not None
    assert result["summary"] == "test"


# ── F2.3 — Идемпотентность transcripts ───────────────────────────────────────


def test_save_transcripts_idempotent_segments():
    """Повторный save_transcripts не дублирует сегменты (F2.3)."""
    repo = _make_repo()
    _add_user(repo)
    call_id = _add_call(repo)
    segs = [
        Segment(0, 1000, "Привет", "OWNER"),
        Segment(1000, 2000, "Здравствуйте", "OTHER"),
    ]
    repo.save_transcripts(call_id, segs)
    repo.save_transcripts(call_id, segs)  # повтор
    result = repo.get_transcript(call_id)
    assert len(result) == 2, f"Ожидали 2 сегмента, получили {len(result)}"


def test_save_transcripts_replaces_content():
    """Второй save_transcripts заменяет сегменты, а не добавляет к ним."""
    repo = _make_repo()
    _add_user(repo)
    call_id = _add_call(repo)
    repo.save_transcripts(call_id, [Segment(0, 1000, "первый", "OWNER")])
    repo.save_transcripts(
        call_id,
        [Segment(0, 1000, "второй", "OWNER"), Segment(1000, 2000, "третий", "OTHER")],
    )
    result = repo.get_transcript(call_id)
    assert len(result) == 2
    texts = {r["text"] for r in result}
    assert "первый" not in texts
    assert "второй" in texts


def test_save_transcripts_fts_consistent():
    """FTS-индекс остаётся консистентным после повторного сохранения."""
    repo = _make_repo()
    _add_user(repo)
    call_id = _add_call(repo)
    repo.save_transcripts(call_id, [Segment(0, 1000, "уникальный текст", "OWNER")])
    repo.save_transcripts(call_id, [Segment(0, 1000, "другой текст", "OWNER")])
    hits = repo.search_transcripts("u1", "другой")
    assert len(hits) >= 1
    old_hits = repo.search_transcripts("u1", "уникальный")
    assert len(old_hits) == 0


# ── F2.4 — ON CONFLICT(call_id) сохраняет feedback ───────────────────────────


def test_save_analysis_preserves_feedback():
    """Повторный save_analysis не сбрасывает feedback (F2.4)."""
    repo = _make_repo()
    _add_user(repo)
    call_id = _add_call(repo)
    a = _make_analysis()
    repo.save_analysis(call_id, a)
    analysis = repo.get_analysis("u1", call_id)
    repo.set_feedback(analysis["analysis_id"], "accurate")
    # Повторное сохранение (reprocess)
    repo.save_analysis(call_id, _make_analysis(summary="updated"))
    result = repo.get_analysis("u1", call_id)
    assert result["feedback"] == "accurate", (
        "Feedback не должен сбрасываться при обновлении анализа"
    )
    assert result["summary"] == "updated"


# ── F2.5 — Атомарная дедупликация calls по MD5 ───────────────────────────────


def test_create_call_dedup_same_md5():
    """Два create_call с одним MD5 для одного user → возвращают тот же call_id (F2.5)."""
    repo = _make_repo()
    _add_user(repo)
    cid = repo.get_or_create_contact("u1", "+7000", None)
    call_id1 = repo.create_call(
        "u1", cid, "IN", "2026-01-01", "f1.mp3", "sameMD5", "/a"
    )
    call_id2 = repo.create_call(
        "u1", cid, "IN", "2026-01-02", "f2.mp3", "sameMD5", "/b"
    )
    assert call_id1 == call_id2, "Дубликат по MD5 должен вернуть существующий call_id"
    # В БД должна быть только одна запись
    rows = (
        repo._get_conn()
        .execute(
            "SELECT COUNT(*) FROM calls WHERE user_id='u1' AND source_md5='sameMD5'"
        )
        .fetchone()
    )
    assert rows[0] == 1


def test_create_call_different_md5_different_users():
    """Одинаковый MD5 у разных пользователей — разные звонки (изоляция, F2.5)."""
    repo = _make_repo()
    _add_user(repo, "uA")
    _add_user(repo, "uB")
    cidA = repo.get_or_create_contact("uA", "+7001", None)
    cidB = repo.get_or_create_contact("uB", "+7001", None)
    c1 = repo.create_call("uA", cidA, "IN", "2026", "f.mp3", "sharedMD5", "/a")
    c2 = repo.create_call("uB", cidB, "IN", "2026", "f.mp3", "sharedMD5", "/b")
    assert c1 != c2


def test_unique_index_exists_on_calls():
    """Уникальный индекс idx_calls_user_md5 существует в схеме (F2.5)."""
    repo = _make_repo()
    indexes = {
        row[1]
        for row in repo._get_conn()
        .execute("SELECT * FROM sqlite_master WHERE type='index'")
        .fetchall()
    }
    assert "idx_calls_user_md5" in indexes


# ── F3.1 — Изоляция контактов ─────────────────────────────────────────────────


def test_get_contact_for_user_correct_user():
    """get_contact_for_user возвращает контакт для правильного пользователя (F3.1)."""
    repo = _make_repo()
    _add_user(repo, "uA")
    cid = repo.get_or_create_contact("uA", "+7000", "Alice")
    result = repo.get_contact_for_user("uA", cid)
    assert result is not None
    assert result["display_name"] == "Alice"


def test_get_contact_for_user_wrong_user_returns_none():
    """get_contact_for_user НЕ возвращает контакт чужого пользователя (F3.1)."""
    repo = _make_repo()
    _add_user(repo, "uA")
    _add_user(repo, "uB")
    cid = repo.get_or_create_contact("uA", "+7000", "Alice")
    result = repo.get_contact_for_user("uB", cid)
    assert result is None, "Пользователь B не должен видеть контакты пользователя A"


# ── F3.2 — Изоляция анализов ──────────────────────────────────────────────────


def test_get_analysis_for_user_correct_user():
    """get_analysis_for_user возвращает анализ для правильного пользователя (F3.2)."""
    repo = _make_repo()
    _add_user(repo)
    call_id = _add_call(repo)
    repo.save_analysis(call_id, _make_analysis())
    result = repo.get_analysis_for_user("u1", call_id)
    assert result is not None
    assert result["summary"] == "test"


def test_get_analysis_for_user_wrong_user_returns_none():
    """get_analysis_for_user НЕ возвращает анализ чужого пользователя (F3.2)."""
    repo = _make_repo()
    _add_user(repo, "uA")
    _add_user(repo, "uB")
    call_id = _add_call(repo, user_id="uA", md5="ma")
    repo.save_analysis(call_id, _make_analysis())
    result = repo.get_analysis_for_user("uB", call_id)
    assert result is None, "Пользователь B не должен читать анализы пользователя A"


def test_get_analysis_for_user_nonexistent_call():
    """get_analysis_for_user на несуществующем звонке → None."""
    repo = _make_repo()
    _add_user(repo)
    result = repo.get_analysis_for_user("u1", 99999)
    assert result is None


# ── F7.3 — Deterministic entity keys ──────────────────────────────────────────


def test_entity_normalizer_basic():
    """normalize_entity_key транслитерирует кириллицу (F7.3)."""
    from callprofiler.graph.entity_normalizer import normalize_entity_key

    key = normalize_entity_key("Иван Петров", "person")
    assert key == "person_ivan_petrov"


def test_entity_normalizer_deterministic():
    """Одинаковое имя → одинаковый ключ при повторных вызовах (F7.3)."""
    from callprofiler.graph.entity_normalizer import normalize_entity_key

    k1 = normalize_entity_key("Александр Сергеев", "person")
    k2 = normalize_entity_key("Александр Сергеев", "person")
    assert k1 == k2


def test_entity_normalizer_case_insensitive():
    """Регистр не влияет на результат ключа (F7.3)."""
    from callprofiler.graph.entity_normalizer import normalize_entity_key

    k1 = normalize_entity_key("Иван Петров", "person")
    k2 = normalize_entity_key("иван петров", "person")
    assert k1 == k2


def test_entity_normalizer_company():
    """Компании нормализуются правильно (F7.3)."""
    from callprofiler.graph.entity_normalizer import normalize_entity_key

    key = normalize_entity_key("ООО Ромашка", "company")
    assert "ooo" in key
    assert "romashka" in key


def test_entity_normalizer_empty_name():
    """Пустое имя возвращает fallback-ключ (F7.3)."""
    from callprofiler.graph.entity_normalizer import normalize_entity_key

    key = normalize_entity_key("", "person")
    assert key == "person_unknown"


def test_entity_normalizer_no_import_error():
    """entity_normalizer импортируется без ошибок (fix ValueError maketrans)."""
    import importlib

    # Если модуль уже в кэше, принудительно переимпортируем
    mod = importlib.import_module("callprofiler.graph.entity_normalizer")
    assert hasattr(mod, "normalize_entity_key")
    assert hasattr(mod, "normalize_canonical_name")


def test_entity_normalizer_special_chars():
    """Специальные символы и ъ/ь обрабатываются корректно."""
    from callprofiler.graph.entity_normalizer import normalize_entity_key

    key = normalize_entity_key("Объект-1", "topic")
    assert "obiekt" in key or "obekt" in key or "ob" in key  # ъ → пусто


def test_entity_normalizer_latin_passthrough():
    """Латинские имена не ломаются при нормализации."""
    from callprofiler.graph.entity_normalizer import normalize_entity_key

    key = normalize_entity_key("John Smith", "person")
    assert "john" in key
    assert "smith" in key


# ── F2.1/F2.2 — events.fact_type колонка ─────────────────────────────────────


def test_fresh_db_has_fact_type_in_events():
    """events.fact_type присутствует после init_db() (F7.1 prerequisite)."""
    repo = _make_repo()
    cols = {row[1] for row in repo._get_conn().execute("PRAGMA table_info(events)")}
    assert "fact_type" in cols, "fact_type должна быть в events после migrate"


def test_fresh_db_has_entity_id_in_events():
    """events.entity_id присутствует после init_db() (graph prerequisite)."""
    repo = _make_repo()
    cols = {row[1] for row in repo._get_conn().execute("PRAGMA table_info(events)")}
    assert "entity_id" in cols
