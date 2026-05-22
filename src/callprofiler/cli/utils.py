# -*- coding: utf-8 -*-
"""
utils.py — утилиты CLI: логирование, загрузка конфига.

Общий модуль без циклических импортов.
Используется: main.py, commands/admin.py, commands/bulk.py и др.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(log_file: str | None = None, verbose: bool = False) -> None:
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


def load_config_and_repo(config_path: str):
    """Загрузить конфиг и инициализировать репозиторий."""
    from callprofiler.config import load_config
    from callprofiler.db.repository import Repository

    cfg = load_config(config_path)

    db_path = Path(cfg.data_dir) / "db" / "callprofiler.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    repo = Repository(str(db_path))
    repo.init_db()

    return cfg, repo
