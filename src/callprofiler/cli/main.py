# -*- coding: utf-8 -*-
"""
main.py — точка входа CLI для CallProfiler.

Использование:
  python -m callprofiler watch                    # watchdog + обработка
  python -m callprofiler process <file> --user ID # обработать один файл
  python -m callprofiler reprocess                # повторить ошибки
  python -m callprofiler add-user ID ...          # добавить пользователя
  python -m callprofiler digest <user> [--days N] # дайджест звонков
  python -m callprofiler status                   # состояние очереди
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _setup_logging(log_file: str | None = None, verbose: bool = False) -> None:
    """Настроить логирование: консоль + опционально файл."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(level=level, format=fmt, handlers=handlers)


def _load_config_and_repo(config_path: str):
    """Загрузить конфиг и инициализировать репозиторий."""
    from callprofiler.config import load_config
    from callprofiler.db.repository import Repository

    cfg = load_config(config_path)

    db_path = Path(cfg.data_dir) / "db" / "callprofiler.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    repo = Repository(str(db_path))
    repo.init_db()

    return cfg, repo


# ── Команды ────────────────────────────────────────────────────────────────


def cmd_watch(args: argparse.Namespace) -> int:
    """watch — запустить watchdog-цикл мониторинга папок."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    from callprofiler.ingest.ingester import Ingester
    from callprofiler.pipeline.orchestrator import Orchestrator
    from callprofiler.pipeline.watcher import FileWatcher

    ingester = Ingester(repo, cfg)
    orchestrator = Orchestrator(cfg, repo)
    watcher = FileWatcher(cfg, repo, ingester, orchestrator)

    logging.getLogger(__name__).info("Запуск watchdog-режима...")
    watcher.run_loop()
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    """process <file> --user ID — обработать один файл."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    # Проверить файл
    filepath = Path(args.file)
    if not filepath.exists():
        log.error("Файл не найден: %s", filepath)
        return 1

    # Проверить пользователя
    user = repo.get_user(args.user)
    if not user:
        log.error(
            "Пользователь '%s' не найден. Сначала добавьте его: add-user",
            args.user,
        )
        return 1

    from callprofiler.ingest.ingester import Ingester
    from callprofiler.pipeline.orchestrator import Orchestrator

    ingester = Ingester(repo, cfg)
    orchestrator = Orchestrator(cfg, repo)

    # Зарегистрировать файл
    call_id = ingester.ingest_file(args.user, str(filepath))
    if call_id is None:
        log.info("Файл уже был обработан ранее (дубликат): %s", filepath)
        return 0

    log.info("Зарегистрирован call_id=%d, запуск обработки...", call_id)

    # Обработать
    success = orchestrator.process_call(call_id)
    if success:
        log.info("✓ Файл обработан: %s", filepath)
        return 0
    else:
        log.error("✗ Ошибка при обработке: %s", filepath)
        return 1


