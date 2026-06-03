# -*- coding: utf-8 -*-
"""
repository.py вЂ” РґРѕСЃС‚СѓРї Рє SQLite. Р‘РµР· ORM, С‚РѕР»СЊРєРѕ sqlite3.
РљР°Р¶РґС‹Р№ РјРµС‚РѕРґ, СЂР°Р±РѕС‚Р°СЋС‰РёР№ СЃ РґР°РЅРЅС‹РјРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ, С„РёР»СЊС‚СЂСѓРµС‚ РїРѕ user_id.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from callprofiler.models import Analysis, Segment


class Repository:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def init_db(self) -> None:
        """РЎРѕР·РґР°С‚СЊ РІСЃРµ С‚Р°Р±Р»РёС†С‹ РїРѕ schema.sql + РїСЂРёРјРµРЅРёС‚СЊ РјРёРіСЂР°С†РёРё."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, encoding="utf-8") as f:
            sql = f.read()
        conn = self._get_conn()
        conn.executescript(sql)
        conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """РџСЂРёРјРµРЅРёС‚СЊ ALTER TABLE РґР»СЏ РєРѕР»РѕРЅРѕРє, РґРѕР±Р°РІР»РµРЅРЅС‹С… РїРѕСЃР»Рµ РїРµСЂРІРѕРіРѕ СЂРµР»РёР·Р°."""
        conn = self._get_conn()

        # contacts migrations
        contacts_cols = [
            ("guessed_name", "TEXT"),
            ("guessed_company", "TEXT"),
            ("guess_source", "TEXT"),
            ("guess_call_id", "INTEGER"),
            ("guess_confidence", "TEXT"),
            ("name_confirmed", "INTEGER NOT NULL DEFAULT 0"),
        ]
        existing_contacts = {
            row[1] for row in conn.execute("PRAGMA table_info(contacts)").fetchall()
        }
        for col_name, col_def in contacts_cols:
            if col_name not in existing_contacts:
                conn.execute(f"ALTER TABLE contacts ADD COLUMN {col_name} {col_def}")

        # analyses migrations
        analyses_cols = [
            ("call_type", "TEXT DEFAULT 'unknown'"),
            ("hook", "TEXT"),
            ("parse_status", "TEXT DEFAULT 'unknown'"),
            ("profanity_count", "INTEGER DEFAULT 0"),
            ("profanity_density", "REAL DEFAULT 0"),
            ("schema_version", "TEXT DEFAULT 'v2'"),
            ("canonical_json", "TEXT DEFAULT ''"),
        ]
        existing_analyses = {
            row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()
        }
        for col_name, col_def in analyses_cols:
            if col_name not in existing_analyses:
                conn.execute(f"ALTER TABLE analyses ADD COLUMN {col_name} {col_def}")

        # events migrations (graph columns)
        events_cols = [
            ("entity_id", "INTEGER"),
            ("fact_id", "TEXT"),
            ("fact_type", "TEXT"),
            ("quote", "TEXT"),
            ("start_ms", "INTEGER"),
            ("end_ms", "INTEGER"),
            ("polarity", "REAL"),
            ("intensity", "REAL"),
        ]
        existing_events = {
            row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()
        }
        for col_name, col_def in events_cols:
            if col_name not in existing_events:
                conn.execute(f"ALTER TABLE events ADD COLUMN {col_name} {col_def}")

        # entities migration
        entities_cols = [
            ("archived", "INTEGER DEFAULT 0"),
            ("merged_into_id", "INTEGER"),
            ("is_owner", "INTEGER DEFAULT 0"),
        ]
        try:
            existing_entities = {
                row[1] for row in conn.execute("PRAGMA table_info(entities)").fetchall()
            }
            for col_name, col_def in entities_cols:
                if col_name not in existing_entities:
                    conn.execute(
                        f"ALTER TABLE entities ADD COLUMN {col_name} {col_def}"
                    )
        except Exception:
            pass  # entities table may not exist yet

        # calls migration: pipeline_stage для crash-resume (Фаза 1 надёжности)
        existing_calls = {
            row[1] for row in conn.execute("PRAGMA table_info(calls)").fetchall()
        }
        if "pipeline_stage" not in existing_calls:
            conn.execute(
                "ALTER TABLE calls ADD COLUMN pipeline_stage INTEGER NOT NULL DEFAULT 0"
            )

        # indexes для dashboard/poller (Фаза 2)
        for _idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_calls_user_status ON calls(user_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_calls_updated_at ON calls(updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_calls_user_datetime ON calls(user_id, call_datetime)",
            "CREATE INDEX IF NOT EXISTS idx_entities_user_archived ON entities(user_id, archived)",
        ]:
            try:
                conn.execute(_idx_sql)
            except Exception:
                pass

        # РЈРЅРёРєР°Р»СЊРЅС‹Р№ РёРЅРґРµРєСЃ РґР»СЏ Р°С‚РѕРјР°СЂРЅРѕР№ MD5-РґРµРґСѓРїР»РёРєР°С†РёРё Р·РІРѕРЅРєРѕРІ (F2.5)
        try:
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_calls_user_md5
                   ON calls(user_id, source_md5)
                   WHERE source_md5 IS NOT NULL"""
            )
        except Exception:
            pass  # Index may already exist or duplicate data prevents it

        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def add_user(
        self,
        user_id: str,
        display_name: str,
        telegram_chat_id: str | None,
        incoming_dir: str,
        sync_dir: str,
        ref_audio: str,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO users (user_id, display_name, telegram_chat_id,
               incoming_dir, sync_dir, ref_audio)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                display_name,
                telegram_chat_id,
                incoming_dir,
                sync_dir,
                ref_audio,
            ),
        )
        conn.commit()

    def get_user(self, user_id: str) -> dict | None:
        row = (
            self._get_conn()
            .execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            .fetchone()
        )
        return dict(row) if row else None

    def get_all_users(self) -> list[dict]:
        rows = self._get_conn().execute("SELECT * FROM users").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    def get_or_create_contact(
        self, user_id: str, phone_e164: str | None, display_name: str | None = None
    ) -> int:
        """РќР°Р№С‚Рё РєРѕРЅС‚Р°РєС‚ РёР»Рё СЃРѕР·РґР°С‚СЊ РЅРѕРІС‹Р№.

        Р•СЃР»Рё display_name РїРµСЂРµРґР°РЅ (РёРјСЏ РёР· РёРјРµРЅРё С„Р°Р№Р»Р° = С‚РµР»РµС„РѕРЅРЅР°СЏ РєРЅРёРіР° РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ),
        РѕРЅРѕ Р’РЎР•Р“Р”Рђ РѕР±РЅРѕРІР»СЏРµС‚СЃСЏ РєР°Рє РїСЂРёРѕСЂРёС‚РµС‚РЅРѕРµ вЂ” РґР°Р¶Рµ РµСЃР»Рё РєРѕРЅС‚Р°РєС‚ СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚.
        РРјСЏ РёР· С‚РµР»РµС„РѕРЅРЅРѕР№ РєРЅРёРіРё РёРјРµРµС‚ Р±РµР·СѓСЃР»РѕРІРЅС‹Р№ РїСЂРёРѕСЂРёС‚РµС‚ РЅР°Рґ auto-extracted РёРјРµРЅР°РјРё.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT contact_id FROM contacts WHERE user_id = ? AND phone_e164 = ?",
            (user_id, phone_e164),
        ).fetchone()
        if row:
            contact_id = row["contact_id"]
            # РРјСЏ РёР· РёРјРµРЅРё С„Р°Р№Р»Р° = РёРјСЏ РёР· С‚РµР»РµС„РѕРЅРЅРѕР№ РєРЅРёРіРё = Р±РµР·СѓСЃР»РѕРІРЅС‹Р№ РїСЂРёРѕСЂРёС‚РµС‚
            if display_name:
                conn.execute(
                    """UPDATE contacts SET display_name = ?, name_confirmed = 1
                       WHERE contact_id = ?""",
                    (display_name, contact_id),
                )
                conn.commit()
            return contact_id
        # РЎРѕР·РґР°С‚СЊ РЅРѕРІС‹Р№ РєРѕРЅС‚Р°РєС‚
        cur = conn.execute(
            """INSERT INTO contacts (user_id, phone_e164, display_name, name_confirmed)
               VALUES (?, ?, ?, ?)""",
            (user_id, phone_e164, display_name, 1 if display_name else 0),
        )
        conn.commit()
        return cur.lastrowid

    def get_contact(self, user_id: str, contact_id: int) -> dict | None:
        row = (
            self._get_conn()
            .execute(
                "SELECT * FROM contacts WHERE contact_id = ? AND user_id = ?",
                (contact_id, user_id),
            )
            .fetchone()
        )
        return dict(row) if row else None

    def get_contact_for_user(self, user_id: str, contact_id: int) -> dict | None:
        """Р’РµСЂРЅСѓС‚СЊ РєРѕРЅС‚Р°РєС‚ С‚РѕР»СЊРєРѕ РµСЃР»Рё РѕРЅ РїСЂРёРЅР°РґР»РµР¶РёС‚ user_id (Р±РµР·РѕРїР°СЃРЅС‹Р№ РІР°СЂРёР°РЅС‚)."""
        row = (
            self._get_conn()
            .execute(
                "SELECT * FROM contacts WHERE contact_id = ? AND user_id = ?",
                (contact_id, user_id),
            )
            .fetchone()
        )
        return dict(row) if row else None

    def get_contact_by_phone(self, user_id: str, phone_e164: str) -> dict | None:
        row = (
            self._get_conn()
            .execute(
                "SELECT * FROM contacts WHERE user_id = ? AND phone_e164 = ?",
                (user_id, phone_e164),
            )
            .fetchone()
        )
        return dict(row) if row else None

    def get_all_contacts_for_user(self, user_id: str) -> list[dict]:
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM contacts WHERE user_id = ? ORDER BY display_name",
                (user_id,),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def get_contacts_without_name(self, user_id: str) -> list[dict]:
        """Р’РµСЂРЅСѓС‚СЊ РєРѕРЅС‚Р°РєС‚С‹ Р±РµР· display_name Рё Р±РµР· РїРѕРґС‚РІРµСЂР¶РґС‘РЅРЅРѕРіРѕ guessed_name."""
        rows = (
            self._get_conn()
            .execute(
                """SELECT * FROM contacts
               WHERE user_id = ?
                 AND (display_name IS NULL OR display_name = '')
                 AND (name_confirmed = 0 OR name_confirmed IS NULL)
               ORDER BY contact_id""",
                (user_id,),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def get_calls_for_contact(self, user_id: str, contact_id: int) -> list[dict]:
        """Р’СЃРµ Р·РІРѕРЅРєРё РєРѕРЅС‚Р°РєС‚Р°, РѕС‚С„РёР»СЊС‚СЂРѕРІР°РЅРЅС‹Рµ РїРѕ user_id."""
        rows = (
            self._get_conn()
            .execute(
                """SELECT * FROM calls
               WHERE user_id = ? AND contact_id = ?
               ORDER BY call_datetime""",
                (user_id, contact_id),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def update_contact_guessed_name(
        self,
        contact_id: int,
        guessed_name: str,
        guess_source: str,
        guess_call_id: int,
        guess_confidence: str,
    ) -> bool:
        """Записать угаданное имя контакта (не перезаписывает подтверждённые)."""
        conn = self._get_conn()
        row = conn.execute(
            """UPDATE contacts
               SET guessed_name=?, guess_source=?,
                   guess_call_id=?, guess_confidence=?
               WHERE contact_id=? AND (name_confirmed = 0 OR name_confirmed IS NULL)""",
            (guessed_name, guess_source, guess_call_id, guess_confidence, contact_id),
        )
        conn.commit()
        return row.rowcount > 0

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def call_exists(self, user_id: str, source_md5: str) -> bool:
        row = (
            self._get_conn()
            .execute(
                "SELECT 1 FROM calls WHERE user_id = ? AND source_md5 = ?",
                (user_id, source_md5),
            )
            .fetchone()
        )
        return row is not None

    def get_call(self, user_id: str, call_id: int) -> dict | None:
        row = (
            self._get_conn()
            .execute(
                "SELECT * FROM calls WHERE call_id = ? AND user_id = ?",
                (call_id, user_id),
            )
            .fetchone()
        )
        return dict(row) if row else None

    def get_call_by_md5(self, user_id: str, source_md5: str) -> dict | None:
        """Найти звонок по MD5 исходника (для безопасной очистки incoming)."""
        row = (
            self._get_conn()
            .execute(
                "SELECT * FROM calls WHERE user_id = ? AND source_md5 = ?",
                (user_id, source_md5),
            )
            .fetchone()
        )
        return dict(row) if row else None

    def create_call(
        self,
        user_id: str,
        contact_id: int | None,
        direction: str,
        call_datetime: datetime | None,
        source_filename: str,
        source_md5: str,
        audio_path: str,
    ) -> int:
        conn = self._get_conn()
        dt_value = (
            call_datetime.isoformat()
            if isinstance(call_datetime, datetime)
            else call_datetime
        )
        try:
            cur = conn.execute(
                """INSERT INTO calls (user_id, contact_id, direction, call_datetime,
                   source_filename, source_md5, audio_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    contact_id,
                    direction,
                    dt_value,
                    source_filename,
                    source_md5,
                    audio_path,
                ),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as exc:
            # РЈРЅРёРєР°Р»СЊРЅС‹Р№ РёРЅРґРµРєСЃ idx_calls_user_md5 РїСЂРµРґРѕС‚РІСЂР°С‰Р°РµС‚ РґСѓР±Р»РёРєР°С‚
            if "UNIQUE constraint failed" in str(exc) and source_md5:
                conn.rollback()
                row = conn.execute(
                    "SELECT call_id FROM calls WHERE user_id=? AND source_md5=?",
                    (user_id, source_md5),
                ).fetchone()
                if row:
                    return row["call_id"]
            raise

    def update_call_status(
        self, call_id: int, status: str, error_message: str | None = None
    ) -> None:
        conn = self._get_conn()
        if error_message is not None:
            conn.execute(
                """UPDATE calls SET status=?, error_message=?,
                   retry_count=retry_count+1,
                   updated_at=datetime('now') WHERE call_id=?""",
                (status, error_message, call_id),
            )
        else:
            conn.execute(
                "UPDATE calls SET status=?, updated_at=datetime('now') WHERE call_id=?",
                (status, call_id),
            )
        conn.commit()

    def update_pipeline_stage(self, call_id: int, stage: int) -> None:
        """Персистировать стадию pipeline (0-4) для crash-resume."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE calls SET pipeline_stage=?, updated_at=datetime('now') WHERE call_id=?",
            (stage, call_id),
        )
        conn.commit()

    def update_call_paths(
        self, call_id: int, norm_path: str, duration_sec: int
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE calls SET norm_path=?, duration_sec=?, updated_at=datetime('now') WHERE call_id=?",
            (norm_path, duration_sec, call_id),
        )
        conn.commit()

    def get_pending_calls(self, user_id: str | None = None) -> list[dict]:
        if user_id:
            rows = (
                self._get_conn()
                .execute(
                    "SELECT * FROM calls WHERE status='new' AND user_id=? ORDER BY created_at",
                    (user_id,),
                )
                .fetchall()
            )
        else:
            rows = (
                self._get_conn()
                .execute("SELECT * FROM calls WHERE status='new' ORDER BY created_at")
                .fetchall()
            )
        return [dict(r) for r in rows]

    def get_stalled_calls(self, user_id: str | None = None) -> list[dict]:
        """Звонки, зависшие в промежуточном состоянии после краша.

        Условие: pipeline_stage > 0 и status не new/done/error.
        Используется process_pending() для crash-resume.
        """
        where = "pipeline_stage > 0 AND status NOT IN ('new','done','error')"
        if user_id:
            rows = self._get_conn().execute(
                f"SELECT * FROM calls WHERE {where} AND user_id=? ORDER BY updated_at",
                (user_id,),
            ).fetchall()
        else:
            rows = self._get_conn().execute(
                f"SELECT * FROM calls WHERE {where} ORDER BY updated_at",
            ).fetchall()
        return [dict(r) for r in rows]

    def get_error_calls(self, user_id: str | None = None, max_retries: int = 3) -> list[dict]:
        if user_id:
            rows = (
                self._get_conn()
                .execute(
                    "SELECT * FROM calls WHERE status='error' AND retry_count < ? AND user_id=? ORDER BY updated_at",
                    (max_retries, user_id),
                )
                .fetchall()
            )
        else:
            rows = (
                self._get_conn()
                .execute(
                    "SELECT * FROM calls WHERE status='error' AND retry_count < ? ORDER BY updated_at",
                    (max_retries,),
                )
                .fetchall()
            )
        return [dict(r) for r in rows]

    def get_call_count_for_contact(self, user_id: str, contact_id: int) -> int:
        row = (
            self._get_conn()
            .execute(
                "SELECT COUNT(*) as cnt FROM calls WHERE user_id=? AND contact_id=?",
                (user_id, contact_id),
            )
            .fetchone()
        )
        return row["cnt"] if row else 0

    def get_calls_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM calls WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Transcripts
    # ------------------------------------------------------------------

    def save_transcripts(self, call_id: int, segments: list[Segment]) -> None:
        """РЎРѕС…СЂР°РЅРёС‚СЊ СЃРµРіРјРµРЅС‚С‹ С‚СЂР°РЅСЃРєСЂРёРїС‚Р°. РРґРµРјРїРѕС‚РµРЅС‚РµРЅ: РїРѕРІС‚РѕСЂРЅС‹Р№ РІС‹Р·РѕРІ
        СѓРґР°Р»СЏРµС‚ СЃС‚Р°СЂС‹Рµ СЃРµРіРјРµРЅС‚С‹ Рё РІСЃС‚Р°РІР»СЏРµС‚ РЅРѕРІС‹Рµ (РґР»СЏ СЃР»СѓС‡Р°РµРІ reprocess).
        """
        conn = self._get_conn()
        # РЈРґР°Р»РёС‚СЊ СЃС‚Р°СЂС‹Рµ СЃРµРіРјРµРЅС‚С‹ РёР· FTS Рё С‚Р°Р±Р»РёС†С‹ (РёРґРµРјРїРѕС‚РµРЅС‚РЅРѕСЃС‚СЊ, F2.3)
        existing = conn.execute(
            "SELECT segment_id, text, speaker, call_id FROM transcripts WHERE call_id=?",
            (call_id,),
        ).fetchall()
        if existing:
            user_row = conn.execute(
                "SELECT user_id FROM calls WHERE call_id=?", (call_id,)
            ).fetchone()
            uid = user_row["user_id"] if user_row else ""
            # FTS5 content table: РЅСѓР¶РЅРѕ СЏРІРЅРѕ СѓРґР°Р»СЏС‚СЊ С‡РµСЂРµР· РєРѕРјР°РЅРґСѓ 'delete'
            conn.executemany(
                """INSERT INTO transcripts_fts(transcripts_fts, rowid, text, speaker, call_id, user_id)
                   VALUES ('delete', ?, ?, ?, ?, ?)""",
                [
                    (r["segment_id"], r["text"], r["speaker"], r["call_id"], uid)
                    for r in existing
                ],
            )
            conn.execute("DELETE FROM transcripts WHERE call_id=?", (call_id,))
        conn.executemany(
            "INSERT INTO transcripts (call_id, start_ms, end_ms, text, speaker) VALUES (?,?,?,?,?)",
            [(call_id, s.start_ms, s.end_ms, s.text, s.speaker) for s in segments],
        )
        conn.commit()

    def get_transcript(self, call_id: int) -> list[dict]:
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM transcripts WHERE call_id=? ORDER BY start_ms",
                (call_id,),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def search_transcripts(
        self, user_id: str, query: str, limit: int = 50
    ) -> list[dict]:
        # FTS5 phrase search; escape " in user input
        fts_query = '"' + query.replace('"', '""') + '"'
        # Subquery gets ranked rowids from FTS5; outer JOIN adds user_id filter
        rows = (
            self._get_conn()
            .execute(
                """SELECT t.*, c.user_id
               FROM (
                   SELECT rowid, rank
                   FROM transcripts_fts
                   WHERE transcripts_fts MATCH ?
                   ORDER BY rank
                   LIMIT 200
               ) ranked
               JOIN transcripts t ON t.segment_id = ranked.rowid
               JOIN calls c ON c.call_id = t.call_id
               WHERE c.user_id = ?
               ORDER BY ranked.rank
               LIMIT ?""",
                (fts_query, user_id, limit),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Analyses
    # ------------------------------------------------------------------

    def save_analysis(self, call_id: int, analysis: Analysis) -> None:
        conn = self._get_conn()
        has_sv = any(
            col[1] == "schema_version"
            for col in conn.execute("PRAGMA table_info(analyses)").fetchall()
        )
        cols = (
            "call_id, priority, risk_score, summary, action_items, "
            "flags, key_topics, raw_response, model, prompt_version, "
            "call_type, hook, parse_status, profanity_count, profanity_density"
        )
        vals = [
            call_id,
            analysis.priority,
            analysis.risk_score,
            analysis.summary,
            json.dumps(analysis.action_items, ensure_ascii=False),
            json.dumps(analysis.flags, ensure_ascii=False),
            json.dumps(analysis.key_topics, ensure_ascii=False),
            analysis.raw_response,
            analysis.model,
            analysis.prompt_version,
            getattr(analysis, "call_type", "unknown"),
            getattr(analysis, "hook", None),
            getattr(analysis, "parse_status", "unknown"),
            int(getattr(analysis, "profanity_count", 0) or 0),
            float(getattr(analysis, "profanity_density", 0.0) or 0.0),
        ]
        canonical = getattr(analysis, "canonical_json", None)
        if canonical:
            cols += ", canonical_json"
            vals.append(canonical)
        if has_sv:
            cols += ", schema_version"
            vals.append(getattr(analysis, "schema_version", None) or "v2")
        ph = ",".join("?" * len(vals))
        update_cols = cols.replace("call_id, ", "")
        update_sets = ", ".join(f"{c}=excluded.{c}" for c in update_cols.split(", "))
        conn.execute(
            f"INSERT INTO analyses ({cols}) VALUES ({ph}) "
            f"ON CONFLICT(call_id) DO UPDATE SET {update_sets}",
            vals,
        )
        conn.commit()

    def get_analysis(self, user_id: str, call_id: int) -> dict | None:
        row = (
            self._get_conn()
            .execute(
                """SELECT a.* FROM analyses a
                   JOIN calls c ON c.call_id = a.call_id
                   WHERE a.call_id = ? AND c.user_id = ?""",
                (call_id, user_id),
            )
            .fetchone()
        )
        if not row:
            return None
        d = dict(row)
        d["action_items"] = json.loads(d["action_items"])
        d["flags"] = json.loads(d["flags"])
        d["key_topics"] = json.loads(d["key_topics"])
        return d

    def get_analysis_for_user(self, user_id: str, call_id: int) -> dict | None:
        """Р’РµСЂРЅСѓС‚СЊ Р°РЅР°Р»РёР· С‚РѕР»СЊРєРѕ РґР»СЏ Р·РІРѕРЅРєР°, РїСЂРёРЅР°РґР»РµР¶Р°С‰РµРіРѕ user_id."""
        row = (
            self._get_conn()
            .execute(
                """SELECT a.* FROM analyses a
               JOIN calls c ON c.call_id = a.call_id
               WHERE a.call_id = ? AND c.user_id = ?""",
                (call_id, user_id),
            )
            .fetchone()
        )
        if not row:
            return None
        d = dict(row)
        d["action_items"] = json.loads(d["action_items"])
        d["flags"] = json.loads(d["flags"])
        d["key_topics"] = json.loads(d["key_topics"])
        return d

    def get_recent_analyses(
        self, user_id: str, contact_id: int, limit: int = 5
    ) -> list[dict]:
        rows = (
            self._get_conn()
            .execute(
                """SELECT a.* FROM analyses a
               JOIN calls c ON c.call_id = a.call_id
               WHERE c.user_id=? AND c.contact_id=?
               ORDER BY a.created_at DESC LIMIT ?""",
                (user_id, contact_id, limit),
            )
            .fetchall()
        )
        result = []
        for row in rows:
            d = dict(row)
            d["action_items"] = json.loads(d["action_items"])
            d["flags"] = json.loads(d["flags"])
            d["key_topics"] = json.loads(d["key_topics"])
            result.append(d)
        return result

    def set_feedback(self, analysis_id: int, feedback: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE analyses SET feedback=? WHERE analysis_id=?",
            (feedback, analysis_id),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Promises
    # ------------------------------------------------------------------

    def save_batch(self, items: list[dict]) -> None:
        """РЎРѕС…СЂР°РЅРёС‚СЊ Р±Р°С‚С‡ Р°РЅР°Р»РёР·РѕРІ Рё promises РІ РѕРґРЅРѕР№ С‚СЂР°РЅР·Р°РєС†РёРё."""
        conn = self._get_conn()
        # РџСЂРѕРІРµСЂСЏРµРј РЅР°Р»РёС‡РёРµ РЅРµРѕР±СЏР·Р°С‚РµР»СЊРЅС‹С… РєРѕР»РѕРЅРѕРє РѕРґРёРЅ СЂР°Р·
        existing_analyses = {
            row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()
        }
        has_sv = "schema_version" in existing_analyses
        has_cj = "canonical_json" in existing_analyses

        for item in items:
            call_id = item["call_id"]
            a = item["analysis"]

            cols = (
                "call_id, priority, risk_score, summary, action_items, "
                "flags, key_topics, raw_response, model, prompt_version, "
                "call_type, hook, parse_status, profanity_count, profanity_density"
            )
            vals = [
                call_id,
                a.priority,
                a.risk_score,
                a.summary,
                json.dumps(a.action_items, ensure_ascii=False),
                json.dumps(a.flags, ensure_ascii=False),
                json.dumps(a.key_topics, ensure_ascii=False),
                a.raw_response,
                a.model,
                a.prompt_version,
                getattr(a, "call_type", "unknown"),
                getattr(a, "hook", None),
                getattr(a, "parse_status", "unknown"),
                int(getattr(a, "profanity_count", 0) or 0),
                float(getattr(a, "profanity_density", 0.0) or 0.0),
            ]
            if has_cj:
                cols += ", canonical_json"
                vals.append(getattr(a, "canonical_json", None) or "")
            if has_sv:
                cols += ", schema_version"
                vals.append(getattr(a, "schema_version", None) or "v2")

            ph = ",".join("?" * len(vals))
            update_cols = cols.replace("call_id, ", "")
            update_sets = []
            for c in update_cols.split(", "):
                c = c.strip()
                if c == "canonical_json":
                    update_sets.append(
                        "canonical_json=COALESCE(excluded.canonical_json, analyses.canonical_json)"
                    )
                else:
                    update_sets.append(f"{c}=excluded.{c}")
            update_str = ", ".join(update_sets)

            conn.execute(
                f"INSERT INTO analyses ({cols}) VALUES ({ph}) "
                f"ON CONFLICT(call_id) DO UPDATE SET {update_str}",
                vals,
            )
            contact_id = item.get("contact_id")
            promises = item.get("promises") or []
            if promises and contact_id is not None:
                conn.executemany(
                    """INSERT INTO promises (user_id, contact_id, call_id, who, what, due)
                       VALUES (?,?,?,?,?,?)""",
                    [
                        (
                            item["user_id"],
                            contact_id,
                            call_id,
                            p.get("who", ""),
                            p.get("what", ""),
                            p.get("due"),
                        )
                        for p in promises
                    ],
                )
        conn.commit()

    def save_promises(
        self, user_id: str, contact_id: int | None, call_id: int, promises: list[dict]
    ) -> None:
        """Save promises. Skip if contact_id is None or no promises."""
        if not promises or contact_id is None:
            return
        conn = self._get_conn()
        conn.executemany(
            """INSERT INTO promises (user_id, contact_id, call_id, who, what, due)
               VALUES (?,?,?,?,?,?)""",
            [
                (
                    user_id,
                    contact_id,
                    call_id,
                    p.get("who", ""),
                    p.get("what", ""),
                    p.get("due"),
                )
                for p in promises
            ],
        )
        conn.commit()

    def get_open_promises(self, user_id: str) -> list[dict]:
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM promises WHERE user_id=? AND status='open' ORDER BY due",
                (user_id,),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def get_contact_promises(self, user_id: str, contact_id: int) -> list[dict]:
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM promises WHERE user_id=? AND contact_id=? ORDER BY created_at DESC",
                (user_id, contact_id),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Events (structured extraction from transcripts and analyses)
    # ------------------------------------------------------------------

    def save_events(self, call_id: int, events: list[dict]) -> None:
        """Save list of events extracted from call analysis.

        Each event dict should contain: user_id, contact_id (nullable),
        event_type, who, payload, source_quote (optional), confidence (optional),
        deadline (optional), status (optional).
        """
        if not events:
            return
        conn = self._get_conn()
        conn.executemany(
            """INSERT INTO events
               (user_id, contact_id, call_id, event_type, who, payload,
                source_quote, confidence, deadline, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    e.get("user_id", ""),
                    e.get("contact_id"),
                    call_id,
                    e.get("event_type", "fact"),
                    e.get("who", "UNKNOWN"),
                    e.get("payload", ""),
                    e.get("source_quote"),
                    e.get("confidence", 1.0),
                    e.get("deadline"),
                    e.get("status", "open"),
                )
                for e in events
            ],
        )
        conn.commit()

    def get_open_events(
        self, user_id: str, contact_id: int | None = None, event_type: str | None = None
    ) -> list[dict]:
        """Get open events for a user, optionally filtered by contact and type."""
        query = "SELECT * FROM events WHERE user_id = ? AND status = 'open'"
        params = [user_id]

        if contact_id is not None:
            query += " AND contact_id = ?"
            params.append(contact_id)

        if event_type is not None:
            query += " AND event_type = ?"
            params.append(event_type)

        query += " ORDER BY deadline, created_at DESC"

        rows = self._get_conn().execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_events_for_contact(
        self, user_id: str, contact_id: int, limit: int = 50
    ) -> list[dict]:
        """Get all events for a contact, newest first."""
        rows = (
            self._get_conn()
            .execute(
                """SELECT * FROM events
               WHERE user_id = ? AND contact_id = ?
               ORDER BY created_at DESC LIMIT ?""",
                (user_id, contact_id, limit),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def update_event_status(self, event_id: int, status: str) -> None:
        """Update status of an event (open в†’ fulfilled/broken/expired/resolved)."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE events SET status = ? WHERE id = ?",
            (status, event_id),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Contact Summaries
    # ------------------------------------------------------------------

    def save_contact_summary(
        self,
        contact_id: int,
        user_id: str,
        total_calls: int = 0,
        last_call_date: str | None = None,
        global_risk: int = 0,
        avg_bs_score: int = 0,
        top_hook: str | None = None,
        open_promises: str | None = None,
        open_debts: str | None = None,
        personal_facts: str | None = None,
        contact_role: str | None = None,
        advice: str | None = None,
    ) -> None:
        """Save or update a contact summary (INSERT OR REPLACE)."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO contact_summaries
               (contact_id, user_id, total_calls, last_call_date, global_risk,
                avg_bs_score, top_hook, open_promises, open_debts, personal_facts,
                contact_role, advice, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                contact_id,
                user_id,
                total_calls,
                last_call_date,
                global_risk,
                avg_bs_score,
                top_hook,
                open_promises,
                open_debts,
                personal_facts,
                contact_role,
                advice,
            ),
        )
        conn.commit()

    def get_contact_summary(self, user_id: str, contact_id: int) -> dict | None:
        """Get contact summary by ID, enforcing user_id isolation."""
        row = (
            self._get_conn()
            .execute(
                "SELECT * FROM contact_summaries WHERE contact_id = ? AND user_id = ?",
                (contact_id, user_id),
            )
            .fetchone()
        )
        return dict(row) if row else None

    def get_all_contacts_for_user(self, user_id: str) -> list[dict]:
        """Get all contacts for a user (previously in queries, now explicit)."""
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM contacts WHERE user_id = ? ORDER BY display_name",
                (user_id,),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]
