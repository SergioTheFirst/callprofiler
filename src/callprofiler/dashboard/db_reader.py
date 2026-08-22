# -*- coding: utf-8 -*-
"""
Database reader for dashboard — read-only SQLite queries.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Any

from callprofiler.dashboard import labels_ru
from callprofiler.db.connection import ConnectionFactory

log = logging.getLogger(__name__)

_MAX_PIVOTAL_SCENES = 5


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
            # T-04: единая точка создания соединений — ConnectionFactory.
            # query_only=ON + не-?mode=ro сохранены (см. докстринг выше).
            self._conn = ConnectionFactory(self.db_path).reader(
                busy_timeout_ms=3000
            )

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

    def user_exists(self, user_id: str) -> bool:
        """Существует ли профиль. Источник истины — таблица ``users``.

        Не ``get_user_ids()``: та выводит профили из ``calls`` GROUP BY, поэтому
        только что заведённый пользователь без единого звонка в неё не попадает.
        Для валидации tenant-идентичности из клиентской cookie это дало бы отказ
        легитимному профилю.
        """
        self.connect()
        row = self._conn.execute(
            "SELECT 1 FROM users WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
        return row is not None

    def get_recent_calls(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent calls with analysis data."""
        self.connect()
        # F4: calls.call_type ('note'/NULL) — миграция, на старой БД её может не быть.
        # Алиас call_kind обязателен: a.call_type (LLM-классификация диалога, analyses)
        # и c.call_type (структурный тип звонка, calls) — РАЗНЫЕ поля с одинаковым именем.
        kind_col = "c.call_type AS call_kind" if self._has_column("calls", "call_type") else "NULL AS call_kind"
        query = f"""
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
            {kind_col},
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

        # Psychology profile (from graph). include_llm=False обязателен:
        # дашборд read-only (query_only) и не должен ждать llama-server до 120s
        # на клик — иначе модалка зависает при живом сервере.
        try:
            from callprofiler.biography.psychology_profiler import PsychologyProfiler
            profiler = PsychologyProfiler(self._conn)
            psych = profiler.build_profile(entity_id, user_id, include_llm=False)
            if psych:
                profile["patterns"] = psych.get("patterns", [])
        except Exception as e:
            log.warning("Failed to load psychology profile for entity %d: %s", entity_id, e)

        # Biography portrait (bio_* таблицы — только если biography запускалась)
        portrait_row = None
        if self._has_table("bio_portraits"):
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

        # Вся характеристика — по-русски (темперамент/мотивация/эмоц.паттерн/тип).
        return labels_ru.localize_character(profile)

    def get_stats(self, user_id: str) -> dict[str, Any]:
        """Get overall system statistics."""
        self.connect()

        total_calls = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM calls WHERE user_id = ?", (user_id,)
        ).fetchone()["cnt"]

        total_entities = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM entities WHERE user_id = ? AND archived = 0", (user_id,)
        ).fetchone()["cnt"]

        total_portraits = 0
        if self._has_table("bio_portraits"):
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
        trust_sel = ("em.trust_score" if self._has_column("entity_metrics", "trust_score")
                     else "NULL AS trust_score")
        rows = self._conn.execute(
            f"""SELECT e.id AS entity_id, e.canonical_name, e.entity_type,
                      em.total_calls, em.avg_risk, em.bs_index, {trust_sel},
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

            risk = row["avg_risk"] or 0
            if risk >= 60:
                label = "Рисковый"
            elif risk >= 30:
                label = "Средний"
            else:
                label = "Надёжный"

            results.append({
                "entity_id": row["entity_id"],
                "canonical_name": row["canonical_name"] or "?",
                "entity_type": row["entity_type"] or "person",
                "total_calls": row["total_calls"] or 0,
                "avg_risk": row["avg_risk"],
                "bs_index": row["bs_index"],
                "character_label": label,
                "has_portrait": self._has_portrait(row["entity_id"], user_id),
                "has_psychology": bool(payload),
            })
        return results

    def _apply_fact_verdicts(self, user_id: str, item_kind: str, items: list[dict],
                              key_field: str = "id") -> list[dict]:
        """F1: rejected выбрасываем, confirmed помечаем ключом 'confirmed'.

        Read-only коннект дашборда (query_only=ON) — НЕ вызывать apply_insight_schema
        здесь (executescript пишет, упадёт на readonly); guard `_has_table` вместо этого,
        нет таблицы = никто ещё не тапал вердикт = отдаём items как есть.
        """
        verdicts: dict[str, str] = {}
        if self._has_table("fact_feedback"):
            keys = [str(it[key_field]) for it in items if it.get(key_field) is not None]
            if keys:
                from callprofiler.insight.repository import get_verdicts
                verdicts = get_verdicts(self._conn, user_id, item_kind, keys)
        out = []
        for it in items:
            key = it.get(key_field)
            verdict = verdicts.get(str(key)) if key is not None else None
            if verdict == "rejected":
                continue
            it = dict(it)
            it["item_kind"] = item_kind
            it["confirmed"] = verdict == "confirmed"
            out.append(it)
        return out

    def _has_portrait(self, entity_id: int, user_id: str) -> bool:
        if not self._has_table("bio_portraits"):
            return False
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

        # trust_score/volatility/conflict_count живут в bio_behavior_patterns,
        # НЕ в entity_metrics — здесь их нет ни на graph-, ни на bio-БД → NULL.
        metrics_row = self._conn.execute(
            """SELECT bs_index, avg_risk, total_calls,
                      NULL AS trust_score, NULL AS volatility,
                      NULL AS conflict_count, emotional_pattern
               FROM entity_metrics WHERE entity_id = ? AND user_id = ?""",
            (entity_id, user_id),
        ).fetchone()

        # Build character_summary from entity_metrics (avg_risk / bs_index) when bio data unavailable
        if metrics_row:
            metrics_dict = dict(metrics_row)
            avg_risk = metrics_dict.get("avg_risk")
            bs_index = metrics_dict.get("bs_index")
            total_calls = metrics_dict.get("total_calls")
            if avg_risk is not None or bs_index is not None:
                parts = []
                if avg_risk is not None and avg_risk > 0:
                    parts.append(f"avg_risk={int(avg_risk)}")
                if bs_index is not None and bs_index > 0:
                    parts.append(f"bs_index={int(bs_index)}")
                if total_calls is not None and total_calls > 0:
                    parts.append(f"calls={int(total_calls)}")
                if parts:
                    profile["character_summary"] = ", ".join(parts)

        # bio_behavior_patterns — ОДНА строка сводных метрик на entity (trust_score/
        # volatility/...), НЕ список именованных паттернов (нет колонок name/severity/
        # ratio/label — regression, bugs.md 2026-06-13/2026-07-02). Паттерны берём из
        # base (PsychologyProfiler._extract_patterns, тот же источник, что и досье —
        # уже посчитан в get_entity_profile, повторный include_llm=False вызов не нужен).
        profile["patterns"] = base.get("patterns") or []

        if self._has_table("bio_contradictions"):
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
                """SELECT promise_id AS id, what, status, due, who FROM promises
                   WHERE user_id = ? AND contact_id = ? AND status = 'open'
                   ORDER BY created_at DESC LIMIT 10""",
                (user_id, cid),
            ).fetchall()
            profile["open_promises"] = self._apply_fact_verdicts(
                user_id, "promise", [dict(r) for r in promise_rows])

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

        # Паттерны/противоречия из bio_* — тоже по-русски (base уже локализован).
        return labels_ru.localize_character(profile)

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
            # F1: open_promises уже несёт "id" (events.id) — aggregate/summary_builder.py
            profile["open_promises"] = self._apply_fact_verdicts(
                user_id, "event", profile["open_promises"])
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

    # ── Person dossier (Ф2 плана досье) ─────────────────────────────────

    def _has_table(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None

    def _has_column(self, table: str, column: str) -> bool:
        # trust_score и пр. добавляет biography-схема — на graph-only БД их нет
        if not self._has_table(table):
            return False
        cols = {r[1] for r in self._conn.execute(
            f"PRAGMA table_info({table})").fetchall()}  # table — литерал кода
        return column in cols

    def get_mirror(self, user_id: str) -> dict[str, Any] | None:
        """A3: досье владельца (payload из owner_mirror). None если ещё не считалось
        (`mirror-build --user X`) или таблицы нет — вкладка не 500, а подсказка."""
        self.connect()
        if not self._has_table("owner_mirror"):
            return None
        row = self._conn.execute(
            "SELECT payload, computed_at FROM owner_mirror WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            return None
        payload["computed_at"] = row["computed_at"]
        return payload

    def get_people(self, user_id: str, limit: int = 500) -> list[dict[str, Any]]:
        """Список личностей-контактов для вкладки «Личности».

        База — contacts/contact_summaries (schema.sql, всегда есть). Архетип и
        BS-index присоединяются ТОЛЬКО если их таблицы существуют (insight/graph
        слои опциональны) — guarded, не 500. На контакта берётся одна map-связка
        с максимальной confidence.
        """
        self.connect()
        has_arch = self._has_table("contact_archetypes")
        has_map = (self._has_table("entity_contact_map")
                   and self._has_table("entity_metrics"))

        select = [
            "ct.contact_id", "ct.display_name", "ct.guessed_name", "ct.phone_e164",
            "cs.total_calls AS total_calls", "cs.last_call_date AS last_call_date",
            "cs.global_risk AS global_risk", "cs.avg_bs_score AS avg_bs_score",
        ]
        joins = [
            "LEFT JOIN contact_summaries cs "
            "ON cs.contact_id = ct.contact_id AND cs.user_id = ct.user_id",
        ]
        if has_arch:
            select += ["ca.archetype_label AS archetype_label",
                       "ca.membership AS membership",
                       "ca.cluster_idx AS cluster_idx"]
            joins += ["LEFT JOIN contact_archetypes ca "
                      "ON ca.contact_id = ct.contact_id AND ca.user_id = ct.user_id"]
        if has_map:
            trust_sel = ("em.trust_score AS trust_score"
                         if self._has_column("entity_metrics", "trust_score")
                         else "NULL AS trust_score")
            select += ["m.entity_id AS entity_id", "em.bs_index AS bs_index",
                       trust_sel]
            joins += [
                "LEFT JOIN (SELECT user_id, contact_id, entity_id, ROW_NUMBER() OVER ("
                "PARTITION BY user_id, contact_id ORDER BY confidence DESC, entity_id"
                ") AS rn FROM entity_contact_map) m ON m.user_id = ct.user_id "
                "AND m.contact_id = ct.contact_id AND m.rn = 1",
                "LEFT JOIN entity_metrics em "
                "ON em.entity_id = m.entity_id AND em.user_id = ct.user_id",
            ]
        has_tiers = self._has_table("contact_tiers")
        if has_tiers:
            select += ["ctier.tier AS tier"]
            joins += ["LEFT JOIN contact_tiers ctier "
                      "ON ctier.contact_id = ct.contact_id AND ctier.user_id = ct.user_id"]
        has_age_est = self._has_table("contact_age_estimates")
        has_age_style = self._has_table("contact_age_style")
        if has_age_est:
            select += ["cae.age_point AS age_point",
                       "cae.age_low AS age_low",
                       "cae.age_high AS age_high",
                       "cae.birth_year_point AS birth_year_point",
                       "cae.birth_year_low AS birth_year_low",
                       "cae.birth_year_high AS birth_year_high",
                       "cae.confidence AS age_confidence",
                       "cae.method AS age_method"]
            joins += ["LEFT JOIN contact_age_estimates cae "
                      "ON cae.contact_id = ct.contact_id AND cae.user_id = ct.user_id"]
        if has_age_style:
            select += ["cas.birth_year_point AS style_birth_year_point",
                       "cas.birth_year_low AS style_birth_year_low",
                       "cas.birth_year_high AS style_birth_year_high",
                       "cas.confidence AS style_age_confidence",
                       "cas.confidence_level AS style_confidence_level"]
            joins += ["LEFT JOIN contact_age_style cas "
                      "ON cas.contact_id = ct.contact_id AND cas.user_id = ct.user_id"]
        order_by = "COALESCE(cs.total_calls, 0) DESC, ct.contact_id"
        if has_tiers:
            # F8: тир — первичная сортировка (core наверху), объём звонков — вторичная
            order_by = (
                "CASE ctier.tier WHEN 'core' THEN 0 WHEN 'active' THEN 1 WHEN 'warm' THEN 2 "
                "WHEN 'cold' THEN 3 WHEN 'archive' THEN 4 ELSE 5 END, " + order_by
            )
        sql = ("SELECT " + ", ".join(select) + " FROM contacts ct " + " ".join(joins)
               + " WHERE ct.user_id = ?"
               + " ORDER BY " + order_by + " LIMIT ?")
        rows = self._conn.execute(sql, (user_id, limit)).fetchall()

        people = []
        for r in rows:
            d = dict(r)
            d["name"] = (d.get("display_name") or d.get("guessed_name")
                         or d.get("phone_e164") or f"#{d['contact_id']}")
            for key in ("archetype_label", "membership", "entity_id",
                        "bs_index", "trust_score", "age_point", "age_confidence",
                        "age_low", "age_high", "age_method", "birth_year_point",
                        "birth_year_low", "birth_year_high",
                        "style_birth_year_point", "style_birth_year_low", "style_birth_year_high",
                        "style_age_confidence", "style_confidence_level", "tier"):
                d.setdefault(key, None)
            if d.get("tier"):
                from callprofiler.dashboard.labels_ru import TIER, ru
                d["tier_label"] = ru(TIER, d["tier"])
            else:
                d["tier_label"] = None

            # C2: age_fused — единая итоговая оценка из маркеров и стиля
            marker_dict = None
            if has_age_est and d.get("age_method"):
                marker_dict = {
                    "method": d.get("age_method"),
                    "birth_year_low": d.get("birth_year_low"),
                    "birth_year_high": d.get("birth_year_high"),
                    "birth_year_point": d.get("birth_year_point"),
                    "confidence": d.get("age_confidence", 50),
                }
            style_dict = None
            if has_age_style and d.get("style_confidence_level"):
                style_dict = {
                    "birth_year_low": d.get("style_birth_year_low"),
                    "birth_year_high": d.get("style_birth_year_high"),
                    "birth_point": d.get("style_birth_year_point"),
                    "confidence": d.get("style_age_confidence", 50),
                    "confidence_level": d.get("style_confidence_level", 1),
                }

            fused = None
            try:
                if marker_dict is not None or style_dict is not None:
                    from callprofiler.insight.age_fusion import fuse_age
                    fused = fuse_age(marker_dict, style_dict, date.today().year)
            except Exception:  # noqa: BLE001 — fusion опционален
                pass

            # Вывод возраста в список из fusion
            if fused is not None:
                d["age_point"] = fused["age_point"]
                d["age_confidence"] = fused["confidence"]
                d["age_source"] = fused["source"]
            else:
                d["age_point"] = None
                d["age_confidence"] = None
                d["age_source"] = None

            # Cleanup
            for key in ("birth_year_point", "birth_year_low", "birth_year_high",
                       "age_low", "age_high", "age_method",
                       "style_birth_year_point", "style_birth_year_low", "style_birth_year_high",
                       "style_age_confidence", "style_confidence_level"):
                d.pop(key, None)
            people.append(d)
        return people

    def get_person_dossier(self, contact_id: int, user_id: str) -> dict[str, Any] | None:
        """Полное досье личности: контакт + сводка + архетип + entity-слой
        (через entity_contact_map) + структурный психопрофиль БЕЗ LLM.

        Дашборд никогда не зовёт модель: интерпретация — только сохранённая
        (profile-all → entity_profiles). Каждая секция guarded: слоя нет →
        None/[] вместо 500.
        """
        base = self.get_contact_profile(contact_id, user_id)
        if base is None:
            return None

        dossier: dict[str, Any] = {
            "contact": {k: base.get(k) for k in (
                "contact_id", "display_name", "guessed_name", "phone_e164",
                "guessed_company", "name_confirmed", "total_calls",
                "last_call_date")},
            "indices": {
                "global_risk": base.get("global_risk"),
                "avg_bs_score": base.get("avg_bs_score"),
                "bs_index": None, "trust_score": None, "avg_risk": None,
                "volatility": None, "conflict_count": None, "emotional_pattern": None,
            },
            "owner_note": None,
            "tier": None,
            "archetype": None,
            "entity": None,
            "age": None,
            "age_style": None,
            "age_fused": None,
            "emotion_palette": None,
            "patterns": [],
            "temporal": None,
            "social": None,
            "network": None,
            "finance": None,
            "mentions": None,
            "promise_outcomes": None,
            "facts": [],
            "deep_facts": [],
            "contradictions": [],
            "promises": {"open": base.get("open_promises") or []},
            "personal_facts": base.get("personal_facts") or [],
            "evolution": [],
            "drift": [],
            "dormant": None,
            "interpretation": None,
            "advice": base.get("advice"),
            "recent_calls": base.get("recent_calls") or [],
            "bs_thresholds": None,
        }

        if self._has_table("contact_notes"):
            row = self._conn.execute(
                """SELECT note, updated_at FROM contact_notes
                    WHERE contact_id = ? AND user_id = ?""",
                (contact_id, user_id),
            ).fetchone()
            if row:
                dossier["owner_note"] = {"note": row["note"], "updated_at": row["updated_at"]}

        if self._has_table("contact_tiers"):
            row = self._conn.execute(
                "SELECT tier FROM contact_tiers WHERE contact_id = ? AND user_id = ?",
                (contact_id, user_id),
            ).fetchone()
            if row:
                from callprofiler.dashboard.labels_ru import TIER, ru
                dossier["tier"] = {"code": row["tier"], "label": ru(TIER, row["tier"])}

        if self._has_table("contact_archetypes"):
            row = self._conn.execute(
                """SELECT archetype_label, membership, confidence, distinctive_dims
                     FROM contact_archetypes
                    WHERE contact_id = ? AND user_id = ?""",
                (contact_id, user_id),
            ).fetchone()
            if row:
                try:
                    dims = json.loads(row["distinctive_dims"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    dims = []
                dossier["archetype"] = {
                    "label": row["archetype_label"],
                    "membership": row["membership"],
                    "confidence": row["confidence"],
                    "traits": [d.get("phrase") for d in dims if d.get("phrase")],
                    # A7 tension.py: сырые (dim,z) — traits выше уже редуцировал до фраз
                    "dims": [{"dim": d.get("dim"), "z": d.get("z")} for d in dims if d.get("dim")],
                }

        # F26: "Мои заметки" (self:notes) — self-леджер, живёт в digest, не в чужом досье
        if self._has_table("deep_facts") and base.get("phone_e164") != "self:notes":
            rows = self._conn.execute(
                """SELECT df.what, df.quote, df.who, df.type, df.deadline_raw,
                          date(c.call_datetime) AS call_date
                     FROM deep_facts df
                     JOIN calls c ON c.call_id = df.call_id
                    WHERE df.contact_id = ? AND df.user_id = ?
                    ORDER BY df.created_at DESC LIMIT 5""",
                (contact_id, user_id),
            ).fetchall()
            dossier["deep_facts"] = [
                {"what": r["what"], "quote": r["quote"], "who": r["who"],
                 "type": r["type"], "deadline_raw": r["deadline_raw"], "call_date": r["call_date"]}
                for r in rows
            ]

        if self._has_table("contact_age_estimates"):
            row = self._conn.execute(
                """SELECT age_low, age_high, age_point, birth_year_low,
                          birth_year_high, birth_year_point, confidence,
                          method, evidence, computed_at
                     FROM contact_age_estimates
                    WHERE contact_id = ? AND user_id = ?""",
                (contact_id, user_id),
            ).fetchone()
            if row and (row["age_point"] is not None
                        or row["birth_year_point"] is not None):
                try:
                    ev = json.loads(row["evidence"] or "[]")[:5]
                except (json.JSONDecodeError, TypeError):
                    ev = []
                yr = date.today().year
                dossier["age"] = {
                    # возраст к текущей дате из года рождения (динамика);
                    # fallback — срез age_* на момент computed_at
                    "age_low": (yr - row["birth_year_high"]
                                if row["birth_year_high"] else row["age_low"]),
                    "age_high": (yr - row["birth_year_low"]
                                 if row["birth_year_low"] else row["age_high"]),
                    "age_point": (yr - row["birth_year_point"]
                                  if row["birth_year_point"] else row["age_point"]),
                    "confidence": row["confidence"],
                    "method": row["method"],
                    "evidence": ev,
                    "computed_at": row["computed_at"],
                }

        if self._has_table("contact_age_style"):
            row = self._conn.execute(
                """SELECT group_code, group_json, birth_year_low, birth_year_high,
                          birth_year_point, confidence, confidence_level,
                          n_conversations, total_tokens, top_json, warnings_json,
                          computed_at
                     FROM contact_age_style
                    WHERE contact_id = ? AND user_id = ?""",
                (contact_id, user_id),
            ).fetchone()
            if row:
                try:
                    group_dist = json.loads(row["group_json"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    group_dist = {}
                try:
                    top_features = json.loads(row["top_json"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    top_features = []
                try:
                    style_warnings = json.loads(row["warnings_json"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    style_warnings = []
                yr = date.today().year
                bp = row["birth_year_point"]
                dossier["age_style"] = {
                    "group_code": row["group_code"],
                    "group_distribution": group_dist,
                    "birth_year_point": bp,
                    "age_point": (yr - bp) if bp is not None else None,
                    "age_low": (yr - row["birth_year_high"]
                                if row["birth_year_high"] is not None else None),
                    "age_high": (yr - row["birth_year_low"]
                                 if row["birth_year_low"] is not None else None),
                    "confidence": row["confidence"],
                    "confidence_level": row["confidence_level"],
                    "n_conversations": row["n_conversations"],
                    "total_tokens": row["total_tokens"],
                    "top_features": top_features,
                    "warnings": style_warnings,
                    "computed_at": row["computed_at"],
                }

        # C2: age_fused — единая итоговая оценка из маркеров и стиля
        if dossier["age"] is not None or dossier["age_style"] is not None:
            try:
                from callprofiler.insight.age_fusion import fuse_age
                marker_dict = None
                if dossier["age"] is not None:
                    marker_dict = {
                        "method": dossier["age"].get("method"),
                        "birth_year_low": (date.today().year - dossier["age"]["age_high"]
                                          if dossier["age"].get("age_high") is not None else None),
                        "birth_year_high": (date.today().year - dossier["age"]["age_low"]
                                           if dossier["age"].get("age_low") is not None else None),
                        "birth_year_point": (date.today().year - dossier["age"]["age_point"]
                                            if dossier["age"].get("age_point") is not None else None),
                        "confidence": dossier["age"].get("confidence", 50),
                    }
                style_dict = None
                if dossier["age_style"] is not None:
                    style_dict = {
                        "birth_year_low": dossier["age_style"].get("birth_year_low"),
                        "birth_year_high": dossier["age_style"].get("birth_year_high"),
                        "birth_point": dossier["age_style"].get("birth_year_point"),
                        "confidence": dossier["age_style"].get("confidence", 50),
                        "confidence_level": dossier["age_style"].get("confidence_level", 1),
                    }
                fused = fuse_age(marker_dict, style_dict, date.today().year)
                if fused is not None:
                    dossier["age_fused"] = fused
            except Exception as exc:  # noqa: BLE001 — fusion слой опционален
                log.debug("dossier: age fusion недоступна: %s", exc)

        if self._has_table("contact_features"):
            rows = self._conn.execute(
                """SELECT feature_name, value, support_n FROM contact_features
                    WHERE contact_id = ? AND user_id = ?
                      AND feature_name IN
                          ('emo_anger','emo_anxiety','emo_joy','emo_contempt')""",
                (contact_id, user_id),
            ).fetchall()
            if rows:
                from callprofiler.insight.labels import FEATURE_LABELS
                dossier["emotion_palette"] = [
                    {"code": r["feature_name"],
                     "label": FEATURE_LABELS.get(r["feature_name"], (r["feature_name"],))[0],
                     "value": r["value"], "support_n": r["support_n"]}
                    for r in rows
                ]

        try:
            from callprofiler.insight.finance import finance_exposure, exposure_phrase
            exp = finance_exposure(self._conn, user_id, contact_id)
        except Exception as exc:  # noqa: BLE001 — display-only слой опционален
            log.debug("dossier: finance_exposure недоступна: %s", exc)
            exp = None
        if exp:
            rows = self._conn.execute(
                """SELECT e.source_quote AS quote, date(c.call_datetime) AS call_date
                     FROM events e JOIN calls c ON c.call_id = e.call_id
                    WHERE e.user_id = ? AND e.contact_id = ?
                      AND e.event_type IN ('promise', 'debt') AND e.status = 'open'
                      AND e.source_quote IS NOT NULL
                    ORDER BY c.call_datetime DESC LIMIT 3""",
                (user_id, contact_id),
            ).fetchall()
            dossier["finance"] = {
                "phrase": exposure_phrase(exp),
                "events": [{"quote": r["quote"], "date": r["call_date"]} for r in rows],
            }

        if self._has_table("promise_outcomes"):
            try:
                from callprofiler.insight.promise_outcomes import contact_reliability
                rel = contact_reliability(self._conn, user_id, contact_id)
            except Exception as exc:  # noqa: BLE001 — надёжность обещаний опциональна
                log.debug("dossier: contact_reliability недоступна: %s", exc)
                rel = None
            if rel:
                rows = self._conn.execute(
                    """SELECT what, status, evidence_date, evidence_quote FROM promise_outcomes
                        WHERE user_id = ? AND contact_id = ? AND side = 'contact'
                          AND status IN ('kept', 'late', 'broken')
                        ORDER BY evidence_date DESC LIMIT 3""",
                    (user_id, contact_id),
                ).fetchall()
                dossier["promise_outcomes"] = {
                    "phrase": rel["phrase"], "kept_ratio": rel["kept_ratio"], "n": rel["n"],
                    "recent": [{"what": r["what"], "status": r["status"],
                               "evidence_date": r["evidence_date"], "quote": r["evidence_quote"]}
                              for r in rows],
                }

        if self._has_table("mention_edges"):
            try:
                from callprofiler.insight.mentions import mentioned_by, outgoing_count
                by = mentioned_by(self._conn, user_id, contact_id, top=3)
                out_n = outgoing_count(self._conn, user_id, contact_id)
                if by or out_n:
                    dossier["mentions"] = {"by": by, "outgoing_count": out_n}
            except Exception as exc:  # noqa: BLE001 — граф упоминаний опционален
                log.debug("dossier: mentions недоступны: %s", exc)

        entity_id = None
        if self._has_table("entity_contact_map"):
            row = self._conn.execute(
                """SELECT m.entity_id, m.method, m.confidence,
                          e.canonical_name, e.aliases
                     FROM entity_contact_map m
                     JOIN entities e ON e.id = m.entity_id AND e.user_id = m.user_id
                    WHERE m.user_id = ? AND m.contact_id = ?
                    ORDER BY m.confidence DESC, m.entity_id LIMIT 1""",
                (user_id, contact_id),
            ).fetchone()
            if row:
                entity_id = row["entity_id"]
                try:
                    aliases = json.loads(row["aliases"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    aliases = []
                dossier["entity"] = {
                    "entity_id": entity_id,
                    "canonical_name": row["canonical_name"],
                    "aliases": aliases,
                    "link_method": row["method"],
                    "link_confidence": row["confidence"],
                }

        if entity_id is not None:
            try:
                from callprofiler.biography.psychology_profiler import PsychologyProfiler
                prof = PsychologyProfiler(self._conn).build_profile(
                    entity_id, user_id, include_llm=False)
            except Exception as exc:  # noqa: BLE001 — психослой опционален
                log.debug("dossier: психопрофиль недоступен (entity=%s): %s",
                          entity_id, exc)
                prof = {}
            if prof:
                metrics = prof.get("metrics") or {}
                for key in ("bs_index", "avg_risk", "trust_score",
                            "volatility", "conflict_count", "emotional_pattern"):
                    if metrics.get(key) is not None:
                        dossier["indices"][key] = metrics.get(key)
                dossier["patterns"] = prof.get("patterns") or []
                dossier["temporal"] = prof.get("temporal")
                dossier["social"] = prof.get("social")
                dossier["network"] = prof.get("network")
                dossier["evolution"] = prof.get("evolution") or []
                dossier["facts"] = prof.get("top_facts") or []
                if isinstance(prof.get("interpretation"), str):
                    dossier["interpretation"] = prof["interpretation"]

            if dossier["interpretation"] is None and self._has_table("entity_profiles"):
                row = self._conn.execute(
                    """SELECT interpretation FROM entity_profiles
                        WHERE entity_id = ? AND user_id = ?
                          AND profile_type = 'psychology'""",
                    (entity_id, user_id),
                ).fetchone()
                if row and row["interpretation"]:
                    dossier["interpretation"] = row["interpretation"]

            if self._has_table("bio_contradictions"):
                rows = self._conn.execute(
                    """SELECT quote_1, quote_2, severity, contradiction_type, delta_days
                         FROM bio_contradictions
                        WHERE entity_id = ? AND user_id = ?
                        ORDER BY severity DESC LIMIT 5""",
                    (entity_id, user_id),
                ).fetchall()
                dossier["contradictions"] = [dict(r) for r in rows]

        if self._has_table("bs_thresholds"):
            row = self._conn.execute(
                "SELECT * FROM bs_thresholds WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
            if row:
                dossier["bs_thresholds"] = dict(row)

        if self._has_column("analyses", "feedback"):
            row = self._conn.execute(
                """SELECT SUM(CASE WHEN a.feedback='inaccurate' THEN 1 ELSE 0 END) AS wrong_n,
                          SUM(CASE WHEN a.feedback='ok' THEN 1 ELSE 0 END) AS ok_n,
                          MAX(CASE WHEN a.feedback='inaccurate' THEN c.call_datetime END) AS last_wrong
                     FROM analyses a JOIN calls c ON c.call_id = a.call_id
                    WHERE c.user_id = ? AND c.contact_id = ?""",
                (user_id, contact_id),
            ).fetchone()
            if row:
                dossier["feedback"] = {
                    "wrong_n": row["wrong_n"] or 0,
                    "ok_n": row["ok_n"] or 0,
                    "last_wrong": row["last_wrong"],
                }

        # A7: Admiralty-грейд в шапку (реюз insight/admiralty.py из A6).
        try:
            from callprofiler.insight.admiralty import grade_line, info_grade, source_grade
            bs_label = None
            if entity_id is not None:
                row = self._conn.execute(
                    "SELECT bs_index FROM entity_metrics WHERE entity_id = ? AND user_id = ?",
                    (entity_id, user_id),
                ).fetchone()
                if row is not None:
                    from callprofiler.graph.calibration import BSCalibrator
                    from callprofiler.graph.repository import GraphRepository
                    bs_label, _ = BSCalibrator(GraphRepository(self._conn)).get_label(
                        row["bs_index"], user_id)
            avg_conf_row = self._conn.execute(
                """SELECT AVG(confidence) AS avg_conf FROM events
                    WHERE user_id = ? AND contact_id = ?
                      AND created_at >= datetime('now', '-180 days')""",
                (user_id, contact_id),
            ).fetchone()
            avg_confidence = avg_conf_row["avg_conf"] if avg_conf_row is not None else None
            kept_ratio = kept_n = None
            if dossier["promise_outcomes"]:
                kept_ratio = dossier["promise_outcomes"]["kept_ratio"]
                kept_n = dossier["promise_outcomes"]["n"]
            dossier["admiralty"] = grade_line(
                source_grade(bs_label, kept_ratio, kept_n or 0), info_grade(avg_confidence))
        except Exception as exc:  # noqa: BLE001 — шапка не должна ронять досье
            log.debug("dossier: admiralty-грейд недоступен: %s", exc)

        # A7: поворотные сцены. bio_scenes has NO entity_id (schema.py) — real link is
        # the bio_scene_entities junction. bio_portraits.pivotal_scenes holds LLM-time
        # positional indices into an ephemeral per-call scene list, not stable scene_id —
        # resolving those would silently show the WRONG scene (bugs.md 2026-07-02 id-space
        # precedent). Use top-importance scenes via the junction instead: reliable, no guess.
        if self._has_table("bio_scene_entities") and self._has_table("bio_scenes") and dossier["contact"].get("display_name"):
            try:
                scene_rows = self._conn.execute(
                    """SELECT bs.call_id, bs.call_datetime, bs.synopsis, bs.importance
                         FROM bio_scene_entities bse
                         JOIN bio_scenes bs ON bs.scene_id = bse.scene_id
                         JOIN bio_entities be ON be.entity_id = bse.entity_id
                        WHERE be.user_id = ? AND bs.user_id = ?
                          AND LOWER(be.canonical_name) = LOWER(?)
                        ORDER BY bs.importance DESC LIMIT ?""",
                    (user_id, user_id, dossier["contact"]["display_name"], _MAX_PIVOTAL_SCENES),
                ).fetchall()
                if scene_rows:
                    dossier["pivotal_scenes"] = [
                        {"call_id": r["call_id"], "call_datetime": r["call_datetime"],
                         "synopsis": (r["synopsis"] or "")[:300]}
                        for r in scene_rows
                    ]
            except Exception as exc:  # noqa: BLE001 — bio-связь по имени необязательна
                log.debug("dossier: поворотные сцены недоступны: %s", exc)

        # B8: дрейф стиля по годам — live-вычисление (numpy/regex, без записи; один
        # контакт дёшево), FRAGILE-gated внутри style_drift.
        try:
            from callprofiler.insight.age_style.drift import style_drift
            dossier["drift"] = style_drift(self._conn, user_id, contact_id)
        except Exception as exc:  # noqa: BLE001 — дрейф стиля опционален
            log.debug("dossier: style_drift недоступен: %s", exc)

        # C3: флаг затухания ценной связи — top=∞, т.к. нужен ЭТОТ контакт целиком,
        # не top-5 (top-5 — только для digest-секции).
        try:
            from callprofiler.insight.dormancy import dormant_valuable
            for d in dormant_valuable(self._conn, user_id, top=10 ** 6):
                if d["contact_id"] == contact_id:
                    dossier["dormant"] = {"why": d["why"], "last_date": d["last_date"]}
                    break
        except Exception as exc:  # noqa: BLE001 — флаг затухания опционален
            log.debug("dossier: dormant_valuable недоступен: %s", exc)

        # A7: 5-слойная презентационная группировка (маппинг существующих секций;
        # ключи с * появятся в Ф-B/Ф-C, рендер app.js для них уже guarded).
        dossier["layers"] = {
            "behavioral": ["patterns", "temporal", "promise_outcomes"],
            "speech": ["age_style", "formality", "traits"],
            "relational": ["network", "mentions", "finance"],
            "dynamic": ["evolution", "drift", "pivotal_scenes"],
            "practical": ["advice", "obligations", "best_time", "dormant"],
        }

        # A7: детерминированные напряжения между слоями (ДО локализации).
        from callprofiler.insight.tension import cross_layer_tensions
        dossier["tensions"] = cross_layer_tensions(dossier)

        # Психотип/паттерны/факты/тренд/противоречия — целиком по-русски.
        return labels_ru.localize_dossier(dossier)


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
        error_col = "c.error_message," if self._has_column("calls", "error_message") else ""
        kind_col = "c.call_type AS call_kind," if self._has_column("calls", "call_type") else "NULL AS call_kind,"
        rows = self._conn.execute(
            f"""SELECT c.call_id, c.call_datetime, c.direction, c.duration_sec,
                      c.status, c.created_at, c.updated_at, c.source_filename,
                      {error_col}
                      {kind_col}
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

    def get_lifeline(self, user_id: str) -> list[dict]:
        """D2: жизненные арки (biography) для линии жизни. Нет bio_arcs -> []."""
        self.connect()
        if not self._has_table("bio_arcs"):
            return []
        rows = self._conn.execute(
            """SELECT title, arc_type, status, start_date, end_date, importance
                 FROM bio_arcs WHERE user_id = ? AND start_date IS NOT NULL
                ORDER BY importance DESC LIMIT 40""",
            (user_id,),
        ).fetchall()
        return [
            {"title": r["title"], "arc_type": r["arc_type"], "status": r["status"],
             "start_date": r["start_date"], "end_date": r["end_date"],
             "importance": r["importance"]}
            for r in rows
        ]

    def get_call_detail(self, call_id: int, user_id: str) -> dict[str, Any] | None:
        """Full call detail: metadata + analysis + transcript segments + contact + promises."""
        self.connect()
        error_col = "c.error_message," if self._has_column("calls", "error_message") else ""
        row = self._conn.execute(
            f"""SELECT c.call_id, c.call_datetime, c.direction, c.duration_sec,
                      c.status, c.created_at, c.updated_at, c.source_filename,
                      c.source_md5, c.role_fragile, c.asr_coverage,
                      {error_col}
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

    def get_call_audio_path(self, call_id: int, user_id: str) -> str | None:
        """Путь к архивному аудио звонка (M2) — None если нет записи/файла нет на диске."""
        self.connect()
        row = self._conn.execute(
            "SELECT audio_path FROM calls WHERE call_id = ? AND user_id = ?",
            (call_id, user_id),
        ).fetchone()
        if row is None or not row["audio_path"]:
            return None
        if not Path(row["audio_path"]).exists():
            return None
        return row["audio_path"]

    def get_calls_filtered(self, user_id: str, limit: int = 50, offset: int = 0,
                           status: str = "", days: int = 0,
                           call_kind: str = "") -> list[dict[str, Any]]:
        """Get paginated calls with optional status/days/call_kind filters.

        call_kind (F4): 'note' — только голосовые заметки владельца.
        """
        self.connect()
        has_call_type = self._has_column("calls", "call_type")
        where = "WHERE c.user_id = ?"
        params: list[Any] = [user_id]
        if status:
            where += " AND c.status = ?"
            params.append(status)
        if days > 0:
            where += " AND COALESCE(c.call_datetime, c.created_at) >= DATE('now', ? || ' days')"
            params.append(f"-{days}")
        if call_kind and has_call_type:
            where += " AND c.call_type = ?"
            params.append(call_kind)
        kind_col = "c.call_type AS call_kind," if has_call_type else "NULL AS call_kind,"
        query = f"""SELECT c.call_id, c.call_datetime, c.direction, c.duration_sec,
                            c.status, c.created_at, c.updated_at, c.source_filename,
                            {kind_col}
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

    # Кэш role-unknown% (класс-уровня, не instance): server.py конструирует НОВЫЙ
    # DashboardDBReader на каждый HTTP-запрос (см. _system() в server.py) — instance-
    # атрибут кэшировал бы 0 раз. SSE-тик каждые 2с, полный скан transcripts (660k+
    # строк) на каждый тик недопустим (0.4, аналог гейта get_role_unknown_share в bugs.md).
    _role_unknown_cache: dict[tuple[str, str, int], tuple[float, dict[str, Any]]] = {}

    def get_role_unknown_share(self, user_id: str, days: int = 30) -> dict[str, Any]:
        """Доля сегментов speaker='UNKNOWN' за последние `days` дней — master-gate FRAGILE."""
        self.connect()
        cache_key = (self.db_path, user_id, days)
        now = time.monotonic()
        cached = self._role_unknown_cache.get(cache_key)
        if cached is not None and now - cached[0] < 60:
            return cached[1]

        row = self._conn.execute(
            """SELECT AVG(CASE WHEN t.speaker = 'UNKNOWN' THEN 1.0 ELSE 0.0 END) AS share,
                      COUNT(*) AS n
                 FROM transcripts t
                 JOIN calls c ON c.call_id = t.call_id
                WHERE c.user_id = ? AND c.created_at >= datetime('now', ?)""",
            (user_id, f"-{days} days"),
        ).fetchone()
        result = {
            "share": row["share"] if row and row["share"] is not None else 0.0,
            "n": row["n"] if row else 0,
        }
        DashboardDBReader._role_unknown_cache[cache_key] = (now, result)
        return result

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
