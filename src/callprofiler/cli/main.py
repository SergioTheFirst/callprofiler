# -*- coding: utf-8 -*-
"""
main.py — точка входа CLI для CallProfiler.

Использование:
  python -m callprofiler watch                         # watchdog + обработка
  python -m callprofiler process <file> --user ID      # обработать один файл
  python -m callprofiler reprocess                     # повторить ошибки
  python -m callprofiler add-user ID ...               # добавить пользователя
  python -m callprofiler digest <user> [--days N]      # дайджест звонков
  python -m callprofiler search <query> --user ID      # FTS5 поиск
  python -m callprofiler promises --user ID            # показать открытые promises
  python -m callprofiler inspect-schema                # вывести схему БД
  python -m callprofiler analytics --user ID           # статистика
  python -m callprofiler status                        # состояние очереди
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


def cmd_rebuild_summaries(args: argparse.Namespace) -> int:
    """rebuild-summaries --user ID — пересчитать contact_summaries."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    from callprofiler.aggregate.summary_builder import SummaryBuilder

    log.info("Пересчет contact_summaries для пользователя '%s'...", args.user_id)

    builder = SummaryBuilder(repo)
    builder.rebuild_all(args.user_id)

    log.info("✓ Contact_summaries пересчитаны для пользователя '%s'", args.user_id)
    return 0


def cmd_rebuild_cards(args: argparse.Namespace) -> int:
    """rebuild-cards --user ID — пересоздать caller cards."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    from callprofiler.aggregate.summary_builder import SummaryBuilder
    from callprofiler.deliver.card_generator import CardGenerator

    log.info("Пересчёт summaries + запись карточек для '%s'...", args.user_id)

    SummaryBuilder(repo).rebuild_all(args.user_id)
    CardGenerator(repo).update_all_cards(args.user_id)

    log.info("✓ Caller cards обновлены для пользователя '%s'", args.user_id)
    return 0


def cmd_backfill_calltypes(args: argparse.Namespace) -> int:
    """backfill-calltypes --user ID — заполнить call_type из raw_response."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    import json as _json

    conn = repo._get_conn()

    # Получить анализы с call_type='unknown' для пользователя
    analyses = conn.execute(
        """
        SELECT a.analysis_id, a.raw_response
        FROM analyses a
        JOIN calls c ON a.call_id = c.call_id
        WHERE c.user_id = ? AND (a.call_type IS NULL OR a.call_type = 'unknown')
        """,
        (args.user_id,),
    ).fetchall()

    if not analyses:
        log.info("Нет анализов с call_type='unknown' для '%s'", args.user_id)
        return 0

    log.info("Обработка %d анализов...", len(analyses))

    _VALID_CALL_TYPES = {"business", "smalltalk", "short", "spam", "personal", "unknown"}
    updated = 0
    skipped = 0

    for analysis_id, raw_response in analyses:
        if not raw_response:
            skipped += 1
            continue
        try:
            parsed = _json.loads(raw_response)
        except (_json.JSONDecodeError, ValueError):
            skipped += 1
            continue

        call_type = str(parsed.get("call_type", "unknown")).lower()
        if call_type not in _VALID_CALL_TYPES:
            call_type = "unknown"

        if call_type != "unknown":
            conn.execute(
                "UPDATE analyses SET call_type = ? WHERE analysis_id = ?",
                (call_type, analysis_id),
            )
            updated += 1
        else:
            skipped += 1

    conn.commit()
    log.info("✓ Обновлено: %d, пропущено: %d", updated, skipped)
    return 0


def _get_best_contact_name(contact: dict | None) -> str:
    """Выбрать лучшее имя контакта: display_name → guessed_name → phone_e164."""
    if not contact:
        return "?"
    name = contact.get("display_name") or ""
    if name:
        return name
    name = contact.get("guessed_name") or ""
    if name:
        return name
    phone = contact.get("phone_e164") or ""
    return phone or "?"


def _translate_who(who: str, contact_name: str | None = None) -> str:
    """Перевести who в человеческий формат.

    Маппинг:
    - "Me" → "Я обещал"
    - "S2" → "{contact_name} обещал" или "Мне обещали"
    - "OWNER" → "Я (Сергей)"
    - "OTHER" → contact_name или "Собеседник"
    """
    if who in ("Me", "OWNER"):
        return "Я (Сергей)"
    elif who in ("S2", "OTHER"):
        return contact_name or "Собеседник"
    else:
        return who


