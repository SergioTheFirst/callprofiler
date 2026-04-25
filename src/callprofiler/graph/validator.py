# -*- coding: utf-8 -*-
"""
graph/validator.py — Enhanced fact validation for Knowledge Graph consistency.

Validates facts extracted by LLM before writing to events table:
1. Quote length (MIN_QUOTE_LEN = 8 chars)
2. Rolling window search in transcript (ratio >= 0.72)
3. Speaker attribution detection ([me] vs [s2])
4. Semantic checks (future markers, negations, vagueness)
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any

log = logging.getLogger(__name__)

# Validator thresholds (Этап 2 stabilization requirements)
MIN_QUOTE_LEN: int = 8
MIN_MATCH_RATIO: float = 0.72


class FactValidator:
    """Validate facts before upsert into events table."""

    def __init__(self) -> None:
        # English + Russian future markers
        self._future_markers = {
            # English
            "will", "shall", "would", "plan", "intend", "promise", "commit",
            "going to", "going", "scheduled", "planned",
            # Russian
            "буду", "будет", "будут", "будешь", "планирую", "собираюсь",
            "обещаю", "пообещаю", "собой", "обязуюсь", "обязуюсь",
        }
        # English + Russian negations
        self._negations = {
            # English
            "not", "no", "never", "n't", "can't", "won't", "don't", "doesn't",
            # Russian
            "не", "нет", "никогда", "нельзя", "невозможно",
        }
        # English + Russian vague words
        self._vague_words = {
            # English
            "probably", "maybe", "perhaps", "might", "could", "seem",
            "appears", "possibly", "roughly", "approximately", "kinda", "sorta",
            # Russian
            "может", "может быть", "наверное", "похоже", "кажется",
            "возможно", "примерно", "вроде", "кой-как", "как-то",
        }

    def validate(self, fact: dict[str, Any], transcript_text: str | None = None) -> dict[str, Any]:
        """
        Validate a single fact before upsert.

        Args:
            fact: Extracted fact dict from LLM (must have 'quote' key)
            transcript_text: Optional full transcript for citation verification

        Returns:
            {
                'valid': bool,
                'errors': list[str],
                'warnings': list[str],
                'speaker': 'me' | 's2' | 'unknown',
                'is_future': bool,
                'is_negated': bool,
                'is_vague': bool,
            }
        """
        errors = []
        warnings = []
        quote = (fact.get("quote") or "").strip()

        # ── Check 1: Quote length ─────────────────────────────────────────
        if len(quote) < MIN_QUOTE_LEN:
            errors.append(f"quote too short ({len(quote)} < {MIN_QUOTE_LEN})")

        # ── Check 2: Verbatimness (rolling window search) ──────────────────
        speaker = "unknown"
        if transcript_text and quote:
            ratio, detected_speaker = self._find_best_match(quote, transcript_text)
            speaker = detected_speaker
            if ratio < MIN_MATCH_RATIO:
                errors.append(
                    f"quote not found in transcript (ratio={ratio:.2f} < {MIN_MATCH_RATIO})"
                )
            elif ratio < 0.85:
                warnings.append(
                    f"quote match is loose (ratio={ratio:.2f}); may need cleanup"
                )
        elif transcript_text is None and quote:
            # No transcript provided — skip verbatimness check but warn
            warnings.append("transcript_text not provided; skipping citation verification")
        else:
            warnings.append("empty quote; cannot verify")

        # ── Check 3: Semantic analysis ───────────────────────────────────
        is_future = self._contains_future_marker(quote)
        is_negated = self._contains_negation(quote)
        is_vague = self._contains_vague_word(quote)

        if is_future:
            warnings.append("quote contains future-tense marker (may be commitment, not fact)")
        if is_vague:
            warnings.append("quote contains vague language (low confidence)")
        if is_negated and is_vague:
            warnings.append("quote is both negated and vague (very low confidence)")

        # ── Return validation result ──────────────────────────────────────
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "speaker": speaker,
            "is_future": is_future,
            "is_negated": is_negated,
            "is_vague": is_vague,
        }

    def _find_best_match(self, quote: str, transcript_text: str) -> tuple[float, str]:
        """
        Find best matching substring in transcript using rolling window.

        Returns:
            (ratio: float, speaker: str)
            ratio in [0.0, 1.0]; speaker in {'me', 's2', 'unknown'}
        """
        if not quote or not transcript_text:
            return 0.0, "unknown"

        best_ratio = 0.0
        best_speaker = "unknown"
        quote_lower = quote.lower()
        transcript_lower = transcript_text.lower()

        # Try exact substring match first (fastest)
        if quote_lower in transcript_lower:
            return 1.0, self._detect_speaker_context(quote, transcript_text)

        # Rolling window search
        quote_len = len(quote)
        for i in range(len(transcript_lower) - quote_len + 1):
            window = transcript_lower[i : i + quote_len]
            ratio = SequenceMatcher(None, quote_lower, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_speaker = self._detect_speaker_context(
                    transcript_text[i : i + quote_len], transcript_text
                )

        return best_ratio, best_speaker

    def _detect_speaker_context(self, text_snippet: str, full_transcript: str) -> str:
        """Detect speaker attribution from context around text snippet."""
        idx = full_transcript.lower().find(text_snippet.lower())
        if idx < 0:
            return "unknown"

        # Look backwards up to 100 chars for [me] or [s2]
        lookback_start = max(0, idx - 100)
        lookback = full_transcript[lookback_start:idx]

        # Find last occurrence of speaker marker
        last_me = lookback.rfind("[me]")
        last_s2 = lookback.rfind("[s2]")

        if last_me > last_s2:
            return "me"
        elif last_s2 > last_me:
            return "s2"
        else:
            return "unknown"

    def _contains_future_marker(self, text: str) -> bool:
        """Check if text contains future-tense language."""
        text_lower = text.lower()
        for marker in self._future_markers:
            if re.search(r"\b" + re.escape(marker) + r"\b", text_lower):
                return True
        return False

    def _contains_negation(self, text: str) -> bool:
        """Check if text contains negation."""
        text_lower = text.lower()
        for neg in self._negations:
            if re.search(r"\b" + re.escape(neg) + r"\b", text_lower):
                return True
        return False

    def _contains_vague_word(self, text: str) -> bool:
        """Check if text contains vague language."""
        text_lower = text.lower()
        for vague in self._vague_words:
            if re.search(r"\b" + re.escape(vague) + r"\b", text_lower):
                return True
        return False
