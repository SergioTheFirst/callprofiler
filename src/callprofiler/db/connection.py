# -*- coding: utf-8 -*-
"""
connection.py — единственное место создания sqlite3-соединений (T-04).

До этого модуля соединения создавались отдельно в repository.py и
dashboard/db_reader.py с частично разными PRAGMA-наборами и без
busy_timeout на writer-стороне. WAL и foreign_keys — load-bearing
(.claude/rules/db.md, bugs.md запись 2026-06-04: read-only ``?mode=ro``
не видит WAL-записи пайплайна) — эта фабрика их не меняет, только
унифицирует создание.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_WRITER_BUSY_TIMEOUT_MS = 5000
DEFAULT_READER_BUSY_TIMEOUT_MS = 3000


class UowConnection(sqlite3.Connection):
    """sqlite3.Connection с одним доп. атрибутом — ``in_uow``.

    Обычный sqlite3.Connection не поддерживает произвольные атрибуты (нет
    __dict__), поэтому commit-guard (db.uow.commit_unless_uow) не мог бы
    хранить флаг "внутри UnitOfWork" прямо на соединении. Подкласс даёт
    __dict__ бесплатно; поведение соединения не меняется.
    """

    in_uow: bool = False


class ConnectionFactory:
    """Единая точка создания writer/reader соединений для одной БД."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _base_connect(self, busy_timeout_ms: int) -> UowConnection:
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self.db_path, check_same_thread=False, factory=UowConnection
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        conn.in_uow = False
        return conn

    def writer(
        self, busy_timeout_ms: int = DEFAULT_WRITER_BUSY_TIMEOUT_MS
    ) -> UowConnection:
        """Read/write соединение — пайплайн, CLI, bulk-операции."""
        return self._base_connect(busy_timeout_ms)

    def reader(
        self, busy_timeout_ms: int = DEFAULT_READER_BUSY_TIMEOUT_MS
    ) -> UowConnection:
        """Read-only соединение (дашборд).

        НЕ ``?mode=ro`` — тот не цепляется к WAL-индексу и читает снимок до
        последнего checkpoint (bugs.md 2026-06-04). ``PRAGMA query_only=ON``
        даёт тот же эффект («писать нельзя») без потери свежести данных —
        WAL допускает много читателей + 1 писатель без блокировок.
        """
        conn = self._base_connect(busy_timeout_ms)
        conn.execute("PRAGMA query_only=ON")
        return conn
