# -*- coding: utf-8 -*-
"""
migrations.py — T-05: versioned, journaled schema migrations (P-DB-01/03/06).

Replaces the old ``Repository._migrate()`` (bare ``except Exception: pass``
around ALTER TABLE, no journal, no checksums). Each migration is a numbered,
named Python function; applying it is one explicit transaction (BEGIN...
COMMIT/ROLLBACK — never silently partial), and every applied migration is
recorded in ``schema_migrations`` with a checksum of its own source. A
checksum mismatch on a migration already marked applied means the migration
code changed after the fact — that is a loud error, not a silent re-apply.

``PRAGMA user_version`` mirrors the highest applied migration id (cheap
external signal; the journal table is the source of truth).
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class MigrationChecksumError(RuntimeError):
    """An already-applied migration's checksum no longer matches its code."""


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_columns_if_missing(
    conn: sqlite3.Connection, table: str, columns: list[tuple[str, str]]
) -> None:
    existing = _existing_columns(conn, table)
    for col_name, col_def in columns:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")


@dataclass(frozen=True)
class Migration:
    id: int
    name: str
    apply: Callable[[sqlite3.Connection], None]

    @property
    def checksum(self) -> str:
        """sha256 of the migration function's own source — tamper/drift detector."""
        return hashlib.sha256(inspect.getsource(self.apply).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Individual migrations (numbered, never renumbered/reordered once released)
# ---------------------------------------------------------------------------


def _m001_contacts_columns(conn: sqlite3.Connection) -> None:
    """contacts: name-guessing columns added post-release."""
    _add_columns_if_missing(
        conn,
        "contacts",
        [
            ("guessed_name", "TEXT"),
            ("guessed_company", "TEXT"),
            ("guess_source", "TEXT"),
            ("guess_call_id", "INTEGER"),
            ("guess_confidence", "TEXT"),
            ("name_confirmed", "INTEGER NOT NULL DEFAULT 0"),
        ],
    )


def _m002_analyses_columns(conn: sqlite3.Connection) -> None:
    """analyses: call_type/hook/parse_status/profanity + graph schema_version/canonical_json."""
    _add_columns_if_missing(
        conn,
        "analyses",
        [
            ("call_type", "TEXT DEFAULT 'unknown'"),
            ("hook", "TEXT"),
            ("parse_status", "TEXT DEFAULT 'unknown'"),
            ("profanity_count", "INTEGER DEFAULT 0"),
            ("profanity_density", "REAL DEFAULT 0"),
            ("schema_version", "TEXT DEFAULT 'v2'"),
            ("canonical_json", "TEXT DEFAULT ''"),
        ],
    )


def _m003_events_graph_columns(conn: sqlite3.Connection) -> None:
    """events: graph aggregation columns (entity_id/fact_id/quote/...)."""
    _add_columns_if_missing(
        conn,
        "events",
        [
            ("entity_id", "INTEGER"),
            ("fact_id", "TEXT"),
            ("fact_type", "TEXT"),
            ("quote", "TEXT"),
            ("start_ms", "INTEGER"),
            ("end_ms", "INTEGER"),
            ("polarity", "REAL"),
            ("intensity", "REAL"),
        ],
    )


def _m004_entities_columns(conn: sqlite3.Connection) -> None:
    """entities: archived/merged_into_id/is_owner. No-op if entities doesn't
    exist yet (graph schema not applied on this DB) — checked explicitly,
    not swallowed via bare except."""
    if not table_exists(conn, "entities"):
        return
    _add_columns_if_missing(
        conn,
        "entities",
        [
            ("archived", "INTEGER DEFAULT 0"),
            ("merged_into_id", "INTEGER"),
            ("is_owner", "INTEGER DEFAULT 0"),
        ],
    )


def _m005_calls_columns(conn: sqlite3.Connection) -> None:
    """calls: pipeline_stage (crash-resume) + role_fragile (role-noise doctrine) + call_type."""
    _add_columns_if_missing(
        conn,
        "calls",
        [
            ("pipeline_stage", "INTEGER NOT NULL DEFAULT 0"),
            ("role_fragile", "INTEGER NOT NULL DEFAULT 0"),
            ("call_type", "TEXT"),
        ],
    )


def _m006_dashboard_indexes(conn: sqlite3.Connection) -> None:
    """Indexes for dashboard/poller hot paths. entities index guarded by
    existence (graph schema may not be applied on this DB)."""
    for sql in (
        "CREATE INDEX IF NOT EXISTS idx_calls_user_status ON calls(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_calls_updated_at ON calls(updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_calls_user_datetime ON calls(user_id, call_datetime)",
    ):
        conn.execute(sql)
    if table_exists(conn, "entities"):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entities_user_archived ON entities(user_id, archived)"
        )


