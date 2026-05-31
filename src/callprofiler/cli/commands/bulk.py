# -*- coding: utf-8 -*-
"""bulk.py — команды массовых операций: extract-names, bulk-load, bulk-enrich."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from callprofiler.cli.utils import load_config_and_repo, setup_logging


def cmd_extract_names(args: argparse.Namespace) -> int:
    """extract-names --user ID [--dry-run] — угадать имена контактов из транскриптов."""
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(None, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    from callprofiler.bulk.name_extractor import NameExtractor

    extractor = NameExtractor(repo)

    if args.dry_run:
        print(f"\n[dry-run] Угадываем имена для '{args.user_id}'...\n")

    updated = extractor.apply_guesses(args.user_id, dry_run=args.dry_run)

    if args.dry_run:
        print(f"\nБудет обновлено контактов: {updated}")
    else:
        log.info("Обновлено контактов: %d", updated)
        if updated == 0:
            print("Нет контактов для обновления (все уже имеют имя или имена не найдены).")
        else:
            print(f"Угаданы имена для {updated} контакт(ов).")

    return 0


def cmd_bulk_load(args: argparse.Namespace) -> int:
    """bulk-load <folder> --user ID — загрузить .txt транскрипты в БД."""
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    from pathlib import Path
    folder = Path(args.folder)
    if not folder.is_dir():
        log.error("Папка не найдена: %s", args.folder)
        return 1

    from callprofiler.bulk.loader import bulk_load

    db_path = Path(cfg.data_dir) / "db" / "callprofiler.db"

    print(f"\n📂 Загрузка транскриптов из: {args.folder}")
    print(f"👤 Пользователь: {args.user_id}")
    print(f"💾 База данных: {db_path}\n")

    stats = bulk_load(
        txt_folder=args.folder,
        user_id=args.user_id,
        db_path=str(db_path),
    )

    print(
        f"\n✅ Завершено!\n"
        f"  Загружено файлов    : {stats['loaded']}\n"
        f"  Пропущено (дубли)   : {stats['skipped']}\n"
        f"  Ошибки парсинга     : {stats['errors']}\n"
        f"  Уникальных контактов: {stats['unique_contacts']}\n"
    )

    return 0


def cmd_bulk_enrich(args: argparse.Namespace) -> int:
    """bulk-enrich --user ID [--limit N] — LLM анализ для всех звонков без анализа."""
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    from callprofiler.bulk.enricher import bulk_enrich

    db_path = Path(cfg.data_dir) / "db" / "callprofiler.db"

    print(f"\n🤖 LLM-анализ звонков")
    print(f"👤 Пользователь: {args.user_id}")
    print(f"📊 Лимит: {args.limit if args.limit > 0 else 'все файлы'}")
    print(f"💾 База данных: {db_path}\n")

    stats = bulk_enrich(
        user_id=args.user_id,
        db_path=str(db_path),
        config_path=args.config,
        limit=args.limit,
    )

    print(
        f"\n✅ Завершено!\n"
        f"  Обработано файлов: {stats['processed']}\n"
        f"  Ошибок: {stats['failed']}\n"
        f"  Пропущено: {stats['skipped']}\n"
        f"  Всего: {stats['total']}\n"
    )

    return 0


def cmd_audio_migrate(args: argparse.Namespace) -> int:
    """audio-migrate --user ID [--dry-run] [--limit N] — переместить оригиналы в originals/YYYY/MM/."""
    import shutil
    from datetime import datetime as _dt
    from pathlib import Path as _Path

    cfg, repo = load_config_and_repo(args.config)
    setup_logging(cfg.log_file, args.verbose)
    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    conn = repo._get_conn()
    rows = conn.execute(
        """SELECT call_id, audio_path, call_datetime
           FROM calls
           WHERE user_id = ? AND audio_path IS NOT NULL
           ORDER BY call_id""",
        (args.user_id,),
    ).fetchall()

    if args.limit > 0:
        rows = rows[: args.limit]

    moved = skipped = failed = 0

    for row in rows:
        call_id = row["call_id"]
        audio_path = row["audio_path"]
        call_datetime_str = row["call_datetime"]

        src = _Path(audio_path)

        # Обнаружить уже забакетированные пути: originals/YYYY/MM/file
        parts = src.parts
        try:
            orig_idx = next(i for i, p in enumerate(parts) if p == "originals")
        except StopIteration:
            skipped += 1
            continue

        after_orig = parts[orig_idx + 1 :]
        if len(after_orig) >= 2 and after_orig[0].isdigit() and len(after_orig[0]) == 4:
            skipped += 1  # уже в YYYY/MM структуре
            continue

        if not src.exists():
            log.warning("call_id=%d: файл не найден: %s", call_id, audio_path)
            skipped += 1
            continue

        # Определить YYYY/MM из call_datetime
        if not call_datetime_str:
            log.warning("call_id=%d: нет call_datetime, пропуск", call_id)
            skipped += 1
            continue
        try:
            dt = _dt.fromisoformat(call_datetime_str)
        except Exception:
            log.warning("call_id=%d: не удалось парсить call_datetime=%s", call_id, call_datetime_str)
            skipped += 1
            continue

        dest_dir = src.parent / str(dt.year) / f"{dt.month:02d}"
        dest_path = dest_dir / src.name

        if args.dry_run:
            print(f"[dry-run] call_id={call_id}: {src.name} → {dest_dir.relative_to(src.parent.parent.parent)}{_Path('/') / src.name}")
            moved += 1
            continue

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if not dest_path.exists():
                shutil.copy2(str(src), str(dest_path))
            conn.execute(
                "UPDATE calls SET audio_path=?, updated_at=datetime('now') WHERE call_id=?",
                (str(dest_path), call_id),
            )
            conn.commit()
            log.info("call_id=%d: %s → %s", call_id, src.name, dest_path)
            moved += 1
        except Exception as exc:
            log.error("call_id=%d: ошибка миграции: %s", call_id, exc)
            failed += 1

    suffix = " (dry-run)" if args.dry_run else ""
    print(f"audio-migrate{suffix}: перемещено={moved}, пропущено={skipped}, ошибок={failed}")
    return 0 if failed == 0 else 1


def register_subparsers(sub: argparse._SubParsersAction) -> None:
    p_extract = sub.add_parser("extract-names", help="Угадать имена собеседников из транскриптов (для контактов без display_name)")
    p_extract.add_argument("--user", dest="user_id", required=True, metavar="USER_ID", help="Идентификатор пользователя")
    p_extract.add_argument("--dry-run", action="store_true", help="Показать результат без записи в БД")

    p_bulk = sub.add_parser("bulk-load", help="Массовая загрузка .txt транскриптов в БД")
    p_bulk.add_argument("folder", help="Папка с .txt файлами транскриптов")
    p_bulk.add_argument("--user", dest="user_id", required=True, metavar="USER_ID", help="Идентификатор пользователя")

    p_enrich = sub.add_parser("bulk-enrich", help="LLM-анализ для всех звонков без анализа")
    p_enrich.add_argument("--user", dest="user_id", required=True, metavar="USER_ID", help="Идентификатор пользователя")
    p_enrich.add_argument("--limit", type=int, default=0, metavar="N", help="Максимум файлов для обработки (0 = все)")
