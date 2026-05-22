# -*- coding: utf-8 -*-
"""biography.py — команды построения биографии."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from callprofiler.cli.utils import load_config_and_repo as _load_config_and_repo, setup_logging as _setup_logging


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




def register_subparsers(sub):
    """Register biography subparsers — defined in _build_parser()."""
    pass  # parsers remain in main.py: _build_parser()
