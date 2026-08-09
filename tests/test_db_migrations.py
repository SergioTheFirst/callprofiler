# -*- coding: utf-8 -*-
"""test_db_migrations.py — T-05: versioned migrations, FTS rebuild, owner triggers."""

import sqlite3

import pytest

from callprofiler.db.connection import ConnectionFactory
from callprofiler.db.migrations import (
    ALL_MIGRATIONS,
    Migration,
    MigrationChecksumError,
    apply_migrations,
    ensure_backup_before_migrate,
    find_owner_mismatches,
    foreign_key_check,
    quick_check,
)
from callprofiler.db.repository import Repository


def _row_count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------------------------------------------------------------------
# Fresh DB / idempotency / checksum
# ---------------------------------------------------------------------------


def test_migrations_apply_on_fresh_db():
    repo = Repository(":memory:")
    repo.init_db()
    conn = repo._get_conn()

    rows = conn.execute("SELECT id, name FROM schema_migrations ORDER BY id").fetchall()
    assert [r["id"] for r in rows] == [m.id for m in ALL_MIGRATIONS]

    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert user_version == max(m.id for m in ALL_MIGRATIONS)


def test_migrations_idempotent_rerun():
    repo = Repository(":memory:")
    repo.init_db()
    conn = repo._get_conn()
    before = _row_count(conn, "schema_migrations")

    apply_migrations(conn)  # second run: nothing new to apply

    after = _row_count(conn, "schema_migrations")
    assert after == before


def test_tampered_checksum_raises_loudly():
    repo = Repository(":memory:")
    repo.init_db()
    conn = repo._get_conn()

    conn.execute(
        "UPDATE schema_migrations SET checksum='deadbeef' WHERE id=1"
    )
    conn.commit()

    with pytest.raises(MigrationChecksumError):
        apply_migrations(conn)


def test_failed_migration_rolls_back_and_does_not_advance_user_version():
    conn = ConnectionFactory(":memory:").writer()
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()

    def _ok(c):
        c.execute("ALTER TABLE t ADD COLUMN y INTEGER")

    def _boom(c):
        c.execute("ALTER TABLE t ADD COLUMN z INTEGER")
        raise RuntimeError("simulated mid-migration failure")

    migrations = [Migration(1, "ok", _ok), Migration(2, "boom", _boom)]

    with pytest.raises(RuntimeError):
        apply_migrations(conn, migrations)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(t)").fetchall()}
    assert "y" in cols  # migration 1 committed
    assert "z" not in cols  # migration 2 rolled back whole transaction

    applied_ids = {r[0] for r in conn.execute("SELECT id FROM schema_migrations").fetchall()}
    assert applied_ids == {1}
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Migration over historical schema shapes (pre-migration gaps seen in _migrate())
# ---------------------------------------------------------------------------


def test_backup_gate_arms_itself_on_real_data(tmp_path):
    """Гейт бэкапа обязан взводиться САМ, без параметра от вызывающего.

    Ни один боевой вызов init_db не передавал backup_dir (включая общую точку
    входа CLI), поэтому опциональный параметр был фиговым листком: боевая БД
    мигрировала бы без снимка — ровно то, ради чего T-20 стоит перед T-05.
    """
    from callprofiler.db.migrations import data_at_risk

    db = tmp_path / "callprofiler.db"
    repo = Repository(str(db))
    repo.init_db()  # пустая БД — гейта нет, миграции применились
    conn = repo._get_conn()
    assert data_at_risk(conn) is False, "на пустой БД гейт взводиться не должен"

    # появились реальные данные + откатим журнал так, будто миграция не применена
    repo.add_user("me", "Me", None, str(tmp_path), str(tmp_path), "")
    repo.create_call(
        user_id="me", contact_id=None, direction="in", call_datetime=None,
        source_filename="a.mp3", source_md5="m1", audio_path="a.mp3",
    )
    conn.execute("DELETE FROM schema_migrations WHERE id = (SELECT MAX(id) FROM schema_migrations)")
    conn.commit()
    assert data_at_risk(conn) is True, "данные + непримененная миграция = риск"
    repo.close()

    # повторный init_db БЕЗ backup_dir теперь обязан отказать
    repo2 = Repository(str(db))
    with pytest.raises(RuntimeError, match="[Nn]o verified backup"):
        repo2.init_db()
    repo2.close()

    # unsafe=True — явный обход
    repo3 = Repository(str(db))
    repo3.init_db(unsafe=True)
    repo3.close()


