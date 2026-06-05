# -*- coding: utf-8 -*-
"""
reset.py — ЧИСТЫЙ ЛИСТ: снести ВСЕ производные файлы в C:\\calls → пересоздать
пустую БД + папки + юзера `me` (через bootstrap). После reset запусти startprocess.bat —
обработка пойдёт заново на файлах из C:\\calls\\in.

ЗАЩИЩЕНО (НЕ трогаем НИКОГДА):
  - C:\\calls\\in      — входящие аудио (вход обработки; startprocess их прогонит)
  - C:\\calls\\source  — мастер-архив исходников

СНОСИМ (рекурсивно ВСЕ файлы в C:\\calls, кроме защищённого):
  - C:\\calls\\data    — ВСЯ: БД, все профили users/* (originals+normalized),
                         logs, biography
  - C:\\calls\\text    — .txt транскрипты
  - C:\\calls\\sync    — caller cards
  - Все остальные остатки обработки

ПО УМОЛЧАНИЮ DRY-RUN: печатает план, НИЧЕГО не трогает. Реальный снос — только --apply.
БД бэкапится ВНЕ data (рядом, в C:\\calls\\) перед сносом — переживает wipe.

  python reset.py            # dry-run (показать план)
  python reset.py --apply     # снести ВСЕ файлы (кроме in/source) → пустая БД + юзер me
  python reset.py --apply --no-backup   # без бэкапа БД

Опции:
  --data-dir PATH (default C:\\calls\\data)   — используется для локации БД
  --text-dir  PATH (default C:\\calls\\text)  — (legacy, для dry-run статистики)
  --sync-dir  PATH (default C:\\calls\\sync)  — (legacy, для dry-run статистики)
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
# Вход обработки и мастер-архив — НЕ трогаем ни при каких условиях.
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
    """True, если path == защищённый, ВНУТРИ него, или СОДЕРЖИТ его (rmtree снёс бы
    in/source). Защита от --data-dir C:\\calls и подобных промахов."""
    t = os.path.normpath(os.path.abspath(path)).lower().rstrip("\\")
    for prot in PROTECTED:
        pr = os.path.normpath(prot).lower().rstrip("\\")
        if t == pr or t.startswith(pr + "\\") or pr.startswith(t + "\\"):
            return True
    return False


def _walk_and_remove(root_path: str, protected: set[str]) -> int:
    """Рекурсивно удалить ВСЕ файлы и пустые папки в root_path, кроме PROTECTED.
    Вернуть кол-во удалённых файлов."""
    if not os.path.isdir(root_path):
        return 0

    protected_abs = {os.path.normpath(os.path.abspath(p)).lower() for p in protected}
    removed = 0

    # topdown=False: обходим листья → родителей (можем удалять папки)
    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        dirpath_norm = os.path.normpath(os.path.abspath(dirpath)).lower()

        # Пропустить, если текущая папка ВНУТРИ защищённой
        is_protected = any(
            dirpath_norm == pr or dirpath_norm.startswith(pr + "\\")
            for pr in protected_abs
        )
        if is_protected:
            continue

        # Удалить файлы в текущей папке
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                os.remove(fpath)
                removed += 1
            except OSError as e:
                print(f"  [!] не удалить {fpath}: {e}")

        # Удалить пустую папку (если не root и не защищённая)
        if dirpath != root_path:
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                pass

    return removed


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
    p = argparse.ArgumentParser(description="Чистый лист CallProfiler (dry-run по умолчанию).")
    p.add_argument("--apply", action="store_true", help="реально снести и пересоздать (иначе dry-run)")
    p.add_argument("--no-backup", action="store_true", help="не бэкапить БД перед сносом")
    p.add_argument("--data-dir", default=DEFAULT_DATA)
    p.add_argument("--text-dir", default=DEFAULT_TEXT)
    p.add_argument("--sync-dir", default=DEFAULT_SYNC)
    args = p.parse_args(argv)

    db = _db_path(args.data_dir)
    calls_root = os.path.dirname(os.path.normpath(args.data_dir))
    targets = [args.data_dir, args.text_dir, args.sync_dir]

    print("== ЧИСТЫЙ ЛИСТ ==")
    print(f"  БД: {db} | {_count_calls(db)} | "
          f"{_mb(os.path.getsize(db)) if os.path.isfile(db) else 'нет файла'}")
    print(f"  СНОСИМ (ВСЕ файлы рекурсивно в {calls_root}, кроме защищённого):")
    files, size = _dir_stats(calls_root)
    print(f"    {calls_root} | файлов: {files} | {_mb(size)}")
    print(f"  ЗАЩИЩЕНО (НЕ трогаем): {', '.join(sorted(PROTECTED))}")

    # Guard: корневая папка не должна быть защищённой.
    if _overlaps_protected(calls_root):
        print(f"[СТОП] корневая папка {calls_root} совпадает с защищённой!")
        return 2

    if not args.apply:
        print("\n  Это DRY-RUN. Ничего не снесено.")
        print("  Реальный чистый лист: reset.bat --apply")
        return 0

    # 1) Бэкап БД ВНЕ data_dir (иначе снесётся вместе с data).
    if os.path.isfile(db) and not args.no_backup:
        backup_root = os.path.dirname(os.path.normpath(args.data_dir)) or "."
        bak = os.path.join(backup_root, f"callprofiler.db.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            shutil.copy2(db, bak)
            print(f"\n[1] Бэкап БД → {bak}")
        except OSError as exc:
            print(f"\n[1] [!] не удалось бэкапить БД ({exc}) — продолжаю без бэкапа")
    elif args.no_backup:
        print("\n[1] --no-backup: бэкап БД пропущен")
    else:
        print("\n[1] БД не было — бэкап не нужен")

    # 2) Снести ВСЕ файлы в C:\calls рекурсивно, кроме PROTECTED (in/, source/).
    calls_root = os.path.dirname(os.path.normpath(args.data_dir))
    print(f"[2] Удаляю файлы в {calls_root} (кроме {', '.join(sorted(PROTECTED))})...")
    removed = _walk_and_remove(calls_root, PROTECTED)
    print(f"    Удалено файлов: {removed}")

    # 3) Пересоздать пустую БД + папки + юзера me (bootstrap, дефолты:
    #    user=me, incoming=C:\calls\in, sync=C:\calls\sync).
    print("[3] bootstrap (пустая БД + папки + юзер me, incoming=C:\\calls\\in)...")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
    rc = subprocess.run(
        [sys.executable, "-m", "callprofiler", "bootstrap"], env=env
    ).returncode
    if rc != 0:
        print(f"[ОШИБКА] bootstrap вернул {rc}. Запусти вручную: python -m callprofiler bootstrap")
        return rc

    print("\n[OK] Чистый лист готов. ВСЕ файлы в C:\\calls удалены (кроме in/source),")
    print("     БД пересоздана, юзер 'me' готов к работе.")
    print("     Запусти startprocess.bat — обработка пойдёт заново на файлах из C:\\calls\\in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
