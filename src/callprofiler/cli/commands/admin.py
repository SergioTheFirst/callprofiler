# -*- coding: utf-8 -*-
"""
admin.py — административные команды CallProfiler.

Содержит: watch, process, reprocess, add-user, status, dashboard, bot.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from callprofiler.cli.utils import load_config_and_repo, setup_logging


def cmd_watch(args: argparse.Namespace) -> int:
    """watch — запустить watchdog-цикл мониторинга папок."""
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(cfg.log_file, args.verbose)

    from callprofiler.ingest.ingester import Ingester
    from callprofiler.pipeline.orchestrator import Orchestrator
    from callprofiler.pipeline.watcher import FileWatcher

    ingester = Ingester(repo, cfg)
    orchestrator = Orchestrator(cfg, repo)
    watcher = FileWatcher(cfg, repo, ingester, orchestrator)

    log = logging.getLogger(__name__)
    if getattr(args, "once", False):
        log.info("Однократный прогон (--once): scan → обработка → cleanup")
        n = watcher.run_once()
        log.info("Однократный прогон завершён: новых файлов=%d", n)
        return 0

    log.info("Запуск watchdog-режима...")
    watcher.run_loop()
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    """process <file> --user ID — обработать один файл."""
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    filepath = Path(args.file)
    if not filepath.exists():
        log.error("Файл не найден: %s", filepath)
        return 1

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

    call_id = ingester.ingest_file(args.user, str(filepath))
    if call_id is None:
        # Дубликат (MD5 уже в БД). С --force — переобработать существующий звонок.
        if getattr(args, "force", False):
            import hashlib

            h = hashlib.md5()
            with open(filepath, "rb") as fh:
                for chunk in iter(lambda: fh.read(8192), b""):
                    h.update(chunk)
            existing = repo.get_call_by_md5(args.user, h.hexdigest())
            if not existing:
                log.error("Дубликат, но звонок не найден по MD5: %s", filepath)
                return 1
            call_id = existing["call_id"]
            log.info(
                "--force: переобработка call_id=%d (status=%s) — транскрипт заменится",
                call_id, existing.get("status"),
            )
        else:
            log.info(
                "Файл уже обработан (дубликат): %s. Для переобработки: --force",
                filepath,
            )
            return 0
    else:
        log.info("Зарегистрирован call_id=%d, запуск обработки...", call_id)

    success = orchestrator.process_call(call_id)
    if success:
        log.info("✓ Файл обработан: %s", filepath)
        return 0
    else:
        log.error("✗ Ошибка при обработке: %s", filepath)
        return 1


def cmd_reprocess(args: argparse.Namespace) -> int:
    """reprocess — повторить звонки с ошибками."""
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(cfg.log_file, args.verbose)

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
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    existing = repo.get_user(args.user_id)
    if existing:
        log.error("Пользователь '%s' уже существует", args.user_id)
        return 1

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


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """bootstrap — создать папки/БД и завести пользователя по умолчанию.

    Provisioning одной командой для чистой машины:
      1. mkdir data_dir (+ db, logs), incoming, text_export_dir, sync
      2. init БД (схема)
      3. добавить пользователя (если ещё нет)
    """
    import yaml as _yaml

    # 1. data_dir берём из YAML напрямую — до валидации существования в load_config
    with open(args.config, encoding="utf-8") as f:
        raw = _yaml.safe_load(f) or {}

    data_dir = Path(raw.get("data_dir", "C:\\calls\\data"))
    (data_dir / "db").mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)

    incoming = Path(args.incoming)
    incoming.mkdir(parents=True, exist_ok=True)

    text_dir = (raw.get("pipeline") or {}).get("text_export_dir", "")
    if text_dir:
        Path(text_dir).mkdir(parents=True, exist_ok=True)

    sync = Path(args.sync_dir)
    sync.mkdir(parents=True, exist_ok=True)

    # 2. конфиг + репозиторий (создаёт схему БД). Здесь же сработает проверка ffmpeg.
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(cfg.log_file, args.verbose)
    log = logging.getLogger(__name__)

    # 3. пользователь
    if repo.get_user(args.user_id):
        log.info("Пользователь '%s' уже существует — пропуск", args.user_id)
    else:
        repo.add_user(
            user_id=args.user_id,
            display_name=args.display_name or args.user_id,
            telegram_chat_id=args.telegram_chat_id,
            incoming_dir=str(incoming),
            sync_dir=str(sync),
            ref_audio=str(args.ref_audio),
        )
        log.info("✓ Пользователь '%s' создан", args.user_id)

    log.info(
        "Bootstrap готов:\n"
        "  data_dir : %s\n"
        "  incoming : %s\n"
        "  text     : %s\n"
        "  sync     : %s\n"
        "  user     : %s",
        data_dir, incoming, text_dir or "(off)", sync, args.user_id,
    )
    log.info(
        "Дальше: положите аудио в %s и запустите `python -m callprofiler watch`",
        incoming,
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """status — показать состояние очереди."""
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(None, args.verbose)

    pending = repo.get_pending_calls()
    errors = repo.get_error_calls(cfg.pipeline.max_retries)
    users = repo.get_all_users()

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
            contact = repo.get_contact(call["user_id"], call.get("contact_id")) if call.get("contact_id") else None
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


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Start real-time dashboard web server."""
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(cfg.log_file, args.verbose)

    from callprofiler.dashboard import run_dashboard
    run_dashboard(args.user_id, cfg, port=args.port, host=args.host)
    return 0


