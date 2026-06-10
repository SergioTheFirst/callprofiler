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
        # Принять как путь к .db, так и data_dir (тогда резолвим db/callprofiler.db,
        # как делает cli.utils.load_config_and_repo). Сервер передаёт data_dir.
        p = Path(db_path)
        if p.suffix.lower() != ".db":
            p = p / "db" / "callprofiler.db"
        self.db_path = str(p)
        self._conn: sqlite3.Connection | None = None

    def connect(self):
        """Открыть соединение, видящее ЖИВЫЕ WAL-записи пайплайна.

        ВАЖНО (root cause «замёрзшего» real-time): ``?mode=ro`` в WAL-режиме НЕ
        видит свежие коммиты — read-only коннект не подключается к WAL-индексу и
        читает снимок до последнего checkpoint. Пайплайн пишет в WAL
        (``repository.py`` → ``PRAGMA journal_mode=WAL``), поэтому дашборд
        показывал устаревшие счётчики, хотя обработка шла.

        Фикс: открываем обычное (read/write) соединение — оно полноценно
        цепляется к WAL и всегда видит последний коммит — и ставим
        ``PRAGMA query_only=ON``: писать нельзя, пайплайн не задеваем. WAL не
        блокирует: много читателей + 1 писатель работают параллельно.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path,
                timeout=DB_QUERY_TIMEOUT_SEC,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA query_only=ON")   # read-only на уровне SQL
            self._conn.execute("PRAGMA busy_timeout=3000")

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

    def get_user_ids(self) -> list[dict[str, Any]]:
        """List all profiles (user_id) with call counts for the switcher.

        Intentionally NOT filtered by user_id — this is the meta-listing that
        powers the dashboard profile dropdown (the one allowed cross-user query).
        """
        self.connect()
        rows = self._conn.execute(
            "SELECT user_id, COUNT(*) AS cnt FROM calls "
            "GROUP BY user_id ORDER BY cnt DESC"
        ).fetchall()
        return [{"user_id": r["user_id"], "calls": r["cnt"]} for r in rows]

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

    def get_calls_by_stage(self, user_id: str) -> dict[str, int]:
        """Get call counts mapped to pipeline stages for the stepper."""
        self.connect()
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM calls WHERE user_id = ? GROUP BY status",
            (user_id,),
        ).fetchall()
        db_counts = {r["status"]: r["cnt"] for r in rows}

        # Порядок = реальный конвейер (orchestrator): new → normalizing →
        # diarizing → transcribing → analyzing → delivering → done/error.
        # Раньше "new" мапился на несуществующий статус "pending" (всегда 0),
        # а "delivering" отсутствовал → степпер врал. Ключи статусов берём из
        # update_call_status() в orchestrator.py.
        STAGE_MAP = {
            "new": ["new"],
            "normalizing": ["normalizing"],
            "diarizing": ["diarizing"],
            "transcribing": ["transcribing"],
            "transcribed": ["transcribed"],
            "analyzing": ["analyzing"],
            "delivering": ["delivering"],
            "done": ["processed", "done"],
            "error": ["error"],
        }
        result: dict[str, int] = {}
        for stage, statuses in STAGE_MAP.items():
            result[stage] = sum(db_counts.get(s, 0) for s in statuses)
        # На случай неизвестных статусов — не теряем их из общего счёта
        known = {s for ss in STAGE_MAP.values() for s in ss}
        other = sum(v for k, v in db_counts.items() if k not in known)
        if other:
            result["other"] = other
        return result

    def get_daily_counts(self, user_id: str, days: int = 7) -> list[dict[str, Any]]:
        """Get daily call counts for the trend chart."""
        self.connect()
        rows = self._conn.execute(
            """SELECT DATE(COALESCE(call_datetime, created_at)) AS dt, COUNT(*) AS cnt
               FROM calls
               WHERE user_id = ? AND dt >= DATE('now', ? || ' days')
               GROUP BY dt ORDER BY dt ASC""",
            (user_id, f"-{days}"),
        ).fetchall()
        return [{"date": r["dt"], "count": r["cnt"]} for r in rows]

    def get_calls(self, user_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Get paginated calls for the calls table."""
        self.connect()
        rows = self._conn.execute(
            """SELECT c.call_id, c.call_datetime, c.direction, c.duration_sec,
                      c.status, c.created_at, c.updated_at, c.source_filename,
                      COALESCE(ct.display_name, ct.phone_e164) AS contact_label,
                      ct.display_name, ct.phone_e164,
                      a.risk_score, a.summary, a.call_type
               FROM calls c
               LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
               LEFT JOIN analyses a ON a.call_id = c.call_id
               WHERE c.user_id = ?
               ORDER BY COALESCE(c.call_datetime, c.created_at) DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_calls(self, user_id: str, q: str, limit: int = 20) -> list[dict[str, Any]]:
        """FTS5 search across transcripts + contact names."""
        self.connect()
        try:
            rows = self._conn.execute(
                """SELECT t.call_id, t.text AS snippet, t.start_ms,
                          COALESCE(ct.display_name, ct.phone_e164) AS contact_name,
                          c.call_datetime, c.direction
                   FROM transcripts_fts fts
                   JOIN transcripts t ON t.rowid = fts.rowid
                   JOIN calls c ON c.call_id = t.call_id
                   LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
                   WHERE c.user_id = ? AND transcripts_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (user_id, q, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            rows = self._conn.execute(
                """SELECT t.call_id, t.text AS snippet, t.start_ms,
                          COALESCE(ct.display_name, ct.phone_e164) AS contact_name,
                          c.call_datetime, c.direction
                   FROM transcripts t
                   JOIN calls c ON c.call_id = t.call_id
                   LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
                   WHERE c.user_id = ? AND t.text LIKE ?
                   ORDER BY c.call_datetime DESC LIMIT ?""",
                (user_id, f"%{q}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_contacts(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get contacts with call counts for the entities tab."""
        self.connect()
        rows = self._conn.execute(
            """SELECT ct.contact_id, ct.phone_e164, ct.display_name, ct.guessed_name,
                      ct.name_confirmed,
                      COUNT(c.call_id) AS call_count,
                      AVG(a.risk_score) AS avg_risk,
                      MAX(COALESCE(c.call_datetime, c.created_at)) AS last_seen
               FROM contacts ct
               LEFT JOIN calls c ON c.contact_id = ct.contact_id AND c.user_id = ct.user_id
               LEFT JOIN analyses a ON a.call_id = c.call_id
               WHERE ct.user_id = ?
               GROUP BY ct.contact_id
               ORDER BY call_count DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Insight Engine visualizations (Phase 7) ─────────────────────────
    # All user_id-scoped. The insight tables (contact_archetypes /
    # archetype_models) may be absent if `archetypes-fit` was never run — every
    # archetype read is guarded so the dashboard degrades to empty, never 500s.

    def _archetype_map(self, user_id: str) -> dict[int, tuple]:
        """{contact_id: (cluster_idx, label)} or {} if no archetype model yet."""
        try:
            rows = self._conn.execute(
                "SELECT contact_id, cluster_idx, archetype_label "
                "FROM contact_archetypes WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        except sqlite3.Error:
            return {}
        return {r["contact_id"]: (r["cluster_idx"], r["archetype_label"]) for r in rows}

    def get_insight_pca(self, user_id: str) -> dict[str, Any]:
        """PCA-2D archetype map: projected per-contact points + cluster centroids.

        Coordinates are persisted by `archetypes-fit` (first two PCA axes). Returns
        empty points if the model has not been fit for this user.
        """
        self.connect()
        out: dict[str, Any] = {"points": [], "clusters": [],
                               "k": 0, "silhouette": None, "version": None}
        try:
            rows = self._conn.execute(
                """SELECT ca.contact_id, ca.cluster_idx, ca.archetype_label,
                          ca.membership, ca.confidence, ca.pca_x, ca.pca_y,
                          COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164) AS name,
                          COUNT(c.call_id) AS calls
                   FROM contact_archetypes ca
                   LEFT JOIN contacts ct
                     ON ct.contact_id = ca.contact_id AND ct.user_id = ca.user_id
                   LEFT JOIN calls c
                     ON c.contact_id = ca.contact_id AND c.user_id = ca.user_id
                   WHERE ca.user_id = ? AND ca.pca_x IS NOT NULL
                   GROUP BY ca.contact_id
                   ORDER BY ca.cluster_idx""",
                (user_id,),
            ).fetchall()
        except sqlite3.Error:
            return out
        out["points"] = [{
            "contact_id": r["contact_id"], "cluster": r["cluster_idx"],
            "label": r["archetype_label"], "membership": r["membership"],
            "confidence": r["confidence"], "x": r["pca_x"], "y": r["pca_y"],
            "name": r["name"] or "?", "calls": r["calls"] or 0,
        } for r in rows]

        try:
            m = self._conn.execute(
                """SELECT k, silhouette, centroids, labels, version
                   FROM archetype_models WHERE user_id = ?
                   ORDER BY model_id DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
        except sqlite3.Error:
            m = None
        if m:
            out["k"] = m["k"]
            out["silhouette"] = m["silhouette"]
            out["version"] = m["version"]
            try:
                centroids = json.loads(m["centroids"] or "[]")
                labels = json.loads(m["labels"] or "{}")
            except (json.JSONDecodeError, TypeError):
                centroids, labels = [], {}
            sizes: dict[int, int] = {}
            for p in out["points"]:
                sizes[p["cluster"]] = sizes.get(p["cluster"], 0) + 1
            for idx, cen in enumerate(centroids):
                out["clusters"].append({
                    "idx": idx,
                    "label": labels.get(str(idx), f"кластер {idx}"),
                    "cx": cen[0] if len(cen) > 0 else 0.0,
                    "cy": cen[1] if len(cen) > 1 else 0.0,
                    "size": sizes.get(idx, 0),
                })
        return out

    def get_insight_network(self, user_id: str, limit: int = 40) -> dict[str, Any]:
        """Owner-centred ego-network: top contacts by call volume.

        The frontend draws the owner node at the centre and one star edge per
        contact (weight = call volume); nodes are coloured by archetype cluster.
        """
        self.connect()
        rows = self._conn.execute(
            """SELECT ct.contact_id,
                      COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164) AS name,
                      COUNT(c.call_id) AS calls,
                      AVG(a.risk_score) AS avg_risk
               FROM contacts ct
               JOIN calls c ON c.contact_id = ct.contact_id AND c.user_id = ct.user_id
               LEFT JOIN analyses a ON a.call_id = c.call_id
               WHERE ct.user_id = ?
               GROUP BY ct.contact_id
               ORDER BY calls DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        arch = self._archetype_map(user_id)
        nodes = []
        for r in rows:
            cid = r["contact_id"]
            cluster, label = arch.get(cid, (None, None))
            nodes.append({
                "contact_id": cid, "name": r["name"] or "?",
                "calls": r["calls"] or 0,
                "risk": round(r["avg_risk"], 1) if r["avg_risk"] is not None else None,
                "cluster": cluster, "label": label,
            })
        return {"owner_label": "Ты", "nodes": nodes}

    def get_insight_circadian(self, user_id: str,
                              contact_id: int | None = None) -> dict[str, Any]:
        """Call-timing heatmap: hour-of-day (0-23) × weekday (Mon..Sun)."""
        self.connect()
        where = "WHERE user_id = ? AND call_datetime IS NOT NULL"
        params: list[Any] = [user_id]
        if contact_id:
            where += " AND contact_id = ?"
            params.append(contact_id)
        rows = self._conn.execute(
            f"""SELECT CAST(strftime('%w', call_datetime) AS INTEGER) AS wd,
                       CAST(strftime('%H', call_datetime) AS INTEGER) AS hr,
                       COUNT(*) AS cnt
                FROM calls {where}
                GROUP BY wd, hr""",
            params,
        ).fetchall()
        cells: list[list[int]] = []
        mx = 0
        for r in rows:
            if r["wd"] is None or r["hr"] is None:
                continue
            mon0 = (r["wd"] + 6) % 7  # strftime %w: 0=Sun..6=Sat → Mon=0..Sun=6
            cells.append([r["hr"], mon0, r["cnt"]])
            mx = max(mx, r["cnt"])
        return {"cells": cells, "max": mx,
                "days": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]}

    def get_insight_ecg(self, user_id: str,
                        contact_id: int | None = None) -> dict[str, Any]:
        """Relationship 'ЭКГ': monthly interaction intensity + avg risk over time."""
        self.connect()
        where = "WHERE c.user_id = ? AND c.call_datetime IS NOT NULL"
        params: list[Any] = [user_id]
        if contact_id:
            where += " AND c.contact_id = ?"
            params.append(contact_id)
        rows = self._conn.execute(
            f"""SELECT strftime('%Y-%m', c.call_datetime) AS period,
                       COUNT(*) AS calls,
                       AVG(a.risk_score) AS avg_risk
                FROM calls c
                LEFT JOIN analyses a ON a.call_id = c.call_id
                {where}
                GROUP BY period ORDER BY period""",
            params,
        ).fetchall()
        series = [{
            "period": r["period"], "calls": r["calls"],
            "risk": round(r["avg_risk"], 1) if r["avg_risk"] is not None else None,
        } for r in rows if r["period"]]
        return {"series": series, "contact_id": contact_id}

    def get_call_detail(self, call_id: int, user_id: str) -> dict[str, Any] | None:
        """Full call detail: metadata + analysis + transcript segments + contact + promises."""
        self.connect()
        row = self._conn.execute(
            """SELECT c.call_id, c.call_datetime, c.direction, c.duration_sec,
                      c.status, c.created_at, c.updated_at, c.source_filename,
                      c.source_md5,
                      COALESCE(ct.display_name, ct.phone_e164) AS contact_label,
                      ct.contact_id, ct.display_name, ct.phone_e164, ct.guessed_name,
                      a.analysis_id, a.call_type, a.risk_score, a.summary,
                      a.flags, a.feedback, a.model, a.schema_version, a.prompt_version
               FROM calls c
               LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
               LEFT JOIN analyses a ON a.call_id = c.call_id
               WHERE c.call_id = ? AND c.user_id = ?""",
            (call_id, user_id),
        ).fetchone()
        if not row:
            return None

        detail = dict(row)

        flags = {}
        try:
            flags = json.loads(detail.pop("flags") or "{}")
        except (json.JSONDecodeError, TypeError):
            pass
        detail["flags"] = flags

        seg_rows = self._conn.execute(
            """SELECT start_ms, end_ms, text, speaker
               FROM transcripts
               WHERE call_id = ? ORDER BY start_ms ASC""",
            (call_id,),
        ).fetchall()
        detail["segments"] = [dict(r) for r in seg_rows]

        promise_rows = self._conn.execute(
            """SELECT what, who, due, status, created_at
               FROM promises
               WHERE call_id = ? AND user_id = ?
               ORDER BY created_at DESC""",
            (call_id, user_id),
        ).fetchall()
        detail["promises"] = [dict(r) for r in promise_rows]

        return detail

    def get_calls_filtered(self, user_id: str, limit: int = 50, offset: int = 0,
                           status: str = "", days: int = 0) -> list[dict[str, Any]]:
        """Get paginated calls with optional status/days filters."""
        self.connect()
        where = "WHERE c.user_id = ?"
        params: list[Any] = [user_id]
        if status:
            where += " AND c.status = ?"
            params.append(status)
        if days > 0:
            where += " AND COALESCE(c.call_datetime, c.created_at) >= DATE('now', ? || ' days')"
            params.append(f"-{days}")
        query = f"""SELECT c.call_id, c.call_datetime, c.direction, c.duration_sec,
                            c.status, c.created_at, c.updated_at, c.source_filename,
                            COALESCE(ct.display_name, ct.phone_e164) AS contact_label,
                            ct.display_name, ct.phone_e164,
                            a.risk_score, a.summary, a.call_type
                     FROM calls c
                     LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
                     LEFT JOIN analyses a ON a.call_id = c.call_id
                     {where}
                     ORDER BY COALESCE(c.call_datetime, c.created_at) DESC
                     LIMIT ? OFFSET ?"""
        params.extend([limit, offset])
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def export_calls(self, user_id: str, status: str = "", days: int = 0) -> list[dict[str, Any]]:
        """All matching calls for CSV export (no pagination). Always filtered by user_id."""
        self.connect()
        where = "WHERE c.user_id = ?"
        params: list[Any] = [user_id]
        if status:
            where += " AND c.status = ?"
            params.append(status)
        if days > 0:
            where += " AND COALESCE(c.call_datetime, c.created_at) >= DATE('now', ? || ' days')"
            params.append(f"-{days}")
        query = f"""SELECT c.call_id, c.call_datetime, c.direction, c.duration_sec,
                           c.status,
                           COALESCE(ct.display_name, ct.phone_e164) AS contact_label,
                           ct.phone_e164, a.call_type, a.risk_score, a.summary
                    FROM calls c
                    LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
                    LEFT JOIN analyses a ON a.call_id = c.call_id
                    {where}
                    ORDER BY COALESCE(c.call_datetime, c.created_at) DESC"""
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def export_book_markdown(self, user_id: str) -> str:
        """Assemble the user's biography as a single markdown document.

        Prefers the newest main book's ``prose_full`` (the canonical stitched
        volume). Falls back to concatenating chapters in ``chapter_num`` order,
        wrapped by the book frame (title / subtitle / epigraph / prologue /
        epilogue) when present. Returns a clearly-empty placeholder when no
        biography content exists. Always filtered by ``user_id``.
        """
        self.connect()
        book = self._conn.execute(
            """SELECT title, subtitle, epigraph, prologue, epilogue, prose_full
               FROM bio_books
               WHERE user_id = ? AND book_type = 'main'
               ORDER BY generated_at DESC, book_id DESC
               LIMIT 1""",
            (user_id,),
        ).fetchone()

        # A fully-assembled volume is the canonical export — chapters are
        # already stitched into it, so don't duplicate them.
        if book and (book["prose_full"] or "").strip():
            return book["prose_full"].strip() + "\n"

        parts: list[str] = []
        if book:
            if book["title"]:
                parts.append(f"# {book['title'].strip()}")
            if book["subtitle"]:
                parts.append(f"_{book['subtitle'].strip()}_")
            if book["epigraph"]:
                parts.append(f"> {book['epigraph'].strip()}")
            if book["prologue"]:
                parts.append(book["prologue"].strip())

        chapter_rows = self._conn.execute(
            """SELECT chapter_num, title, prose
               FROM bio_chapters
               WHERE user_id = ?
               ORDER BY chapter_num ASC""",
            (user_id,),
        ).fetchall()
        for ch in chapter_rows:
            heading = (ch["title"] or "").strip() or f"Глава {ch['chapter_num']}"
            parts.append(f"## {heading}")
            if (ch["prose"] or "").strip():
                parts.append(ch["prose"].strip())

        if book and book["epilogue"]:
            parts.append(book["epilogue"].strip())

        if not parts:
            return "# Биография\n\n_Книга ещё не сгенерирована._\n"
        return "\n\n".join(parts).strip() + "\n"

    def get_db_stats(self, user_id: str) -> dict[str, Any]:
        """Database-level statistics for the system tab."""
        self.connect()
        result: dict[str, Any] = {}
        tables = [
            "calls", "contacts", "entities", "entity_metrics", "analyses",
            "transcripts", "promises", "events", "bio_portraits",
        ]
        for tbl in tables:
            try:
                cnt = self._conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM {tbl} WHERE user_id = ?", (user_id,)
                ).fetchone()
                result[tbl] = cnt["cnt"] if cnt else 0
            except Exception:
                result[tbl] = 0

        db_size = 0
        try:
            db_size = Path(self.db_path).stat().st_size
        except Exception:
            pass
        result["db_size_mb"] = round(db_size / (1024 * 1024), 2)
        result["db_path"] = self.db_path
        return result

    def read_logs(self, lines: int = 200, level: str = "") -> list[str]:
        """Read last N lines from the log file."""
        log_dir = Path(self.db_path).parent.parent / "logs"
        log_files = sorted(log_dir.glob("callprofiler*.log"), reverse=True)
        if not log_files:
            return [f"[no log files found in {log_dir}]"]
        result: list[str] = []
        for lf in log_files:
            try:
                with open(lf, "r", encoding="utf-8") as fh:
                    file_lines = fh.readlines()
                break
            except Exception:
                continue
        else:
            return [f"[cannot read log files in {log_dir}]"]

        recent = file_lines[-lines:]
        for line in recent:
            line = line.rstrip("\n\r")
            if level and level.upper() not in line:
                continue
            result.append(line)
        return result if result else recent[:lines]
