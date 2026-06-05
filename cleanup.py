# -*- coding: utf-8 -*-
"""
cleanup.py — безопасная чистка БД (запускается на рабочей машине, как diag.py).

ТРИ режима. Все по умолчанию DRY-RUN: печатают, что будет удалено, и НИЧЕГО не
трогают. Реальное удаление — только с флагом --apply.

  # 1) Снести мёртвые error-звонки (оригинал аудио отсутствует на диске):
  python cleanup.py prune-missing --user me            # dry-run (показать план)
  python cleanup.py prune-missing --user me --apply     # удалить

  # 2) Полностью снести ОДНОГО юзера и все его данные:
  python cleanup.py purge-user --user serhio            # dry-run (показать план)
  python cleanup.py purge-user --user serhio --apply     # удалить

  # 3) Оставить ТОЛЬКО одного юзера, снести всех остальных (консолидация профиля):
  python cleanup.py keep-only --user me                 # dry-run (показать план)
  python cleanup.py keep-only --user me --apply          # снести всех, кроме me

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


def cmd_keep_only(args) -> int:
    """Оставить ТОЛЬКО одного юзера (keeper), снести всех остальных.

    Инверсия purge-user: для прогона «все работы в одном профиле». Защита —
    keeper ОБЯЗАН существовать (иначе отказ, чтобы не снести всех)."""
    repo = _repo(args.db)
    keeper = args.user
    print(f"== keep-only (оставить ТОЛЬКО '{keeper}', снести остальных) ==")
    ids = sorted(u["user_id"] for u in repo.get_all_users())
    print(f"  Юзеров в БД: {len(ids)} → {', '.join(ids) or '(нет)'}")

    try:
        result = repo.purge_other_users(keeper, apply=args.apply)
    except ValueError as exc:
        print(f"[СТОП] {exc}")
        print("       Отказ — иначе снёс бы всех. Проверьте --user.")
        return 2

    if not result:
        print(f"  Только '{keeper}' и есть — удалять некого. ✓")
        return 0

    grand: dict[str, int] = {}
    for uid in sorted(result):
        counts = result[uid]
        print(f"\n  [{'УДАЛЁН' if args.apply else 'БУДЕТ удалён (dry-run)'}] {uid}:")
        _print_counts(counts)
        for k, v in counts.items():
            grand[k] = grand.get(k, 0) + v

    print("\n  ── ИТОГО по удаляемым юзерам ──")
    _print_counts(grand)
    print(f"  Удаляемых юзеров: {len(result)} → {', '.join(sorted(result))}")
    if not args.apply:
        print(f"\n  → Повторите с --apply, чтобы НЕОБРАТИМО оставить ТОЛЬКО '{keeper}'.")
    else:
        left = sorted(u["user_id"] for u in repo.get_all_users())
        print(f"\n  [OK] Осталось юзеров: {len(left)} → {', '.join(left)}")
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

    ko = sub.add_parser(
        "keep-only", parents=[common],
        help="снести ВСЕХ юзеров, кроме одного (--user, default me)",
    )
    ko.add_argument(
        "--user", default="me",
        help="user_id, которого ОСТАВИТЬ (все прочие удаляются; default: me)",
    )
    ko.set_defaults(func=cmd_keep_only)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
