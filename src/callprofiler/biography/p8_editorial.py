# -*- coding: utf-8 -*-
"""
p8_editorial.py — Pass 8: Editorial Pass.

Walks every chapter in bio_chapters (status != 'final'), asks the LLM
to polish it (dedupe, tighten, remove call-count leaks), and writes
the revised prose back with status='final'.

Idempotent: chapters already marked 'final' are skipped on re-run.
In the standard pipeline p7_book runs *after* p8b_doc_dedup, so
reassemble defaults to False.
"""

from __future__ import annotations

import logging
import time

from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.prompts import build_editorial_prompt
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p8_editorial"


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
    reassemble: bool = False,
) -> dict:
    chapters = bio.get_chapters_for_user(user_id)
    todo = [c for c in chapters if c.get("status") != "final"]
    log.info("[p8_editorial] chapters=%d, to_edit=%d", len(chapters), len(todo))

    bio.start_checkpoint(user_id, PASS_NAME, len(todo) or 1)
    began = time.monotonic()
    edited = 0
    failed = 0

    for c in todo:
        chapter_id = int(c["chapter_id"])
        prose = (c.get("prose") or "").strip()
        if len(prose) < 200:
            bio.tick_checkpoint(user_id, PASS_NAME, f"chapter:{chapter_id}")
            continue

        messages = build_editorial_prompt(prose)
        response = llm.call(
            user_id=user_id,
            pass_name=PASS_NAME,
            context_key=f"edit:chapter:{chapter_id}",
            messages=messages,
            temperature=0.4,
            max_tokens=5500,
        )
        if not response or len(response.strip()) < 200:
            failed += 1
            bio.tick_checkpoint(user_id, PASS_NAME, f"chapter:{chapter_id}",
                                processed_delta=1, failed_delta=1)
            continue

        bio.set_chapter_prose(chapter_id, response.strip(), status="final")
        edited += 1
        bio.tick_checkpoint(user_id, PASS_NAME, f"chapter:{chapter_id}")

    bio.finish_checkpoint(user_id, PASS_NAME, "done")

    stats = {
        "chapters_edited": edited,
        "failed": failed,
        "elapsed_sec": round(time.monotonic() - began, 1),
    }

    if reassemble:
        from callprofiler.biography import p7_book
        reassembled = p7_book.run(user_id, bio, llm, version_label="final")
        stats["book"] = reassembled

    log.info("[p8_editorial] done %s", stats)
    return stats
