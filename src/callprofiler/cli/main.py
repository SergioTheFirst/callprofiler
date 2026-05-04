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

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
    """biography-run --user ID [--passes ...] — многодневный прогон 9-проходного
    конвейера построения биографии по БД и транскриптам."""
    cfg, repo = _load_config_and_repo(args.config)
    log_file = args.log_file or cfg.log_file
    _setup_logging(log_file, args.verbose)

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
    _setup_logging(None, args.verbose)

    import sqlite3
    import yaml
    from callprofiler.biography.schema import apply_biography_schema

    log = logging.getLogger(__name__)

    try:
        with open(args.config, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        data_dir = raw.get("data_dir", "")
    except Exception as exc:
        log.error("Не удалось прочитать конфиг %s: %s", args.config, exc)
        return 1

    db_path = Path(data_dir) / "db" / "callprofiler.db" if data_dir else Path("db/callprofiler.db")
    if not db_path.exists():
        log.error("БД не найдена: %s", db_path)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    apply_biography_schema(conn)

    import json
    row = conn.execute(
        "SELECT * FROM bio_books WHERE user_id=? AND book_type='main'"
        " ORDER BY generated_at DESC LIMIT 1",
        (args.user_id,),
    ).fetchone()
    conn.close()

    if not row:
        log.error("Для пользователя '%s' нет собранного book — "
                  "запустите biography-run", args.user_id)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(row["prose_full"] or "", encoding="utf-8")
    log.info(
        "Экспорт завершён: %s (title=%r, version=%s, word_count=%s)",
        out_path, row["title"], row["version_label"], row["word_count"],
    )
    return 0


def cmd_graph_backfill(args: argparse.Namespace) -> int:
    """graph-backfill — populate Knowledge Graph from v2 analyses."""
    cfg, repo = _load_config_and_repo(args.config)
    log_file = args.log_file or cfg.log_file
    _setup_logging(log_file, getattr(args, "verbose", False))
    log = logging.getLogger(__name__)

    from callprofiler.graph.auditor import GraphAuditor
    from callprofiler.graph.builder import GraphBuilder
    from callprofiler.graph.calibration import BSCalibrator
    from callprofiler.graph.repository import GraphRepository, apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)
    builder = GraphBuilder(conn)
    grepo = GraphRepository(conn)

    schema_filter = getattr(args, "schema", "v2")
    rows = conn.execute(
        """SELECT a.call_id FROM analyses a
           JOIN calls c ON c.call_id = a.call_id
           WHERE c.user_id = ? AND (a.schema_version = ? OR ? = 'all')
           ORDER BY a.call_id""",
        (args.user_id, schema_filter, schema_filter),
    ).fetchall()

    total = len(rows)
    log.info("[graph-backfill] %d analyses to process (schema=%s)", total, schema_filter)
    ok = fail = skip = 0
    for i, row in enumerate(rows, 1):
        call_id = row[0]
        try:
            transcript_text = None
            try:
                segments = repo.get_transcript(call_id)
                if segments:
                    transcript_text = " ".join(seg.text for seg in segments if seg.text)
            except Exception as exc:
                log.debug("[graph-backfill] call_id=%d transcript unavailable: %s", call_id, exc)

            updated = builder.update_from_call(call_id, transcript_text=transcript_text)
            if updated:
                ok += 1
            else:
                skip += 1
        except Exception as exc:
            log.error("[graph-backfill] call_id=%d failed: %s", call_id, exc)
            fail += 1
        if i % 100 == 0:
            log.info("[graph-backfill] %d/%d  ok=%d skip=%d fail=%d", i, total, ok, skip, fail)

    bstats = builder.get_stats()
    entities_count = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE user_id=? AND archived=0",
        (args.user_id,),
    ).fetchone()[0]
    avg_bs_raw = conn.execute(
        "SELECT AVG(bs_index) FROM entity_metrics WHERE user_id=?",
        (args.user_id,),
    ).fetchone()[0]
    avg_bs_index = round(float(avg_bs_raw), 2) if avg_bs_raw is not None else None

    auditor = GraphAuditor(conn)
    audit_result = auditor.run_checks(args.user_id)
    audit_critical = 1 if audit_result.get("has_critical") else 0
    grepo.save_replay_run(
        user_id=args.user_id,
        calls_processed=ok + skip,
        facts_total=bstats["facts_total"],
        facts_inserted=bstats["facts_inserted"],
        facts_rejected=bstats["facts_rejected"],
        entities_count=entities_count,
        avg_bs_index=avg_bs_index,
        audit_critical=audit_critical,
    )
    calibration = BSCalibrator(grepo).analyze(args.user_id)
    if calibration.get("ok"):
        log.info(
            "[graph-backfill] BS thresholds calibrated on %d entities",
            calibration["entity_count"],
        )
    else:
        log.warning(
            "[graph-backfill] BS thresholds not calibrated: entity_count=%d",
            calibration["entity_count"],
        )

    log.info("[graph-backfill] done: ok=%d skip=%d fail=%d / total=%d", ok, skip, fail, total)
    return 0


