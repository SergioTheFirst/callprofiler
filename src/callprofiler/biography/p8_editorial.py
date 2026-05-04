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
from callprofiler.biography.prompts import (
    build_editorial_prompt,
    calculate_dynamic_budget,
)
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p8_editorial"


def chunk_chapter_prose(prose: str, max_chunk_chars: int = 18000) -> list[str]:
    """Split chapter prose on semantic boundaries (## headers).

    Args:
        prose: Full chapter markdown
        max_chunk_chars: Maximum characters per chunk

    Returns:
        List of prose chunks, each starting with section header
    """
    if len(prose) <= max_chunk_chars:
        return [prose]

    # Split on ## headers (section boundaries)
    lines = prose.split('\n')
    chunks = []
    current_chunk = []
    current_size = 0

    for line in lines:
        line_size = len(line) + 1  # +1 for newline

        # If this is a section header and we have content, consider splitting
        if line.startswith('## ') and current_chunk and current_size > max_chunk_chars * 0.7:
            chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_size = line_size
        else:
            current_chunk.append(line)
            current_size += line_size

            # Hard split if we exceed max size
            if current_size > max_chunk_chars:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0

    # Add remaining content
    if current_chunk:
        chunks.append('\n'.join(current_chunk))

    return chunks


def editorial_pass_chunked(
    chunks: list[str],
    llm: ResilientLLMClient,
    user_id: str,
    chapter_id: int,
    prev_context: str = "",
) -> str:
    """Process chapter chunks sequentially, preserving continuity.

    Args:
        chunks: List of prose chunks
        llm: LLM client
        user_id: User identifier
        chapter_id: Chapter ID for context key
        prev_context: Context from previous chunk (last 500 chars)

    Returns:
        Merged edited prose
    """
    results = []

    for i, chunk in enumerate(chunks):
        is_first = (i == 0)
        is_last = (i == len(chunks) - 1)

        # Build prompt with continuity context
        if prev_context and not is_first:
            chunk_with_context = f"[Предыдущий контекст: ...{prev_context}]\n\n{chunk}"
        else:
            chunk_with_context = chunk

        messages = build_editorial_prompt(chunk_with_context)

        response = llm.call(
            user_id=user_id,
            pass_name=PASS_NAME,
            context_key=f"edit:chapter:{chapter_id}:chunk:{i}",
            messages=messages,
            temperature=0.4,
            max_tokens=5500,
        )

        if not response or len(response.strip()) < 100:
            log.warning(
                "[p8_editorial] Chunk %d/%d failed for chapter %d",
                i + 1, len(chunks), chapter_id
            )
            # Use original chunk as fallback
            results.append(chunk)
        else:
            results.append(response.strip())

        # Update context for next chunk (last 500 chars)
        prev_context = results[-1][-500:] if results[-1] else ""

    return '\n\n'.join(results)


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

        # Calculate dynamic budget for this chapter
        # Use CRS=0.5 as default (will be refined when we have scene data)
        dynamic_budget = calculate_dynamic_budget(
            pass_name=PASS_NAME,
            crs=0.5,
            is_long_call=False,
        )

        # Check if chunking is needed
        if len(prose) > dynamic_budget:
            log.info(
                "[p8_editorial] Chapter %d exceeds budget (%d > %d chars), using chunked processing",
                chapter_id, len(prose), dynamic_budget
            )
            chunks = chunk_chapter_prose(prose, max_chunk_chars=dynamic_budget)
            response = editorial_pass_chunked(
                chunks=chunks,
                llm=llm,
                user_id=user_id,
                chapter_id=chapter_id,
            )
        else:
            # Normal single-pass editing
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
