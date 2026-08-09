# -*- coding: utf-8 -*-
"""
uow.py — Unit of Work: граница транзакции на уровне сценария (T-04).

    with uow_for(conn):
        repo.save_analysis(...)
        repo.save_promises(...)
        GraphBuilder(conn).update_from_call(call_id)
    # успех -> один commit здесь; исключение -> rollback, re-raise.

Repository-методы (и GraphBuilder/GraphRepository/EntityMetricsAggregator)
по-прежнему сами вызывают commit в конце своей записи — это НЕ переписано
массово (см. отчёт T-04 за список остатка). Вместо правки каждого метода
по отдельности они зовут ``commit_unless_uow(conn)`` — единственное место,
которое проверяет ``conn.in_uow`` и решает, коммитить реально или нет.
Так один и тот же метод работает и как самостоятельная операция (коммитит
сразу), и как часть чужого UoW (коммит подавлен до общей границы).

Соединение НЕ закрывается на выходе — UoW управляет только транзакцией,
жизненным циклом соединения владеет вызывающий код (Repository, фабрика).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager


def commit_unless_uow(conn: sqlite3.Connection) -> None:
    """Коммитить, если соединение не находится внутри активного UnitOfWork."""
    if not getattr(conn, "in_uow", False):
        conn.commit()


def rollback_unless_uow(conn: sqlite3.Connection) -> None:
    """Откатить, ТОЛЬКО если соединение вне активного UnitOfWork.

    Симметрична ``commit_unless_uow`` и закрывает латентную мину: голый
    ``conn.rollback()`` внутри чужого UoW откатил бы ВЕСЬ внешний сценарий,
    после чего UoW на выходе спокойно сделал бы commit — вызывающий получил
    бы «успех» при потерянных ранних записях. Ровно тот класс тихой частичной
    записи, ради которого T-04 и существует.

    Локальное восстановление внутри UoW при этом не нужно: SQLite при
    нарушении UNIQUE применяет ABORT к ОДНОМУ оператору, транзакция остаётся
    живой и последующий SELECT корректен.
    """
    if not getattr(conn, "in_uow", False):
        conn.rollback()


@contextmanager
def uow_for(conn: sqlite3.Connection):
    """Открыть границу транзакции на ``conn``. Реентерабелен (nested no-op)."""
    already_active = getattr(conn, "in_uow", False)
    conn.in_uow = True
    try:
        yield conn
        if not already_active:
            conn.commit()
    except Exception:
        if not already_active:
            conn.rollback()
        raise
    finally:
        conn.in_uow = already_active