def cmd_reenrich_v2(args: argparse.Namespace) -> int:
    """reenrich-v2 — re-run LLM analysis on v1 calls to produce v2 schema_version."""
    cfg, repo = _load_config_and_repo(args.config)
    log_file = args.log_file or cfg.log_file
    _setup_logging(log_file, getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    log.info(
        "[reenrich-v2] Re-enriching v1 analyses for user=%s limit=%s",
        args.user_id, args.limit,
    )
    # Delegate to bulk_enrich — it always uses the current prompt (v2).
    # We filter for calls that have v1 analysis so they get re-processed.
    from callprofiler.bulk.enricher import bulk_enrich

    conn = repo._get_conn()
    # Mark v1 analyses as needing reenrichment by deleting them (idempotent via MD5 dedup).
    limit = args.limit or 0
    rows = conn.execute(
        """SELECT a.call_id FROM analyses a
           JOIN calls c ON c.call_id = a.call_id
           WHERE c.user_id = ? AND (a.schema_version IS NULL OR a.schema_version = 'v1')
           ORDER BY a.call_id LIMIT ?""",
        (args.user_id, limit if limit else -1),
    ).fetchall()

    call_ids = [r[0] for r in rows]
    if not call_ids:
        log.info("[reenrich-v2] No v1 analyses found.")
        return 0

    log.info("[reenrich-v2] Deleting %d v1 analyses to trigger re-enrichment", len(call_ids))
    placeholders = ",".join("?" * len(call_ids))
    conn.execute(f"DELETE FROM analyses WHERE call_id IN ({placeholders})", call_ids)
    conn.commit()

    db_path = str(Path(cfg.data_dir) / "db" / "callprofiler.db")
    stats = bulk_enrich(
        user_id=args.user_id,
        db_path=db_path,
        config_path=args.config,
        limit=limit,
    )
    log.info("[reenrich-v2] bulk_enrich result: %s", stats)
    return 0


def cmd_graph_stats(args: argparse.Namespace) -> int:
    """graph-stats — show Knowledge Graph statistics for a user."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = _load_config_and_repo(args.config)
    log = logging.getLogger(__name__)

    from callprofiler.graph.repository import GraphRepository, apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)
    grepo = GraphRepository(conn)
    stats = grepo.stats(args.user_id)

    print(f"\nKnowledge Graph — user: {args.user_id}")
    print("─" * 40)
    print("Entities:")
    for etype, cnt in sorted(stats["entities"].items()):
        print(f"  {etype:<20} {cnt:>6}")
    if not stats["entities"]:
        print("  (none)")

    print("Relations:")
    for rtype, cnt in sorted(stats["relations"].items()):
        print(f"  {rtype:<20} {cnt:>6}")
    if not stats["relations"]:
        print("  (none)")

    print("Facts (graph-linked events):")
    for ftype, cnt in sorted(stats["facts"].items()):
        print(f"  {ftype:<20} {cnt:>6}")
    if not stats["facts"]:
        print("  (none)")

    print(f"Entities with metrics: {stats['entities_with_metrics']}")
    print()
    return 0


def cmd_graph_replay(args: argparse.Namespace) -> int:
    """graph-replay — rebuild graph layer from v2 analyses."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.graph.repository import GraphRepository, apply_graph_schema
    from callprofiler.graph.replay import GraphReplayer

    conn = repo._get_conn()
    apply_graph_schema(conn)

    graph_repo = GraphRepository(conn)
    replayer = GraphReplayer(repo, graph_repo)

    user_id = args.user
    limit = getattr(args, "limit", None)

    log.info("[graph-replay] starting for user_id=%s, limit=%s", user_id, limit)
    stats = replayer.replay(user_id, limit=limit)

    print("\n=== GRAPH REPLAY STATS ===\n")
    print(f"Calls processed:    {stats['calls_processed']}")
    print(f"Entities:           {stats['entities_count']}")
    print(f"Relations:          {stats['relations_count']}")
    print(f"Facts:              {stats['facts_count']}")
    print(f"Avg BS-index:       {stats['avg_bs_index']}")
    print()

    if stats["warnings"]:
        print("WARNINGS:")
        for w in stats["warnings"]:
            print(f"  ⚠️  {w}")
        return 2 if any("ASSERT FAILED" in w for w in stats["warnings"]) else 1

    return 0


def cmd_entity_merge(args: argparse.Namespace) -> int:
    """entity-merge — merge duplicate entity into canonical."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.graph.repository import apply_graph_schema
    from callprofiler.graph.resolver import EntityResolver

    conn = repo._get_conn()
    apply_graph_schema(conn)
    resolver = EntityResolver(conn)

    loop = getattr(args, "loop", False)
    max_iterations = 50  # safety cap for --loop

    iteration = 0
    while True:
        iteration += 1
        if getattr(args, "dry_run", False):
            preview = resolver.preview_merge(args.canonical_id, args.duplicate_id)
            import json as _json
            print(_json.dumps(preview, ensure_ascii=False, indent=2))
            return 0

        try:
            resolver.execute_merge(
                canonical_id=args.canonical_id,
                duplicate_id=args.duplicate_id,
                signals={"score": getattr(args, "score", 0.0)},
                merged_by="manual",
                reason=getattr(args, "reason", "") or "",
            )
            log.info(
                "[entity-merge] merged %d → %d (iteration %d)",
                args.duplicate_id, args.canonical_id, iteration,
            )
        except Exception as exc:
            log.error("[entity-merge] failed: %s", exc)
            return 1

        if not loop:
            break

        # In --loop mode: find next candidate for the same canonical
        user_row = conn.execute(
            "SELECT user_id, entity_type FROM entities WHERE id=?", (args.canonical_id,)
        ).fetchone()
        if not user_row:
            break
        candidates = resolver.find_candidates(
            user_row[0], user_row[1], min_score=0.65, limit=1
        )
        candidates = [c for c in candidates if c.canonical_id == args.canonical_id]
        if not candidates:
            log.info("[entity-merge] no more candidates for canonical_id=%d", args.canonical_id)
            break
        if iteration >= max_iterations:
            log.warning("[entity-merge] loop safety cap reached (%d)", max_iterations)
            break
        args.duplicate_id = candidates[0].duplicate_id
        log.info(
            "[entity-merge] loop: next candidate duplicate_id=%d score=%.3f",
            args.duplicate_id, candidates[0].score,
        )

    return 0


def cmd_entity_unmerge(args: argparse.Namespace) -> int:
    """entity-unmerge — reverse a previously recorded merge."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.graph.repository import GraphRepository, apply_graph_schema
    from callprofiler.graph.aggregator import EntityMetricsAggregator

    conn = repo._get_conn()
    apply_graph_schema(conn)

    # Fetch merge log entry
    log_row = conn.execute(
        """SELECT * FROM entity_merges_log
           WHERE canonical_id=? AND duplicate_id=? AND reversible=1
           ORDER BY merged_at DESC LIMIT 1""",
        (args.canonical_id, args.duplicate_id),
    ).fetchone()
    if not log_row:
        log.error(
            "[entity-unmerge] no reversible merge found for canonical=%d duplicate=%d",
            args.canonical_id, args.duplicate_id,
        )
        return 1

    import json as _json
    snapshot = _json.loads(log_row["snapshot_json"] or "{}")

    with conn:
        # Restore duplicate entity from snapshot
        conn.execute(
            "UPDATE entities SET archived=0, merged_into_id=NULL WHERE id=?",
            (args.duplicate_id,),
        )
        # Restore aliases from snapshot
        if "aliases" in snapshot:
            conn.execute(
                "UPDATE entities SET aliases=? WHERE id=?",
                (_json.dumps(snapshot["aliases"]), args.duplicate_id),
            )
        # Transfer events back (all events currently on canonical that came from duplicate)
        # Without per-event provenance we cannot split them perfectly;
        # we mark the merge log entry as reversed and warn the user.
        conn.execute(
            "UPDATE entity_merges_log SET unmerged_at=CURRENT_TIMESTAMP, reversible=0 "
            "WHERE id=?",
            (log_row["id"],),
        )

    # Recalculate both entities
    grepo = GraphRepository(conn)
    agg = EntityMetricsAggregator(grepo)
    for eid in (args.canonical_id, args.duplicate_id):
        try:
            agg.full_recalc_from_events(eid)
        except Exception as exc:
            log.warning("[entity-unmerge] recalc failed for %d: %s", eid, exc)

    log.info(
        "[entity-unmerge] restored entity %d from canonical %d. "
        "NOTE: event ownership cannot be split — manual review recommended.",
        args.duplicate_id, args.canonical_id,
    )
    return 0


def cmd_graph_audit(args: argparse.Namespace) -> int:
    """graph-audit — run 9 sanity checks on the Knowledge Graph."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.graph.auditor import GraphAuditor
    from callprofiler.graph.repository import apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)
    auditor = GraphAuditor(conn)
    result = auditor.run_checks(args.user_id)

    print(f"\nGraph Audit — user: {args.user_id}")
    print("─" * 50)
    for name, check in sorted(result["checks"].items()):
        status = "CRITICAL" if (not check["ok"] and name in {"owner_contamination", "orphan_events"}) \
                 else "WARN" if not check["ok"] else "OK"
        flag = "✗" if not check["ok"] else "✓"
        print(f"  {flag} {name:<40} {status}  (n={check['count']})")
        if not check["ok"] and check["details"]:
            for d in check["details"][:3]:
                print(f"      {d}")

    print()
    if result["has_critical"]:
        print("CRITICAL issues found — data integrity requires attention.")
        return 2
    if result["has_warnings"]:
        print("Warnings found.")
        return 1
    print("All checks passed.")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Start real-time dashboard web server."""
    from callprofiler.dashboard import run_dashboard
    run_dashboard(args.user_id, port=args.port, host=args.host)
    return 0


def cmd_book_chapter(args: argparse.Namespace) -> int:
    """book-chapter — show structured graph profile for one entity."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.graph.repository import apply_graph_schema
    from callprofiler.biography.data_extractor import (
        get_entity_profile_from_graph,
        get_behavioral_patterns,
        get_social_position,
    )

    conn = repo._get_conn()
    apply_graph_schema(conn)

    import json as _json

    profile = get_entity_profile_from_graph(args.entity_id, conn)
    if not profile:
        log.error("[book-chapter] entity_id=%d not found", args.entity_id)
        return 1

    patterns = get_behavioral_patterns(args.entity_id, conn)
    social = get_social_position(args.entity_id, conn)

    output = {
        "entity_id": args.entity_id,
        "canonical_name": profile.get("canonical_name"),
        "entity_type": profile.get("entity_type"),
        "aliases": profile.get("aliases", []),
        "metrics": profile.get("metrics", {}),
        "behavioral_patterns": patterns.get("patterns", []),
        "behavioral_raw": patterns.get("raw", {}),
        "top_relations": profile.get("top_relations", []),
        "org_links": social.get("org_links", []),
        "open_promises": social.get("open_promises", 0),
        "conflict_count": social.get("conflict_count", 0),
        "centrality": social.get("centrality", 0),
        "timeline": profile.get("timeline", []),
        "top_facts": profile.get("top_facts", [])[:10],
    }

    print(_json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_person_profile(args: argparse.Namespace) -> int:
    """person-profile — generate psychology profile for one graph entity."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.biography.psychology_profiler import PsychologyProfiler
    from callprofiler.graph.repository import apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)

    llm_url = getattr(cfg, "llm_url", "http://127.0.0.1:8080/v1/chat/completions")
    profiler = PsychologyProfiler(conn, llm_url=llm_url)
    profile = profiler.build_profile(args.entity_id, args.user_id)

    if not profile:
        print(f"Entity {args.entity_id} not found for user {args.user_id}.")
        return 1

    import json as _json

    if getattr(args, "json", False):
        print(_json.dumps(profile, ensure_ascii=False, indent=2))
    else:
        print(f"\n=== Psychology Profile: {profile['canonical_name']} ===")
        print(f"Type: {profile['entity_type']}  |  Aliases: {', '.join(profile['aliases']) or 'none'}")
        print(f"BS-index: {profile['metrics'].get('bs_index', 'n/a')}  |  avg_risk: {profile['metrics'].get('avg_risk', 'n/a')}")
        print(f"Temporal: {profile['temporal']['avg_calls_per_week']} calls/week  |  trend: {profile['temporal']['frequency_trend']}")
        print("\nPatterns:")
        for p in profile["patterns"]:
            print(f"  [{p['severity']}] {p['name']}: {p['label']}")
        print(f"\nSocial: centrality={profile['social']['centrality']}, open_promises={profile['social']['open_promises']}, conflicts={profile['social']['conflict_count']}")
        if profile.get("interpretation"):
            print(f"\n--- Interpretation ---\n{profile['interpretation']}")
        else:
            print("\n(LLM interpretation unavailable)")
    return 0


