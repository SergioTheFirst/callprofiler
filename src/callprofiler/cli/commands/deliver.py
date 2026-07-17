# -*- coding: utf-8 -*-
"""cli/commands/deliver.py — A1: obligations-digest (реестр обязательств) +
F2: reminders-due (ручной прогон/отладка без бота)."""

from __future__ import annotations

import argparse
from datetime import datetime

from callprofiler.cli.utils import load_config_and_repo, setup_logging


def cmd_obligations_digest(args: argparse.Namespace) -> int:
    """obligations-digest --user X [--out FILE] — просроченные/открытые promise+debt."""
    setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = load_config_and_repo(args.config)
    conn = repo._get_conn()

    from callprofiler.deliver.digest import build_digest
    from callprofiler.insight.deep_extract import recent_deep_lines
    from callprofiler.insight.dormancy import dormant_valuable

    dormant_lines = [
        f"{d['name']} — тишина с {d['last_date']}; {d['why']}"
        for d in dormant_valuable(conn, args.user_id)
    ]
    extra = [
        ("🔎 Из глубокого прохода", recent_deep_lines(conn, args.user_id)),
        ("😴 Спящие ценные связи", dormant_lines),
    ]
    report = build_digest(conn, args.user_id, extra_sections=extra)

    # F8: тиры — дёшево, обновляем при каждом построении дайджеста (Fable §3.8 п.3)
    try:
        from callprofiler.insight.tiers import recompute_tiers

        recompute_tiers(conn, args.user_id)
    except Exception as exc:  # noqa: BLE001 — digest не должен падать из-за тиров
        import logging

        logging.getLogger(__name__).warning("tiers-recompute error (non-fatal): %s", exc)

    out = getattr(args, "out", None)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"obligations-digest: записано в {out} (user={args.user_id})")
    else:
        print(report)
    return 0


def cmd_daily_report(args: argparse.Namespace) -> int:
    """daily-report --user X [--date YYYY-MM-DD] [--send] — F5 вечерний отчёт."""
    setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = load_config_and_repo(args.config)
    conn = repo._get_conn()

    from callprofiler.deliver.daily_report import build_daily_report

    date = getattr(args, "date", None) or datetime.now().date().isoformat()
    report = build_daily_report(conn, args.user_id, date)

    if getattr(args, "send", False):
        from callprofiler.deliver.telegram_sender import send_telegram_message

        user = repo.get_user(args.user_id)
        chat_id = user.get("telegram_chat_id") if user else None
        if not chat_id:
            print(f"daily-report: у пользователя {args.user_id} не задан telegram_chat_id")
            return 1
        ok = send_telegram_message(chat_id, report)
        print(f"daily-report: {'отправлен' if ok else 'ОШИБКА отправки'} (user={args.user_id}, date={date})")
        return 0 if ok else 1

    print(report or f"daily-report: нечего показать за {date} (user={args.user_id})")
    return 0


def cmd_reminders_due(args: argparse.Namespace) -> int:
    """reminders-due --user X — печать ждущих/просроченных напоминаний (F2, без бота)."""
    setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = load_config_and_repo(args.config)
    conn = repo._get_conn()

    from callprofiler.insight.repository import apply_insight_schema
    from callprofiler.deliver.reminders import due_reminders

    apply_insight_schema(conn)
    due = [r for r in due_reminders(conn, datetime.now()) if r["user_id"] == args.user_id]

    if not due:
        print(f"reminders-due: нет ждущих напоминаний (user={args.user_id})")
        return 0

    print(f"reminders-due: {len(due)} ждут отправки (user={args.user_id})")
    for r in due:
        print(f"  #{r['reminder_id']} due={r['due_at']}: {r['text']}")
    return 0