def _m007_calls_md5_unique_index(conn: sqlite3.Connection) -> None:
    """Atomic MD5-dedup index (F2.5). If pre-existing duplicate (user_id,
    source_md5) rows already violate it, that is a real pre-existing data
    problem — log loudly and continue (do not guess which duplicate to keep;
    do not block all later migrations over it)."""
    try:
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_calls_user_md5
               ON calls(user_id, source_md5)
               WHERE source_md5 IS NOT NULL"""
        )
    except sqlite3.IntegrityError as exc:
        logger.warning(
            "idx_calls_user_md5: cannot create — duplicate (user_id, source_md5) "
            "rows already exist in calls (%s). Dedup index left absent; "
            "investigate and de-duplicate manually.",
            exc,
        )


def _m008_fts_drop_user_id(conn: sqlite3.Connection) -> None:
    """P-DB-06: transcripts_fts declared `user_id` as an FTS column, but its
    content table `transcripts` has no such column — `INSERT INTO
    transcripts_fts(transcripts_fts) VALUES('rebuild')` fails looking for it.
    Ownership filtering never actually used the FTS column (search_transcripts
    / dashboard search both join to `calls.user_id`) — safe to drop. Recreate
    the virtual table without it and rebuild the index from `transcripts`.
    No-op on a fresh schema.sql-created DB (already correct)."""
    cols = _existing_columns(conn, "transcripts_fts") if table_exists(conn, "transcripts_fts") else set()
    if "user_id" not in cols:
        return
    conn.execute("DROP TABLE transcripts_fts")
    conn.execute(
        """CREATE VIRTUAL TABLE transcripts_fts USING fts5(
            text, speaker, call_id UNINDEXED,
            content='transcripts', content_rowid='segment_id'
        )"""
    )
    conn.execute("INSERT INTO transcripts_fts(transcripts_fts) VALUES('rebuild')")


def _m009_owner_triggers(conn: sqlite3.Connection) -> None:
    """P-DB-03: calls/promises/events each carry their own `user_id` AND a FK
    to a parent (contacts/calls) that also has `user_id` — nothing stopped a
    child row disagreeing with its parent's owner. Composite FKs would require
    rebuilding these tables (calls/events/promises are large hot tables) —
    out of scope for a migration; triggers give the same guarantee (rejected
    by SQLite itself, not just application code) without a rewrite."""
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS trg_calls_owner_ins
        BEFORE INSERT ON calls
        WHEN NEW.contact_id IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'calls.user_id does not match contacts.user_id for contact_id')
            WHERE NOT EXISTS (
                SELECT 1 FROM contacts WHERE contact_id = NEW.contact_id AND user_id = NEW.user_id
            );
        END;

        CREATE TRIGGER IF NOT EXISTS trg_calls_owner_upd
        BEFORE UPDATE OF contact_id, user_id ON calls
        WHEN NEW.contact_id IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'calls.user_id does not match contacts.user_id for contact_id')
            WHERE NOT EXISTS (
                SELECT 1 FROM contacts WHERE contact_id = NEW.contact_id AND user_id = NEW.user_id
            );
        END;

        CREATE TRIGGER IF NOT EXISTS trg_promises_owner_ins
        BEFORE INSERT ON promises
        BEGIN
            SELECT RAISE(ABORT, 'promises.user_id does not match calls.user_id')
            WHERE NOT EXISTS (SELECT 1 FROM calls WHERE call_id = NEW.call_id AND user_id = NEW.user_id);
            SELECT RAISE(ABORT, 'promises.user_id does not match contacts.user_id for contact_id')
            WHERE NEW.contact_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM contacts WHERE contact_id = NEW.contact_id AND user_id = NEW.user_id
            );
        END;

        CREATE TRIGGER IF NOT EXISTS trg_promises_owner_upd
        BEFORE UPDATE OF call_id, contact_id, user_id ON promises
        BEGIN
            SELECT RAISE(ABORT, 'promises.user_id does not match calls.user_id')
            WHERE NOT EXISTS (SELECT 1 FROM calls WHERE call_id = NEW.call_id AND user_id = NEW.user_id);
            SELECT RAISE(ABORT, 'promises.user_id does not match contacts.user_id for contact_id')
            WHERE NEW.contact_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM contacts WHERE contact_id = NEW.contact_id AND user_id = NEW.user_id
            );
        END;

        CREATE TRIGGER IF NOT EXISTS trg_events_owner_ins
        BEFORE INSERT ON events
        BEGIN
            SELECT RAISE(ABORT, 'events.user_id does not match calls.user_id')
            WHERE NOT EXISTS (SELECT 1 FROM calls WHERE call_id = NEW.call_id AND user_id = NEW.user_id);
            SELECT RAISE(ABORT, 'events.user_id does not match contacts.user_id for contact_id')
            WHERE NEW.contact_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM contacts WHERE contact_id = NEW.contact_id AND user_id = NEW.user_id
            );
        END;

        CREATE TRIGGER IF NOT EXISTS trg_events_owner_upd
        BEFORE UPDATE OF call_id, contact_id, user_id ON events
        BEGIN
            SELECT RAISE(ABORT, 'events.user_id does not match calls.user_id')
            WHERE NOT EXISTS (SELECT 1 FROM calls WHERE call_id = NEW.call_id AND user_id = NEW.user_id);
            SELECT RAISE(ABORT, 'events.user_id does not match contacts.user_id for contact_id')
            WHERE NEW.contact_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM contacts WHERE contact_id = NEW.contact_id AND user_id = NEW.user_id
            );
        END;
        """
    )


