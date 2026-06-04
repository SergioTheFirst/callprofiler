# -*- coding: utf-8 -*-
"""
reset.py — ЧИСТЫЙ СТАРТ: бэкап старой БД → удалить БД и производные данные →
пересоздать пустую БД + папки + юзера `me` (через bootstrap).

ПО УМОЛЧАНИЮ DRY-RUN: печатает, что будет снесено, и НИЧЕГО не трогает.
Реальная очистка — только с флагом --apply.

НИКОГДА не трогает источники: C:\\calls\\in и C:\\calls\\source.
Сносит ТОЛЬКО производное: БД, C:\\calls\\data\\users\\* (originals-копии +
normalized), C:\\calls\\text, C:\\calls\\sync. Старая БД бэкапится перед удалением.

  python reset.py            # dry-run (показать план)
  python reset.py --apply     # снести и пересоздать (bootstrap)
  python reset.py --apply --keep-files   # снести только БД, data-файлы оставить

Опции:
  --data-dir PATH (default C:\\calls\\data)
  --text-dir  PATH (default C:\\calls\\text)
  --sync-dir  PATH (default C:\\calls\\sync)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_DATA = r"C:\calls\data"
DEFAULT_TEXT = r"C:\calls\text"
DEFAULT_SYNC = r"C:\calls\sync"
# Источники — НЕ трогаем ни при каких условиях.
PROTECTED = {r"c:\calls\in", r"c:\calls\source"}


def _db_path(data_dir: str) -> str:
    return os.path.join(data_dir, "db", "callprofiler.db")


def _dir_stats(path: str) -> tuple[int, int]:
    """(кол-во файлов, суммарный размер в байтах) рекурсивно."""
    files = total = 0
    if not os.path.isdir(path):
        return 0, 0
    for root, _dirs, names in os.walk(path):
        for n in names:
            try:
                total += os.path.getsize(os.path.join(root, n))
                files += 1
            except OSError:
                pass
    return files, total


def _mb(n: int) -> str:
    return f"{n / 1048576:.1f} MB"


def _overlaps_protected(path: str) -> bool:
    """True, если path == источник, ВНУТРИ источника, или СОДЕРЖИТ источник
    (последнее = rmtree снёс бы источники). Защита от --data-dir C:\\calls и т.п."""
    t = os.path.normpath(os.path.abspath(path)).lower().rstrip("\\")
    for prot in PROTECTED:
        pr = os.path.normpath(prot).lower().rstrip("\\")
        if t == pr or t.startswith(pr + "\\") or pr.startswith(t + "\\"):
            return True
    return False


def _count_calls(db: str) -> str:
    if not os.path.isfile(db):
        return "нет БД"
    try:
        import sqlite3

        uri = f"file:{db}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            n = con.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
            u = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            return f"{n} звонков, {u} юзеров"
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001
        return f"не прочитать ({exc})"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Чистый старт CallProfiler (dry-run по умолчанию).")
    p.add_argument("--apply", action="store_true", help="реально снести и пересоздать (иначе dry-run)")
    p.add_argument("--keep-files", action="store_true", help="снести только БД, data-файлы оставить")
    p.add_argument("--data-dir", default=DEFAULT_DATA)
    p.add_argument("--text-dir", default=DEFAULT_TEXT)
    p.add_argument("--sync-dir", default=DEFAULT_SYNC)
    args = p.parse_args(argv)

    db = _db_path(args.data_dir)
    users_dir = os.path.join(args.data_dir, "users")
    targets = [users_dir, args.text_dir, args.sync_dir]

    print("== ЧИСТЫЙ СТАРТ ==")
    print(f"  БД: {db} | {_count_calls(db)} | "
          f"{_mb(os.path.getsize(db)) if os.path.isfile(db) else 'нет файла'}")
    if not args.keep_files:
        for t in targets:
            files, size = _dir_stats(t)
            print(f"  data: {t} | файлов: {files} | {_mb(size)}")
    print(f"  ИСТОЧНИКИ (НЕ трогаем): {', '.join(sorted(PROTECTED))}")

    # Guard: ни одна цель не должна пересекаться с источниками (in/source)
    for t in [db] + (targets if not args.keep_files else []):
        if _overlaps_protected(t):
            print(f"[СТОП] цель пересекается с источником (in/source): {t}")
            return 2

    if not args.apply:
        print("\n  Это DRY-RUN. Ничего не снесено.")
        print("  Реальный чистый старт: reset.bat --apply")
        return 0

    # 1) Бэкап БД
    if os.path.isfile(db):
        bak = f"{db}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(db, bak)
        print(f"\n[1] Бэкап БД → {bak}")
        for ext in ("", "-wal", "-shm"):
            try:
                if os.path.isfile(db + ext):
                    os.remove(db + ext)
            except OSError as exc:
                print(f"    [!] не удалить {db + ext}: {exc}")
        print("[2] Старая БД удалена")
    else:
        print("\n[1-2] БД не было — пропуск")

    # 2) Снести производные data-файлы
    if not args.keep_files:
        for t in targets:
            if os.path.isdir(t):
                try:
                    shutil.rmtree(t)
                    print(f"[3] Снесено: {t}")
                except OSError as exc:
                    print(f"    [!] не снести {t}: {exc}")
    else:
        print("[3] --keep-files: data-файлы оставлены")

    # 3) Пересоздать пустую БД + папки + юзера me (через bootstrap)
    print("[4] bootstrap (пустая БД + папки + юзер me)...")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
    rc = subprocess.run(
        [sys.executable, "-m", "callprofiler", "bootstrap"], env=env
    ).returncode
    if rc != 0:
        print(f"[ОШИБКА] bootstrap вернул {rc}. Запусти вручную: python -m callprofiler bootstrap")
        return rc

    print("\n[OK] Чистый старт готов. Клади источники в C:\\calls\\in и запускай run-watch.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
