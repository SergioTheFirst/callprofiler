# -*- coding: utf-8 -*-
"""
p8b_doc_dedup.py — Pass 8b: Cross-chapter paragraph deduplication.

Deterministic, no LLM. Two-stage per the architecture recommendation:
  1. Exact-hash detector: MD5 of normalised paragraph text.
  2. Near-dup detector: Jaccard similarity on word-sets (threshold 0.72).

Chapters are walked in ascending chapter_num order. The first occurrence
of a paragraph wins; later occurrences in subsequent chapters are removed.
Short paragraphs (headers, single-sentence quotes) are skipped — dedup unit
is the paragraph, not the sentence.

Idempotent: chapters that lost nothing are not re-written. Running again
after a p6 re-run resets the 'final' status so p8 will re-edit them before
p8b runs again.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time

from callprofiler.biography.repo import BiographyRepo
from callprofiler.biography.llm_client import ResilientLLMClient

log = logging.getLogger(__name__)

PASS_NAME = "p8b_doc_dedup"

MIN_PARA_LEN = 80        # paragraphs shorter than this skip dedup entirely
NEAR_THRESHOLD = 0.72    # Jaccard on word-sets
NEAR_LOOKBACK = 60       # how many recent paragraphs to compare against


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _para_hash(text: str) -> str:
    return hashlib.md5(_normalise(text).encode("utf-8")).hexdigest()


def _jaccard(a: str, b: str) -> float:
    wa = set(_normalise(a).split())
    wb = set(_normalise(b).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _split_paragraphs(prose: str) -> list[str]:
    return [p.strip() for p in prose.split("\n\n") if p.strip()]


def _dedup_chapter(
    paras: list[str],
    seen_hashes: set[str],
    seen_paras: list[str],
) -> tuple[list[str], int]:
    """Return (kept_paragraphs, removed_count). seen_* updated in-place."""
    kept: list[str] = []
    removed = 0
    for para in paras:
        if len(para) < MIN_PARA_LEN:
            kept.append(para)
            continue

        ph = _para_hash(para)
        if ph in seen_hashes:
            removed += 1
            log.debug("[p8b] exact-dup removed: %.60s…", para)
            continue

        # Near-dup scan over recent paragraphs only (bounded cost).
        is_near_dup = any(
            len(sp) >= MIN_PARA_LEN and _jaccard(para, sp) >= NEAR_THRESHOLD
            for sp in seen_paras[-NEAR_LOOKBACK:]
        )
        if is_near_dup:
            removed += 1
            log.debug("[p8b] near-dup removed: %.60s…", para)
            continue

        seen_hashes.add(ph)
        seen_paras.append(para)
        kept.append(para)
    return kept, removed


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
) -> dict:
    chapters = bio.get_chapters_for_user(user_id)
    chapters_with_prose = [c for c in chapters if (c.get("prose") or "").strip()]

    if not chapters_with_prose:
        log.warning("[p8b] no chapters with prose — run p6 first")
        bio.start_checkpoint(user_id, PASS_NAME, 0)
        bio.finish_checkpoint(user_id, PASS_NAME, "done")
        return {"ok": False, "reason": "no_prose"}

    bio.start_checkpoint(user_id, PASS_NAME, len(chapters_with_prose))
    began = time.monotonic()

    seen_hashes: set[str] = set()
    seen_paras: list[str] = []
    total_removed = 0
    chapters_rewritten = 0

    for c in chapters_with_prose:
        chapter_id = int(c["chapter_id"])
        prose = c["prose"].strip()
        paras = _split_paragraphs(prose)

        kept, removed = _dedup_chapter(paras, seen_hashes, seen_paras)

        if removed:
            new_prose = "\n\n".join(kept)
            # Preserve the current status so p8 idempotency is not broken.
            current_status = c.get("status") or "draft"
            bio.set_chapter_prose(chapter_id, new_prose, status=current_status)
            total_removed += removed
            chapters_rewritten += 1
            log.info(
                "[p8b] chapter %d: removed %d duplicate paragraph(s)",
                chapter_id, removed,
            )

        bio.tick_checkpoint(user_id, PASS_NAME, f"chapter:{chapter_id}")

    bio.finish_checkpoint(user_id, PASS_NAME, "done")

    stats = {
        "chapters_scanned": len(chapters_with_prose),
        "chapters_rewritten": chapters_rewritten,
        "paragraphs_removed": total_removed,
        "elapsed_sec": round(time.monotonic() - began, 1),
    }
    log.info("[p8b] done %s", stats)
    return stats
