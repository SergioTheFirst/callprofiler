"""Prompt budget estimation and transcript clipping for LLM context windows."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Approximate: 1 char ≈ 0.4 tokens for Russian, 0.3 for English
_TOKENS_PER_CHAR = 0.4


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) * _TOKENS_PER_CHAR))


def clip_transcript_for_llm(transcript: str, max_chars: int) -> dict:
    original_chars = len(transcript)
    if original_chars <= max_chars:
        return {
            "text": transcript,
            "truncated": False,
            "estimated_tokens": estimate_tokens(transcript),
            "original_chars": original_chars,
            "final_chars": original_chars,
        }

    # Keep beginning + dense middle + ending
    head_size = max_chars // 3
    tail_size = max_chars // 4
    middle_size = max_chars - head_size - tail_size

    head = transcript[:head_size]
    tail = transcript[-tail_size:]
    # Extract middle from central portion with word boundary
    mid_start = (original_chars - middle_size) // 2
    middle = transcript[mid_start:mid_start + middle_size]

    clipped = f"{head}\n\n... [середина разговора] ...\n\n{middle}\n\n... [конец разговора] ...\n\n{tail}"
    final_chars = len(clipped)

    result = {
        "text": clipped,
        "truncated": True,
        "estimated_tokens": estimate_tokens(clipped),
        "original_chars": original_chars,
        "final_chars": final_chars,
    }
    log.info(
        "Transcript clipped: %d → %d chars (~%d tokens)",
        original_chars, final_chars, result["estimated_tokens"],
    )
    return result
