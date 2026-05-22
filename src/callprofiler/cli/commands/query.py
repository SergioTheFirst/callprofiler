# -*- coding: utf-8 -*-
"""query.py — команды запросов и поиска."""

from __future__ import annotations

import argparse
import json as _json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from callprofiler.cli.utils import load_config_and_repo as _load_config_and_repo, setup_logging as _setup_logging


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
        analysis = repo.get_analysis(args.user_id, call["call_id"])
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
        contact = repo.get_contact(args.user_id, contact_id) if contact_id else None
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

# ---- bulk commands ----
from callprofiler.cli.commands.bulk import (  # noqa: E402
    cmd_extract_names, cmd_bulk_load, cmd_bulk_enrich,
)





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
        call = repo.get_call(args.user_id, call_id)

        if not call:
            continue

        contact_id = call["contact_id"]
        contact = repo.get_contact(args.user_id, contact_id) if contact_id else None
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
        contact = repo.get_contact(args.user_id, contact_id) if contact_id else None
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




# ── biography ──────────────────────────────────────────────────────────────




def register_subparsers(sub):
    """Register query subparsers — defined in _build_parser()."""
    pass  # parsers remain in main.py: _build_parser()
