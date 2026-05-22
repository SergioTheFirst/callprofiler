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
