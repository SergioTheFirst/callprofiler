# -*- coding: utf-8 -*-
"""cli/commands/doctor.py — CLI-обёртка над doctor.py (M1)."""

from __future__ import annotations

import argparse
from pathlib import Path

from callprofiler.cli.utils import setup_logging
from callprofiler.doctor import format_report, run_checks


def cmd_doctor(args: argparse.Namespace) -> int:
    setup_logging(verbose=getattr(args, "verbose", False))

    from callprofiler.config import load_config

    try:
        cfg = load_config(args.config, validate=False)
    except Exception as exc:  # noqa: BLE001 — конфиг не парсится вообще
        print(f"🔴 config  FAIL  не удалось загрузить {args.config}: {exc}")
        return 1

    conn = None
    try:
        data_dir = getattr(cfg, "data_dir", "") or ""
        db_path = Path(data_dir) / "db" / "callprofiler.db" if data_dir else None
        if db_path and db_path.exists():
            from callprofiler.db.repository import Repository
            conn = Repository(str(db_path))._get_conn()
    except Exception:
        conn = None

    checks = run_checks(cfg, conn=conn)
    print(format_report(checks))

    return 1 if any(c.status == "FAIL" for c in checks) else 0