def cmd_profile_all(args: argparse.Namespace) -> int:
    """profile-all — generate psychology profiles for all entities of a user."""
    cfg, repo = _load_config_and_repo(args.config)
    log_file = args.log_file or cfg.log_file
    _setup_logging(log_file, getattr(args, "verbose", False))
    log = logging.getLogger(__name__)

    from callprofiler.biography.psychology_profiler import PsychologyProfiler
    from callprofiler.graph.repository import apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)

    limit = getattr(args, "limit", 0) or 0

    query = """
        SELECT e.id
          FROM entities e
          LEFT JOIN entity_metrics em ON em.entity_id = e.id
         WHERE e.user_id=? AND e.archived=0
         ORDER BY
           CASE
             WHEN UPPER(e.entity_type) = 'PERSON' THEN 0
             WHEN UPPER(e.entity_type) IN ('COMPANY', 'ORG', 'PROJECT') THEN 1
             ELSE 2
           END,
           COALESCE(em.total_calls, 0) DESC,
           (
             COALESCE(em.total_promises, 0)
             + COALESCE(em.contradictions, 0)
             + COALESCE(em.emotional_spikes, 0)
           ) DESC,
           e.id
    """
    params: list = [args.user_id]
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    if not rows:
        print(f"No entities found for user {args.user_id}.")
        return 0

    llm_url = getattr(cfg, "llm_url", "http://127.0.0.1:8080/v1/chat/completions")
    profiler = PsychologyProfiler(conn, llm_url=llm_url)

    success = 0
    failed = 0
    for row in rows:
        eid = row[0]
        try:
            profile = profiler.build_profile(eid, args.user_id)
            if profile:
                name = profile.get("canonical_name", str(eid))
                interp = profile.get("interpretation")
                status = "cached" if profile.get("_cache_hit") else ("ok" if interp else "no-llm")
                print(f"  [{status}] {eid}: {name}")
                success += 1
            else:
                print(f"  [skip] {eid}: not found")
        except Exception as exc:
            logging.getLogger(__name__).error("profile-all entity %d failed: %s", eid, exc)
            failed += 1

    print(f"\nDone: {success} profiled, {failed} failed.")
    return 0 if failed == 0 else 1


