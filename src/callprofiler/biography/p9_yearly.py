# -*- coding: utf-8 -*-
"""
p9_yearly.py — Pass 9: Yearly Summary.

Generates a Dovlatov-style annual retrospective (3-5 paragraphs, no
subheadings) from all chapters belonging to a given year and saves it
as a bio_books row with book_type='yearly_summary'.

Idempotent: a re-run with the same year generates a new row (old ones
remain for audit), but LLM memoization means the same prompt returns
the cached response unless PROMPT_VERSION was bumped.
"""

from __future__ import annotations

import logging
import time

from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.prompts import build_yearly_summary_prompt
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p9_yearly"


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
    year: int | None = None,
) -> dict:
    all_chapters = bio.get_chapters_for_user(user_id)
    if not all_chapters:
        log.warning("[p9_yearly] no chapters found — run passes p1-p6 first")
        bio.start_checkpoint(user_id, PASS_NAME, 0)
        bio.finish_checkpoint(user_id, PASS_NAME, "done")
        return {"ok": False, "reason": "no_chapters"}

    # Determine target year.
    if year is None:
        years = sorted(
            {(c.get("period_start") or "")[:4]
             for c in all_chapters
             if (c.get("period_start") or "")[:4].isdigit()},
            reverse=True,
        )
        if not years:
            log.warning("[p9_yearly] chapters have no period_start dates")
            bio.start_checkpoint(user_id, PASS_NAME, 0)
            bio.finish_checkpoint(user_id, PASS_NAME, "done")
            return {"ok": False, "reason": "no_dates"}
        year = int(years[0])

    year_prefix = str(year)
    chapters = [
        c for c in all_chapters
        if (c.get("period_start") or "").startswith(year_prefix)
    ]
    if not chapters:
        log.warning("[p9_yearly] no chapters for year %d", year)
        bio.start_checkpoint(user_id, PASS_NAME, 0)
        bio.finish_checkpoint(user_id, PASS_NAME, "done")
        return {"ok": False, "reason": f"no_chapters_for_{year}"}

    top_arcs = bio.get_arcs_for_user(user_id)[:12]
    top_entities = bio.get_entities_for_user(user_id, min_mentions=2)[:15]

    bio.start_checkpoint(user_id, PASS_NAME, 1)
    began = time.monotonic()

    messages = build_yearly_summary_prompt(
        year=year,
        chapters=chapters,
        top_arcs=top_arcs,
        top_entities=top_entities,
    )
    response = llm.call(
        user_id=user_id,
        pass_name=PASS_NAME,
        context_key=f"yearly:{year}",
        messages=messages,
        temperature=0.55,
        max_tokens=4000,
    )

    if not response or len(response.strip()) < 100:
        bio.tick_checkpoint(user_id, PASS_NAME, f"yearly:{year}",
                            processed_delta=1, failed_delta=1)
        bio.finish_checkpoint(user_id, PASS_NAME, "failed")
        log.warning("[p9_yearly] LLM returned empty/short response for year %d", year)
        return {"ok": False, "reason": "llm_empty"}

    period_start = chapters[0].get("period_start")
    period_end = chapters[-1].get("period_end")

    book_id = bio.insert_book(
        user_id=user_id,
        title=f"Итоги {year}",
        subtitle="",
        epigraph="",
        prologue="",
        epilogue="",
        toc=[],
        prose_full=response.strip(),
        period_start=period_start,
        period_end=period_end,
        model=llm.model_name,
        version_label=f"yearly-{year}",
        book_type="yearly_summary",
    )
    bio.tick_checkpoint(user_id, PASS_NAME, f"yearly:{year}")
    bio.finish_checkpoint(user_id, PASS_NAME, "done")

    stats = {
        "book_id": book_id,
        "year": year,
        "chapters_used": len(chapters),
        "word_count": len(response.split()),
        "elapsed_sec": round(time.monotonic() - began, 1),
    }
    log.info("[p9_yearly] done %s", stats)
    return stats
