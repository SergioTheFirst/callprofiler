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
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def init_db(self) -> None:
        """Создать все таблицы по schema.sql."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, encoding="utf-8") as f:
            sql = f.read()
        conn = self._get_conn()
        conn.executescript(sql)
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
        conn = self._get_conn()
        row = conn.execute(
            "SELECT contact_id FROM contacts WHERE user_id = ? AND phone_e164 = ?",
            (user_id, phone_e164),
        ).fetchone()
        if row:
            return row["contact_id"]
        cur = conn.execute(
            "INSERT INTO contacts (user_id, phone_e164, display_name) VALUES (?, ?, ?)",
            (user_id, phone_e164, display_name),
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

    def save_promises(self, user_id: str, contact_id: int, call_id: int,
                      promises: list[dict]) -> None:
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