def _legacy_conn() -> sqlite3.Connection:
    """A DB shaped like production BEFORE any of the ALTER-migrations ran:
    calls without pipeline_stage/role_fragile, events without graph columns,
    no entities table, and the P-DB-06 broken FTS definition (user_id column
    on an external-content table that has none)."""
    conn = ConnectionFactory(":memory:").writer()
    conn.executescript(
        """
        CREATE TABLE users (user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
            incoming_dir TEXT NOT NULL, sync_dir TEXT NOT NULL, ref_audio TEXT NOT NULL);
        CREATE TABLE contacts (contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(user_id), phone_e164 TEXT,
            display_name TEXT);
        CREATE TABLE calls (call_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(user_id),
            contact_id INTEGER REFERENCES contacts(contact_id),
            call_datetime TEXT,
            source_filename TEXT NOT NULL, source_md5 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            updated_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE TABLE transcripts (segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id INTEGER NOT NULL REFERENCES calls(call_id),
            start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
            text TEXT NOT NULL, speaker TEXT NOT NULL DEFAULT 'UNKNOWN');
        CREATE TABLE analyses (analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id INTEGER NOT NULL UNIQUE REFERENCES calls(call_id));
        CREATE TABLE promises (promise_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(user_id),
            contact_id INTEGER REFERENCES contacts(contact_id),
            call_id INTEGER NOT NULL REFERENCES calls(call_id),
            who TEXT NOT NULL, what TEXT NOT NULL, due TEXT,
            status TEXT NOT NULL DEFAULT 'open');
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(user_id),
            contact_id INTEGER REFERENCES contacts(contact_id),
            call_id INTEGER NOT NULL REFERENCES calls(call_id),
            event_type TEXT NOT NULL, who TEXT, payload TEXT NOT NULL,
            status TEXT DEFAULT 'open');
        -- P-DB-06 as-found: user_id column on an fts5 table whose content
        -- table (transcripts) has none.
        CREATE VIRTUAL TABLE transcripts_fts USING fts5(
            text, speaker, call_id UNINDEXED, user_id UNINDEXED,
            content='transcripts', content_rowid='segment_id');
        """
    )
    conn.commit()
    return conn


def test_legacy_broken_fts_rebuild_fails_before_migration():
    """Proves P-DB-06 is real: rebuild on the as-found definition errors."""
    conn = _legacy_conn()
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO transcripts_fts(transcripts_fts) VALUES('rebuild')")