def cmd_reprocess(args: argparse.Namespace) -> int:
    """reprocess — повторить звонки с ошибками."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    errors = repo.get_error_calls(cfg.pipeline.max_retries)
    if not errors:
        log.info("Нет звонков для повторной обработки")
        return 0

    log.info("Повтор %d звонков с ошибками...", len(errors))

    from callprofiler.pipeline.orchestrator import Orchestrator

    orchestrator = Orchestrator(cfg, repo)
    orchestrator.retry_errors()
    return 0


def cmd_add_user(args: argparse.Namespace) -> int:
    """add-user ID ... — добавить нового пользователя."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    # Проверить что пользователь не существует
    existing = repo.get_user(args.user_id)
    if existing:
        log.error("Пользователь '%s' уже существует", args.user_id)
        return 1

    # Проверить пути
    incoming = Path(args.incoming)
    if not incoming.exists():
        log.warning(
            "incoming_dir не существует (будет создан): %s", incoming
        )
        incoming.mkdir(parents=True, exist_ok=True)

    sync = Path(args.sync_dir)
    if not sync.exists():
        sync.mkdir(parents=True, exist_ok=True)

    repo.add_user(
        user_id=args.user_id,
        display_name=args.display_name or args.user_id,
        telegram_chat_id=args.telegram_chat_id,
        incoming_dir=str(args.incoming),
        sync_dir=str(args.sync_dir),
        ref_audio=str(args.ref_audio),
    )

    log.info(
        "✓ Пользователь '%s' добавлен\n"
        "  display_name : %s\n"
        "  incoming_dir : %s\n"
        "  sync_dir     : %s\n"
        "  ref_audio    : %s\n"
        "  telegram     : %s",
        args.user_id,
        args.display_name or args.user_id,
        args.incoming,
        args.sync_dir,
        args.ref_audio,
        args.telegram_chat_id or "(не задан)",
    )
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    """digest <user> [--days N] — показать дайджест звонков."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(None, args.verbose)  # digest выводит в консоль без лог-файла

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(days=args.days)).isoformat()

    calls = repo.get_calls_for_user(args.user_id, limit=50)
    if not calls:
        print(f"Нет звонков для пользователя '{args.user_id}'")
        return 0

    # Фильтр по дате и получить анализы
    results = []
    for call in calls:
        if call.get("created_at", "") < cutoff:
            continue
        analysis = repo.get_analysis(call["call_id"])
        priority = analysis.get("priority", 0) if analysis else 0
        results.append((priority, call, analysis))

    if not results:
        print(f"Нет звонков за последние {args.days} дней")
        return 0

    # Сортировка по priority убыванию
    results.sort(key=lambda x: x[0], reverse=True)

    print(f"\n📊 Дайджест '{args.user_id}' за {args.days} дней ({len(results)} звонков)\n")
    print("─" * 60)

    for priority, call, analysis in results[:10]:
        contact_id = call.get("contact_id")
        contact = repo.get_contact(contact_id) if contact_id else None
        name = contact.get("display_name", "?") if contact else "?"
        phone = contact.get("phone_e164", "?") if contact else "?"
        direction = call.get("direction", "?")
        created = (call.get("created_at") or "")[:16]

        print(f"[P:{priority:3d}] {name} ({phone}) | {direction} | {created}")
        if analysis:
            risk = analysis.get("risk_score", 0)
            summary = (analysis.get("summary") or "")[:100]
            print(f"       Risk:{risk} | {summary}")
        print()

    return 0


def cmd_extract_names(args: argparse.Namespace) -> int:
    """extract-names --user ID [--dry-run] — угадать имена контактов из транскриптов."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(None, args.verbose)

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
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    # Проверить пользователя
    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    # Проверить папку
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
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    # Проверить пользователя
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


