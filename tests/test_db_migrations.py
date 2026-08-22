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


# ---------------------------------------------------------------------------
# M12 — BS-v2 additive schema (R-01, docs/100bsindex.md §6)
# ---------------------------------------------------------------------------


def _norm_sql(sql: str) -> str:
    import re

    return re.sub(r"\s+", " ", sql or "").strip()


def _schema_dump(conn) -> dict:
    return {
        r["name"]: _norm_sql(r["sql"])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
    }


def _built(tmp_path, order, name):
    """Apply the three schema owners in the requested order on a fresh file DB."""
    from callprofiler.graph.repository import apply_graph_schema
    from callprofiler.insight.repository import apply_insight_schema

    repo = Repository(str(tmp_path / name))
    conn = repo._get_conn()
    for step in order:
        if step == "init":
            repo.init_db()
        elif step == "graph":
            apply_graph_schema(conn)
        else:
            apply_insight_schema(conn)
    return repo, conn


def _legacy_bs_fixture() -> sqlite3.Connection:
    """Pre-M12 DB with everything M12 has to migrate: phone-less contact,
    NULL-contact call, entity_metrics row, contact_summaries.avg_bs_score,
    v2 analysis with one valid + one invalid relation, and a second user."""
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
            call_datetime TEXT, source_filename TEXT NOT NULL, source_md5 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE TABLE transcripts (segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id INTEGER NOT NULL REFERENCES calls(call_id),
            start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
            text TEXT NOT NULL, speaker TEXT NOT NULL DEFAULT 'UNKNOWN');
        CREATE TABLE analyses (analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id INTEGER NOT NULL UNIQUE REFERENCES calls(call_id),
            raw_response TEXT NOT NULL DEFAULT '');
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
            fact_id TEXT, status TEXT DEFAULT 'open');
        CREATE TABLE entities (id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL, entity_type TEXT NOT NULL,
            canonical_name TEXT NOT NULL, normalized_key TEXT NOT NULL);
        CREATE TABLE entity_metrics (entity_id INTEGER PRIMARY KEY, user_id TEXT NOT NULL,
            total_calls INTEGER DEFAULT 0, contradictions INTEGER DEFAULT 0,
            bs_index REAL DEFAULT 0, bs_formula_version TEXT DEFAULT 'v1_linear');
        CREATE TABLE contact_summaries (contact_id INTEGER PRIMARY KEY, user_id TEXT NOT NULL,
            avg_bs_score INTEGER DEFAULT 0, advice TEXT);
        CREATE VIRTUAL TABLE transcripts_fts USING fts5(
            text, speaker, call_id UNINDEXED,
            content='transcripts', content_rowid='segment_id');

        INSERT INTO users VALUES ('me','Me','/in','/sync','/ref.wav'),
                                 ('other','Other','/in2','/sync2','/ref2.wav');
        INSERT INTO contacts (contact_id, user_id, phone_e164) VALUES (1,'me',NULL);
        INSERT INTO contacts (contact_id, user_id, phone_e164) VALUES (2,'other','+79990000000');
        INSERT INTO calls (call_id,user_id,contact_id,call_datetime,source_filename,source_md5,status)
            VALUES (1,'me',1,'2026-01-05 10:00:00','a.mp3','AABB11','done');
        INSERT INTO calls (call_id,user_id,contact_id,call_datetime,source_filename,source_md5,status)
            VALUES (2,'me',NULL,'2026-02-06 11:00:00','b.mp3','CCDD22','done');
        INSERT INTO calls (call_id,user_id,contact_id,call_datetime,source_filename,source_md5,status)
            VALUES (3,'other',2,'2026-02-07 09:00:00','c.mp3','EEFF33','done');
        INSERT INTO events (user_id,contact_id,call_id,event_type,who,payload,fact_id)
            VALUES ('me',1,1,'fact','UNKNOWN','{}','abc123');
        INSERT INTO events (user_id,contact_id,call_id,event_type,who,payload,fact_id)
            VALUES ('me',1,1,'contradiction','UNKNOWN','{}',NULL);
        INSERT INTO entities (id,user_id,entity_type,canonical_name,normalized_key)
            VALUES (7,'me','person','Ivan Petrov','ivan_petrov');
        INSERT INTO entity_metrics (entity_id,user_id,total_calls,contradictions,bs_index,bs_formula_version)
            VALUES (7,'me',4,2,10.0,'v1_linear');
        INSERT INTO contact_summaries (contact_id,user_id,avg_bs_score,advice)
            VALUES (1,'me',33,'old advice');
        """
    )
    conn.execute("ALTER TABLE analyses ADD COLUMN schema_version TEXT DEFAULT 'v1'")
    conn.execute(
        "INSERT INTO analyses (call_id, raw_response, schema_version) VALUES (1, ?, 'v2')",
        (
            '{"relations":[{"src_type":"person","src_key":"ivan_petrov",'
            '"dst_type":"org","dst_key":"acme","relation_type":"works_at","confidence":0.9},'
            '{"src_type":"person","src_key":"","dst_type":"org","dst_key":"acme",'
            '"relation_type":"works_at","confidence":0.5}]}',
        ),
    )
    conn.commit()
    return conn


def test_migration_12_bs_v2_full_contract(tmp_path):
    """R-01: fresh/upgraded DBs converge on one BS-v2 contract (user_version 12),
    ownership/immutability triggers hold, purge stays possible, v1 values are
    snapshotted byte-exact, and NULL-contact calls get a placeholder + 0/1 row."""
    from callprofiler.db.bs_schema import (
        BS_FORMULA_VERSION_V2,
        CONFIDENCE_FORMULA_VERSION_V1,
    )

    # ── schema owners are order-independent ──────────────────────────────
    repo_a, conn_a = _built(tmp_path, ["init", "graph", "insight"], "a.db")
    repo_b, conn_b = _built(tmp_path, ["graph", "init", "insight"], "b.db")
    dump_a, dump_b = _schema_dump(conn_a), _schema_dump(conn_b)
    assert dump_a == dump_b
    assert conn_a.execute("PRAGMA user_version").fetchone()[0] == 12
    assert [
        r["id"] for r in conn_a.execute("SELECT id FROM schema_migrations ORDER BY id")
    ] == list(range(1, 13))
    repo_a.init_db()  # second full pass changes no DDL at all
    assert _schema_dump(conn_a) == dump_a
    for name in ("contact_bs_metrics", "bs_legacy_snapshots", "relation_evidence"):
        assert name in dump_a
    repo_b.close()

    # ── legacy upgrade path ──────────────────────────────────────────────
    conn = _legacy_bs_fixture()
    pre_summary = dict(
        conn.execute("SELECT * FROM contact_summaries WHERE contact_id=1").fetchone()
    )
    apply_migrations(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12

    from callprofiler.db.bs_schema import BS_V2_COLUMNS

    for table in ("promises", "events", "contact_summaries", "entity_metrics", "contacts", "users"):
        expected = {name for name, _ in BS_V2_COLUMNS.get(table, [])}
        fresh = {r[1] for r in conn_a.execute("PRAGMA table_info(%s)" % table)}
        upgraded = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        assert expected <= fresh, table
        assert expected <= upgraded, table

    producers = dict(
        conn.execute("SELECT COALESCE(fact_id,'-'), producer FROM events ORDER BY id").fetchall()
    )
    assert producers == {"abc123": "graph_v1", "-": "legacy"}

    call2 = conn.execute("SELECT contact_id, user_id FROM calls WHERE call_id=2").fetchone()
    assert call2["contact_id"] is not None
    placeholder = conn.execute(
        "SELECT user_id, placeholder_key FROM contacts WHERE contact_id=?",
        (call2["contact_id"],),
    ).fetchone()
    assert placeholder["user_id"] == "me"
    assert placeholder["placeholder_key"] == "md5-ccdd22"
    baseline = conn.execute(
        "SELECT * FROM contact_bs_metrics WHERE contact_id=?", (call2["contact_id"],)
    ).fetchall()
    assert len(baseline) == 1
    assert (baseline[0]["bs_index"], baseline[0]["bs_confidence"]) == (0.0, 1)
    assert baseline[0]["no_evidence"] == 1
    assert baseline[0]["bs_formula_version"] == BS_FORMULA_VERSION_V2
    assert baseline[0]["computed_as_of"] == "2026-02-06"
    assert (
        conn.execute("SELECT placeholder_key FROM contacts WHERE contact_id=1").fetchone()[0]
        == "md5-aabb11"
    )

    ledger = conn.execute("SELECT * FROM relation_evidence").fetchall()
    assert len(ledger) == 1
    assert (ledger[0]["raw_src_key"], ledger[0]["relation_type"], ledger[0]["producer"]) == (
        "ivan_petrov",
        "works_at",
        "graph_v1",
    )
    assert ledger[0]["source_date"].startswith("2026-01-05")

    entity_snap = conn.execute(
        "SELECT * FROM bs_legacy_snapshots WHERE subject_kind='entity'"
    ).fetchone()
    assert entity_snap["subject_key"] == "person|ivan_petrov"
    assert entity_snap["bs_index"] == 10.0
    contact_snap = conn.execute(
        "SELECT * FROM bs_legacy_snapshots WHERE subject_kind='contact_fallback'"
    ).fetchone()
    assert contact_snap["bs_index"] == 33.0
    import json as _json

    assert _json.loads(contact_snap["payload_json"])["advice"] == pre_summary["advice"]

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE bs_legacy_snapshots SET bs_index=99 WHERE subject_kind='entity'")
    conn.execute(
        "INSERT OR IGNORE INTO bs_legacy_snapshots (user_id, subject_kind, subject_key,"
        " contact_id, bs_index, bs_formula_version, payload_json)"
        " VALUES ('me','entity','person|ivan_petrov',NULL,99.0,'v1_linear','{}')"
    )
    assert (
        conn.execute(
            "SELECT bs_index FROM bs_legacy_snapshots WHERE subject_kind='entity'"
        ).fetchone()[0]
        == 10.0
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM bs_legacy_snapshots WHERE subject_kind='entity'")
    conn.execute("UPDATE users SET purge_started_at=datetime('now') WHERE user_id='me'")
    conn.execute("DELETE FROM bs_legacy_snapshots WHERE subject_kind='entity'")
    conn.rollback()

    other_contact = 2
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO contact_bs_metrics (user_id, contact_id, bs_index, bs_confidence,"
            " bs_formula_version, confidence_formula_version, potential_mass, qualified_mass,"
            " quality_score, agreement_score, stability_score, no_evidence, source_signature,"
            " callset_signature, computed_as_of)"
            " VALUES ('me',?,0.0,1,?,?,0,0,0,0,0,1,'s','c','2026-01-01')",
            (other_contact, BS_FORMULA_VERSION_V2, CONFIDENCE_FORMULA_VERSION_V1),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO bs_legacy_snapshots (user_id, subject_kind, subject_key, contact_id,"
            " bs_index, bs_formula_version, payload_json)"
            " VALUES ('me','contact_fallback','x',?,1.0,'v1_linear','{}')",
            (other_contact,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO relation_evidence (user_id, evidence_key, source_call_id, raw_src_type,"
            " raw_src_key, raw_dst_type, raw_dst_key, relation_type, confidence, source_date,"
            " producer) VALUES ('me','k',3,'person','a','org','b','works_at',0.5,"
            "'2026-01-01','graph_v2')"
        )

    cid = call2["contact_id"]
    for conf_version in (CONFIDENCE_FORMULA_VERSION_V1, "c2_experimental"):
        conn.execute(
            "INSERT OR IGNORE INTO contact_bs_metrics (user_id, contact_id, bs_index,"
            " bs_confidence, bs_formula_version, confidence_formula_version, potential_mass,"
            " qualified_mass, quality_score, agreement_score, stability_score, no_evidence,"
            " source_signature, callset_signature, computed_as_of)"
            " VALUES ('me',?,1.0,5,?,?,0,0,0,0,0,0,'s','c','2026-02-06')",
            (cid, BS_FORMULA_VERSION_V2, conf_version),
        )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM contact_bs_metrics WHERE contact_id=?", (cid,)
        ).fetchone()[0]
        == 2
    )
    conn.close()
    repo_a.close()


def test_migration_12_failure_leaves_pre_state_exact():
    """Injected failure inside M12 rolls the whole migration back (journal,
    user_version and every M12 table/column)."""
    conn = _legacy_bs_fixture()
    pre_tables = _schema_dump(conn)

    def boom(_conn):
        raise RuntimeError("injected")

    migrations = [m for m in ALL_MIGRATIONS if m.id < 12] + [Migration(12, "bs_v2", boom)]
    with pytest.raises(RuntimeError):
        apply_migrations(conn, migrations)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 11
    assert "contact_bs_metrics" not in _schema_dump(conn)
    assert "bs_legacy_snapshots" not in pre_tables
    conn.close()


def test_purge_user_survives_legacy_snapshot(tmp_path):
    """T-06 privacy contract holds with M12: a user owning an immutable
    snapshot can still be purged (flag lifts the DELETE guard)."""
    repo = Repository(str(tmp_path / "purge.db"))
    repo.init_db()
    repo.add_user("me", "Me", None, "/in", "/sync", "/ref.wav")
    contact_id = repo.get_or_create_contact("me", "+79990000001", "Ivan")
    conn = repo._get_conn()
    conn.execute(
        "INSERT INTO bs_legacy_snapshots (user_id, subject_kind, subject_key, contact_id,"
        " bs_index, bs_formula_version, payload_json)"
        " VALUES ('me','contact_fallback',?,?,42.0,'legacy','{}')",
        (str(contact_id), contact_id),
    )
    conn.commit()
    counts = repo.purge_user("me", apply=True)
    assert counts["bs_legacy_snapshots"] == 1
    assert conn.execute("SELECT COUNT(*) FROM bs_legacy_snapshots").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    repo.close()
