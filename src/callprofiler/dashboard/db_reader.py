# -*- coding: utf-8 -*-
"""
Database reader for dashboard — read-only SQLite queries.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from callprofiler.dashboard.config import DB_QUERY_TIMEOUT_SEC

log = logging.getLogger(__name__)


class DashboardDBReader:
    """Read-only database access for dashboard."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self):
        """Open read-only connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                f"file:{self.db_path}?mode=ro",
                uri=True,
                timeout=DB_QUERY_TIMEOUT_SEC,
            )
            self._conn.row_factory = sqlite3.Row

    def close(self):
        """Close connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_latest_timestamp(self, user_id: str) -> str | None:
        """Get MAX(updated_at) across all tables for polling."""
        self.connect()
        query = """
        SELECT MAX(ts) AS latest FROM (
            SELECT MAX(updated_at) AS ts FROM calls WHERE user_id = ?
            UNION ALL
            SELECT MAX(updated_at) AS ts FROM analyses WHERE call_id IN (SELECT call_id FROM calls WHERE user_id = ?)
            UNION ALL
            SELECT MAX(updated_at) AS ts FROM entities WHERE user_id = ?
            UNION ALL
            SELECT MAX(updated_at) AS ts FROM entity_metrics WHERE user_id = ?
        )
        """
        row = self._conn.execute(query, (user_id, user_id, user_id, user_id)).fetchone()
        return row["latest"] if row else None

    def get_recent_calls(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent calls with analysis data."""
        self.connect()
        query = """
        SELECT
            c.call_id,
            c.call_datetime,
            c.direction,
            c.duration_sec,
            c.status,
            COALESCE(ct.display_name, c.source_filename) AS contact_label,
            a.call_type,
            a.risk_score,
            a.summary
        FROM calls c
        LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
        LEFT JOIN analyses a ON a.call_id = c.call_id
        WHERE c.user_id = ?
        ORDER BY COALESCE(c.call_datetime, c.created_at) DESC
        LIMIT ?
        """
        rows = self._conn.execute(query, (user_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def get_entity_profile(self, entity_id: int, user_id: str) -> dict[str, Any] | None:
        """Get full entity profile (metrics + psychology + biography)."""
        self.connect()

        # Base entity
        entity_row = self._conn.execute(
            """SELECT id, canonical_name, entity_type, aliases
               FROM entities
               WHERE id = ? AND user_id = ? AND archived = 0""",
            (entity_id, user_id),
        ).fetchone()
        if not entity_row:
            return None

        profile = {
            "entity_id": entity_row["id"],
            "canonical_name": entity_row["canonical_name"],
            "entity_type": entity_row["entity_type"],
            "aliases": json.loads(entity_row["aliases"] or "[]"),
        }

        # Entity metrics
        metrics_row = self._conn.execute(
            """SELECT bs_index, avg_risk, total_calls, trust_score, volatility, conflict_count
               FROM entity_metrics
               WHERE entity_id = ? AND user_id = ?""",
            (entity_id, user_id),
        ).fetchone()
        if metrics_row:
            profile.update({
                "bs_index": metrics_row["bs_index"],
                "avg_risk": metrics_row["avg_risk"],
                "total_calls": metrics_row["total_calls"],
                "trust_score": metrics_row["trust_score"],
                "volatility": metrics_row["volatility"],
                "conflict_count": metrics_row["conflict_count"],
            })

        # Psychology profile (from graph)
        try:
            from callprofiler.biography.psychology_profiler import PsychologyProfiler
            profiler = PsychologyProfiler(self._conn)
            psych = profiler.build_profile(entity_id, user_id)
            if psych:
                profile["temperament"] = psych.get("temperament")
                profile["big_five"] = psych.get("big_five")
                profile["motivation"] = psych.get("motivation")
        except Exception as e:
            log.warning("Failed to load psychology profile for entity %d: %s", entity_id, e)

        # Biography portrait
        portrait_row = self._conn.execute(
            """SELECT prose, traits, relationship
               FROM bio_portraits
               WHERE entity_id = ? AND user_id = ?""",
            (entity_id, user_id),
        ).fetchone()
        if portrait_row:
            profile["prose"] = portrait_row["prose"]
            profile["traits"] = json.loads(portrait_row["traits"] or "[]")
            profile["relationship"] = portrait_row["relationship"]

        return profile

    def get_stats(self, user_id: str) -> dict[str, Any]:
        """Get overall system statistics."""
        self.connect()

        total_calls = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM calls WHERE user_id = ?", (user_id,)
        ).fetchone()["cnt"]

        total_entities = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM entities WHERE user_id = ? AND archived = 0", (user_id,)
        ).fetchone()["cnt"]

        total_portraits = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM bio_portraits WHERE user_id = ?", (user_id,)
        ).fetchone()["cnt"]

        avg_risk_row = self._conn.execute(
            """SELECT AVG(a.risk_score) AS avg_risk
               FROM analyses a
               JOIN calls c ON c.call_id = a.call_id
               WHERE c.user_id = ? AND a.risk_score IS NOT NULL""",
            (user_id,),
        ).fetchone()
        avg_risk = avg_risk_row["avg_risk"] if avg_risk_row else None

        last_call_row = self._conn.execute(
            """SELECT MAX(call_datetime) AS last_dt
               FROM calls
               WHERE user_id = ? AND call_datetime IS NOT NULL""",
            (user_id,),
        ).fetchone()
        last_call_datetime = last_call_row["last_dt"] if last_call_row else None

        return {
            "total_calls": total_calls,
            "total_entities": total_entities,
            "total_portraits": total_portraits,
            "avg_risk": avg_risk,
            "last_call_datetime": last_call_datetime,
        }