def cmd_search(args: argparse.Namespace) -> int:
    """search <query> --user <user_id> — FTS5 поиск по транскриптам."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(None, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    results = repo.search_transcripts(args.user_id, args.query)
    if not results:
        print(f"\nПо запросу '{args.query}' ничего не найдено")
        return 0

    # Показать до 10 результатов
    print(f"\n🔍 Результаты поиска по запросу '{args.query}' ({len(results)} найдено)\n")
    print("─" * 80)

    for i, result in enumerate(results[:10], 1):
        call_id = result.get("call_id")
        call = repo._get_conn().execute(
            "SELECT call_id, contact_id, created_at, call_datetime FROM calls WHERE call_id = ?",
            (call_id,)
        ).fetchone()

        if not call:
            continue

        contact_id = call["contact_id"]
        contact = repo.get_contact(contact_id) if contact_id else None
        name = _get_best_contact_name(contact)
        phone = contact.get("phone_e164", "?") if contact else "?"
        call_date = (call.get("call_datetime") or "")[:16]

        text = (result.get("text") or "")[:120]

        print(f"{i}. [{call_date}] {name} ({phone}) [call_id={call_id}]")
        print(f"   {text}")
        print()

    return 0


def cmd_promises(args: argparse.Namespace) -> int:
    """promises --user <user_id> — показать открытые promises, сгруппированные по контакту."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(None, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    promises = repo.get_open_promises(args.user_id)
    if not promises:
        print(f"\nНет открытых promises для пользователя '{args.user_id}'")
        return 0

    # Сгруппировать по контакту
    by_contact = {}
    for promise in promises:
        contact_id = promise.get("contact_id")
        if contact_id not in by_contact:
            by_contact[contact_id] = []
        by_contact[contact_id].append(promise)

    print(f"\n📋 Открытые promises для '{args.user_id}'\n")
    print("─" * 80)

    total = 0
    for contact_id in sorted(by_contact.keys()):
        contact = repo.get_contact(contact_id) if contact_id else None
        contact_name = _get_best_contact_name(contact)
        phone = contact.get("phone_e164", "?") if contact else "?"

        print(f"\n📞 {contact_name} ({phone})")

        for promise in by_contact[contact_id]:
            who_raw = promise.get("who", "?")
            what = promise.get("what", "?")
            due = promise.get("due", "")
            status = promise.get("status", "open")
            call_datetime = promise.get("call_datetime", "")

            # Перевести who в человеческий формат
            who_translated = _translate_who(who_raw, contact_name)

            due_str = f" | due: {due}" if due else " | без срока"
            call_date_str = f" | из звонка: {call_datetime[:10]}" if call_datetime else ""
            status_emoji = "✓" if status == "closed" else "⏳"

            print(f"  {status_emoji} {who_translated}: {what}{due_str}{call_date_str}")
            total += 1

    print(f"\n─" * 80)
    print(f"Всего: {total} promise(s)")
    return 0


