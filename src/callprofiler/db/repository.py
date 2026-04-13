# -*- coding: utf-8 -*-
"""
repository.py — доступ к SQLite. Без ORM, только sqlite3.
Каждый метод, работающий с данными пользователя, фильтрует по user_id.
"""

import json
import sqlite3
from pathlib import Path

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
        """Создать все таблицы по schema.sql + применить миграции."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, encoding="utf-8") as f:
            sql = f.read()
        conn = self._get_conn()
        conn.executescript(sql)
        conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """Применить ALTER TABLE для колонок, добавленных после первого релиза."""
        conn = self._get_conn()
        new_cols = [
            ("guessed_name",    "TEXT"),
            ("guessed_company", "TEXT"),
            ("guess_source",    "TEXT"),
            ("guess_call_id",   "INTEGER"),
            ("guess_confidence","TEXT"),
            ("name_confirmed",  "INTEGER NOT NULL DEFAULT 0"),
        ]
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(contacts)").fetchall()
        }
        for col_name, col_def in new_cols:
            if col_name not in existing:
                conn.execute(
                    f"ALTER TABLE contacts ADD COLUMN {col_name} {col_def}"
                )
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def add_user(self, user_id: str, display_name: str, telegram_chat_id: str | None,
                 incoming_dir: str, sync_dir: str, ref_audio: str) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO users (user_id, display_name, telegram_chat_id,
               incoming_dir, sync_dir, ref_audio)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, display_name, telegram_chat_id, incoming_dir, sync_dir, ref_audio),
        )
        conn.commit()

    def get_user(self, user_id: str) -> dict | None:
        row = self._get_conn().execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_users(self) -> list[dict]:
        rows = self._get_conn().execute("SELECT * FROM users").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    def get_or_create_contact(self, user_id: str, phone_e164: str | None,
                               display_name: str | None = None) -> int:
        """Найти контакт или создать новый.

        Если display_name передан (имя из имени файла = телефонная книга пользователя),
        оно ВСЕГДА обновляется как приоритетное — даже если контакт уже существует.
        Имя из телефонной книги имеет безусловный приоритет над auto-extracted именами.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT contact_id FROM contacts WHERE user_id = ? AND phone_e164 = ?",
            (user_id, phone_e164),
        ).fetchone()
        if row:
            contact_id = row["contact_id"]
            # Имя из имени файла = имя из телефонной книги = безусловный приоритет
            if display_name:
                conn.execute(
                    """UPDATE contacts SET display_name = ?, name_confirmed = 1
                       WHERE contact_id = ?""",
                    (display_name, contact_id),
                )
                conn.commit()
            return contact_id
        # Создать новый контакт
        cur = conn.execute(
            """INSERT INTO contacts (user_id, phone_e164, display_name, name_confirmed)
               VALUES (?, ?, ?, ?)""",
            (user_id, phone_e164, display_name, 1 if display_name else 0),
        )
        conn.commit()
        return cur.lastrowid

    def get_contact(self, contact_id: int) -> dict | None:
        row = self._get_conn().execute(
            "SELECT * FROM contacts WHERE contact_id = ?", (contact_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_contact_by_phone(self, user_id: str, phone_e164: str) -> dict | None:
        row = self._get_conn().execute(
            "SELECT * FROM contacts WHERE user_id = ? AND phone_e164 = ?",
            (user_id, phone_e164),
        ).fetchone()
        return dict(row) if row else None

    def get_all_contacts_for_user(self, user_id: str) -> list[dict]:
        rows = self._get_conn().execute(
            "SELECT * FROM contacts WHERE user_id = ? ORDER BY display_name",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_contacts_without_name(self, user_id: str) -> list[dict]:
        """Вернуть контакты без display_name и без подтверждённого guessed_name."""
        rows = self._get_conn().execute(
            """SELECT * FROM contacts
               WHERE user_id = ?
                 AND (display_name IS NULL OR display_name = '')
                 AND (name_confirmed = 0 OR name_confirmed IS NULL)
               ORDER BY contact_id""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_calls_for_contact(self, user_id: str, contact_id: int) -> list[dict]:
        """Все звонки контакта, отфильтрованные по user_id."""
        rows = self._get_conn().execute(
            """SELECT * FROM calls
               WHERE user_id = ? AND contact_id = ?
               ORDER BY call_datetime""",
            (user_id, contact_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_contact_guessed_name(
        self,
        contact_id: int,
        guessed_name: str,
        guess_source: str,
        guess_call_id: int,
        guess_confidence: str,
    ) -> None:
        """Записать угаданное имя контакта (не перезаписывает подтверждённые)."""
        conn = self._get_conn()
        conn.execute(
            """UPDATE contacts
               SET guessed_name=?, guess_source=?,
                   guess_call_id=?, guess_confidence=?
               WHERE contact_id=? AND (name_confirmed = 0 OR name_confirmed IS NULL)""",
            (guessed_name, guess_source, guess_call_id, guess_confidence, contact_id),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def call_exists(self, user_id: str, source_md5: str) -> bool:
        row = self._get_conn().execute(
            "SELECT 1 FROM calls WHERE user_id = ? AND source_md5 = ?",
            (user_id, source_md5),
        ).fetchone()
        return row is not None

    def create_call(self, user_id: str, contact_id: int | None, direction: str,
                    call_datetime: str | None, source_filename: str,
                    source_md5: str, audio_path: str) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO calls (user_id, contact_id, direction, call_datetime,
               source_filename, source_md5, audio_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, contact_id, direction, call_datetime,
             source_filename, source_md5, audio_path),
        )
        conn.commit()
        return cur.lastrowid

    def update_call_status(self, call_id: int, status: str,
                            error_message: str | None = None) -> None:
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

    def update_call_paths(self, call_id: int, norm_path: str,
                          duration_sec: int) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE calls SET norm_path=?, duration_sec=?, updated_at=datetime('now') WHERE call_id=?",
            (norm_path, duration_sec, call_id),
        )
        conn.commit()

    def get_pending_calls(self) -> list[dict]:
        rows = self._get_conn().execute(
            "SELECT * FROM calls WHERE status='new' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_error_calls(self, max_retries: int = 3) -> list[dict]:
        rows = self._get_conn().execute(
            "SELECT * FROM calls WHERE status='error' AND retry_count < ? ORDER BY updated_at",
            (max_retries,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_call_count_for_contact(self, user_id: str, contact_id: int) -> int:
        row = self._get_conn().execute(
            "SELECT COUNT(*) as cnt FROM calls WHERE user_id=? AND contact_id=?",
            (user_id, contact_id),
        ).fetchone()
        return row["cnt"] if row else 0

    def get_calls_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        rows = self._get_conn().execute(
            "SELECT * FROM calls WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Transcripts
    # ------------------------------------------------------------------

    def save_transcripts(self, call_id: int, segments: list[Segment]) -> None:
        conn = self._get_conn()
        conn.executemany(
            "INSERT INTO transcripts (call_id, start_ms, end_ms, text, speaker) VALUES (?,?,?,?,?)",
            [(call_id, s.start_ms, s.end_ms, s.text, s.speaker) for s in segments],
        )
        conn.commit()

    def get_transcript(self, call_id: int) -> list[dict]:
        rows = self._get_conn().execute(
            "SELECT * FROM transcripts WHERE call_id=? ORDER BY start_ms",
            (call_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_transcripts(self, user_id: str, query: str) -> list[dict]:
        rows = self._get_conn().execute(
            """SELECT t.*, c.user_id FROM transcripts t
               JOIN calls c ON c.call_id = t.call_id
               WHERE c.user_id = ? AND t.text LIKE ?
               ORDER BY t.call_id, t.start_ms""",
            (user_id, f"%{query}%"),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Analyses
    # ------------------------------------------------------------------

    def save_analysis(self, call_id: int, analysis: Analysis) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO analyses
               (call_id, priority, risk_score, summary, action_items,
                flags, key_topics, raw_response, model, prompt_version)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
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
            ),
        )
        conn.commit()

    def get_analysis(self, call_id: int) -> dict | None:
        row = self._get_conn().execute(
            "SELECT * FROM analyses WHERE call_id=?", (call_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["action_items"] = json.loads(d["action_items"])
        d["flags"] = json.loads(d["flags"])
        d["key_topics"] = json.loads(d["key_topics"])
        return d

    def get_recent_analyses(self, user_id: str, contact_id: int,
                             limit: int = 5) -> list[dict]:
        rows = self._get_conn().execute(
            """SELECT a.* FROM analyses a
               JOIN calls c ON c.call_id = a.call_id
               WHERE c.user_id=? AND c.contact_id=?
               ORDER BY a.created_at DESC LIMIT ?""",
            (user_id, contact_id, limit),
        ).fetchall()
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
        """Сохранить батч анализов и promises в одной транзакции.

        Формат каждого элемента: {call_id, analysis, user_id, contact_id, promises}.
        contact_id может быть None — тогда promises пропускаются.
        """
        conn = self._get_conn()
        for item in items:
            call_id = item["call_id"]
            a = item["analysis"]
            conn.execute(
                """INSERT OR REPLACE INTO analyses
                   (call_id, priority, risk_score, summary, action_items,
                    flags, key_topics, raw_response, model, prompt_version)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
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
                ),
            )
            contact_id = item.get("contact_id")
            promises = item.get("promises") or []
            if promises and contact_id is not None:
                conn.executemany(
                    """INSERT INTO promises (user_id, contact_id, call_id, who, what, due)
                       VALUES (?,?,?,?,?,?)""",
                    [(item["user_id"], contact_id, call_id,
                      p.get("who", ""), p.get("what", ""), p.get("due"))
                     for p in promises],
                )
        conn.commit()

    def save_promises(self, user_id: str, contact_id: int | None, call_id: int,
                      promises: list[dict]) -> None:
        """Save promises. Skip if contact_id is None or no promises."""
        if not promises or contact_id is None:
            return
        conn = self._get_conn()
        conn.executemany(
            """INSERT INTO promises (user_id, contact_id, call_id, who, what, due)
               VALUES (?,?,?,?,?,?)""",
            [(user_id, contact_id, call_id,
              p.get("who", ""), p.get("what", ""), p.get("due"))
             for p in promises],
        )
        conn.commit()

    def get_open_promises(self, user_id: str) -> list[dict]:
        rows = self._get_conn().execute(
            "SELECT * FROM promises WHERE user_id=? AND status='open' ORDER BY due",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_contact_promises(self, user_id: str, contact_id: int) -> list[dict]:
        rows = self._get_conn().execute(
            "SELECT * FROM promises WHERE user_id=? AND contact_id=? ORDER BY created_at DESC",
            (user_id, contact_id),
        ).fetchall()
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
            [(
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
             ) for e in events],
        )
        conn.commit()

    def get_open_events(self, user_id: str, contact_id: int | None = None,
                        event_type: str | None = None) -> list[dict]:
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

    def get_events_for_contact(self, user_id: str, contact_id: int,
                                limit: int = 50) -> list[dict]:
        """Get all events for a contact, newest first."""
        rows = self._get_conn().execute(
            """SELECT * FROM events
               WHERE user_id = ? AND contact_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, contact_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_event_status(self, event_id: int, status: str) -> None:
        """Update status of an event (open → fulfilled/broken/expired/resolved)."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE events SET status = ? WHERE id = ?",
            (status, event_id),
        )
        conn.commit()