def cmd_status(args: argparse.Namespace) -> int:
    """status — показать состояние очереди."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(None, args.verbose)

    pending = repo.get_pending_calls()
    errors = repo.get_error_calls(cfg.pipeline.max_retries)
    users = repo.get_all_users()

    # Все звонки по статусу
    conn = repo._get_conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM calls GROUP BY status ORDER BY cnt DESC"
    ).fetchall()

    print("\n⚙️  CallProfiler — статус очереди\n")
    print(f"  Пользователей : {len(users)}")
    print()

    if rows:
        print("  Статусы звонков:")
        for row in rows:
            print(f"    {row['status']:15s} : {row['cnt']}")
    else:
        print("  Звонков нет")

    print()
    print(f"  Новых (ожидают) : {len(pending)}")
    print(f"  Ошибок (retry)  : {len(errors)}")

    if pending:
        print("\n  ⏳ Ожидают обработки:")
        for call in pending[:5]:
            contact = repo.get_contact(call.get("contact_id")) if call.get("contact_id") else None
            name = contact.get("display_name", "?") if contact else "?"
            print(f"    call_id={call['call_id']} | {name} | user={call['user_id']}")

    if errors:
        print("\n  ❌ С ошибками:")
        for call in errors[:5]:
            retry = call.get("retry_count", 0)
            err = (call.get("error_message") or "")[:60]
            print(f"    call_id={call['call_id']} | попытка {retry} | {err}")

    print()
    return 0


# ── Построение парсера ────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    """Построить argparse парсер со всеми подкомандами."""
    parser = argparse.ArgumentParser(
        prog="callprofiler",
        description="CallProfiler — локальная система анализа телефонных звонков",
    )
    parser.add_argument(
        "--config",
        default="configs/base.yaml",
        help="Путь к конфигурационному файлу (по умолчанию: configs/base.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Подробное логирование (DEBUG)",
    )

    sub = parser.add_subparsers(dest="command", metavar="КОМАНДА")
    sub.required = True

    # ── watch ────────────────────────────────────────────────
    sub.add_parser(
        "watch",
        help="Запустить watchdog: мониторинг папок + автообработка",
    )

    # ── process ──────────────────────────────────────────────
    p_process = sub.add_parser(
        "process",
        help="Обработать один аудиофайл",
    )
    p_process.add_argument("file", help="Путь к аудиофайлу")
    p_process.add_argument(
        "--user", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── reprocess ────────────────────────────────────────────
    sub.add_parser(
        "reprocess",
        help="Повторить звонки с ошибками (retry_count < max_retries)",
    )

    # ── add-user ─────────────────────────────────────────────
    p_add = sub.add_parser(
        "add-user",
        help="Добавить нового пользователя",
    )
    p_add.add_argument("user_id", help="Уникальный ID пользователя (латиница)")
    p_add.add_argument("--display-name", help="Отображаемое имя")
    p_add.add_argument(
        "--incoming", required=True, metavar="DIR",
        help="Папка для входящих аудиофайлов",
    )
    p_add.add_argument(
        "--ref-audio", required=True, metavar="FILE",
        help="Эталонная запись голоса (.wav) для диаризации",
    )
    p_add.add_argument(
        "--sync-dir", required=True, metavar="DIR",
        help="Папка для caller cards (FolderSync → телефон)",
    )
    p_add.add_argument(
        "--telegram-chat-id", metavar="ID",
        help="Telegram chat_id для уведомлений",
    )

    # ── digest ───────────────────────────────────────────────
    p_digest = sub.add_parser(
        "digest",
        help="Показать дайджест звонков по priority",
    )
    p_digest.add_argument("user_id", help="Идентификатор пользователя")
    p_digest.add_argument(
        "--days", type=int, default=7,
        help="Период дайджеста в днях (по умолчанию: 7)",
    )

    # ── status ───────────────────────────────────────────────
    sub.add_parser(
        "status",
        help="Показать состояние очереди обработки",
    )

    # ── extract-names ─────────────────────────────────────────
    p_extract = sub.add_parser(
        "extract-names",
        help="Угадать имена собеседников из транскриптов (для контактов без display_name)",
    )
    p_extract.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_extract.add_argument(
        "--dry-run", action="store_true",
        help="Показать результат без записи в БД",
    )

    # ── bulk-load ──────────────────────────────────────────────
    p_bulk = sub.add_parser(
        "bulk-load",
        help="Массовая загрузка .txt транскриптов в БД",
    )
    p_bulk.add_argument(
        "folder", help="Папка с .txt файлами транскриптов",
    )
    p_bulk.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── bulk-enrich ────────────────────────────────────────────
    p_enrich = sub.add_parser(
        "bulk-enrich",
        help="LLM-анализ для всех звонков без анализа",
    )
    p_enrich.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_enrich.add_argument(
        "--limit", type=int, default=0, metavar="N",
        help="Максимум файлов для обработки (0 = все)",
    )

    return parser


def main() -> None:
    """Главная функция CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    dispatch = {
        "watch": cmd_watch,
        "process": cmd_process,
        "reprocess": cmd_reprocess,
        "add-user": cmd_add_user,
        "digest": cmd_digest,
        "status": cmd_status,
        "extract-names": cmd_extract_names,
        "bulk-load": cmd_bulk_load,
        "bulk-enrich": cmd_bulk_enrich,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        exit_code = handler(args)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        sys.exit(0)
    except Exception as exc:
        logging.getLogger(__name__).error("Неожиданная ошибка: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