def cmd_inspect_schema(args: argparse.Namespace) -> int:
    """inspect-schema — вывести реальную схему всех таблиц."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(None, args.verbose)

    conn = repo._get_conn()
    cursor = conn.cursor()

    # Получить список всех таблиц (исключая FTS5 служебные)
    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()

    print("\n📋 CallProfiler SQLite Schema\n")
    print("=" * 100)

    for (table_name,) in tables:
        print(f"\n🔷 TABLE: {table_name}\n")

        info = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
        if not info:
            print("  (нет колонок)")
            continue

        # Заголовок
        print(f"  {'Column':<20} {'Type':<15} {'Nullable':<10} {'Default':<15}")
        print("  " + "─" * 75)

        for row in info:
            cid, name, typ, notnull, dflt_value, pk = row
            nullable = "NOT NULL" if notnull else "NULL"
            default = dflt_value or ""
            pk_mark = f" [PK]" if pk else ""

            print(f"  {name:<20} {typ:<15} {nullable:<10} {default:<15}{pk_mark}")

        # Индексы
        indices = cursor.execute(
            f"PRAGMA index_list({table_name})"
        ).fetchall()
        if indices:
            print(f"\n  Indices:")
            for idx_row in indices:
                seq, name, unique, origin, partial = idx_row
                unique_mark = " [UNIQUE]" if unique else ""
                print(f"    • {name}{unique_mark}")

    # Виртуальные таблицы (FTS5)
    virtual = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%VIRTUAL%' ORDER BY name"
    ).fetchall()

    if virtual:
        print(f"\n\n🔶 VIRTUAL TABLES (FTS5)\n")
        print("=" * 100)
        for (table_name,) in virtual:
            print(f"\n📌 {table_name}")

    print("\n" + "=" * 100 + "\n")
    return 0


def cmd_backfill_events(args: argparse.Namespace) -> int:
    """backfill-events --user <user_id> — заполнить пропущенные события из анализов."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    conn = repo._get_conn()

    # Получить все анализы для пользователя
    analyses = conn.execute(
        """
        SELECT a.analysis_id, a.call_id, a.raw_response, c.contact_id
        FROM analyses a
        JOIN calls c ON a.call_id = c.call_id
        WHERE c.user_id = ?
        """,
        (args.user_id,)
    ).fetchall()

    if not analyses:
        log.info("Нет анализов для пользователя '%s'", args.user_id)
        return 0

    log.info("Обработка %d анализов...", len(analyses))

    processed = 0
    failed = 0

    for analysis_id, call_id, raw_response, contact_id in analyses:
        try:
            if not raw_response:
                log.debug("  [skip] call_id=%d: raw_response пусто", call_id)
                continue

            import json
            try:
                parsed = json.loads(raw_response)
            except (json.JSONDecodeError, ValueError):
                log.warning("  [fail] call_id=%d: raw_response не JSON", call_id)
                failed += 1
                continue

            events = []

            # Promises → 'promise' events
            promises = parsed.get("promises", [])
            if promises and isinstance(promises, list):
                for p in promises:
                    if isinstance(p, dict):
                        try:
                            who_raw = p.get("who", "UNKNOWN")
                            who_mapped = "OWNER" if who_raw == "Me" else (
                                "OTHER" if who_raw == "S2" else "UNKNOWN"
                            )
                            events.append({
                                "user_id": args.user_id,
                                "contact_id": contact_id,
                                "call_id": call_id,
                                "event_type": "promise",
                                "who": who_mapped,
                                "payload": p.get("what", ""),
                                "deadline": p.get("due"),
                                "confidence": 0.9,
                                "status": "open",
                            })
                        except Exception as e:
                            log.debug("  [skip] promise extraction error: %s", e)

            # Action items → 'task' events
            action_items = parsed.get("action_items", [])
            if action_items and isinstance(action_items, list):
                for item in action_items:
                    if isinstance(item, str):
                        try:
                            events.append({
                                "user_id": args.user_id,
                                "contact_id": contact_id,
                                "call_id": call_id,
                                "event_type": "task",
                                "who": "OWNER",
                                "payload": item,
                                "confidence": 0.85,
                                "status": "open",
                            })
                        except Exception as e:
                            log.debug("  [skip] action_item error: %s", e)

            # bs_evidence → 'contradiction' events
            bs_evidence = parsed.get("bs_evidence", [])
            if bs_evidence and isinstance(bs_evidence, list):
                for evidence in bs_evidence:
                    if isinstance(evidence, str) and len(evidence) > 0:
                        try:
                            events.append({
                                "user_id": args.user_id,
                                "contact_id": contact_id,
                                "call_id": call_id,
                                "event_type": "contradiction",
                                "who": "UNKNOWN",
                                "payload": evidence,
                                "source_quote": evidence[:100],
                                "confidence": 0.8,
                                "status": "open",
                            })
                        except Exception as e:
                            log.debug("  [skip] bs_evidence error: %s", e)

            # amounts → 'debt' events
            amounts = parsed.get("amounts", [])
            if amounts and isinstance(amounts, list):
                for amount in amounts:
                    if isinstance(amount, str) and len(amount) > 0:
                        try:
                            events.append({
                                "user_id": args.user_id,
                                "contact_id": contact_id,
                                "call_id": call_id,
                                "event_type": "debt",
                                "who": "UNKNOWN",
                                "payload": f"Сумма упомянута: {amount}",
                                "source_quote": amount[:100],
                                "confidence": 0.75,
                                "status": "open",
                            })
                        except Exception as e:
                            log.debug("  [skip] amount error: %s", e)

            # Сохранить события
            if events:
                try:
                    repo.save_events(call_id, events)
                    log.info("  [✓] call_id=%d: сохранено %d событий", call_id, len(events))
                    processed += 1
                except Exception as e:
                    log.error("  [✗] call_id=%d: ошибка сохранения: %s", call_id, e)
                    failed += 1
            else:
                log.debug("  [skip] call_id=%d: нет событий для сохранения", call_id)

        except Exception as e:
            log.error("  [✗] call_id=%d: неожиданная ошибка: %s", call_id, e)
            failed += 1

    log.info(
        "✅ Backfill завершён: %d успешных, %d ошибок из %d анализов",
        processed, failed, len(analyses)
    )
    return 0 if failed == 0 else 1


