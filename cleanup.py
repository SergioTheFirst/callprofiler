# -*- coding: utf-8 -*-
"""
cleanup.py — безопасная чистка БД (запускается на рабочей машине, как diag.py).

ДВА режима. Оба по умолчанию DRY-RUN: печатают, что будет удалено, и НИЧЕГО не
трогают. Реальное удаление — только с флагом --apply.

  # 1) Снести мёртвые error-звонки (оригинал аудио отсутствует на диске):
  python cleanup.py prune-missing --user me            # dry-run (показать план)
  python cleanup.py prune-missing --user me --apply     # удалить

  # 2) Полностью снести юзера и все его данные:
  python cleanup.py purge-user --user serhio            # dry-run (показать план)
  python cleanup.py purge-user --user serhio --apply     # удалить

Опции:
  --db PATH   путь к БД (по умолчанию C:\\calls\\data\\db\\callprofiler.db)

Удаление идёт в одной транзакции и FTS-safe (поисковый индекс остаётся целым).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_DB = r"C:\calls\data\db\callprofiler.db"
_ALL_RETRIES = 10**9  # get_error_calls(max_retries) — взять ВСЕ error, без фильтра retry


def _repo(db_path: str):
    from callprofiler.db.repository import Repository

    if not os.path.isfile(db_path):
        print(f"[ОШИБКА] БД не найдена: {db_path}")
        print("        Укажите путь через --db <path>.")
        sys.exit(2)
    repo = Repository(db_path)
    repo.init_db()  # идемпотентно (CREATE IF NOT EXISTS) — схема гарантирована
    return repo


def _print_counts(counts: dict) -> int:
    total = 0
    for tbl, n in counts.items():
        if n:
            print(f"    {tbl:18}: {n}")
            total += n
    if total == 0:
        print("    (нечего удалять)")
    return total


def cmd_prune_missing(args) -> int:
    """Удалить error-звонки, чей ИСХОДНЫЙ аудиофайл отсутствует на диске."""
    repo = _repo(args.db)
    errors = repo.get_error_calls(_ALL_RETRIES, args.user)
    print(f"== prune-missing (user={args.user or 'ВСЕ'}) ==")
    print(f"  error-звонков всего: {len(errors)}")

    orphan_ids, present = [], 0
    for c in errors:
        audio = (c.get("audio_path") or "").strip()
        if audio and os.path.isfile(audio):
            present += 1  # исходник на месте — возможно, чинимо; НЕ трогаем
        else:
            orphan_ids.append(c["call_id"])

    print(f"  исходник на месте (пропускаем): {present}")
    print(f"  исходник ОТСУТСТВУЕТ (кандидаты на удаление): {len(orphan_ids)}")
    if not orphan_ids:
        print("  Нечего делать.")
        return 0

    for c in errors[:8]:
        if c["call_id"] in orphan_ids:
            print(f"    пример call_id={c['call_id']}: {c.get('source_filename')}")

    counts = repo.delete_calls(orphan_ids, apply=args.apply)
    print("  " + ("УДАЛЕНО:" if args.apply else "БУДЕТ удалено (dry-run):"))
    _print_counts(counts)
    if not args.apply:
        print("  → Повторите с --apply, чтобы удалить.")
    return 0


def cmd_purge_user(args) -> int:
    """Полностью удалить юзера и все его данные."""
    if not args.user:
        print("[ОШИБКА] purge-user требует --user <id>.")
        return 2
    repo = _repo(args.db)
    user = repo.get_user(args.user)
    print(f"== purge-user (user={args.user}) ==")
    if not user:
        print(f"  Юзер '{args.user}' не найден — нечего удалять.")
        return 0
    print(f"  display_name: {user.get('display_name')}  incoming: {user.get('incoming_dir')}")

    counts = repo.purge_user(args.user, apply=args.apply)
    print("  " + ("УДАЛЕНО:" if args.apply else "БУДЕТ удалено (dry-run):"))
    total = _print_counts(counts)
    if not args.apply and total:
        print(f"  → Повторите с --apply, чтобы НЕОБРАТИМО снести юзера '{args.user}'.")
    return 0


def main(argv=None) -> int:
    # Общие опции (--db/--apply принимаются ПОСЛЕ подкоманды через parents=)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=DEFAULT_DB, help=f"путь к БД (default: {DEFAULT_DB})")
    common.add_argument("--apply", action="store_true", help="реально удалить (иначе dry-run)")

    p = argparse.ArgumentParser(description="Безопасная чистка БД CallProfiler (dry-run по умолчанию).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("prune-missing", parents=[common], help="снести error-звонки без исходного аудио")
    pm.add_argument("--user", default=None, help="user_id (если опущен — все юзеры)")
    pm.set_defaults(func=cmd_prune_missing)

    pu = sub.add_parser("purge-user", parents=[common], help="полностью снести юзера и все его данные")
    pu.add_argument("--user", required=True, help="user_id для удаления")
    pu.set_defaults(func=cmd_purge_user)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
