# -*- coding: utf-8 -*-
"""T-04: ConnectionFactory + Unit of Work — транзакционные границы.

Покрывает: rollback через несколько репозиториев на одном conn, отсутствие
двойного коммита, конкурентность reader+writer на файловой БД, busy_timeout
на writer, регресс WAL/foreign_keys, архитектурный инвариант "ML вне
транзакции", отсутствие утечки соединений.
"""
from __future__ import annotations

import sqlite3
import threading

import pytest

from callprofiler.db.connection import ConnectionFactory
from callprofiler.db.repository import Repository
from callprofiler.db.uow import commit_unless_uow, rollback_unless_uow, uow_for
from callprofiler.graph.repository import GraphRepository, apply_graph_schema


def _add_user(repo: Repository, user_id: str = "u1") -> None:
    repo.add_user(
        user_id=user_id,
        display_name="Test User",
        telegram_chat_id=None,
        incoming_dir="C:\\calls",
        sync_dir="C:\\sync",
        ref_audio="C:\\ref.wav",
    )


def test_dedup_rollback_inside_uow_does_not_discard_outer_writes():
    """MD5-дедуп в create_call не смеет откатывать чужой UoW.

    Голый conn.rollback() в этой ветке сносил бы ВЕСЬ внешний сценарий, после
    чего UoW на выходе сделал бы commit — вызывающий получил бы «успех» при
    потерянных ранних записях. Тест фиксирует, что ранняя запись выживает,
    а дедуп по-прежнему возвращает id существующего звонка.
    """
    repo = Repository(":memory:")
    repo.init_db()
    conn = repo._get_conn()
    _add_user(repo)

    first_id = repo.create_call(
        user_id="u1", contact_id=None, direction="in", call_datetime=None,
        source_filename="a.mp3", source_md5="deadbeef", audio_path="a.mp3",
    )

    with uow_for(conn):
        # ранняя запись внутри того же сценария
        assert repo.update_call_status("u1", first_id, "normalizing") is True
        # дубликат по MD5 -> ветка с rollback_unless_uow
        dup_id = repo.create_call(
            user_id="u1", contact_id=None, direction="in", call_datetime=None,
            source_filename="a-copy.mp3", source_md5="deadbeef",
            audio_path="a-copy.mp3",
        )
        assert dup_id == first_id

    row = conn.execute(
        "SELECT status FROM calls WHERE call_id=?", (first_id,)
    ).fetchone()
    assert row["status"] == "normalizing", "ранняя запись UoW не должна теряться"


def test_rollback_unless_uow_still_rolls_back_outside_uow():
    """Вне UoW поведение прежнее — откат реально происходит."""
    repo = Repository(":memory:")
    repo.init_db()
    conn = repo._get_conn()
    _add_user(repo)
    conn.execute(
        "INSERT INTO contacts (user_id, phone_e164) VALUES (?, ?)", ("u1", "+79990000000")
    )
    rollback_unless_uow(conn)
    n = conn.execute("SELECT COUNT(*) AS c FROM contacts").fetchone()["c"]
    assert n == 0


# ------------------------------------------------------------------
# Rollback across multiple repositories sharing one connection
# ------------------------------------------------------------------

def test_uow_rollback_leaves_zero_partial_rows():
    repo = Repository(":memory:")
    repo.init_db()
    conn = repo._get_conn()
    apply_graph_schema(conn)
    graph_repo = GraphRepository(conn)
    _add_user(repo)

    with pytest.raises(RuntimeError):
        with uow_for(conn):
            repo.create_call(
                user_id="u1", contact_id=None, direction="IN",
                call_datetime=None, source_filename="a.mp3",
                source_md5="deadbeef", audio_path="a.wav",
            )
            graph_repo.upsert_entity(
                user_id="u1", entity_type="PERSON",
                canonical_name="Vasya", normalized_key="person::vasya",
            )
            raise RuntimeError("boom mid-uow")

    assert conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0


# ------------------------------------------------------------------
# No double commit: writes inside UoW aren't visible before it exits
# ------------------------------------------------------------------

def test_no_commit_before_uow_exits(tmp_path):
    db_path = str(tmp_path / "test.db")
    repo = Repository(db_path)
    repo.init_db()
    conn = repo._get_conn()
    _add_user(repo)

    observer = ConnectionFactory(db_path).reader()
    try:
        with uow_for(conn):
            repo.create_call(
                user_id="u1", contact_id=None, direction="IN",
                call_datetime=None, source_filename="a.mp3",
                source_md5="md5-1", audio_path="a.wav",
            )
            # Ещё внутри UoW -> commit подавлен -> другому соединению не видно.
            assert observer.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0

        # UoW завершился успешно -> ровно один commit на выходе -> видно.
        assert observer.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 1
    finally:
        observer.close()


