# -*- coding: utf-8 -*-
"""backup.py — T-20 CLI: backup / verify-backup / restore (see ops/backup.py)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from callprofiler.cli.utils import setup_logging as _setup_logging


def _db_path(cfg) -> str:
    return str(Path(cfg.data_dir) / "db" / "callprofiler.db")


def _backup_dir(cfg, args) -> str:
    out = getattr(args, "out", None) or getattr(args, "backup_dir", None)
    if out:
        return out
    return str(Path(cfg.data_dir) / "backups")


def cmd_backup(args: argparse.Namespace) -> int:
    from callprofiler.config import load_config
    from callprofiler.ops.backup import create_backup

    cfg = load_config(args.config)
    _setup_logging(args.log_file or cfg.log_file, getattr(args, "verbose", False))
    log = logging.getLogger(__name__)

    db_path = _db_path(cfg)
    backup_dir = _backup_dir(cfg, args)
    try:
        manifest = create_backup(
            db_path,
            backup_dir,
            kind=args.kind,
            retention_daily=args.retention_daily,
            retention_weekly=args.retention_weekly,
        )
    except Exception as exc:
        log.error("[backup] failed: %s", exc)
        return 1

    log.info(
        "[backup] ok file=%s size=%d sha256=%s counts=%s",
        manifest.filename, manifest.size_bytes, manifest.sha256[:12], manifest.table_counts,
    )
    return 0


def cmd_verify_backup(args: argparse.Namespace) -> int:
    from callprofiler.ops.backup import verify_backup

    _setup_logging(args.log_file, getattr(args, "verbose", False))
    log = logging.getLogger(__name__)

    result = verify_backup(args.path)
    if result.ok:
        log.info("[verify-backup] OK: %s", args.path)
        return 0
    log.error("[verify-backup] FAILED: %s -- %s", args.path, "; ".join(result.problems))
    return 1


def cmd_restore(args: argparse.Namespace) -> int:
    from callprofiler.config import load_config
    from callprofiler.ops.backup import latest_verified_backup, restore_backup

    cfg = load_config(args.config)
    _setup_logging(args.log_file or cfg.log_file, getattr(args, "verbose", False))
    log = logging.getLogger(__name__)

    backup_dir = _backup_dir(cfg, args)
    backup_path = args.from_path or latest_verified_backup(backup_dir)
    if not backup_path:
        log.error("[restore] no backups found in %s (pass --from)", backup_dir)
        return 1

    result = restore_backup(
        backup_path,
        args.to,
        overwrite=args.overwrite,
        snapshot_dir_on_overwrite=backup_dir if args.overwrite else None,
    )
    if result.ok:
        log.info("[restore] ok -> %s (from %s)", args.to, backup_path)
        return 0
    log.error("[restore] FAILED: %s", "; ".join(result.problems))
    return 1
