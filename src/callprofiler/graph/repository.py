# -*- coding: utf-8 -*-
"""
graph/repository.py — CRUD for Knowledge Graph tables.

Follows the same sqlite3-direct style as db/repository.py.
Every method filters by user_id. No ORM.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


# ── Schema migration helpers ────────────────────────────────────────────────

def _col_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    return column in existing


def _index_exists(conn: sqlite3.Connection, index_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ).fetchone()
    return row is not None


def apply_graph_schema(conn: sqlite3.Connection) -> None:
    """Apply graph DDL and run incremental migrations.

    Safe to call on every startup — all operations are idempotent.
    """
    conn.executescript(_GRAPH_DDL)

    # ── analyses.schema_version ──────────────────────────────────────────
    if not _col_exists(conn, "analyses", "schema_version"):
        conn.execute(
            "ALTER TABLE analyses ADD COLUMN schema_version TEXT DEFAULT 'v1'"
        )
        log.info("[graph] migration: analyses.schema_version added (DEFAULT 'v1')")

    # ── events graph-extension columns ───────────────────────────────────
    _migrations = [
        ("events", "entity_id", "INTEGER REFERENCES entities(id)"),
        ("events", "fact_id",   "TEXT"),
        ("events", "quote",     "TEXT"),
        ("events", "start_ms",  "INTEGER"),
        ("events", "end_ms",    "INTEGER"),
        ("events", "polarity",  "INTEGER"),
        ("events", "intensity", "REAL"),
    ]
    for table, col, defn in _migrations:
        if not _col_exists(conn, table, col):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
            log.info("[graph] migration: %s.%s added", table, col)

    # ── entities merge + owner fields ────────────────────────────────────
    _entity_migrations = [
        ("entities", "archived",       "INTEGER DEFAULT 0"),
        ("entities", "merged_into_id", "INTEGER REFERENCES entities(id)"),
        ("entities", "is_owner",       "INTEGER DEFAULT 0"),
    ]
    for table, col, defn in _entity_migrations:
        if not _col_exists(conn, table, col):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
            log.info("[graph] migration: %s.%s added", table, col)

    if not _index_exists(conn, "idx_entities_owner"):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entities_owner "
            "ON entities(user_id, is_owner)"
        )

    # Unique index on events.fact_id (partial — only non-NULL values)
    if not _index_exists(conn, "idx_events_factid"):
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_factid "
            "ON events(fact_id) WHERE fact_id IS NOT NULL"
        )
    if not _index_exists(conn, "idx_events_entity"):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_id)"
        )

    conn.commit()


_GRAPH_DDL = """
CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    entity_type     TEXT    NOT NULL,
    canonical_name  TEXT    NOT NULL,
    normalized_key  TEXT    NOT NULL,
    aliases         TEXT,
    attributes      TEXT,
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, entity_type, normalized_key)
);
CREATE INDEX IF NOT EXISTS idx_entities_user_type ON entities(user_id, entity_type);

