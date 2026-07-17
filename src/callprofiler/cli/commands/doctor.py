# -*- coding: utf-8 -*-
"""cli/commands/doctor.py — CLI-обёртка над doctor.py (M1)."""

from __future__ import annotations

import argparse
from pathlib import Path

from callprofiler.cli.utils import setup_logging
from callprofiler.doctor import build_doctor_message, format_report, run_checks


def cmd_doctor(args: argparse.Namespace) -> int:
    setup_logging(verbose=getattr(args, "verbose", False))

    from callprofiler.config import load_config

    try:
        cfg = load_config(args.config, validate=False)
    except Exception as exc:  # noqa: BLE001 — конфиг не парсится вообще
        print(f"🔴 config  FAIL  не удалось загрузить {args.config}: {exc}")
        return 1

    repo = None
    conn = None
    try:
        data_dir = getattr(cfg, "data_dir", "") or ""
        db_path = Path(data_dir) / "db" / "callprofiler.db" if data_dir else None
        if db_path and db_path.exists():
            from callprofiler.db.repository import Repository
            repo = Repository(str(db_path))
            conn = repo._get_conn()
    except Exception:
        repo = None
        conn = None

    checks = run_checks(cfg, conn=conn)
    print(format_report(checks))

    if getattr(args, "send", False):
        from callprofiler.deliver.telegram_sender import send_telegram_message

        message = build_doctor_message(checks)
        if repo is None:
            print("doctor --send: БД недоступна, отправка невозможна")
        else:
            for user in repo.get_all_users():
                chat_id = user.get("telegram_chat_id")
                if not chat_id:
                    continue
                ok = send_telegram_message(chat_id, message)
                print(f"doctor --send: {'отправлен' if ok else 'ОШИБКА'} user={user['user_id']}")

    return 1 if any(c.status == "FAIL" for c in checks) else 0
