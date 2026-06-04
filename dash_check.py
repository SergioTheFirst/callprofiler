# -*- coding: utf-8 -*-
"""Проба «живости» БД для дашборда.

Открывает БД ТАК ЖЕ, как дашборд после фикса (обычный коннект + query_only),
печатает journal_mode, MAX(updated_at) и счётчики статусов ДВАЖДЫ с паузой.
Если запустить во время прогона пайплайна и значения меняются — real-time
работает (read-коннект видит живые WAL-записи).

Запуск:  python dash_check.py [путь_к_.db] [user_id]
"""

from __future__ import annotations

import sqlite3
import sys
import time

DB = sys.argv[1] if len(sys.argv) > 1 else r"C:\calls\data\db\callprofiler.db"
USER = sys.argv[2] if len(sys.argv) > 2 else "me"


def _open(path: str) -> sqlite3.Connection:
    # Обычный (read/write) коннект → полноценно цепляется к WAL-индексу и видит
    # последний коммит. query_only=ON запрещает запись (пайплайн не задеваем).
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _snap(conn: sqlite3.Connection) -> tuple[str | None, dict[str, int]]:
    ts = conn.execute(
        "SELECT MAX(updated_at) FROM calls WHERE user_id=?", (USER,)
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM calls WHERE user_id=? GROUP BY status",
        (USER,),
    ).fetchall()
    return ts, {s: c for s, c in rows}


def main() -> None:
    print(f"DB:   {DB}")
    print(f"user: {USER}")
    conn = _open(DB)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    print(f"journal_mode = {mode}   (ожидаем 'wal')\n")

    ts1, st1 = _snap(conn)
    print(f"[t=0]   MAX(updated_at) = {ts1}")
    print(f"        статусы:          {st1}")

    time.sleep(4)

    # Свежий коннект — как делает поллер дашборда на каждом тике.
    ts2, st2 = _snap(_open(DB))
    print(f"\n[t=4s]  MAX(updated_at) = {ts2}")
    print(f"        статусы:          {st2}")

    if ts2 != ts1 or st2 != st1:
        print("\nOK: данные ДВИГАЮТСЯ → дашборд покажет real-time.")
    else:
        print("\nНЕТ движения за 4с. Если пайплайн СЕЙЧАС обрабатывает —")
        print("пришли этот вывод (и проверь, что user_id верный).")


if __name__ == "__main__":
    main()