# ------------------------------------------------------------------
# Concurrency: file-based DB, parallel reader + writer
# ------------------------------------------------------------------

def test_concurrent_reader_and_writer_no_lock_errors(tmp_path):
    db_path = str(tmp_path / "concurrent.db")
    repo = Repository(db_path)
    repo.init_db()
    _add_user(repo)

    errors: list[Exception] = []
    n_writes = 25

    def writer():
        conn = repo._get_conn()
        for i in range(n_writes):
            try:
                with uow_for(conn):
                    repo.create_call(
                        user_id="u1", contact_id=None, direction="IN",
                        call_datetime=None, source_filename=f"w{i}.mp3",
                        source_md5=f"md5-w-{i}", audio_path="w.wav",
                    )
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

    def reader():
        rconn = ConnectionFactory(db_path).reader()
        try:
            for _ in range(n_writes):
                try:
                    rconn.execute("SELECT COUNT(*) FROM calls").fetchone()
                except Exception as exc:  # pragma: no cover - failure path
                    errors.append(exc)
        finally:
            rconn.close()

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"lock/read errors during concurrent access: {errors}"
    final = repo._get_conn().execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    assert final == n_writes  # no writes lost


# ------------------------------------------------------------------
# busy_timeout actually configured on the writer connection
# ------------------------------------------------------------------

def test_writer_busy_timeout_is_set(tmp_path):
    factory = ConnectionFactory(str(tmp_path / "bt.db"))
    conn = factory.writer(busy_timeout_ms=4321)
    try:
        value = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert value == 4321
    finally:
        conn.close()


def test_reader_busy_timeout_default(tmp_path):
    factory = ConnectionFactory(str(tmp_path / "bt2.db"))
    w = factory.writer()
    w.close()
    conn = factory.reader()
    try:
        value = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert value == 3000
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
    finally:
        conn.close()


# ------------------------------------------------------------------
# Regression: factory still turns on WAL + foreign_keys
# ------------------------------------------------------------------

def test_factory_keeps_wal_and_foreign_keys(tmp_path):
    factory = ConnectionFactory(str(tmp_path / "wal.db"))
    conn = factory.writer()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_repository_get_conn_still_wal_and_fk(tmp_path):
    repo = Repository(str(tmp_path / "repo_wal.db"))
    repo.init_db()
    conn = repo._get_conn()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


# ------------------------------------------------------------------
# Architectural invariant: ML calls happen with no open transaction
# ------------------------------------------------------------------

def test_ml_call_runs_outside_any_open_transaction():
    """Mirrors orchestrator._analyze_call's shape: the ASR/LLM call happens
    BEFORE `with uow_for(conn):`, never inside it — GPU work must never sit
    behind an open SQLite transaction (Hard Constraint: no long-lived
    transactions around ML work)."""
    conn = ConnectionFactory(":memory:").writer()
    conn.execute("CREATE TABLE t(x)")
    commit_unless_uow(conn)

    seen_in_transaction = []

    def fake_asr_or_llm_call():
        seen_in_transaction.append(conn.in_transaction)
        return "stub-result"

    result = fake_asr_or_llm_call()
    with uow_for(conn):
        conn.execute("INSERT INTO t VALUES (?)", (result,))

    assert seen_in_transaction == [False]
    assert conn.in_transaction is False


# ------------------------------------------------------------------
# No leaked connections across a UoW-driven scenario
# ------------------------------------------------------------------

def test_connections_close_cleanly_no_leak(tmp_path):
    db_path = str(tmp_path / "leak.db")
    factory = ConnectionFactory(db_path)
    for _ in range(10):
        w = factory.writer()
        w.execute("CREATE TABLE IF NOT EXISTS t(x)")
        commit_unless_uow(w)
        w.close()
        r = factory.reader()
        r.execute("SELECT COUNT(*) FROM t")
        r.close()

    # Ничего не осталось залипшим — новое writer-соединение сразу получает
    # эксклюзивный доступ без ожидания (иначе одна из предыдущих утекла).
    final = factory.writer()
    try:
        final.execute("INSERT INTO t VALUES (1)")
        final.commit()
    finally:
        final.close()
