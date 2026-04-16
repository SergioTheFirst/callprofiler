# -*- coding: utf-8 -*-
"""
p7_book.py — Pass 7: Book Assembler.

Generates book-level frame (title, subtitle, epigraph, prologue, epilogue,
TOC) via one LLM call over chapters+top_arcs+top_entities, then stitches
the full markdown (prologue + chapters in order + epilogue) and saves one
bio_books row as a new version.

Idempotent w.r.t. memoization but always writes a new book row (each run
represents a fresh assembly snapshot — old drafts are retained for audit).
"""

from __future__ import annotations

import logging
import time

from callprofiler.biography.json_utils import extract_json
from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.prompts import build_book_frame_prompt
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p7_book"


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
    version_label: str = "draft-1",
) -> dict:
    chapters = bio.get_chapters_for_user(user_id)
    if not chapters:
        log.warning("[p7_book] no chapters found — run pass 6 first")
        return {"ok": False, "reason": "no_chapters"}

    top_arcs = bio.get_arcs_for_user(user_id)[:15]
    top_entities = bio.get_entities_for_user(user_id, min_mentions=2)[:20]

    period_start = chapters[0].get("period_start")
    period_end = chapters[-1].get("period_end")

    bio.start_checkpoint(user_id, PASS_NAME, 1)
    began = time.monotonic()

    messages = build_book_frame_prompt(
        chapters=chapters,
        top_arcs=top_arcs,
        top_entities=top_entities,
        period_start=period_start,
        period_end=period_end,
    )
    response = llm.call(
        user_id=user_id,
        pass_name=PASS_NAME,
        context_key=f"book:frame:{version_label}",
        messages=messages,
        temperature=0.6,
        max_tokens=2000,
    )
    frame = extract_json(response) if response else None
    if not isinstance(frame, dict):
        log.warning("[p7_book] frame parse failed — using fallback")
        frame = {
            "title": "Биография",
            "subtitle": f"{period_start or ''} — {period_end or ''}",
            "epigraph": "",
            "prologue": "",
            "epilogue": "",
            "toc": [
                {"chapter_num": c["chapter_num"],
                 "title": c.get("title"),
                 "one_liner": c.get("theme")}
                for c in chapters
            ],
        }

    title = (frame.get("title") or "Биография").strip()
    subtitle = (frame.get("subtitle") or "").strip()
    epigraph = (frame.get("epigraph") or "").strip()
    prologue = (frame.get("prologue") or "").strip()
    epilogue = (frame.get("epilogue") or "").strip()
    toc = frame.get("toc") or []

    prose_full = _stitch(
        title=title,
        subtitle=subtitle,
        epigraph=epigraph,
        prologue=prologue,
        epilogue=epilogue,
        toc=toc,
        chapters=chapters,
    )

    book_id = bio.insert_book(
        user_id=user_id,
        title=title,
        subtitle=subtitle,
        epigraph=epigraph,
        prologue=prologue,
        epilogue=epilogue,
        toc=toc if isinstance(toc, list) else [],
        prose_full=prose_full,
        period_start=period_start,
        period_end=period_end,
        model=llm.model_name,
        version_label=version_label,
    )
    bio.tick_checkpoint(user_id, PASS_NAME, f"book:{book_id}")
    bio.finish_checkpoint(user_id, PASS_NAME, "done")

    stats = {
        "book_id": book_id,
        "chapters": len(chapters),
        "word_count": len(prose_full.split()),
        "version": version_label,
        "elapsed_sec": round(time.monotonic() - began, 1),
    }
    log.info("[p7_book] done %s", stats)
    return stats


def _stitch(
    title: str,
    subtitle: str,
    epigraph: str,
    prologue: str,
    epilogue: str,
    toc,
    chapters: list[dict],
) -> str:
    lines: list[str] = []
    lines.append(f"# {title}")
    if subtitle:
        lines.append("")
        lines.append(f"*{subtitle}*")
    if epigraph:
        lines.append("")
        lines.append("> " + epigraph.replace("\n", "\n> "))
    lines.append("")

    if isinstance(toc, list) and toc:
        lines.append("## Оглавление")
        lines.append("")
        for entry in toc:
            if not isinstance(entry, dict):
                continue
            num = entry.get("chapter_num", "")
            t = entry.get("title", "")
            one = entry.get("one_liner", "")
            suffix = f" — *{one}*" if one else ""
            lines.append(f"{num}. {t}{suffix}")
        lines.append("")

    if prologue:
        lines.append("## Пролог")
        lines.append("")
        lines.append(prologue)
        lines.append("")

    for c in chapters:
        prose = (c.get("prose") or "").strip()
        if not prose:
            continue
        # Each chapter already starts with "# ..." so just include it.
        lines.append(prose)
        lines.append("")

    if epilogue:
        lines.append("## Эпилог")
        lines.append("")
        lines.append(epilogue)
        lines.append("")

    return "\n".join(lines).strip() + "\n"