def cmd_analytics(args: argparse.Namespace) -> int:
    """analytics --user <user_id> — статистика по контактам и звонкам."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(None, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    conn = repo._get_conn()

    # Всего контактов
    total_contacts = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE user_id = ?",
        (args.user_id,)
    ).fetchone()[0]

    # Всего звонков и анализов
    all_calls = conn.execute(
        "SELECT COUNT(*) FROM calls WHERE user_id = ?",
        (args.user_id,)
    ).fetchone()[0]

    analyzed_calls = conn.execute(
        "SELECT COUNT(*) FROM analyses WHERE call_id IN ("
        "  SELECT call_id FROM calls WHERE user_id = ?"
        ")",
        (args.user_id,)
    ).fetchone()[0]

    # События по типам
    events_by_type = conn.execute(
        "SELECT event_type, COUNT(*) FROM events WHERE user_id = ? GROUP BY event_type",
        (args.user_id,)
    ).fetchall()

    # Promises
    open_promises = conn.execute(
        "SELECT COUNT(*) FROM promises WHERE user_id = ? AND status = 'open'",
        (args.user_id,)
    ).fetchone()[0]

    all_promises = conn.execute(
        "SELECT COUNT(*) FROM promises WHERE user_id = ?",
        (args.user_id,)
    ).fetchone()[0]

    # Топ-5 контактов по кол-ву звонков
    top_by_calls = conn.execute(
        """
        SELECT c.contact_id, c.display_name, c.guessed_name, c.phone_e164, COUNT(*) as cnt
        FROM calls ca
        JOIN contacts c ON c.contact_id = ca.contact_id
        WHERE ca.user_id = ?
        GROUP BY c.contact_id
        ORDER BY cnt DESC
        LIMIT 5
        """,
        (args.user_id,)
    ).fetchall()

    # Топ-5 по risk_score (average)
    top_by_risk = conn.execute(
        """
        SELECT c.contact_id, c.display_name, c.guessed_name, c.phone_e164,
               ROUND(AVG(a.risk_score), 1) as avg_risk
        FROM analyses a
        JOIN calls ca ON a.call_id = ca.call_id
        JOIN contacts c ON c.contact_id = ca.contact_id
        WHERE ca.user_id = ?
        GROUP BY c.contact_id
        ORDER BY avg_risk DESC
        LIMIT 5
        """,
        (args.user_id,)
    ).fetchall()

    # Топ-5 по bs_score
    top_by_bs = conn.execute(
        """
        SELECT c.contact_id, c.display_name, c.guessed_name, c.phone_e164,
               ROUND(AVG(CAST(json_extract(a.flags, '$.bs_score') AS REAL)), 1) as avg_bs
        FROM analyses a
        JOIN calls ca ON a.call_id = ca.call_id
        JOIN contacts c ON c.contact_id = ca.contact_id
        WHERE ca.user_id = ? AND json_extract(a.flags, '$.bs_score') IS NOT NULL
        GROUP BY c.contact_id
        ORDER BY avg_bs DESC
        LIMIT 5
        """,
        (args.user_id,)
    ).fetchall()

    # Контакты с guessed_name
    guessed = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE user_id = ? AND guessed_name IS NOT NULL AND guessed_name != ''",
        (args.user_id,)
    ).fetchone()[0]

    def get_contact_name(row):
        """Выбрать best name: display_name → guessed_name → phone_e164."""
        display, guessed, phone = row[1], row[2], row[3]
        if display:
            return display
        if guessed:
            return guessed
        return phone or "?"

    print(f"\n📊 Analytics для пользователя '{args.user_id}'\n")
    print("=" * 70)

    print(f"\n📞 КОНТАКТЫ И ЗВОНКИ")
    print(f"  Всего контактов     : {total_contacts}")
    print(f"  Всего звонков       : {all_calls} (анализ: {analyzed_calls})")
    print(f"  Контакты с guessed  : {guessed} из {total_contacts}")

    print(f"\n📋 СОБЫТИЯ")
    if events_by_type:
        for event_type, count in sorted(events_by_type, key=lambda x: x[1], reverse=True):
            print(f"  {event_type:<15}: {count}")
    else:
        print("  (нет событий)")

    print(f"\n🤝 PROMISES")
    print(f"  Open promises       : {open_promises}")
    print(f"  Всего promises      : {all_promises}")

    print(f"\n🔥 ТОП-5 по КОЛИЧЕСТВУ ЗВОНКОВ")
    for i, row in enumerate(top_by_calls, 1):
        name = get_contact_name(row)
        count = row[4]
        print(f"  {i}. {name:<30} ({count} звонков)")

    print(f"\n⚠️  ТОП-5 по RISK_SCORE")
    for i, row in enumerate(top_by_risk, 1):
        name = get_contact_name(row)
        risk = row[4]
        print(f"  {i}. {name:<30} (avg risk: {risk})")

    print(f"\n🤥 ТОП-5 по BS_SCORE")
    for i, row in enumerate(top_by_bs, 1):
        name = get_contact_name(row)
        bs = row[4]
        print(f"  {i}. {name:<30} (avg bs: {bs})")

    print(f"\n" + "=" * 70 + "\n")
    return 0


def cmd_bot(args: argparse.Namespace) -> int:
    """bot — запустить Telegram-бот (long polling)."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(repo)

    if not notifier.token:
        log.error(
            "TELEGRAM_BOT_TOKEN не установлен. "
            "Установите переменную окружения: export TELEGRAM_BOT_TOKEN=<ваш_токен>"
        )
        return 1

    # Получить список пользователей с chat_id для регистрации
    users = repo.get_all_users()
    registered_users = [u for u in users if u.get("telegram_chat_id")]

    log.info("✓ Telegram-бот инициализирован")
    log.info("  Зарегистрировано пользователей: %d", len(registered_users))

    if len(registered_users) == 0:
        log.warning(
            "⚠️  Нет пользователей с telegram_chat_id. "
            "Добавьте их с помощью: add-user --telegram-chat-id <id>"
        )

    for user in registered_users:
        log.info("  • %s (chat_id=%s)", user.get("user_id"),
                user.get("telegram_chat_id"))

    log.info("Запуск Telegram-бота...")
    notifier.run()

    # Бот работает в фоновом потоке, вводим бесконечный цикл
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Бот остановлен пользователем")
        return 0