ALL_MIGRATIONS: list[Migration] = [
    Migration(1, "contacts_columns", _m001_contacts_columns),
    Migration(2, "analyses_columns", _m002_analyses_columns),
    Migration(3, "events_graph_columns", _m003_events_graph_columns),
    Migration(4, "entities_columns", _m004_entities_columns),
    Migration(5, "calls_columns", _m005_calls_columns),
    Migration(6, "dashboard_indexes", _m006_dashboard_indexes),
    Migration(7, "calls_md5_unique_index", _m007_calls_md5_unique_index),
    Migration(8, "fts_drop_user_id", _m008_fts_drop_user_id),
    Migration(9, "owner_triggers", _m009_owner_triggers),
]


def _journal_ddl() -> str:
    return """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            checksum    TEXT NOT NULL,
            applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """


def apply_migrations(
    conn: sqlite3.Connection, migrations: list[Migration] = ALL_MIGRATIONS
) -> None:
    """Apply every migration not yet recorded in schema_migrations, in id
    order. Each migration is its own transaction: on any exception it rolls
    back completely (no partial ALTERs, user_version not advanced) and
    re-raises — no ``except: pass``. An already-applied migration whose
    checksum no longer matches its current source raises
    :class:`MigrationChecksumError` before touching anything further.
    Idempotent: a second call with nothing new to apply changes zero rows.
    """
    conn.execute(_journal_ddl())
    conn.commit()

    applied = {
        row["id"]: row["checksum"]
        for row in conn.execute("SELECT id, checksum FROM schema_migrations").fetchall()
    }

    for m in sorted(migrations, key=lambda x: x.id):
        if m.id in applied:
            if applied[m.id] != m.checksum:
                raise MigrationChecksumError(
                    f"migration {m.id} ({m.name}): checksum on disk does not match "
                    f"schema_migrations — the applied migration's code changed after "
                    f"the fact. Never edit a released migration; add a new one."
                )
            continue

        conn.execute("BEGIN")
        try:
            m.apply(conn)
            conn.execute(
                "INSERT INTO schema_migrations (id, name, checksum) VALUES (?, ?, ?)",
                (m.id, m.name, m.checksum),
            )
            conn.execute(f"PRAGMA user_version={int(m.id)}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        logger.info("migration %d (%s) applied", m.id, m.name)


# ---------------------------------------------------------------------------
# Pre/post-flight integrity checks (report only — never auto-fix ownership)
# ---------------------------------------------------------------------------


def quick_check(conn: sqlite3.Connection) -> str:
    return conn.execute("PRAGMA quick_check").fetchone()[0]


def foreign_key_check(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("PRAGMA foreign_key_check").fetchall()]


_OWNER_MISMATCH_QUERIES: dict[str, str] = {
    "calls": """
        SELECT c.call_id AS row_id, c.user_id, c.contact_id
        FROM calls c JOIN contacts k ON k.contact_id = c.contact_id
        WHERE c.contact_id IS NOT NULL AND k.user_id != c.user_id
    """,
    "promises": """
        SELECT p.promise_id AS row_id, p.user_id, p.call_id, p.contact_id
        FROM promises p JOIN calls c ON c.call_id = p.call_id
        WHERE c.user_id != p.user_id
        UNION
        SELECT p.promise_id AS row_id, p.user_id, p.call_id, p.contact_id
        FROM promises p JOIN contacts k ON k.contact_id = p.contact_id
        WHERE p.contact_id IS NOT NULL AND k.user_id != p.user_id
    """,
    "events": """
        SELECT e.id AS row_id, e.user_id, e.call_id, e.contact_id
        FROM events e JOIN calls c ON c.call_id = e.call_id
        WHERE c.user_id != e.user_id
        UNION
        SELECT e.id AS row_id, e.user_id, e.call_id, e.contact_id
        FROM events e JOIN contacts k ON k.contact_id = e.contact_id
        WHERE e.contact_id IS NOT NULL AND k.user_id != e.user_id
    """,
}


def find_owner_mismatches(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Scan direct-user_id child tables for rows disagreeing with a parent's
    owner. Report-only — callers must quarantine/investigate, never guess
    and rewrite the owner."""
    out: dict[str, list[dict]] = {}
    for table, sql in _OWNER_MISMATCH_QUERIES.items():
        if not table_exists(conn, table):
            continue
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
        if rows:
            out[table] = rows
    return out


def integrity_report(conn: sqlite3.Connection) -> dict:
    """Bundle quick_check + foreign_key_check + owner-mismatch scan.
    Used as both preflight (before applying migrations) and postflight
    (after) — same shape, diffable."""
    return {
        "quick_check": quick_check(conn),
        "foreign_key_violations": foreign_key_check(conn),
        "owner_mismatches": find_owner_mismatches(conn),
    }


def data_at_risk(conn: sqlite3.Connection, migrations: list["Migration"] = None) -> bool:
    """True, если применение НЕОТРАБОТАННЫХ миграций затронет реальные данные.

    Гейт бэкапа обязан взводиться САМ, а не по желанию вызывающего: параметр
    ``backup_dir``, который никто не передаёт, — это фиговый листок, а не
    защита (проверено: ни один боевой вызов ``init_db`` его не передавал,
    включая общую точку входа CLI ``cli/utils.load_config_and_repo``).

    Взводимся только когда есть что терять: (1) остались непримененные
    миграции и (2) в БД есть хоть один звонок. Пустая/свежая/``:memory:``
    база данных ничего не теряет — тесты и первый bootstrap не задеваются.
    """
    if migrations is None:
        migrations = ALL_MIGRATIONS
    try:
        conn.execute(_journal_ddl())
        applied = {
            row["id"] for row in conn.execute("SELECT id FROM schema_migrations").fetchall()
        }
    except sqlite3.Error:
        return False
    if all(m.id in applied for m in migrations):
        return False
    try:
        return conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0] > 0
    except sqlite3.Error:
        return False


def default_backup_dir(db_path: str) -> str:
    """Каталог бэкапов по умолчанию рядом с БД (``<родитель БД>/backups``)."""
    return str(Path(db_path).resolve().parent / "backups")


def ensure_backup_before_migrate(
    db_path: str, backup_dir: str, *, unsafe: bool = False
) -> None:
    """Require a verified backup in ``backup_dir`` before migrating a real
    database. Skipped when ``unsafe=True`` (explicit "I understand the risk",
    e.g. throwaway/test runs) or when ``db_path`` does not exist yet (nothing
    to protect). Reuses ops.backup — this module owns no backup logic itself.
    """
    if unsafe or not Path(db_path).exists():
        return
    from callprofiler.ops.backup import latest_verified_backup

    if latest_verified_backup(backup_dir) is None:
        raise RuntimeError(
            f"No verified backup found in {backup_dir}. Run "
            "callprofiler.ops.backup.create_backup() first, or pass unsafe=True "
            "if you understand the risk."
        )
