# -*- coding: utf-8 -*-
"""
repository.py вЂ” РґРѕСЃС‚СѓРї Рє SQLite. Р‘РµР· ORM, С‚РѕР»СЊРєРѕ sqlite3.
РљР°Р¶РґС‹Р№ РјРµС‚РѕРґ, СЂР°Р±РѕС‚Р°СЋС‰РёР№ СЃ РґР°РЅРЅС‹РјРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ, С„РёР»СЊС‚СЂСѓРµС‚ РїРѕ user_id.
"""

import json
import logging
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from callprofiler.db.connection import ConnectionFactory
from callprofiler.db.uow import commit_unless_uow, rollback_unless_uow
from callprofiler.identity import validate_user_id
from callprofiler.models import Analysis, Segment

logger = logging.getLogger(__name__)


class Repository:
    backoff_base_sec: int = 60   # T-07: база exp-backoff; Orchestrator ставит из config.pipeline.retry_interval_sec
    backoff_max_sec: int = 3600

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = ConnectionFactory(self._db_path).writer()
        return self._conn

    def _commit(self, conn: sqlite3.Connection) -> None:
        """Коммит, подавляемый внутри UnitOfWork (db.uow.uow_for) — T-04.

        Единственное место проверки ``conn.in_uow``, чтобы не пришлось
        отдельно править семантику каждого из ~22 бывших ``conn.commit()``
        вызовов в этом файле."""
        commit_unless_uow(conn)

    def init_db(self, *, backup_dir: str | None = None, unsafe: bool = False) -> None:
        """Создать все таблицы по schema.sql + применить миграции (T-05).

        ``backup_dir`` — если задан, требует свежий верифицированный бэкап
        (``ops.backup``) перед миграцией существующей (не только что
        созданной) БД; ``unsafe=True`` явно снимает этот гейт. По умолчанию
        (``backup_dir=None``) гейт пропущен — так ведут себя все тесты и
        первый bootstrap на пустой БД, где бэкапить нечего.
        """
        from callprofiler.db.migrations import (
            apply_migrations,
            data_at_risk,
            default_backup_dir,
            ensure_backup_before_migrate,
        )

        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, encoding="utf-8") as f:
            sql = f.read()
        conn = self._get_conn()
        conn.executescript(sql)
        self._commit(conn)

        # Гейт бэкапа взводится САМ, когда есть что терять (непримененные
        # миграции + непустая таблица calls). Опциональный параметр, который
        # никто не передаёт, защитой не является — T-20 ставился перед T-05
        # именно чтобы боевая БД не мигрировала без проверенного снимка.
        if not unsafe and data_at_risk(conn):
            ensure_backup_before_migrate(
                self._db_path,
                backup_dir or default_backup_dir(self._db_path),
                unsafe=False,
            )

        apply_migrations(conn)
        self._commit(conn)

    def _migrate(self) -> None:
        """Совместимость: некоторые тесты/вызовы дёргают _migrate() напрямую."""
        from callprofiler.db.migrations import apply_migrations

        conn = self._get_conn()
        apply_migrations(conn)
        self._commit(conn)

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
        validate_user_id(user_id)  # P-TEN-06: allowlist slug — user_id feeds paths
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
        self._commit(conn)

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
                self._commit(conn)
            return contact_id
        # РЎРѕР·РґР°С‚СЊ РЅРѕРІС‹Р№ РєРѕРЅС‚Р°РєС‚
        cur = conn.execute(
            """INSERT INTO contacts (user_id, phone_e164, display_name, name_confirmed)
               VALUES (?, ?, ?, ?)""",
            (user_id, phone_e164, display_name, 1 if display_name else 0),
        )
        self._commit(conn)
        return cur.lastrowid

    def find_contact_by_name(
        self, user_id: str, name: str
    ) -> tuple[dict | None, bool]:
        """Найти контакт по имени (F4, caption-привязка голосовой заметки).

        Порядок: точное совпадение display_name/guessed_name, иначе
        case-insensitive префикс (Python .lower() — корректно для кириллицы,
        в отличие от SQL LIKE, чья регистронезависимость ASCII-only).
        Несколько совпадений на любом шаге = ambiguous, не выбираем никого.

        Возвращает (contact_or_None, ambiguous).
        """
        target = (name or "").strip()
        if not target:
            return None, False

        rows = [
            dict(r)
            for r in self._get_conn()
            .execute("SELECT * FROM contacts WHERE user_id = ?", (user_id,))
            .fetchall()
        ]

        exact = [
            r for r in rows
            if r.get("display_name") == target or r.get("guessed_name") == target
        ]
        if len(exact) == 1:
            return exact[0], False
        if len(exact) > 1:
            return None, True

        target_lower = target.lower()
        prefix = [
            r for r in rows
            if (r.get("display_name") or "").lower().startswith(target_lower)
            or (r.get("guessed_name") or "").lower().startswith(target_lower)
        ]
        if len(prefix) == 1:
            return prefix[0], False
        if len(prefix) > 1:
            return None, True
        return None, False

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
        user_id: str,
        contact_id: int,
        guessed_name: str,
        guess_source: str,
        guess_call_id: int,
        guess_confidence: str,
    ) -> bool:
        """Записать угаданное имя контакта (не перезаписывает подтверждённые).

        Возвращает False без исключения при чужом/несуществующем contact_id.
        """
        conn = self._get_conn()
        row = conn.execute(
            """UPDATE contacts
               SET guessed_name=?, guess_source=?,
                   guess_call_id=?, guess_confidence=?
               WHERE contact_id=? AND user_id=?
                 AND (name_confirmed = 0 OR name_confirmed IS NULL)""",
            (guessed_name, guess_source, guess_call_id, guess_confidence, contact_id, user_id),
        )
        self._commit(conn)
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

    def reset_call(self, user_id: str, call_id: int) -> bool:
        """Сбросить звонок на полную переобработку: status='new', stage=0,
        retry_count=0, error_message=NULL, next_retry_at=NULL. Используется при восстановлении
        потерянного аудио / форс-переобработке. False без исключения при
        чужом/несуществующем call_id."""
        conn = self._get_conn()
        row = conn.execute(
            "UPDATE calls SET status='new', pipeline_stage=0, retry_count=0, "
            "error_message=NULL, next_retry_at=NULL WHERE call_id=? AND user_id=?",
            (call_id, user_id),
        )
        self._commit(conn)
        return row.rowcount > 0

    def create_call(
        self,
        user_id: str,
        contact_id: int | None,
        direction: str,
        call_datetime: datetime | None,
        source_filename: str,
        source_md5: str,
        audio_path: str,
        call_type: str | None = None,
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
                   source_filename, source_md5, audio_path, call_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    contact_id,
                    direction,
                    dt_value,
                    source_filename,
                    source_md5,
                    audio_path,
                    call_type,
                ),
            )
            self._commit(conn)
            return cur.lastrowid
        except Exception as exc:
            # РЈРЅРёРєР°Р»СЊРЅС‹Р№ РёРЅРґРµРєСЃ idx_calls_user_md5 РїСЂРµРґРѕС‚РІСЂР°С‰Р°РµС‚ РґСѓР±Р»РёРєР°С‚
            if "UNIQUE constraint failed" in str(exc) and source_md5:
                rollback_unless_uow(conn)
                row = conn.execute(
                    "SELECT call_id FROM calls WHERE user_id=? AND source_md5=?",
                    (user_id, source_md5),
                ).fetchone()
                if row:
                    return row["call_id"]
            raise

    def update_call_status(
        self,
        user_id: str,
        call_id: int,
        status: str,
        error_message: str | None = None,
        force: bool = False,
        backoff_base_sec: int | None = None,
        backoff_max_sec: int | None = None,
    ) -> bool:
        """Set call status. Returns False without error if call not found or terminal
        status cannot be overwritten (P-TEN-02).

        If error_message is not None, sets next_retry_at with exponential backoff + jitter:
        delay = min(base * 2^retry_count, max) * uniform(0.8, 1.2); base/max default to
        Repository.backoff_base_sec / backoff_max_sec (Orchestrator sets base from
        config.pipeline.retry_interval_sec).

        If force=True, allows overwriting terminal statuses (done/transcribed).
        If force=False (default), refuses to overwrite terminal statuses with different status.
        """
        conn = self._get_conn()

        # Terminal status guard: refuse overwrite unless forced or status unchanged
        if not force:
            current = conn.execute(
                "SELECT status FROM calls WHERE call_id = ? AND user_id = ?",
                (call_id, user_id),
            ).fetchone()
            if current and current["status"] in ("done", "transcribed") and current["status"] != status:
                logger.warning(
                    "update_call_status: refuse %s→%s call_id=%s (terminal; force=False)",
                    current["status"], status, call_id,
                )
                return False

        if error_message is not None:
            # Exponential backoff + jitter (T-07 slice): delay = min(base·2^retry_count, max)·U(0.8,1.2),
            # retry_count = число ПРЕДЫДУЩИХ ошибок. Первая ошибка тоже ждёт base — иначе tight retry
            # в каждом цикле watcher. ponytail: один worker — без lease/attempts; добавить при втором писателе.
            retry_row = conn.execute(
                "SELECT retry_count FROM calls WHERE call_id = ? AND user_id = ?",
                (call_id, user_id),
            ).fetchone()
            retry_count = retry_row["retry_count"] if retry_row else 0
            base = self.backoff_base_sec if backoff_base_sec is None else backoff_base_sec
            cap = self.backoff_max_sec if backoff_max_sec is None else backoff_max_sec
            delay_sec = min(base * (2 ** min(retry_count, 20)), cap) * random.uniform(0.8, 1.2)
            row = conn.execute(
                """UPDATE calls SET status=?, error_message=?,
                   retry_count=retry_count+1,
                   next_retry_at=datetime('now', '+' || ? || ' seconds'),
                   updated_at=datetime('now')
                   WHERE call_id=? AND user_id=?""",
                (status, error_message, int(delay_sec), call_id, user_id),
            )
        else:
            row = conn.execute(
                "UPDATE calls SET status=?, updated_at=datetime('now') "
                "WHERE call_id=? AND user_id=?",
                (status, call_id, user_id),
            )
        self._commit(conn)
        return row.rowcount > 0

    def update_pipeline_stage(self, user_id: str, call_id: int, stage: int) -> bool:
        """Персистировать стадию pipeline (0-4) для crash-resume."""
        conn = self._get_conn()
        row = conn.execute(
            "UPDATE calls SET pipeline_stage=?, updated_at=datetime('now') "
            "WHERE call_id=? AND user_id=?",
            (stage, call_id, user_id),
        )
        self._commit(conn)
        return row.rowcount > 0

    def set_role_fragile(self, user_id: str, call_id: int, fragile: bool) -> bool:
        """Пометить звонок role_fragile (роль-шум-доктрина, OzaluplivanieFable.md §4.2)."""
        conn = self._get_conn()
        row = conn.execute(
            "UPDATE calls SET role_fragile=? WHERE call_id=? AND user_id=?",
            (1 if fragile else 0, call_id, user_id),
        )
        self._commit(conn)
        return row.rowcount > 0

    def update_call_paths(
        self, user_id: str, call_id: int, norm_path: str, duration_sec: int
    ) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "UPDATE calls SET norm_path=?, duration_sec=?, updated_at=datetime('now') "
            "WHERE call_id=? AND user_id=?",
            (norm_path, duration_sec, call_id, user_id),
        )
        self._commit(conn)
        return row.rowcount > 0

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

        Условие: ``status NOT IN ('new','done','error','transcribed')`` — любой
        промежуточный статус (normalizing/diarizing/transcribing/analyzing/
        delivering) значит, что воркер начал, но не закончил. ``transcribed`` —
        ТЕРМИНАЛЬНЫЙ статус Stage-1 (транскрипт в БД, LLM-анализ отложён на
        Stage-2 при ``enable_llm_analysis=false``): он НЕ зависший, иначе
        transcribe-only прогон реклаймил бы его бесконечно. Фильтр по
        ``pipeline_stage`` НЕ
        применяем: ``update_call_status('normalizing')`` ставится ДО
        ``update_pipeline_stage(1)``, поэтому крах во время нормализации
        оставляет звонок на stage 0 со status='normalizing'. Прежнее условие
        ``pipeline_stage > 0`` навсегда сиротило такие звонки — их не видел ни
        pending (status='new'), ни этот resume. ``process_batch`` идемпотентен по
        stage, так что переподхват с stage 0 безопасен.
        """
        where = "status NOT IN ('new','done','error','transcribed')"
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

    def get_error_calls(self, max_retries: int = 3, user_id: str | None = None) -> list[dict]:
        # ВНИМАНИЕ: max_retries ПЕРВЫМ — все вызовы передают его позиционно
        # (retry_errors/cmd_reprocess/cmd_status/dashboard). Раньше user_id был
        # первым → get_error_calls(3) трактовался как user_id=3 → пустой результат.
        #
        # Фильтр по next_retry_at (exponential backoff): пропускаем звонки, еще не готовые
        # к повтору. next_retry_at=NULL → никогда не устанавливался (старые error-звонки) →
        # готовы; next_retry_at <= now → пора повторять.
        if user_id:
            rows = (
                self._get_conn()
                .execute(
                    """SELECT * FROM calls WHERE status='error' AND retry_count < ?
                       AND user_id=?
                       AND (next_retry_at IS NULL OR next_retry_at <= datetime('now'))
                       ORDER BY updated_at""",
                    (max_retries, user_id),
                )
                .fetchall()
            )
        else:
            rows = (
                self._get_conn()
                .execute(
                    """SELECT * FROM calls WHERE status='error' AND retry_count < ?
                       AND (next_retry_at IS NULL OR next_retry_at <= datetime('now'))
                       ORDER BY updated_at""",
                    (max_retries,),
                )
                .fetchall()
            )
        return [dict(r) for r in rows]

    # ── Деструктивная чистка (всегда dry-run по умолчанию: apply=False) ─────────

    @staticmethod
    def _table_exists(conn, name: str) -> bool:
        return (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            is not None
        )

    def _fts_delete_rows(self, conn, rows: list) -> None:
        """Удалить строки из внешнего FTS5-индекса ``transcripts_fts``.

        ``rows`` — список кортежей ``(segment_id, text, speaker, call_id)``
        для удаляемых сегментов. Используем FTS5 special-command ``'delete'``
        со СТАРЫМИ значениями (external-content FTS5 хранит только индекс,
        поэтому old-values нужны явно). Вызывать ДО DELETE из transcripts.
        Колонки FTS больше не включают ``user_id`` (P-DB-06, db/migrations.py
        ``_m008_fts_drop_user_id``) — ownership фильтруется через JOIN к
        ``calls`` во всех читателях, а не через колонку в самом индексе.
        """
        if rows and self._table_exists(conn, "transcripts_fts"):
            conn.executemany(
                "INSERT INTO transcripts_fts(transcripts_fts, rowid, text, speaker, call_id) "
                "VALUES ('delete', ?, ?, ?, ?)",
                rows,
            )

    def delete_calls(
        self,
        call_ids: list[int],
        apply: bool = False,
        *,
        user_id: str | None,
    ) -> dict[str, int]:
        """Удалить звонки и все зависимые строки (FTS-safe, идемпотентно).

        ``apply=False`` (по умолчанию) — ТОЛЬКО считает, что будет удалено, и
        ничего не трогает. ``apply=True`` — удаляет в одной транзакции:
        FTS-delete старых сегментов → events/promises/analyses/transcripts
        (дети) → calls (родитель). Использует TEMP-таблицу, поэтому число id
        не ограничено лимитом параметров SQLite (~999).

        ``user_id`` — если задан, удаление СКОУПЛЕНО этим владельцем (чужие
        id из ``call_ids`` молча отбрасываются). ``user_id=None`` — явный
        ADMIN-путь (кросс-тенантное удаление по голым id, как раньше); нет
        неявного дефолта, вызывающий обязан написать ``user_id=None`` явно.

        Возвращает счётчики по таблицам (что удалено / будет удалено).
        """
        counts = {t: 0 for t in ("calls", "transcripts", "analyses", "events", "promises")}
        ids = sorted({int(c) for c in call_ids})
        if not ids:
            return counts

        conn = self._get_conn()
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _del_ids (call_id INTEGER PRIMARY KEY)")
        conn.execute("DELETE FROM _del_ids")
        conn.executemany("INSERT OR IGNORE INTO _del_ids(call_id) VALUES (?)", [(i,) for i in ids])
        if user_id is not None:
            conn.execute(
                """DELETE FROM _del_ids WHERE call_id NOT IN
                   (SELECT call_id FROM calls WHERE user_id=?)""",
                (user_id,),
            )
        in_set = "IN (SELECT call_id FROM _del_ids)"
        try:
            for tbl in ("transcripts", "analyses", "events", "promises", "calls"):
                counts[tbl] = conn.execute(
                    f"SELECT COUNT(*) AS c FROM {tbl} WHERE call_id {in_set}"
                ).fetchone()["c"]

            if apply:
                # FTS-строки убираем ДО удаления transcripts (нужны old-values +
                # calls для user_id). См. _fts_delete_rows.
                fts_rows = conn.execute(
                    "SELECT t.segment_id, t.text, t.speaker, t.call_id, c.user_id "
                    "FROM transcripts t JOIN calls c ON c.call_id = t.call_id "
                    f"WHERE t.call_id {in_set}"
                ).fetchall()
                self._fts_delete_rows(
                    conn,
                    [
                        (r["segment_id"], r["text"], r["speaker"], r["call_id"])
                        for r in fts_rows
                    ],
                )
                for tbl in ("events", "promises", "analyses", "transcripts", "calls"):
                    conn.execute(f"DELETE FROM {tbl} WHERE call_id {in_set}")
                self._commit(conn)
        finally:
            conn.execute("DROP TABLE IF EXISTS _del_ids")
        return counts

    def purge_user(self, user_id: str, apply: bool = False) -> dict[str, int]:
        """Полностью удалить пользователя и ВСЕ его данные (FTS-safe, introspection-based).

        ``apply=False`` — только счётчики. ``apply=True`` — удаляет в одной транзакции.
        Таблицы открыты через introspection (PRAGMA table_info), но удаляются в
        безопасном FK-порядке (дети до родителей).
        """
        conn = self._get_conn()
        counts: dict[str, int] = {}

        def _count(sql: str) -> int:
            return conn.execute(sql, (user_id,)).fetchone()[0]

        # Enum все таблицы (кроме sqlite_master и FTS shadow-таблиц)
        all_tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'transcripts_fts%' "
                "ORDER BY name"
            )
        ]

        # Classify таблицы: PROTECTED (никогда не трогаем) + CHILD_RULES (без user_id)
        PROTECTED_TABLES = {"schema_migrations"}
        CHILD_RULES = {
            "transcripts": "call_id IN (SELECT call_id FROM calls WHERE user_id=?)",
            "analyses": "call_id IN (SELECT call_id FROM calls WHERE user_id=?)",
            "bio_scene_entities": "scene_id IN (SELECT scene_id FROM bio_scenes WHERE user_id=?)",
        }

        # Deletion order (FK-safe, children before parents)
        # Defined here (not in if apply:) so count loop can filter to only these tables
        delete_order = [
            "transcripts", "analyses",  # children of calls
            "events", "promises",  # user_id FKs
            "bio_checkpoints", "bio_checkpoint_items", "bio_llm_calls",
            "bio_threads", "bio_portraits", "bio_behavior_patterns",
            "bio_contradictions", "bio_arcs", "bio_chapters", "bio_books",
            "bio_scene_entities",  # child of bio_scenes
            "bio_scenes", "bio_entities",  # parents of above
            "contact_notes",  # user_id FK
            "ask_log",  # user_id FK
            "entity_profiles",  # user_id FK (graph)
            "contact_summaries",  # user_id FK
            "calls",  # user_id FK, parent of transcripts/analyses/bio_scenes
            "mention_edges", "contact_archetypes", "contact_features", "archetype_models",  # user_id FKs (insight)
            "contact_tiers",  # user_id FK
            "entity_contact_map", "graph_replay_runs",  # user_id FKs
            "promise_outcomes", "deep_facts",  # user_id FKs (but no FK constraint)
            "llm_calls",  # user_id FK
            "bs_thresholds",  # user_id FK
            "reminders",  # user_id FK
            "report_state", "owner_mirror",  # user_id FKs
            "contacts",  # user_id FK, parent of calls
            "entity_merges_log", "entity_metrics", "relations", "entities",  # user_id FKs (graph)
            "risk_thresholds",  # user_id FK (insight)
            "users",  # PK, delete last
        ]

        # Count rows before apply
        for tbl in all_tables:
            if tbl in PROTECTED_TABLES:
                continue
            # Only count tables that will actually be deleted (in delete_order)
            if tbl not in delete_order:
                continue

            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({tbl})")}
            has_user_id = "user_id" in cols

            if has_user_id:
                counts[tbl] = _count(f"SELECT COUNT(*) FROM {tbl} WHERE user_id=?")
            elif tbl in CHILD_RULES:
                rule = CHILD_RULES[tbl]
                counts[tbl] = _count(f"SELECT COUNT(*) FROM {tbl} WHERE {rule}")
            else:
                raise RuntimeError(
                    f"purge_user: таблица '{tbl}' не имеет user_id и нет правила в CHILD_RULES. "
                    f"Добавьте правило перед использованием."
                )

        if apply:
            # Defer FK checks until all deletes complete
            conn.execute("PRAGMA defer_foreign_keys=ON")

            # FTS-строки убираем ДО удаления transcripts
            sub = "(SELECT call_id FROM calls WHERE user_id=?)"
            fts_rows = conn.execute(
                f"SELECT segment_id, text, speaker, call_id FROM transcripts "
                f"WHERE call_id IN {sub}",
                (user_id,),
            ).fetchall()
            self._fts_delete_rows(
                conn,
                [
                    (r["segment_id"], r["text"], r["speaker"], r["call_id"])
                    for r in fts_rows
                ],
            )

            # Удаления в FK-безопасном порядке (дети перед родителями):
            # FTS уже удалены; transcripts/analyses (дети calls) → events/promises →
            # bio_* (дети bio_scenes/bio_entities) → calls → contact_summaries →
            # contacts → граф (entities/relations/entity_metrics) → users

            for tbl in delete_order:
                if tbl not in all_tables or tbl in PROTECTED_TABLES:
                    continue

                cols = {row[1] for row in conn.execute(f"PRAGMA table_info({tbl})")}
                has_user_id = "user_id" in cols

                if has_user_id:
                    conn.execute(f"DELETE FROM {tbl} WHERE user_id=?", (user_id,))
                elif tbl in CHILD_RULES:
                    rule = CHILD_RULES[tbl]
                    conn.execute(f"DELETE FROM {tbl} WHERE {rule}", (user_id,))

            # Fail-safe: check for unmapped tables (guard against schema drift)
            unmapped = set(all_tables) - set(delete_order) - PROTECTED_TABLES
            if unmapped:
                raise RuntimeError(
                    f"purge_user: tables exist but not in delete_order: {sorted(unmapped)}. "
                    f"Add them to delete_order in repository.py before purging."
                )

            self._commit(conn)

        return counts

    def purge_other_users(
        self, keeper_id: str, apply: bool = False
    ) -> dict[str, dict[str, int]]:
        """Снести ВСЕХ юзеров, кроме ``keeper_id`` (инверсия :meth:`purge_user`).

        Возвращает ``{user_id: counts}`` по каждому УДАЛЯЕМОМУ юзеру. ``apply=False``
        — только счётчики (ничего не трогает). ``apply=True`` — необратимо сносит
        каждого не-keeper через ``purge_user`` (каждый в своей транзакции).

        ``ValueError``, если ``keeper_id`` нет в БД — защита: иначе снесли бы ВСЕХ.
        """
        ids = [u["user_id"] for u in self.get_all_users()]
        if keeper_id not in ids:
            raise ValueError(
                f"keeper '{keeper_id}' не найден среди юзеров: {sorted(ids)}"
            )
        result: dict[str, dict[str, int]] = {}
        for uid in ids:
            if uid == keeper_id:
                continue
            result[uid] = self.purge_user(uid, apply=apply)
        return result

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

    def save_transcripts(
        self, user_id: str, call_id: int, segments: list[Segment]
    ) -> bool:
        """РЎРѕС…СЂР°РЅРёС‚СЊ СЃРµРіРјРµРЅС‚С‹ С‚СЂР°РЅСЃРєСЂРёРїС‚Р°. РРґРµРјРїРѕС‚РµРЅС‚РµРЅ: РїРѕРІС‚РѕСЂРЅС‹Р№ РІС‹Р·РѕРІ
        СѓРґР°Р»СЏРµС‚ СЃС‚Р°СЂС‹Рµ СЃРµРіРјРµРЅС‚С‹ Рё РІСЃС‚Р°РІР»СЏРµС‚ РЅРѕРІС‹Рµ (РґР»СЏ СЃР»СѓС‡Р°РµРІ reprocess).
        """
        conn = self._get_conn()
        owns = conn.execute(
            "SELECT 1 FROM calls WHERE call_id=? AND user_id=?", (call_id, user_id)
        ).fetchone()
        if not owns:
            return False
        # Удалить старые сегменты из FTS и таблицы (идемпотентность, F2.3)
        existing = conn.execute(
            "SELECT segment_id, text, speaker, call_id FROM transcripts WHERE call_id=?",
            (call_id,),
        ).fetchall()
        if existing:
            # FTS5 content table: нужно явно удалять через команду 'delete'
            conn.executemany(
                """INSERT INTO transcripts_fts(transcripts_fts, rowid, text, speaker, call_id)
                   VALUES ('delete', ?, ?, ?, ?)""",
                [
                    (r["segment_id"], r["text"], r["speaker"], r["call_id"])
                    for r in existing
                ],
            )
            conn.execute("DELETE FROM transcripts WHERE call_id=?", (call_id,))
        conn.executemany(
            "INSERT INTO transcripts (call_id, start_ms, end_ms, text, speaker) VALUES (?,?,?,?,?)",
            [(call_id, s.start_ms, s.end_ms, s.text, s.speaker) for s in segments],
        )
        self._commit(conn)
        return True

    def get_transcript(self, user_id: str, call_id: int) -> list[dict]:
        rows = (
            self._get_conn()
            .execute(
                """SELECT t.* FROM transcripts t
                   JOIN calls c ON c.call_id = t.call_id
                   WHERE t.call_id=? AND c.user_id=? ORDER BY t.start_ms""",
                (call_id, user_id),
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

    def save_analysis(self, user_id: str, call_id: int, analysis: Analysis) -> bool:
        """False без записи при чужом/несуществующем call_id (P-TEN-02)."""
        conn = self._get_conn()
        owns = conn.execute(
            "SELECT 1 FROM calls WHERE call_id=? AND user_id=?", (call_id, user_id)
        ).fetchone()
        if not owns:
            return False
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
        self._commit(conn)
        return True

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

    def set_feedback(self, user_id: str, analysis_id: int, feedback: str) -> bool:
        """False без записи при чужом/несуществующем analysis_id."""
        conn = self._get_conn()
        row = conn.execute(
            """UPDATE analyses SET feedback=? WHERE analysis_id=? AND call_id IN
               (SELECT call_id FROM calls WHERE user_id=?)""",
            (feedback, analysis_id, user_id),
        )
        self._commit(conn)
        return row.rowcount > 0

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
            item_user_id = item["user_id"]
            owns = conn.execute(
                "SELECT 1 FROM calls WHERE call_id=? AND user_id=?",
                (call_id, item_user_id),
            ).fetchone()
            if not owns:
                logger.warning(
                    "save_batch: call_id=%s не принадлежит user_id=%s — пропуск",
                    call_id, item_user_id,
                )
                continue
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
        self._commit(conn)

    def save_promises(
        self, user_id: str, contact_id: int | None, call_id: int, promises: list[dict]
    ) -> None:
        """Save promises. Skip if contact_id is None, no promises, or call_id
        does not belong to user_id."""
        if not promises or contact_id is None:
            return
        conn = self._get_conn()
        owns = conn.execute(
            "SELECT 1 FROM calls WHERE call_id=? AND user_id=?", (call_id, user_id)
        ).fetchone()
        if not owns:
            logger.warning(
                "save_promises: call_id=%s не принадлежит user_id=%s — пропуск",
                call_id, user_id,
            )
            return
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
        self._commit(conn)

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

    def save_events(self, user_id: str, call_id: int, events: list[dict]) -> bool:
        """Save list of events extracted from call analysis.

        Each event dict should contain: user_id, contact_id (nullable),
        event_type, who, payload, source_quote (optional), confidence (optional),
        deadline (optional), status (optional).

        False (no write) if call_id does not belong to user_id. Individual
        events whose own ``user_id`` field disagrees with the call owner are
        silently dropped (defense-in-depth — same class as P-TEN-02).
        """
        if not events:
            return False
        conn = self._get_conn()
        owns = conn.execute(
            "SELECT 1 FROM calls WHERE call_id=? AND user_id=?", (call_id, user_id)
        ).fetchone()
        if not owns:
            logger.warning(
                "save_events: call_id=%s не принадлежит user_id=%s — пропуск",
                call_id, user_id,
            )
            return False
        rows = [
            (
                user_id,
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
            if e.get("user_id", user_id) == user_id
        ]
        conn.executemany(
            """INSERT INTO events
               (user_id, contact_id, call_id, event_type, who, payload,
                source_quote, confidence, deadline, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._commit(conn)
        return True

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

    def update_event_status(self, user_id: str, event_id: int, status: str) -> bool:
        """Update status of an event (open -> fulfilled/broken/expired/resolved).

        False without exception on a foreign/nonexistent event_id (P-TEN-02).
        """
        conn = self._get_conn()
        row = conn.execute(
            "UPDATE events SET status = ? WHERE id = ? AND user_id = ?",
            (status, event_id, user_id),
        )
        self._commit(conn)
        return row.rowcount > 0

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
    ) -> bool:
        """Save or update a contact summary (INSERT OR REPLACE).

        False (no write) if contact_id does not belong to user_id — PK is
        contact_id alone, so writing without this check could reassign a
        summary row owned by another tenant.
        """
        conn = self._get_conn()
        owns = conn.execute(
            "SELECT 1 FROM contacts WHERE contact_id=? AND user_id=?",
            (contact_id, user_id),
        ).fetchone()
        if not owns:
            logger.warning(
                "save_contact_summary: contact_id=%s не принадлежит user_id=%s — пропуск",
                contact_id, user_id,
            )
            return False
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
        self._commit(conn)
        return True

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
