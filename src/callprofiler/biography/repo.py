# -*- coding: utf-8 -*-
"""
repo.py — biography-specific DB access layer.

Wraps the existing Repository's sqlite3 connection. All queries filter by
user_id. No ORM. Idempotent upserts keyed by natural keys so passes can be
safely re-run.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Iterable

from callprofiler.biography.schema import apply_biography_schema

log = logging.getLogger(__name__)


def _j(value: Any) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def _uj(raw: str | None) -> Any:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


class BiographyRepo:
    """DB-layer for biography tables. Reuses the host Repository connection."""

    def __init__(self, repo: Any):
        # host Repository exposes _get_conn()
        self._conn: sqlite3.Connection = repo._get_conn()
        apply_biography_schema(self._conn)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    # ------------------------------------------------------------------
    # Source data (read-only): calls + transcripts + analyses for one user.
    # ------------------------------------------------------------------

    def iter_calls_for_user(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT c.call_id, c.contact_id, c.call_datetime, c.direction,
                   c.duration_sec, c.status, c.source_filename
              FROM calls c
             WHERE c.user_id = ?
             ORDER BY COALESCE(c.call_datetime, c.created_at)
            """,
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def call_count_for_user(self, user_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM calls WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row["n"]) if row else 0

    def get_transcript_text(self, call_id: int, user_id: str) -> str:
        """Return joined transcript text for a call (user_id-guarded)."""
        rows = self._conn.execute(
            """
            SELECT t.speaker, t.text
              FROM transcripts t
              JOIN calls c ON c.call_id = t.call_id
             WHERE t.call_id = ? AND c.user_id = ?
             ORDER BY t.start_ms
            """,
            (call_id, user_id),
        ).fetchall()
        parts = []
        for r in rows:
            speaker = (r["speaker"] or "UNKNOWN").upper()
            role = "[me]" if speaker == "OWNER" else (
                "[s2]" if speaker == "OTHER" else "[?]"
            )
            text = (r["text"] or "").strip()
            if text:
                parts.append(f"{role}: {text}")
        return "\n".join(parts)

    def get_analysis_snapshot(self, call_id: int, user_id: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT a.priority, a.risk_score, a.summary, a.call_type, a.hook,
                   a.key_topics, a.raw_response
              FROM analyses a
              JOIN calls c ON c.call_id = a.call_id
             WHERE a.call_id = ? AND c.user_id = ?
            """,
            (call_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def get_calls_for_contact(self, contact_id: int, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT call_id, direction, call_datetime, duration_sec
                 FROM calls WHERE contact_id=? AND user_id=?
                 ORDER BY call_datetime""",
            (contact_id, user_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_contact_label(self, contact_id: int | None) -> str:
        if not contact_id:
            return "Неизвестный"
        row = self._conn.execute(
            """SELECT display_name, guessed_name, phone_e164
                 FROM contacts WHERE contact_id = ?""",
            (contact_id,),
        ).fetchone()
        if not row:
            return "Неизвестный"
        return (
            row["display_name"]
            or row["guessed_name"]
            or row["phone_e164"]
            or "Неизвестный"
        )

    # ------------------------------------------------------------------
    # Scenes
    # ------------------------------------------------------------------

    def upsert_scene(self, user_id: str, call_id: int, data: dict) -> int:
        row = self._conn.execute(
            "SELECT scene_id FROM bio_scenes WHERE call_id = ?", (call_id,)
        ).fetchone()
        params = (
            user_id,
            call_id,
            data.get("call_datetime"),
            int(data.get("importance", 0) or 0),
            data.get("scene_type") or "routine",
            data.get("setting") or "",
            data.get("synopsis") or "",
            (data.get("key_quote") or "")[:400],
            data.get("emotional_tone") or "neutral",
            _j(data.get("named_entities", [])),
            _j(data.get("themes", [])),
            data.get("insight") or "",
            data.get("raw_llm") or "",
            data.get("model") or "",
            data.get("prompt_version") or "",
            data.get("status") or "ok",
        )
        if row:
            self._conn.execute(
                """UPDATE bio_scenes SET
                        user_id=?, call_id=?, call_datetime=?, importance=?,
                        scene_type=?, setting=?, synopsis=?, key_quote=?,
                        emotional_tone=?, named_entities=?, themes=?, insight=?,
                        raw_llm=?, model=?, prompt_version=?, status=?
                   WHERE scene_id=?""",
                params + (row["scene_id"],),
            )
            self._conn.commit()
            return int(row["scene_id"])
        cur = self._conn.execute(
            """INSERT INTO bio_scenes
                   (user_id, call_id, call_datetime, importance, scene_type,
                    setting, synopsis, key_quote, emotional_tone,
                    named_entities, themes, insight, raw_llm, model,
                    prompt_version, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            params,
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def scene_exists(self, call_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM bio_scenes WHERE call_id = ? AND status != 'failed'",
            (call_id,),
        ).fetchone()
        return row is not None

    def get_scenes_for_user(
        self, user_id: str, min_importance: int = 0
    ) -> list[dict]:
        rows = self._conn.execute(
            """SELECT * FROM bio_scenes
               WHERE user_id = ? AND importance >= ?
               ORDER BY call_datetime""",
            (user_id, min_importance),
        ).fetchall()
        return [self._hydrate_scene(dict(r)) for r in rows]

    def get_scene(self, scene_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM bio_scenes WHERE scene_id = ?", (scene_id,)
        ).fetchone()
        return self._hydrate_scene(dict(row)) if row else None

    @staticmethod
    def _hydrate_scene(d: dict) -> dict:
        d["named_entities"] = _uj(d.get("named_entities"))
        d["themes"] = _uj(d.get("themes"))
        return d

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    def find_entity_by_alias(
        self, user_id: str, entity_type: str, name: str
    ) -> dict | None:
        # exact canonical match first
        row = self._conn.execute(
            """SELECT * FROM bio_entities
                WHERE user_id=? AND entity_type=? AND canonical_name=?""",
            (user_id, entity_type, name),
        ).fetchone()
        if row:
            return dict(row)
        # alias match (scan — entity count per user is small, hundreds)
        rows = self._conn.execute(
            """SELECT * FROM bio_entities
                WHERE user_id=? AND entity_type=?""",
            (user_id, entity_type),
        ).fetchall()
        low = name.strip().lower()
        for r in rows:
            aliases = _uj(r["aliases"])
            for a in aliases:
                if isinstance(a, str) and a.strip().lower() == low:
                    return dict(r)
        return None

    def upsert_entity(
        self,
        user_id: str,
        canonical_name: str,
        entity_type: str,
        aliases: list[str] | None = None,
        contact_id: int | None = None,
        role: str | None = None,
        description: str | None = None,
    ) -> int:
        existing = self._conn.execute(
            """SELECT entity_id, aliases FROM bio_entities
                WHERE user_id=? AND entity_type=? AND canonical_name=?""",
            (user_id, entity_type, canonical_name),
        ).fetchone()
        aliases = aliases or []
        if existing:
            prev = _uj(existing["aliases"])
            merged: list[str] = []
            seen = set()
            for a in list(prev) + list(aliases):
                if isinstance(a, str) and a.strip():
                    key = a.strip().lower()
                    if key not in seen:
                        seen.add(key)
                        merged.append(a.strip())
            self._conn.execute(
                """UPDATE bio_entities
                      SET aliases=?,
                          contact_id=COALESCE(?, contact_id),
                          role=COALESCE(?, role),
                          description=COALESCE(?, description)
                    WHERE entity_id=?""",
                (_j(merged), contact_id, role, description, existing["entity_id"]),
            )
            self._conn.commit()
            return int(existing["entity_id"])
        cur = self._conn.execute(
            """INSERT INTO bio_entities
                (user_id, canonical_name, entity_type, aliases, contact_id,
                 role, description)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, canonical_name, entity_type, _j(aliases), contact_id, role,
             description),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def link_scene_entity(
        self, scene_id: int, entity_id: int, mention_text: str | None = None
    ) -> None:
        self._conn.execute(
            """INSERT OR IGNORE INTO bio_scene_entities
                (scene_id, entity_id, mention_text) VALUES (?,?,?)""",
            (scene_id, entity_id, (mention_text or "")[:200]),
        )
        self._conn.commit()

    def refresh_entity_stats(self, user_id: str) -> None:
        """Recompute first_seen/last_seen/mention_count/importance per entity."""
        conn = self._conn
        conn.execute(
            """UPDATE bio_entities
                  SET first_seen = (
                        SELECT MIN(s.call_datetime)
                          FROM bio_scene_entities se
                          JOIN bio_scenes s ON s.scene_id = se.scene_id
                         WHERE se.entity_id = bio_entities.entity_id
                  ),
                      last_seen = (
                        SELECT MAX(s.call_datetime)
                          FROM bio_scene_entities se
                          JOIN bio_scenes s ON s.scene_id = se.scene_id
                         WHERE se.entity_id = bio_entities.entity_id
                  ),
                      mention_count = (
                        SELECT COUNT(*)
                          FROM bio_scene_entities se
                         WHERE se.entity_id = bio_entities.entity_id
                  ),
                      importance = (
                        SELECT COALESCE(MIN(SUM(s.importance),100),0)
                          FROM bio_scene_entities se
                          JOIN bio_scenes s ON s.scene_id = se.scene_id
                         WHERE se.entity_id = bio_entities.entity_id
                  )
                WHERE user_id = ?""",
            (user_id,),
        )
        conn.commit()

    def get_entities_for_user(
        self, user_id: str, entity_type: str | None = None, min_mentions: int = 1
    ) -> list[dict]:
        if entity_type:
            rows = self._conn.execute(
                """SELECT * FROM bio_entities
                    WHERE user_id=? AND entity_type=? AND mention_count >= ?
                    ORDER BY importance DESC, mention_count DESC""",
                (user_id, entity_type, min_mentions),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM bio_entities
                    WHERE user_id=? AND mention_count >= ?
                    ORDER BY importance DESC, mention_count DESC""",
                (user_id, min_mentions),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["aliases"] = _uj(d.get("aliases"))
            out.append(d)
        return out

    def get_scenes_for_entity(self, entity_id: int) -> list[dict]:
        rows = self._conn.execute(
            """SELECT s.* FROM bio_scenes s
                 JOIN bio_scene_entities se ON se.scene_id = s.scene_id
                WHERE se.entity_id = ?
                ORDER BY s.call_datetime""",
            (entity_id,),
        ).fetchall()
        return [self._hydrate_scene(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    def upsert_thread(
        self,
        user_id: str,
        entity_id: int,
        title: str,
        scene_ids: list[int],
        start_date: str | None,
        end_date: str | None,
        summary: str,
        tension_curve: list[int],
    ) -> int:
        row = self._conn.execute(
            "SELECT thread_id FROM bio_threads WHERE user_id=? AND entity_id=?",
            (user_id, entity_id),
        ).fetchone()
        params = (title, _j(scene_ids), start_date, end_date, summary,
                  _j(tension_curve))
        if row:
            self._conn.execute(
                """UPDATE bio_threads SET
                        title=?, scene_ids=?, start_date=?, end_date=?,
                        summary=?, tension_curve=?
                   WHERE thread_id=?""",
                params + (row["thread_id"],),
            )
            self._conn.commit()
            return int(row["thread_id"])
        cur = self._conn.execute(
            """INSERT INTO bio_threads
                (user_id, entity_id, title, scene_ids, start_date, end_date,
                 summary, tension_curve)
               VALUES (?,?,?,?,?,?,?,?)""",
            (user_id, entity_id) + params,
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_threads_for_user(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM bio_threads WHERE user_id=? ORDER BY end_date DESC",
            (user_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["scene_ids"] = _uj(d.get("scene_ids"))
            d["tension_curve"] = _uj(d.get("tension_curve"))
            out.append(d)
        return out

    # ------------------------------------------------------------------
    # Arcs
    # ------------------------------------------------------------------

    def insert_arc(
        self,
        user_id: str,
        title: str,
        arc_type: str,
        start_date: str | None,
        end_date: str | None,
        status: str,
        synopsis: str,
        scene_ids: list[int],
        entity_ids: list[int],
        outcome: str,
        importance: int,
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO bio_arcs
                (user_id, title, arc_type, start_date, end_date, status,
                 synopsis, scene_ids, entity_ids, outcome, importance)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, title, arc_type, start_date, end_date, status, synopsis,
             _j(scene_ids), _j(entity_ids), outcome, importance),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def clear_arcs(self, user_id: str) -> None:
        self._conn.execute("DELETE FROM bio_arcs WHERE user_id=?", (user_id,))
        self._conn.commit()

    def get_arcs_for_user(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT * FROM bio_arcs WHERE user_id=?
                ORDER BY importance DESC, start_date""",
            (user_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["scene_ids"] = _uj(d.get("scene_ids"))
            d["entity_ids"] = _uj(d.get("entity_ids"))
            out.append(d)
        return out

    # ------------------------------------------------------------------
    # Portraits
    # ------------------------------------------------------------------

    def upsert_portrait(
        self,
        user_id: str,
        entity_id: int,
        prose: str,
        traits: list[str],
        relationship: str,
        pivotal_scenes: list[int],
    ) -> int:
        row = self._conn.execute(
            "SELECT portrait_id FROM bio_portraits WHERE user_id=? AND entity_id=?",
            (user_id, entity_id),
        ).fetchone()
        params = (prose, _j(traits), relationship, _j(pivotal_scenes))
        if row:
            self._conn.execute(
                """UPDATE bio_portraits SET
                        prose=?, traits=?, relationship=?, pivotal_scenes=?
                   WHERE portrait_id=?""",
                params + (row["portrait_id"],),
            )
            self._conn.commit()
            return int(row["portrait_id"])
        cur = self._conn.execute(
            """INSERT INTO bio_portraits
                (user_id, entity_id, prose, traits, relationship, pivotal_scenes)
               VALUES (?,?,?,?,?,?)""",
            (user_id, entity_id) + params,
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_portraits_for_user(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT p.*, e.canonical_name, e.entity_type, e.role,
                      e.mention_count, e.importance, e.contact_id, e.aliases,
                      bp.trust_score, bp.volatility, bp.dependency,
                      bp.role_type, bp.conflict_count, bp.call_count,
                      bp.initiator_out_ratio
                 FROM bio_portraits p
                 JOIN bio_entities e ON e.entity_id = p.entity_id
                 LEFT JOIN bio_behavior_patterns bp
                        ON bp.entity_id = p.entity_id AND bp.user_id = p.user_id
                WHERE p.user_id=?
                ORDER BY e.importance DESC""",
            (user_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["traits"] = _uj(d.get("traits"))
            d["pivotal_scenes"] = _uj(d.get("pivotal_scenes"))
            d["aliases"] = _uj(d.get("aliases"))
            out.append(d)
        return out

    # ------------------------------------------------------------------
    # Chapters
    # ------------------------------------------------------------------

    def upsert_chapter(
        self,
        user_id: str,
        chapter_num: int,
        title: str,
        period_start: str | None,
        period_end: str | None,
        theme: str,
        prose: str,
        scene_ids: list[int],
        arc_ids: list[int],
        entity_ids: list[int],
        model: str,
    ) -> int:
        word_count = len((prose or "").split())
        row = self._conn.execute(
            "SELECT chapter_id FROM bio_chapters WHERE user_id=? AND chapter_num=?",
            (user_id, chapter_num),
        ).fetchone()
        params = (title, period_start, period_end, theme, prose,
                  _j(scene_ids), _j(arc_ids), _j(entity_ids), word_count, model)
        if row:
            self._conn.execute(
                """UPDATE bio_chapters SET
                        title=?, period_start=?, period_end=?, theme=?,
                        prose=?, scene_ids=?, arc_ids=?, entity_ids=?,
                        word_count=?, model=?, status='draft'
                   WHERE chapter_id=?""",
                params + (row["chapter_id"],),
            )
            self._conn.commit()
            return int(row["chapter_id"])
        cur = self._conn.execute(
            """INSERT INTO bio_chapters
                (user_id, chapter_num, title, period_start, period_end, theme,
                 prose, scene_ids, arc_ids, entity_ids, word_count, model)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, chapter_num) + params,
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_chapters_for_user(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM bio_chapters WHERE user_id=? ORDER BY chapter_num",
            (user_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["scene_ids"] = _uj(d.get("scene_ids"))
            d["arc_ids"] = _uj(d.get("arc_ids"))
            d["entity_ids"] = _uj(d.get("entity_ids"))
            out.append(d)
        return out

    def set_chapter_prose(self, chapter_id: int, prose: str, status: str) -> None:
        self._conn.execute(
            """UPDATE bio_chapters
                  SET prose=?, word_count=?, status=?
                WHERE chapter_id=?""",
            (prose, len((prose or "").split()), status, chapter_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Book
    # ------------------------------------------------------------------

    def insert_book(
        self,
        user_id: str,
        title: str,
        subtitle: str,
        epigraph: str,
        prologue: str,
        epilogue: str,
        toc: list[dict],
        prose_full: str,
        period_start: str | None,
        period_end: str | None,
        model: str,
        version_label: str,
        book_type: str = "main",
    ) -> int:
        wc = len((prose_full or "").split())
        cur = self._conn.execute(
            """INSERT INTO bio_books
                (user_id, title, subtitle, epigraph, prologue, epilogue, toc,
                 prose_full, word_count, period_start, period_end, model,
                 version_label, book_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, title, subtitle, epigraph, prologue, epilogue, _j(toc),
             prose_full, wc, period_start, period_end, model, version_label,
             book_type),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def latest_book(self, user_id: str, book_type: str = "main") -> dict | None:
        row = self._conn.execute(
            """SELECT * FROM bio_books WHERE user_id=? AND book_type=?
                ORDER BY generated_at DESC LIMIT 1""",
            (user_id, book_type),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["toc"] = _uj(d.get("toc"))
        return d

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def get_checkpoint(self, user_id: str, pass_name: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM bio_checkpoints WHERE user_id=? AND pass_name=?",
            (user_id, pass_name),
        ).fetchone()
        return dict(row) if row else None

    def start_checkpoint(
        self, user_id: str, pass_name: str, total_items: int
    ) -> None:
        existing = self._conn.execute(
            "SELECT status, processed_items, failed_items FROM bio_checkpoints WHERE user_id=? AND pass_name=?",
            (user_id, pass_name),
        ).fetchone()

        if existing and existing["status"] == "done":
            # Pass was completed — reset everything for a fresh run.
            self._conn.execute(
                """UPDATE bio_checkpoints SET
                     total_items=?, processed_items=0, failed_items=0,
                     last_item_key=NULL, status='running',
                     updated_at=datetime('now')
                   WHERE user_id=? AND pass_name=?""",
                (total_items, user_id, pass_name),
            )
            self.clear_checkpoint_items(user_id, pass_name)
        elif existing and existing["status"] in ("running", "paused", "failed"):
            # Resume from where we left off — keep counters and completed items.
            self._conn.execute(
                """UPDATE bio_checkpoints SET
                     total_items=?, status='running',
                     updated_at=datetime('now')
                   WHERE user_id=? AND pass_name=?""",
                (total_items, user_id, pass_name),
            )
        else:
            # Fresh start
            self._conn.execute(
                """INSERT INTO bio_checkpoints
                    (user_id, pass_name, total_items, processed_items,
                     failed_items, status, started_at, updated_at)
                   VALUES (?, ?, ?, 0, 0, 'running', datetime('now'), datetime('now'))
                   ON CONFLICT(user_id, pass_name) DO UPDATE SET
                        total_items=excluded.total_items,
                        processed_items=0, failed_items=0,
                        last_item_key=NULL, status='running',
                        updated_at=datetime('now')""",
                (user_id, pass_name, total_items),
            )
        self._conn.commit()

    def tick_checkpoint(
        self,
        user_id: str,
        pass_name: str,
        last_item_key: str | None,
        processed_delta: int = 1,
        failed_delta: int = 0,
        notes: str | None = None,
    ) -> None:
        self._conn.execute(
            """UPDATE bio_checkpoints
                  SET last_item_key = COALESCE(?, last_item_key),
                      processed_items = processed_items + ?,
                      failed_items = failed_items + ?,
                      notes = COALESCE(?, notes),
                      updated_at = datetime('now')
                WHERE user_id=? AND pass_name=?""",
            (last_item_key, processed_delta, failed_delta, notes,
             user_id, pass_name),
        )
        if last_item_key and processed_delta > 0:
            self.save_checkpoint_item(user_id, pass_name, last_item_key)
        self._conn.commit()

    def finish_checkpoint(self, user_id: str, pass_name: str, status: str) -> None:
        self._conn.execute(
            """UPDATE bio_checkpoints
                  SET status=?, updated_at=datetime('now')
                WHERE user_id=? AND pass_name=?""",
            (status, user_id, pass_name),
        )
        self._conn.commit()

    def save_checkpoint_item(self, user_id: str, pass_name: str, item_key: str) -> None:
        self._conn.execute(
            """INSERT OR IGNORE INTO bio_checkpoint_items
               (user_id, pass_name, item_key) VALUES (?,?,?)""",
            (user_id, pass_name, item_key),
        )
        self._conn.commit()

    def get_completed_items(self, user_id: str, pass_name: str) -> set[str]:
        rows = self._conn.execute(
            """SELECT item_key FROM bio_checkpoint_items
               WHERE user_id=? AND pass_name=?""",
            (user_id, pass_name),
        ).fetchall()
        return {r[0] for r in rows}

    def clear_checkpoint_items(self, user_id: str, pass_name: str) -> None:
        self._conn.execute(
            "DELETE FROM bio_checkpoint_items WHERE user_id=? AND pass_name=?",
            (user_id, pass_name),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # LLM call log / memoization
    # ------------------------------------------------------------------

    def get_cached_llm(self, prompt_hash: str) -> dict | None:
        row = self._conn.execute(
            """SELECT response, status FROM bio_llm_calls
                WHERE prompt_hash=? AND status='ok'
                ORDER BY created_at DESC LIMIT 1""",
            (prompt_hash,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Behavioral patterns
    # ------------------------------------------------------------------

    def upsert_behavior_pattern(
        self,
        user_id: str,
        entity_id: int,
        contact_id: int | None,
        trust_score: float,
        volatility: float,
        dependency: float,
        role_type: str,
        call_count: int,
        conflict_count: int,
        initiator_out_ratio: float,
        promise_kept: int = 0,
        promise_broken: int = 0,
    ) -> int:
        row = self._conn.execute(
            "SELECT pattern_id FROM bio_behavior_patterns WHERE user_id=? AND entity_id=?",
            (user_id, entity_id),
        ).fetchone()
        params = (trust_score, volatility, dependency, role_type, call_count,
                  conflict_count, promise_kept, promise_broken, initiator_out_ratio)
        if row:
            self._conn.execute(
                """UPDATE bio_behavior_patterns SET
                        trust_score=?, volatility=?, dependency=?, role_type=?,
                        call_count=?, conflict_count=?, promise_kept=?,
                        promise_broken=?, initiator_out_ratio=?,
                        computed_at=datetime('now')
                   WHERE pattern_id=?""",
                params + (row["pattern_id"],),
            )
            self._conn.commit()
            return int(row["pattern_id"])
        cur = self._conn.execute(
            """INSERT INTO bio_behavior_patterns
                (user_id, entity_id, contact_id, trust_score, volatility,
                 dependency, role_type, call_count, conflict_count,
                 promise_kept, promise_broken, initiator_out_ratio)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, entity_id, contact_id) + params,
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_behavior_pattern_for_entity(
        self, user_id: str, entity_id: int
    ) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM bio_behavior_patterns WHERE user_id=? AND entity_id=?",
            (user_id, entity_id),
        ).fetchone()
        return dict(row) if row else None

    def get_behavior_patterns_for_user(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT bp.*, e.canonical_name, e.entity_type
                 FROM bio_behavior_patterns bp
                 JOIN bio_entities e ON e.entity_id = bp.entity_id
                WHERE bp.user_id=?
                ORDER BY bp.trust_score DESC""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Contradictions
    # ------------------------------------------------------------------

    def upsert_contradiction(
        self,
        user_id: str,
        entity_id: int,
        contact_id: int | None,
        call_id_1: int,
        call_id_2: int,
        quote_1: str,
        quote_2: str,
        delta_days: int,
        severity: str,
        contradiction_type: str,
    ) -> int:
        existing = self._conn.execute(
            """SELECT contradiction_id FROM bio_contradictions
                WHERE user_id=? AND entity_id=? AND call_id_1=? AND call_id_2=?""",
            (user_id, entity_id, call_id_1, call_id_2),
        ).fetchone()
        if existing:
            return int(existing["contradiction_id"])
        cur = self._conn.execute(
            """INSERT INTO bio_contradictions
                (user_id, entity_id, contact_id, call_id_1, call_id_2,
                 quote_1, quote_2, delta_days, severity, contradiction_type)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (user_id, entity_id, contact_id, call_id_1, call_id_2,
             quote_1, quote_2, delta_days, severity, contradiction_type),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_contradictions_for_entity(
        self, user_id: str, entity_id: int
    ) -> list[dict]:
        rows = self._conn.execute(
            """SELECT * FROM bio_contradictions
                WHERE user_id=? AND entity_id=?
                ORDER BY severity DESC, delta_days DESC""",
            (user_id, entity_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def log_llm_call(
        self,
        user_id: str,
        pass_name: str,
        context_key: str,
        prompt_hash: str,
        prompt_preview: str,
        response: str | None,
        duration_sec: float,
        status: str,
        error: str | None,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._conn.execute(
            """INSERT INTO bio_llm_calls
                (user_id, pass_name, context_key, prompt_hash, prompt_preview,
                 response, duration_sec, status, error, model, temperature,
                 max_tokens)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, pass_name, context_key, prompt_hash, prompt_preview[:400],
             response, duration_sec, status, error, model, temperature,
             max_tokens),
        )
        self._conn.commit()
