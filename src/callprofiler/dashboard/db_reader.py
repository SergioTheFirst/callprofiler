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
            SELECT MAX(updated_at) AS ts FROM entities WHERE user_id = ?
            UNION ALL
            SELECT MAX(updated_at) AS ts FROM entity_metrics WHERE user_id = ?
        )
        """
        row = self._conn.execute(query, (user_id, user_id, user_id)).fetchone()
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
            c.created_at,
            c.updated_at,
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
            """SELECT bs_index, avg_risk, total_calls, emotional_pattern
               FROM entity_metrics
               WHERE entity_id = ? AND user_id = ?""",
            (entity_id, user_id),
        ).fetchone()
        if metrics_row:
            profile.update({
                "bs_index": metrics_row["bs_index"],
                "avg_risk": metrics_row["avg_risk"],
                "total_calls": metrics_row["total_calls"],
                "emotional_pattern": metrics_row["emotional_pattern"],
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

    def get_new_analyses(self, user_id: str, since_id: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        """Get analyses created after since_id for the live feed."""
        self.connect()
        rows = self._conn.execute(
            """SELECT a.analysis_id, a.call_id, a.parse_status, a.summary,
                      a.risk_score, a.call_type, a.schema_version, a.model,
                      a.prompt_version, a.created_at,
                      COALESCE(cnt.display_name, cnt.phone_e164, '?') as contact_name,
                      cnt.phone_e164,
                      c.call_datetime, c.direction, c.duration_sec,
                      c.source_filename
               FROM analyses a
               JOIN calls c ON c.call_id = a.call_id
               LEFT JOIN contacts cnt ON cnt.contact_id = c.contact_id
               WHERE c.user_id = ? AND a.analysis_id > ?
               ORDER BY a.analysis_id DESC
               LIMIT ?""",
            (user_id, since_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_characters(self, user_id: str) -> list[dict[str, Any]]:
        """Get all entities with metrics and psychology summary."""
        self.connect()
        rows = self._conn.execute(
            """SELECT e.id AS entity_id, e.canonical_name, e.entity_type,
                      em.total_calls, em.avg_risk, em.bs_index, em.trust_score,
                      ep.payload_json
               FROM entities e
               LEFT JOIN entity_metrics em ON em.entity_id = e.id AND em.user_id = e.user_id
               LEFT JOIN entity_profiles ep ON ep.entity_id = e.id AND ep.profile_type = 'psychology'
               WHERE e.user_id = ? AND e.archived = 0
               ORDER BY COALESCE(em.total_calls, 0) DESC""",
            (user_id,),
        ).fetchall()

        results = []
        for row in rows:
            payload = {}
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                pass

            temperament = (payload.get("temperament") or {})
            motivation = (payload.get("motivation") or {})

            results.append({
                "entity_id": row["entity_id"],
                "canonical_name": row["canonical_name"] or "?",
                "entity_type": row["entity_type"] or "person",
                "total_calls": row["total_calls"] or 0,
                "avg_risk": row["avg_risk"],
                "bs_index": row["bs_index"],
                "temperament_type": temperament.get("type"),
                "motivation_primary": motivation.get("primary"),
                "character_label": self._build_character_label(row, temperament, motivation),
                "has_portrait": self._has_portrait(row["entity_id"], user_id),
                "has_psychology": bool(payload),
            })
        return results

    def _build_character_label(self, row, temperament, motivation):
        parts = []
        tmp_type = (temperament or {}).get("type")
        mot_primary = (motivation or {}).get("primary")
        if tmp_type:
            parts.append(tmp_type.capitalize())
        if mot_primary:
            mot_map = {"achievement": "достиженец", "power": "властный", "affiliation": "партнёр", "security": "осторожный"}
            parts.append(mot_map.get(mot_primary, mot_primary))
        if not parts:
            risk = row["avg_risk"] or 0
            if risk >= 60:
                parts.append("Рисковый")
            elif risk >= 30:
                parts.append("Средний")
            else:
                parts.append("Надёжный")
        return "-".join(parts) if parts else "Неизвестный"

    def _has_portrait(self, entity_id: int, user_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM bio_portraits WHERE entity_id = ? AND user_id = ?",
            (entity_id, user_id),
        ).fetchone()
        return bool(row)

    def get_character_profile(self, entity_id: int, user_id: str) -> dict[str, Any] | None:
        """Full character profile: entity + metrics + psychology + portrait + contact + calls."""
        base = self.get_entity_profile(entity_id, user_id)
        if not base:
            return None

        profile = dict(base)
        profile["character_summary"] = ""
        profile["patterns"] = []
        profile["contact"] = None
        profile["open_promises"] = []
        profile["recent_calls"] = []
        profile["contradictions"] = []
        profile["temporal"] = None
        profile["network"] = None

        metrics_row = self._conn.execute(
            """SELECT bs_index, avg_risk, total_calls, trust_score,
                      volatility, conflict_count, emotional_pattern
               FROM entity_metrics WHERE entity_id = ? AND user_id = ?""",
            (entity_id, user_id),
        ).fetchone()

        psych = {}
        temperament = profile.get("temperament") or {}
        motivation = profile.get("motivation") or {}

        profile["character_summary"] = self._build_character_summary(
            metrics_row, temperament, motivation
        )

        pattern_rows = self._conn.execute(
            """SELECT name, severity, ratio, label
               FROM bio_behavior_patterns
               WHERE entity_id = ? AND user_id = ?""",
            (entity_id, user_id),
        ).fetchall()
        profile["patterns"] = [dict(r) for r in pattern_rows]

        contradiction_rows = self._conn.execute(
            """SELECT quote_1, quote_2, severity, contradiction_type, delta_days
               FROM bio_contradictions
               WHERE entity_id = ? AND user_id = ?
               ORDER BY severity DESC LIMIT 5""",
            (entity_id, user_id),
        ).fetchall()
        profile["contradictions"] = [dict(r) for r in contradiction_rows]

        canon = (base.get("canonical_name") or "").strip()
        aliases = base.get("aliases") or []
        contact_row = None
        if canon:
            contact_row = self._conn.execute(
                """SELECT contact_id, phone_e164, display_name, guessed_name, name_confirmed
                   FROM contacts
                   WHERE user_id = ? AND (display_name = ? OR display_name IN ({seq}))
                   LIMIT 1""".format(seq=",".join("?" * len(aliases))),
                (user_id, canon, *aliases),
            ).fetchone()
        if contact_row:
            profile["contact"] = dict(contact_row)
            cid = contact_row["contact_id"]
            promise_rows = self._conn.execute(
                """SELECT what, status, due, who FROM promises
                   WHERE user_id = ? AND contact_id = ? AND status = 'open'
                   ORDER BY created_at DESC LIMIT 10""",
                (user_id, cid),
            ).fetchall()
            profile["open_promises"] = [dict(r) for r in promise_rows]

            call_rows = self._conn.execute(
                """SELECT c.call_id, c.call_datetime, c.direction, c.duration_sec,
                          c.status, a.call_type, a.risk_score, a.summary,
                          COALESCE(ct.display_name, c.source_filename) AS contact_label
                   FROM calls c
                   LEFT JOIN analyses a ON a.call_id = c.call_id
                   LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
                   WHERE c.user_id = ? AND c.contact_id = ?
                   ORDER BY COALESCE(c.call_datetime, c.created_at) DESC LIMIT 10""",
                (user_id, cid),
            ).fetchall()
            profile["recent_calls"] = [dict(r) for r in call_rows]

        return profile

    def _build_character_summary(self, metrics_row, temperament, motivation):
        if not metrics_row:
            return "Нет данных."
        parts = []
        risk = metrics_row["avg_risk"] or 0
        bs = metrics_row["bs_index"] or 0
        trust = metrics_row["trust_score"] or 0

        if risk >= 70:
            parts.append("Высокорисковый")
        elif risk >= 40:
            parts.append("Средний риск")
        else:
            parts.append("Низкорисковый")

        tmp_type = (temperament or {}).get("type")
        if tmp_type:
            parts.append(tmp_type)

        mot_primary = (motivation or {}).get("primary")
        if mot_primary:
            mot_map = {"achievement": "достижение", "power": "власть", "affiliation": "привязанность", "security": "безопасность"}
            parts.append(f"мотивация — {mot_map.get(mot_primary, mot_primary)}")

        if bs >= 60:
            parts.append("склонен к размытым обещаниям")
        if trust >= 70:
            parts.append("высокое доверие")
        elif trust <= 30:
            parts.append("низкое доверие")

        return ". ".join(parts) + "."

    def get_contact_profile(self, contact_id: int, user_id: str) -> dict[str, Any] | None:
        """Full contact profile: contact info + summary + linked entities + recent calls."""
        self.connect()
        contact_row = self._conn.execute(
            """SELECT contact_id, phone_e164, display_name, guessed_name,
                      guessed_company, guess_confidence, name_confirmed, created_at
               FROM contacts WHERE contact_id = ? AND user_id = ?""",
            (contact_id, user_id),
        ).fetchone()
        if not contact_row:
            return None

        profile = dict(contact_row)
        profile["name_confirmed"] = bool(profile.get("name_confirmed", 0))

        summary_row = self._conn.execute(
            """SELECT total_calls, last_call_date, global_risk, avg_bs_score,
                      top_hook, open_promises, open_debts, personal_facts,
                      contact_role, advice
               FROM contact_summaries WHERE contact_id = ? AND user_id = ?""",
            (contact_id, user_id),
        ).fetchone()

        if summary_row:
            profile["total_calls"] = summary_row["total_calls"] or 0
            profile["last_call_date"] = summary_row["last_call_date"]
            profile["global_risk"] = summary_row["global_risk"]
            profile["avg_bs_score"] = summary_row["avg_bs_score"]
            profile["top_hook"] = summary_row["top_hook"]
            profile["contact_role"] = summary_row["contact_role"]
            profile["advice"] = summary_row["advice"]
            for field in ("open_promises", "open_debts", "personal_facts"):
                try:
                    profile[field] = json.loads(summary_row[field] or "[]")
                except (json.JSONDecodeError, TypeError):
                    profile[field] = []
        else:
            profile["total_calls"] = 0
            profile["open_promises"] = profile["open_debts"] = profile["personal_facts"] = []

        call_rows = self._conn.execute(
            """SELECT c.call_id, c.call_datetime, c.direction, c.duration_sec,
                      c.status, c.source_filename,
                      a.call_type, a.risk_score, a.summary,
                      COALESCE(ct.display_name, c.source_filename) AS contact_label
               FROM calls c
               LEFT JOIN analyses a ON a.call_id = c.call_id
               LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
               WHERE c.user_id = ? AND c.contact_id = ?
               ORDER BY COALESCE(c.call_datetime, c.created_at) DESC LIMIT 20""",
            (user_id, contact_id),
        ).fetchall()
        profile["recent_calls"] = [dict(r) for r in call_rows]

        canon = profile.get("display_name") or profile.get("guessed_name") or ""
        if canon:
            entity_rows = self._conn.execute(
                """SELECT id AS entity_id, canonical_name, entity_type
                   FROM entities
                   WHERE user_id = ? AND (canonical_name = ? OR canonical_name LIKE ?)
                   AND archived = 0 LIMIT 3""",
                (user_id, canon, f"%{canon}%"),
            ).fetchall()
            profile["linked_entities"] = [dict(r) for r in entity_rows]
        else:
            profile["linked_entities"] = []

        return profile


    def get_analytics(self, user_id: str) -> dict[str, Any]:
        """Comprehensive analytics: distributions, trends, top contacts."""
        self.connect()

        result = {}

        risk_rows = self._conn.execute(
            """SELECT a.risk_score
               FROM analyses a JOIN calls c ON c.call_id = a.call_id
               WHERE c.user_id = ? AND a.risk_score IS NOT NULL""",
            (user_id,),
        ).fetchall()
        risks = [r["risk_score"] for r in risk_rows]
        result["risk_distribution"] = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
        for r in risks:
            if r < 20: result["risk_distribution"]["0-20"] += 1
            elif r < 40: result["risk_distribution"]["20-40"] += 1
            elif r < 60: result["risk_distribution"]["40-60"] += 1
            elif r < 80: result["risk_distribution"]["60-80"] += 1
            else: result["risk_distribution"]["80-100"] += 1

        day_rows = self._conn.execute(
            """SELECT DATE(COALESCE(c.call_datetime, c.created_at)) as dt, COUNT(*) as cnt
               FROM calls c WHERE c.user_id = ?
               GROUP BY dt ORDER BY dt DESC LIMIT 30""",
            (user_id,),
        ).fetchall()
        result["calls_by_day"] = [{"date": r["dt"], "count": r["cnt"]} for r in reversed(day_rows)]

        top_calls_rows = self._conn.execute(
            """SELECT COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164) as name,
                      COUNT(*) as cnt
               FROM calls c
               LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
               WHERE c.user_id = ? AND c.contact_id IS NOT NULL
               GROUP BY ct.contact_id ORDER BY cnt DESC LIMIT 10""",
            (user_id,),
        ).fetchall()
        result["top_contacts_by_calls"] = [{"name": r["name"] or "?", "count": r["cnt"]} for r in top_calls_rows]

        top_risk_rows = self._conn.execute(
            """SELECT COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164) as name,
                      ROUND(AVG(a.risk_score), 1) as avg_risk
               FROM analyses a
               JOIN calls c ON c.call_id = a.call_id
               LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
               WHERE c.user_id = ? AND c.contact_id IS NOT NULL AND a.risk_score IS NOT NULL
               GROUP BY ct.contact_id ORDER BY avg_risk DESC LIMIT 10""",
            (user_id,),
        ).fetchall()
        result["top_contacts_by_risk"] = [{"name": r["name"] or "?", "avg_risk": r["avg_risk"]} for r in top_risk_rows]

        tmp_rows = self._conn.execute(
            """SELECT ep.payload_json
               FROM entity_profiles ep
               JOIN entities e ON e.id = ep.entity_id
               WHERE e.user_id = ? AND ep.profile_type = 'psychology'
               AND ep.payload_json IS NOT NULL""",
            (user_id,),
        ).fetchall()
        tmp_dist = {}
        for row in tmp_rows:
            try:
                p = json.loads(row["payload_json"] or "{}")
                t = (p.get("temperament") or {}).get("type")
                if t: tmp_dist[t] = tmp_dist.get(t, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        result["temperament_distribution"] = tmp_dist or {"нет данных": 1}

        type_rows = self._conn.execute(
            """SELECT a.call_type, COUNT(*) as cnt
               FROM analyses a JOIN calls c ON c.call_id = a.call_id
               WHERE c.user_id = ? GROUP BY a.call_type ORDER BY cnt DESC""",
            (user_id,),
        ).fetchall()
        result["call_type_distribution"] = {r["call_type"] or "unknown": r["cnt"] for r in type_rows}

        dir_rows = self._conn.execute(
            """SELECT c.direction, COUNT(*) as cnt
               FROM calls c WHERE c.user_id = ? GROUP BY c.direction""",
            (user_id,),
        ).fetchall()
        result["direction_distribution"] = {r["direction"] or "unknown": r["cnt"] for r in dir_rows}

        status_rows = self._conn.execute(
            """SELECT status, COUNT(*) as cnt FROM calls WHERE user_id = ?
               GROUP BY status""",
            (user_id,),
        ).fetchall()
        result["status_counts"] = {r["status"]: r["cnt"] for r in status_rows}

        bs_rows = self._conn.execute(
            """SELECT DATE(c.created_at) as dt,
                      ROUND(AVG(CAST(json_extract(a.flags, '$.bs_score') AS REAL)), 1) as avg_bs
               FROM analyses a JOIN calls c ON c.call_id = a.call_id
               WHERE c.user_id = ? AND json_extract(a.flags, '$.bs_score') IS NOT NULL
               GROUP BY dt ORDER BY dt DESC LIMIT 30""",
            (user_id,),
        ).fetchall()
        result["bs_trend"] = [{"date": r["dt"], "avg_bs": r["avg_bs"]} for r in reversed(bs_rows)]

        prom_rows = self._conn.execute(
            """SELECT status, COUNT(*) as cnt FROM promises
               WHERE user_id = ? GROUP BY status""",
            (user_id,),
        ).fetchall()
        result["promise_fulfillment"] = {r["status"]: r["cnt"] for r in prom_rows}

        return result

    def get_new_events(self, user_id: str, since_id: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        """Get events created after since_id for the live feed."""
        self.connect()
        rows = self._conn.execute(
            """SELECT ev.id, ev.event_type, ev.who, ev.payload, ev.call_id,
                       e.canonical_name as entity_name
               FROM events ev
               LEFT JOIN entities e ON e.id = ev.entity_id
               WHERE ev.user_id = ? AND ev.id > ?
               ORDER BY ev.id DESC
               LIMIT ?""",
            (user_id, since_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
