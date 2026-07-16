# -*- coding: utf-8 -*-
"""cli/commands/ask.py — A2: вопрос к архиву звонков."""

from __future__ import annotations

import argparse
import logging

import requests

from callprofiler.cli.utils import load_config_and_repo, setup_logging

log = logging.getLogger(__name__)


def cmd_ask(args: argparse.Namespace) -> int:
    """ask "<вопрос>" --user X [--k 8] — FTS5-поиск + LLM-синтез со ссылками [n]."""
    setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = load_config_and_repo(args.config)
    conn = repo._get_conn()

    from callprofiler.ask import answer_question

    try:
        result = answer_question(
            conn, args.user_id, args.question,
            llm_url=cfg.models.llm_url, k=getattr(args, "k", 8),
        )
    except (ConnectionError, requests.exceptions.RequestException) as exc:
        log.error("llama-server недоступен: %s", exc)
        return 2

    print(result["answer"])
    if result["citations"]:
        print("\nИсточники:")
        for c in result["citations"]:
            print(f"  [{c['n']}] {c['contact']}, {c['date']} (call_id={c['call_id']})")
    return 0