def cmd_bot(args: argparse.Namespace) -> int:
    """bot — запустить Telegram-бота."""
    cfg, repo = load_config_and_repo(args.config)
    setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    from callprofiler.deliver.telegram_bot import TelegramNotifier

    users = repo.get_all_users()
    if not users:
        log.error("Нет зарегистрированных пользователей")
        return 1

    log.info("Зарегистрированные пользователи:")
    for user in users:
        log.info(
            "  %s → chat_id=%s",
            user["user_id"],
            user.get("telegram_chat_id", "(не задан)"),
        )

    notifier = TelegramNotifier(repo)
    notifier.run()
    return 0


def register_subparsers(sub: argparse._SubParsersAction) -> None:
    """Зарегистрировать админ-подкоманды в парсере."""
    sub.add_parser("watch", help="Запустить watchdog: мониторинг папок + автообработка")

    p_process = sub.add_parser("process", help="Обработать один аудиофайл")
    p_process.add_argument("file", help="Путь к аудиофайлу")
    p_process.add_argument("--user", required=True, metavar="USER_ID", help="Идентификатор пользователя")

    sub.add_parser("reprocess", help="Повторить звонки с ошибками (retry_count < max_retries)")

    p_add = sub.add_parser("add-user", help="Добавить нового пользователя")
    p_add.add_argument("user_id", help="Уникальный ID пользователя (латиница)")
    p_add.add_argument("--display-name", help="Отображаемое имя")
    p_add.add_argument("--incoming", required=True, metavar="DIR", help="Папка для входящих аудиофайлов")
    p_add.add_argument("--ref-audio", required=True, metavar="FILE", help="Эталонная запись голоса (.wav) для диаризации")
    p_add.add_argument("--sync-dir", required=True, metavar="DIR", help="Папка для caller cards (FolderSync → телефон)")
    p_add.add_argument("--telegram-chat-id", metavar="ID", help="Telegram chat_id для уведомлений")

    sub.add_parser("status", help="Показать состояние очереди обработки")

    p_dashboard = sub.add_parser("dashboard", help="Запустить real-time web dashboard для мониторинга pipeline")
    p_dashboard.add_argument("--user", dest="user_id", required=True, metavar="USER_ID", help="Идентификатор пользователя")
    p_dashboard.add_argument("--port", type=int, default=8765, metavar="PORT", help="Порт веб-сервера (по умолчанию: 8765)")
    p_dashboard.add_argument("--host", default="127.0.0.1", metavar="HOST", help="Хост веб-сервера (по умолчанию: 127.0.0.1)")

    sub.add_parser("bot", help="Запустить Telegram-бот (long polling, requires TELEGRAM_BOT_TOKEN)")