# ── biography ──────────────────────────────────────────────────────────────


def cmd_biography_run(args: argparse.Namespace) -> int:
    """biography-run --user ID [--passes ...] — многодневный прогон 8-проходного
    конвейера построения биографии по БД и транскриптам."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    from callprofiler.analyze.llm_client import LLMClient
    from callprofiler.biography.llm_client import ResilientLLMClient
    from callprofiler.biography.orchestrator import Orchestrator
    from callprofiler.biography.repo import BiographyRepo

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    try:
        llm_core = LLMClient(base_url=cfg.models.llm_url, timeout=300)
    except ConnectionError as e:
        log.error("Ошибка подключения к LLM %s: %s", cfg.models.llm_url, e)
        return 1

    bio = BiographyRepo(repo)
    rllm = ResilientLLMClient(
        llm_core, bio,
        model_name=cfg.models.llm_model or "local",
        max_retries=args.max_retries,
    )
    orch = Orchestrator(args.user_id, bio, rllm)

    if args.passes:
        passes = [p.strip() for p in args.passes.split(",") if p.strip()]
        log.info("Запуск проходов: %s", passes)
        result = orch.run_passes(passes)
    else:
        log.info("Запуск всех 8 проходов для пользователя %s", args.user_id)
        result = orch.run_all()

    log.info("Итог: %s", result)
    return 0


def cmd_biography_status(args: argparse.Namespace) -> int:
    """biography-status --user ID — показать состояние всех checkpoint'ов."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    from callprofiler.biography.orchestrator import Orchestrator
    from callprofiler.biography.repo import BiographyRepo

    bio = BiographyRepo(repo)
    # Use a dummy llm since status() only queries checkpoints.
    orch = Orchestrator.__new__(Orchestrator)
    orch.user_id = args.user_id
    orch.bio = bio
    orch.llm = None  # type: ignore[assignment]

    rows = orch.status()
    print(f"{'Pass':<16}{'Status':<12}{'Items':<14}{'Failed':<8}Updated")
    print("-" * 72)
    for r in rows:
        items = f"{r['processed']}/{r['total']}"
        print(
            f"{r['pass']:<16}{r['status']:<12}{items:<14}"
            f"{r['failed']:<8}{r['updated_at'] or ''}"
        )
    return 0


