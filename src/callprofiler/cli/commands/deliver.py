# -*- coding: utf-8 -*-
"""cli/commands/deliver.py — A1: obligations-digest (реестр обязательств)."""

from __future__ import annotations

import argparse

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