def test_migration_over_legacy_missing_calls_columns():
    conn = _legacy_conn()
    apply_migrations(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(calls)").fetchall()}
    assert {"pipeline_stage", "role_fragile", "call_type"} <= cols


def test_migration_over_legacy_missing_events_graph_columns():
    conn = _legacy_conn()
    apply_migrations(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    assert {"entity_id", "fact_id", "quote", "polarity", "intensity"} <= cols


def test_migration_over_legacy_missing_entities_table_is_noop_not_error():
    conn = _legacy_conn()
    apply_migrations(conn)  # must not raise despite no `entities` table
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "entities" not in tables


def test_migration_fixes_fts_and_rebuild_matches_search_before_and_after():
    conn = _legacy_conn()
    conn.execute(
        "INSERT INTO users (user_id, display_name, incoming_dir, sync_dir, ref_audio) "
        "VALUES ('me','Me','/in','/sync','/ref.wav')"
    )
    conn.execute(
        "INSERT INTO calls (call_id, user_id, source_filename, source_md5) "
        "VALUES (1,'me','a.mp3','md5a')"
    )
    conn.execute(
        "INSERT INTO transcripts (call_id, start_ms, end_ms, text, speaker) "
        "VALUES (1, 0, 1000, 'привет мир', 'OWNER')"
    )
    # Legacy FTS row inserted the old way (with user_id column present).
    conn.execute(
        "INSERT INTO transcripts_fts(rowid, text, speaker, call_id, user_id) "
        "VALUES (1, 'привет мир', 'OWNER', 1, 'me')"
    )
    conn.commit()

    def _search():
        return {
            r[0]
            for r in conn.execute(
                "SELECT rowid FROM transcripts_fts WHERE transcripts_fts MATCH 'привет'"
            ).fetchall()
        }

    before = _search()
    assert before == {1}

    apply_migrations(conn)  # drops user_id column, rebuilds

    cols = {r[1] for r in conn.execute("PRAGMA table_info(transcripts_fts)").fetchall()}
    assert "user_id" not in cols

    after = _search()
    assert after == before == {1}


# ---------------------------------------------------------------------------
# Owner triggers (P-DB-03) — DB itself rejects cross-tenant child rows
# ---------------------------------------------------------------------------


def _repo_with_two_owners():
    repo = Repository(":memory:")
    repo.init_db()
    conn = repo._get_conn()
    conn.execute(
        "INSERT INTO users (user_id, display_name, incoming_dir, sync_dir, ref_audio) "
        "VALUES ('alice','Alice','/in/a','/sync/a','/ref/a.wav')"
    )
    conn.execute(
        "INSERT INTO users (user_id, display_name, incoming_dir, sync_dir, ref_audio) "
        "VALUES ('bob','Bob','/in/b','/sync/b','/ref/b.wav')"
    )
    conn.execute(
        "INSERT INTO contacts (contact_id, user_id, phone_e164) VALUES (1,'alice','+1')"
    )
    conn.execute(
        "INSERT INTO calls (call_id, user_id, source_filename, source_md5) "
        "VALUES (1,'alice','a.mp3','md5a')"
    )
    conn.commit()
    return repo, conn


def test_cross_owner_call_insert_rejected_by_db():
    repo, conn = _repo_with_two_owners()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO calls (user_id, contact_id, source_filename, source_md5) "
            "VALUES ('bob', 1, 'b.mp3', 'md5b')"
        )


def test_cross_owner_promise_insert_rejected_by_db():
    repo, conn = _repo_with_two_owners()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO promises (user_id, contact_id, call_id, who, what) "
            "VALUES ('bob', 1, 1, 'OWNER', 'x')"
        )


def test_cross_owner_event_insert_rejected_by_db():
    repo, conn = _repo_with_two_owners()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO events (user_id, contact_id, call_id, event_type, payload) "
            "VALUES ('bob', 1, 1, 'fact', 'x')"
        )


def test_same_owner_insert_still_works():
    repo, conn = _repo_with_two_owners()
    conn.execute(
        "INSERT INTO promises (user_id, contact_id, call_id, who, what) "
        "VALUES ('alice', 1, 1, 'OWNER', 'x')"
    )
    conn.commit()
    assert _row_count(conn, "promises") == 1


def test_call_without_contact_id_still_allowed():
    """contact_id nullable — a call with no contact must not be blocked."""
    repo, conn = _repo_with_two_owners()
    conn.execute(
        "INSERT INTO calls (user_id, source_filename, source_md5) "
        "VALUES ('bob', 'c.mp3', 'md5c')"
    )
    conn.commit()
    assert _row_count(conn, "calls") == 2


# ---------------------------------------------------------------------------
# Pre/post-flight checks
# ---------------------------------------------------------------------------


def test_quick_check_and_fk_check_clean_after_migrations():
    repo = Repository(":memory:")
    repo.init_db()
    conn = repo._get_conn()
    assert quick_check(conn) == "ok"
    assert foreign_key_check(conn) == []


def test_find_owner_mismatches_empty_on_clean_db():
    repo, conn = _repo_with_two_owners()
    assert find_owner_mismatches(conn) == {}


def test_ensure_backup_before_migrate_skips_when_db_missing(tmp_path):
    ensure_backup_before_migrate(str(tmp_path / "nope.db"), str(tmp_path / "backups"))


def test_ensure_backup_before_migrate_skips_when_unsafe(tmp_path):
    db_path = tmp_path / "real.db"
    db_path.write_bytes(b"x")
    ensure_backup_before_migrate(str(db_path), str(tmp_path / "backups"), unsafe=True)


def test_ensure_backup_before_migrate_raises_without_backup(tmp_path):
    db_path = tmp_path / "real.db"
    db_path.write_bytes(b"x")
    with pytest.raises(RuntimeError):
        ensure_backup_before_migrate(str(db_path), str(tmp_path / "backups"))