def cmd_biography_export(args: argparse.Namespace) -> int:
    """biography-export --user ID --out FILE — выгрузить последний собранный
    book в markdown-файл."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    from callprofiler.biography.repo import BiographyRepo

    log = logging.getLogger(__name__)
    bio = BiographyRepo(repo)
    book = bio.latest_book(args.user_id)
    if not book:
        log.error("Для пользователя '%s' нет собранного book — "
                  "запустите biography-run", args.user_id)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(book.get("prose_full") or "", encoding="utf-8")
    log.info(
        "Экспорт завершён: %s (title=%r, version=%s, word_count=%s)",
        out_path, book.get("title"), book.get("version_label"),
        book.get("word_count"),
    )
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

    # ── rebuild-summaries ──────────────────────────────────────
    p_rebuild_sum = sub.add_parser(
        "rebuild-summaries",
        help="Пересчитать contact_summaries (взвешенный риск, события, совет)",
    )
    p_rebuild_sum.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── rebuild-cards ──────────────────────────────────────────
    p_rebuild_cards = sub.add_parser(
        "rebuild-cards",
        help="Пересоздать caller cards (≤512 байт) в sync_dir",
    )
    p_rebuild_cards.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── search ────────────────────────────────────────────────────
    p_search = sub.add_parser(
        "search",
        help="FTS5 поиск по транскриптам",
    )
    p_search.add_argument(
        "query", help="Текст для поиска",
    )
    p_search.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── promises ───────────────────────────────────────────────────
    p_promises = sub.add_parser(
        "promises",
        help="Показать открытые promises, сгруппированные по контакту",
    )
    p_promises.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── inspect-schema ─────────────────────────────────────────────
    sub.add_parser(
        "inspect-schema",
        help="Вывести реальную схему всех таблиц БД (PRAGMA table_info)",
    )

    # ── backfill-events ────────────────────────────────────────────
    p_backfill = sub.add_parser(
        "backfill-events",
        help="Заполнить пропущенные события из существующих анализов",
    )
    p_backfill.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── backfill-calltypes ─────────────────────────────────────────
    p_backfill_ct = sub.add_parser(
        "backfill-calltypes",
        help="Заполнить call_type в analyses из raw_response JSON",
    )
    p_backfill_ct.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── analytics ──────────────────────────────────────────────────
    p_analytics = sub.add_parser(
        "analytics",
        help="Аналитика по контактам, звонкам, событиям и promises",
    )
    p_analytics.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── bot ────────────────────────────────────────────────────────
    sub.add_parser(
        "bot",
        help="Запустить Telegram-бот (long polling, requires TELEGRAM_BOT_TOKEN)",
    )

    # ── biography-run ──────────────────────────────────────────────
    p_bio_run = sub.add_parser(
        "biography-run",
        help="Запустить многодневный 8-проходный конвейер построения биографии",
    )
    p_bio_run.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_bio_run.add_argument(
        "--passes", default="", metavar="p1,p2,...",
        help="Список проходов через запятую; пусто = все 8 по порядку "
             "(p1_scene,p2_entities,p3_threads,p4_arcs,"
             "p5_portraits,p6_chapters,p7_book,p8_editorial)",
    )
    p_bio_run.add_argument(
        "--max-retries", type=int, default=5, dest="max_retries",
        help="Максимум попыток LLM-запроса перед отказом (по умолчанию: 5)",
    )

    # ── biography-status ───────────────────────────────────────────
    p_bio_status = sub.add_parser(
        "biography-status",
        help="Состояние checkpoint'ов всех 8 проходов биографии",
    )
    p_bio_status.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── biography-export ───────────────────────────────────────────
    p_bio_export = sub.add_parser(
        "biography-export",
        help="Экспортировать последний собранный book в markdown-файл",
    )
    p_bio_export.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_bio_export.add_argument(
        "--out", required=True, metavar="FILE",
        help="Путь к выходному .md файлу",
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
        "rebuild-summaries": cmd_rebuild_summaries,
        "rebuild-cards": cmd_rebuild_cards,
        "search": cmd_search,
        "promises": cmd_promises,
        "inspect-schema": cmd_inspect_schema,
        "backfill-events": cmd_backfill_events,
        "backfill-calltypes": cmd_backfill_calltypes,
        "analytics": cmd_analytics,
        "bot": cmd_bot,
        "biography-run": cmd_biography_run,
        "biography-status": cmd_biography_status,
        "biography-export": cmd_biography_export,
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
