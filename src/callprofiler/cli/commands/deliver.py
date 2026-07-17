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

    report = build_digest(conn, args.user_id)
    out = getattr(args, "out", None)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"obligations-digest: записано в {out} (user={args.user_id})")
    else:
        print(report)
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