def cmd_graph_health(args: argparse.Namespace) -> int:
    """graph-health — 4 stability checks before biography generation.

    Exit 0 if all checks pass. Exit 1 if any check fails.
    """
    cfg, repo = _load_config_and_repo(args.config)
    log_file = args.log_file or cfg.log_file
    _setup_logging(log_file, getattr(args, "verbose", False))
    user_id = args.user_id

    from callprofiler.graph.auditor import GraphAuditor
    from callprofiler.graph.repository import GraphRepository, apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)
    grepo = GraphRepository(conn)

    checks: list[tuple[str, bool, str]] = []

    # Check 1: last replay run rejection_rate < 0.90
    last_run = grepo.get_last_replay_run(user_id)
    if last_run:
        rr = float(last_run.get("rejection_rate") or 0.0)
        ok1 = rr < 0.90
        label1 = f"rejection={rr * 100:.1f}% ({'stable' if ok1 else 'UNSTABLE'})"
    else:
        ok1 = False
        label1 = "no replay run found — run graph-replay first"
    checks.append(("replay", ok1, label1))

    # Check 2: graph-audit → no critical issues
    auditor = GraphAuditor(conn)
    audit_result = auditor.run_checks(user_id)
    ok2 = not audit_result["has_critical"]
    label2 = (
        "no critical issues"
        if ok2
        else f"{sum(1 for c in audit_result['checks'].values() if not c['ok'])} check(s) failed"
    )
    checks.append(("audit", ok2, label2))

    # Check 3: entity_metrics has rows for user
    em_count = conn.execute(
        """SELECT COUNT(*) FROM entity_metrics em
           JOIN entities e ON e.id = em.entity_id
           WHERE e.user_id = ?""",
        (user_id,),
    ).fetchone()[0]
    ok3 = em_count > 0
    label3 = f"{em_count} entity metric row(s)"
    checks.append(("entity_metrics", ok3, label3))

    # Check 4: bs_thresholds calibrated for user
    th_count = conn.execute(
        "SELECT COUNT(*) FROM bs_thresholds WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    ok4 = th_count > 0
    label4 = f"{th_count} threshold row(s)" if ok4 else "no thresholds — run graph-replay to calibrate"
    checks.append(("bs_thresholds", ok4, label4))

    print(f"\nGraph Health — user: {user_id}")
    print("─" * 50)
    all_ok = True
    for name, ok, detail in checks:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name:<20} {detail}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("All checks passed — graph is ready for biography generation.")
        return 0
    print("Health gate FAILED — fix issues above before running book-chapter.")
    return 1


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
    parser.add_argument(
        "--log-file",
        default=None,
        metavar="PATH",
        help="Путь к файлу лога (переопределяет cfg.log_file)",
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

    # ── graph-backfill ─────────────────────────────────────────────
    p_graph_bf = sub.add_parser(
        "graph-backfill",
        help="Наполнить Knowledge Graph из существующих v2 analyses",
    )
    p_graph_bf.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_graph_bf.add_argument(
        "--schema", default="v2", metavar="VERSION",
        help="Фильтр по schema_version: v2 (по умолчанию) или all",
    )

    # ── reenrich-v2 ────────────────────────────────────────────────
    p_reenrich = sub.add_parser(
        "reenrich-v2",
        help="Переобогатить v1 analyses через LLM для получения v2 (entities/facts)",
    )
    p_reenrich.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_reenrich.add_argument(
        "--limit", type=int, default=0, metavar="N",
        help="Максимум записей (0 = все)",
    )

    # ── graph-replay ───────────────────────────────────────────────
    p_graph_replay = sub.add_parser(
        "graph-replay",
        help="Пересоздать Knowledge Graph из v2 analyses (идемпотентно)",
    )
    p_graph_replay.add_argument(
        "--user", dest="user", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_graph_replay.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="Максимум calls для обработки (для тестирования)",
    )

    # ── entity-merge ───────────────────────────────────────────────
    p_entity_merge = sub.add_parser(
        "entity-merge",
        help="Слить дублирующую сущность в каноническую (Knowledge Graph)",
    )
    p_entity_merge.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_entity_merge.add_argument(
        "--canonical", dest="canonical_id", type=int, required=True,
        metavar="ID", help="ID канонической сущности",
    )
    p_entity_merge.add_argument(
        "--duplicate", dest="duplicate_id", type=int, required=True,
        metavar="ID", help="ID дублирующей сущности (будет архивирована)",
    )
    p_entity_merge.add_argument(
        "--score", type=float, default=0.0, help="Оценка схожести (0-1)",
    )
    p_entity_merge.add_argument(
        "--reason", default="", help="Комментарий к слиянию",
    )
    p_entity_merge.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Показать предпросмотр без записи",
    )
    p_entity_merge.add_argument(
        "--loop", action="store_true",
        help="Продолжать слияние пока есть кандидаты для canonical_id",
    )

    # ── entity-unmerge ─────────────────────────────────────────────
    p_entity_unmerge = sub.add_parser(
        "entity-unmerge",
        help="Отменить слияние сущностей (восстановить дубликат из snapshot)",
    )
    p_entity_unmerge.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
    )
    p_entity_unmerge.add_argument(
        "--canonical", dest="canonical_id", type=int, required=True, metavar="ID",
    )
    p_entity_unmerge.add_argument(
        "--duplicate", dest="duplicate_id", type=int, required=True, metavar="ID",
    )

    # ── graph-audit ────────────────────────────────────────────────
    p_graph_audit = sub.add_parser(
        "graph-audit",
        help="9 проверок целостности Knowledge Graph",
    )
    p_graph_audit.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
    )

    # ── book-chapter ────────────────────────────────────────────────
    p_book_chapter = sub.add_parser(
        "book-chapter",
        help="Структурированный граф-профиль сущности для главы биографии",
    )
    p_book_chapter.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
    )
    p_book_chapter.add_argument(
        "entity_id", type=int, metavar="ENTITY_ID",
        help="ID сущности из Knowledge Graph",
    )

    # ── person-profile ─────────────────────────────────────────────
    p_person_profile = sub.add_parser(
        "person-profile",
        help="Сгенерировать психологический профиль для одной сущности",
    )
    p_person_profile.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
    )
    p_person_profile.add_argument(
        "entity_id", type=int, metavar="ENTITY_ID",
    )
    p_person_profile.add_argument(
        "--json", action="store_true", dest="json",
        help="Выводить полный профиль в JSON",
    )

    # ── profile-all ────────────────────────────────────────────────
    p_profile_all = sub.add_parser(
        "profile-all",
        help="Сгенерировать профили для всех сущностей пользователя",
    )
    p_profile_all.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
    )
    p_profile_all.add_argument(
        "--limit", type=int, default=0, metavar="N",
        help="Максимум сущностей (0 = все)",
    )

    # ── graph-health ───────────────────────────────────────────────
    p_graph_health = sub.add_parser(
        "graph-health",
        help="4 stability checks: replay rejection, audit, entity_metrics, bs_thresholds",
    )
    p_graph_health.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── dashboard ──────────────────────────────────────────────────
    p_dashboard = sub.add_parser(
        "dashboard",
        help="Запустить real-time web dashboard для мониторинга pipeline",
    )
    p_dashboard.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_dashboard.add_argument(
        "--port", type=int, default=8765, metavar="PORT",
        help="Порт веб-сервера (по умолчанию: 8765)",
    )
    p_dashboard.add_argument(
        "--host", default="127.0.0.1", metavar="HOST",
        help="Хост веб-сервера (по умолчанию: 127.0.0.1)",
    )

    # ── graph-stats ────────────────────────────────────────────────
    p_graph_stats = sub.add_parser(
        "graph-stats",
        help="Статистика Knowledge Graph: entities, relations, facts",
    )
    p_graph_stats.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
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
        "graph-backfill": cmd_graph_backfill,
        "reenrich-v2": cmd_reenrich_v2,
        "graph-replay": cmd_graph_replay,
        "graph-stats": cmd_graph_stats,
        "entity-merge": cmd_entity_merge,
        "entity-unmerge": cmd_entity_unmerge,
        "graph-audit": cmd_graph_audit,
        "graph-health": cmd_graph_health,
        "dashboard": cmd_dashboard,
        "book-chapter": cmd_book_chapter,
        "person-profile": cmd_person_profile,
        "profile-all": cmd_profile_all,
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