CREATE TABLE IF NOT EXISTS relations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT    NOT NULL REFERENCES users(user_id),
    src_entity_id       INTEGER NOT NULL REFERENCES entities(id),
    dst_entity_id       INTEGER NOT NULL REFERENCES entities(id),
    relation_type       TEXT    NOT NULL,
    weight              REAL    DEFAULT 1.0,
    confidence          REAL    DEFAULT 1.0,
    first_seen_call_id  INTEGER REFERENCES calls(call_id),
    last_seen_call_id   INTEGER REFERENCES calls(call_id),
    call_count          INTEGER DEFAULT 1,
    created_at          TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, src_entity_id, dst_entity_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_relations_src ON relations(src_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_dst ON relations(dst_entity_id);

CREATE TABLE IF NOT EXISTS entity_metrics (
    entity_id           INTEGER PRIMARY KEY REFERENCES entities(id),
    user_id             TEXT    NOT NULL,
    total_calls         INTEGER DEFAULT 0,
    total_promises      INTEGER DEFAULT 0,
    fulfilled_promises  INTEGER DEFAULT 0,
    broken_promises     INTEGER DEFAULT 0,
    overdue_promises    INTEGER DEFAULT 0,
    contradictions      INTEGER DEFAULT 0,
    vagueness_count     INTEGER DEFAULT 0,
    blame_shift_count   INTEGER DEFAULT 0,
    emotional_spikes    INTEGER DEFAULT 0,
    avg_risk            REAL    DEFAULT 0,
    bs_index            REAL    DEFAULT 0,
    bs_formula_version  TEXT    DEFAULT 'v1_linear',
    emotional_pattern   TEXT,
    last_interaction    TEXT,
    updated_at          TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entity_merges_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    canonical_id    INTEGER NOT NULL REFERENCES entities(id),
    duplicate_id    INTEGER NOT NULL REFERENCES entities(id),
    confidence      REAL,
    signals_json    TEXT,
    reason          TEXT,
    snapshot_json   TEXT,
    merged_by       TEXT,
    reversible      INTEGER DEFAULT 1,
    merged_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
    unmerged_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_entity_merges_user ON entity_merges_log(user_id);
CREATE INDEX IF NOT EXISTS idx_entity_merges_canonical ON entity_merges_log(canonical_id);

CREATE TABLE IF NOT EXISTS graph_replay_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL,
    calls_processed INTEGER DEFAULT 0,
    facts_total     INTEGER DEFAULT 0,
    facts_inserted  INTEGER DEFAULT 0,
    facts_rejected  INTEGER DEFAULT 0,
    rejection_rate  REAL    DEFAULT 0,
    entities_count  INTEGER DEFAULT 0,
    avg_bs_index    REAL,
    audit_critical  INTEGER DEFAULT 0,
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_replay_runs_user ON graph_replay_runs(user_id, created_at);

CREATE TABLE IF NOT EXISTS bs_thresholds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL,
    reliable_max    REAL    NOT NULL,
    noisy_max       REAL    NOT NULL,
    risky_max       REAL    NOT NULL,
    unreliable_max  REAL    NOT NULL,
    entity_count    INTEGER DEFAULT 0,
    std_dev         REAL,
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bs_thresholds_user ON bs_thresholds(user_id, created_at);
"""


# ── GraphRepository ──────────────────────────────────────────────────────────

class GraphRepository:
    """Low-level CRUD for graph tables. Caller owns the connection lifecycle."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        self._conn = conn

    # ── entities ─────────────────────────────────────────────────────────

    def upsert_entity(
        self,
        user_id: str,
        entity_type: str,
        canonical_name: str,
        normalized_key: str,
        aliases: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        """Insert or update entity; returns entity id."""
        now = _now()
        aliases_json = json.dumps(aliases or [], ensure_ascii=False)
        attrs_json = json.dumps(attributes or {}, ensure_ascii=False)

        self._conn.execute(
            """
            INSERT INTO entities
                (user_id, entity_type, canonical_name, normalized_key,
                 aliases, attributes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, entity_type, normalized_key) DO UPDATE SET
                canonical_name = excluded.canonical_name,
                aliases        = excluded.aliases,
                attributes     = excluded.attributes,
                updated_at     = excluded.updated_at
            """,
            (user_id, entity_type, canonical_name, normalized_key,
             aliases_json, attrs_json, now, now),
        )
        row = self._conn.execute(
            "SELECT id FROM entities WHERE user_id=? AND entity_type=? AND normalized_key=?",
            (user_id, entity_type, normalized_key),
        ).fetchone()
        return row["id"]

    def get_entity(self, entity_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM entities WHERE id=?", (entity_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_entities(self, user_id: str, entity_type: str | None = None) -> list[dict]:
        if entity_type:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE user_id=? AND entity_type=? ORDER BY id",
                (user_id, entity_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE user_id=? ORDER BY entity_type, id",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── relations ─────────────────────────────────────────────────────────

    def get_relation(
        self,
        user_id: str,
        src_id: int,
        dst_id: int,
        relation_type: str,
    ) -> dict | None:
        row = self._conn.execute(
            """SELECT * FROM relations
               WHERE user_id=? AND src_entity_id=? AND dst_entity_id=? AND relation_type=?""",
            (user_id, src_id, dst_id, relation_type),
        ).fetchone()
        return dict(row) if row else None

    def upsert_relation_with_decay(
        self,
        user_id: str,
        src_id: int,
        dst_id: int,
        relation_type: str,
        confidence: float,
        call_id: int,
        call_datetime: str | None,
        decay_days: int = 180,
    ) -> None:
        now = _now()
        existing = self.get_relation(user_id, src_id, dst_id, relation_type)
        if existing:
            updated_at = existing.get("updated_at") or now
            try:
                dt_updated = datetime.fromisoformat(updated_at.replace(" ", "T"))
                dt_now = datetime.fromisoformat(now.replace(" ", "T"))
                days_since = max(0, (dt_now - dt_updated).days)
            except (ValueError, AttributeError):
                days_since = 0

            decay_factor = 0.5 ** (days_since / decay_days)
            new_weight = existing["weight"] * decay_factor + confidence

            self._conn.execute(
                """UPDATE relations SET
                       weight             = ?,
                       confidence         = ?,
                       last_seen_call_id  = ?,
                       call_count         = call_count + 1,
                       updated_at         = ?
                   WHERE user_id=? AND src_entity_id=? AND dst_entity_id=? AND relation_type=?""",
                (new_weight, confidence, call_id, now,
                 user_id, src_id, dst_id, relation_type),
            )
        else:
            self._conn.execute(
                """INSERT INTO relations
                       (user_id, src_entity_id, dst_entity_id, relation_type,
                        weight, confidence, first_seen_call_id, last_seen_call_id,
                        call_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (user_id, src_id, dst_id, relation_type,
                 confidence, confidence, call_id, call_id, now, now),
            )

    def get_relations_for_entity(self, entity_id: int, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT * FROM relations
               WHERE user_id=? AND (src_entity_id=? OR dst_entity_id=?)
               ORDER BY weight DESC""",
            (user_id, entity_id, entity_id),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── facts (events extension) ──────────────────────────────────────────

    def upsert_fact(
        self,
        user_id: str,
        call_id: int,
        contact_id: int | None,
        entity_id: int | None,
        fact_id: str,
        event_type: str,
        quote: str,
        value: str | None = None,
        polarity: int | None = None,
        intensity: float | None = None,
        confidence: float = 1.0,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> None:
        """Insert fact into events table using fact_id for deduplication.

        Maps structured_fact types to the events.event_type CHECK constraint:
          promise, contradiction → kept as-is
          emotion_spike, vagueness, blame_shift, claim → 'fact'
        """
        allowed = {"promise", "debt", "contradiction", "risk", "task", "fact", "smalltalk"}
        db_event_type = event_type if event_type in allowed else "fact"

        self._conn.execute(
            """
            INSERT OR IGNORE INTO events
                (user_id, contact_id, call_id, event_type, who,
                 payload, source_quote, confidence, status,
                 entity_id, fact_id, quote, start_ms, end_ms, polarity, intensity)
            VALUES (?, ?, ?, ?, 'UNKNOWN', ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, contact_id, call_id, db_event_type,
             value or "", quote, confidence,
             entity_id, fact_id, quote, start_ms, end_ms, polarity, intensity),
        )

    def get_facts_for_entity(
        self, entity_id: int, user_id: str, event_types: list[str] | None = None
    ) -> list[dict]:
        if event_types:
            placeholders = ",".join("?" * len(event_types))
            rows = self._conn.execute(
                f"""SELECT e.*, c.call_datetime
                    FROM events e
                    LEFT JOIN calls c ON c.call_id = e.call_id
                    WHERE e.user_id=? AND e.entity_id=? AND e.event_type IN ({placeholders})
                    ORDER BY c.call_datetime""",
                (user_id, entity_id, *event_types),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT e.*, c.call_datetime
                   FROM events e
                   LEFT JOIN calls c ON c.call_id = e.call_id
                   WHERE e.user_id=? AND e.entity_id=?
                   ORDER BY c.call_datetime""",
                (user_id, entity_id),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── entity_metrics ────────────────────────────────────────────────────

    def upsert_entity_metrics(
        self,
        entity_id: int,
        user_id: str,
        total_calls: int = 0,
        total_promises: int = 0,
        fulfilled_promises: int = 0,
        broken_promises: int = 0,
        overdue_promises: int = 0,
        contradictions: int = 0,
        vagueness_count: int = 0,
        blame_shift_count: int = 0,
        emotional_spikes: int = 0,
        avg_risk: float = 0.0,
        bs_index: float = 0.0,
        bs_formula_version: str = "v1_linear",
        emotional_pattern: str | None = None,
        last_interaction: str | None = None,
    ) -> None:
        now = _now()
        self._conn.execute(
            """
            INSERT INTO entity_metrics
                (entity_id, user_id, total_calls, total_promises, fulfilled_promises,
                 broken_promises, overdue_promises, contradictions, vagueness_count,
                 blame_shift_count, emotional_spikes, avg_risk, bs_index,
                 bs_formula_version, emotional_pattern, last_interaction, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                user_id             = excluded.user_id,
                total_calls         = excluded.total_calls,
                total_promises      = excluded.total_promises,
                fulfilled_promises  = excluded.fulfilled_promises,
                broken_promises     = excluded.broken_promises,
                overdue_promises    = excluded.overdue_promises,
                contradictions      = excluded.contradictions,
                vagueness_count     = excluded.vagueness_count,
                blame_shift_count   = excluded.blame_shift_count,
                emotional_spikes    = excluded.emotional_spikes,
                avg_risk            = excluded.avg_risk,
                bs_index            = excluded.bs_index,
                bs_formula_version  = excluded.bs_formula_version,
                emotional_pattern   = excluded.emotional_pattern,
                last_interaction    = excluded.last_interaction,
                updated_at          = excluded.updated_at
            """,
            (entity_id, user_id, total_calls, total_promises, fulfilled_promises,
             broken_promises, overdue_promises, contradictions, vagueness_count,
             blame_shift_count, emotional_spikes, avg_risk, bs_index,
             bs_formula_version, emotional_pattern, last_interaction, now),
        )

    def get_entity_metrics(self, entity_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM entity_metrics WHERE entity_id=?", (entity_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── aggregation queries ───────────────────────────────────────────────

    def count_facts_by_type(self, entity_id: int, user_id: str) -> dict[str, int]:
        rows = self._conn.execute(
            """SELECT event_type, COUNT(*) as cnt
               FROM events
               WHERE entity_id=? AND user_id=?
               GROUP BY event_type""",
            (entity_id, user_id),
        ).fetchall()
        return {r["event_type"]: r["cnt"] for r in rows}

    def count_distinct_calls(self, entity_id: int, user_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT call_id) as n FROM events WHERE entity_id=? AND user_id=?",
            (entity_id, user_id),
        ).fetchone()
        return row["n"] if row else 0

    def avg_risk_for_entity(self, entity_id: int, user_id: str) -> float:
        row = self._conn.execute(
            """SELECT AVG(a.risk_score) as avg_r
               FROM events e
               JOIN analyses a ON a.call_id = e.call_id
               WHERE e.entity_id=? AND e.user_id=?""",
            (entity_id, user_id),
        ).fetchone()
        return float(row["avg_r"] or 0.0)

    def last_interaction_for_entity(self, entity_id: int, user_id: str) -> str | None:
        row = self._conn.execute(
            """SELECT MAX(c.call_datetime) as last_dt
               FROM events e
               JOIN calls c ON c.call_id = e.call_id
               WHERE e.entity_id=? AND e.user_id=?""",
            (entity_id, user_id),
        ).fetchone()
        return row["last_dt"] if row else None

    # ── replay runs ───────────────────────────────────────────────────────

    def save_replay_run(
        self,
        user_id: str,
        calls_processed: int,
        facts_total: int,
        facts_inserted: int,
        facts_rejected: int,
        entities_count: int,
        avg_bs_index: float | None,
        audit_critical: int,
    ) -> int:
        """Save a replay run record; returns the new row id."""
        rejection_rate = facts_rejected / facts_total if facts_total > 0 else 0.0
        self._conn.execute(
            """INSERT INTO graph_replay_runs
               (user_id, calls_processed, facts_total, facts_inserted,
                facts_rejected, rejection_rate, entities_count, avg_bs_index, audit_critical)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, calls_processed, facts_total, facts_inserted,
             facts_rejected, rejection_rate, entities_count, avg_bs_index, audit_critical),
        )
        self._conn.commit()
        return self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_last_replay_run(self, user_id: str) -> dict | None:
        row = self._conn.execute(
            """SELECT * FROM graph_replay_runs
               WHERE user_id=? ORDER BY created_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    # ── bs_thresholds ────────────────────────────────────────────────────

    def save_bs_thresholds(
        self,
        user_id: str,
        thresholds: dict[str, float],
        entity_count: int,
        std_dev: float,
    ) -> None:
        self._conn.execute(
            """INSERT INTO bs_thresholds
               (user_id, reliable_max, noisy_max, risky_max, unreliable_max,
                entity_count, std_dev)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id,
             thresholds["reliable_max"], thresholds["noisy_max"],
             thresholds["risky_max"], thresholds["unreliable_max"],
             entity_count, std_dev),
        )
        self._conn.commit()

    def get_latest_bs_thresholds(self, user_id: str) -> dict | None:
        row = self._conn.execute(
            """SELECT * FROM bs_thresholds
               WHERE user_id=? ORDER BY created_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_bs_scores_filtered(
        self,
        user_id: str,
        min_calls: int = 3,
        min_promises: int = 1,
    ) -> list[float]:
        rows = self._conn.execute(
            """SELECT m.bs_index
               FROM entity_metrics m
               JOIN entities e ON e.id = m.entity_id
               WHERE m.user_id=? AND e.archived=0 AND COALESCE(e.is_owner,0)=0
                 AND m.total_calls >= ? AND m.total_promises >= ?
               ORDER BY m.bs_index""",
            (user_id, min_calls, min_promises),
        ).fetchall()
        return [float(r["bs_index"]) for r in rows]

    # ── stats ─────────────────────────────────────────────────────────────

    def stats(self, user_id: str) -> dict:
        entity_rows = self._conn.execute(
            "SELECT entity_type, COUNT(*) as n FROM entities WHERE user_id=? GROUP BY entity_type",
            (user_id,),
        ).fetchall()
        relation_rows = self._conn.execute(
            "SELECT relation_type, COUNT(*) as n FROM relations WHERE user_id=? GROUP BY relation_type",
            (user_id,),
        ).fetchall()
        fact_rows = self._conn.execute(
            """SELECT event_type, COUNT(*) as n FROM events
               WHERE user_id=? AND entity_id IS NOT NULL GROUP BY event_type""",
            (user_id,),
        ).fetchall()
        metrics_count = self._conn.execute(
            "SELECT COUNT(*) as n FROM entity_metrics WHERE user_id=?", (user_id,)
        ).fetchone()["n"]

        return {
            "entities": {r["entity_type"]: r["n"] for r in entity_rows},
            "relations": {r["relation_type"]: r["n"] for r in relation_rows},
            "facts": {r["event_type"]: r["n"] for r in fact_rows},
            "entities_with_metrics": metrics_count,
        }


# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
