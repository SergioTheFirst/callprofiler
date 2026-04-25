# -*- coding: utf-8 -*-
"""
graph/llm_disambiguator.py — LLM-assisted entity disambiguation.

Used ONLY for gray-zone merge candidates (score 0.50 – 0.64).
The LLM provides reasoned doubt, NOT a merge decision.
Final decision always belongs to the user.

Confidence thresholds:
  >= 0.65 → manual merge (EntityResolver, no LLM)
  0.50 – 0.64 → LLM advisory (this module)
  < 0.50 → skip (not a candidate)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"
LLM_TIMEOUT = 60
PROMPT_PATH = Path(__file__).parent.parent.parent.parent / "configs" / "prompts" / "entity_disambiguation.txt"

GRAY_ZONE_MIN = 0.50
GRAY_ZONE_MAX = 0.64


class LLMDisambiguator:
    """LLM-assisted disambiguation for gray-zone entity pairs.

    The LLM is advisory only: it returns structured signals for/against merge,
    but never issues a merge decision. The caller (CLI or UI) presents the
    reasoning to the user who decides.
    """

    def __init__(self, llm_url: str = LLM_URL, timeout: int = LLM_TIMEOUT) -> None:
        self._llm_url = llm_url
        self._timeout = timeout
        self._prompt_template = self._load_prompt()

    def _load_prompt(self) -> str:
        try:
            return PROMPT_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            log.warning("[disambiguator] prompt file not found: %s", PROMPT_PATH)
            return ""

    def in_gray_zone(self, score: float) -> bool:
        return GRAY_ZONE_MIN <= score <= GRAY_ZONE_MAX

    def disambiguate_pair(
        self,
        entity_a: dict,
        entity_b: dict,
        score: float,
        signals: dict,
    ) -> dict:
        """Request LLM analysis for a gray-zone pair.

        Returns:
          {
            "llm_says": "MERGE" | "SEPARATE" | "UNCLEAR",
            "confidence": float,   # LLM's self-reported confidence 0-1
            "reasoning": str,      # LLM's argument
            "signals_for": [...],  # textual clues supporting merge
            "signals_against": [...],  # textual clues against merge
            "raw_response": str,
          }

        The "llm_says" field is advisory — do NOT auto-merge based on it.
        """
        if not self.in_gray_zone(score):
            raise ValueError(
                f"score={score:.3f} outside gray zone [{GRAY_ZONE_MIN}, {GRAY_ZONE_MAX}]"
            )

        if not self._prompt_template:
            return {
                "llm_says": "UNCLEAR",
                "confidence": 0.0,
                "reasoning": "Prompt template missing",
                "signals_for": [],
                "signals_against": [],
                "raw_response": "",
            }

        prompt_body = self._build_prompt(entity_a, entity_b, score, signals)

        try:
            resp = requests.post(
                self._llm_url,
                json={
                    "messages": [{"role": "user", "content": prompt_body}],
                    "temperature": 0.1,
                    "max_tokens": 800,
                },
                timeout=self._timeout,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            log.warning("[disambiguator] LLM call failed: %s", exc)
            return {
                "llm_says": "UNCLEAR",
                "confidence": 0.0,
                "reasoning": f"LLM unavailable: {exc}",
                "signals_for": [],
                "signals_against": [],
                "raw_response": "",
            }

        return self._parse_response(raw)

    def _build_prompt(
        self, entity_a: dict, entity_b: dict, score: float, signals: dict
    ) -> str:
        a_json = json.dumps(
            {
                "canonical_name": entity_a.get("canonical_name", ""),
                "aliases": entity_a.get("aliases", []),
                "entity_type": entity_a.get("entity_type", ""),
                "call_count": entity_a.get("call_count", 0),
                "bs_index": entity_a.get("metrics", {}).get("bs_index") if entity_a.get("metrics") else None,
            },
            ensure_ascii=False,
            indent=2,
        )
        b_json = json.dumps(
            {
                "canonical_name": entity_b.get("canonical_name", ""),
                "aliases": entity_b.get("aliases", []),
                "entity_type": entity_b.get("entity_type", ""),
                "call_count": entity_b.get("call_count", 0),
                "bs_index": entity_b.get("metrics", {}).get("bs_index") if entity_b.get("metrics") else None,
            },
            ensure_ascii=False,
            indent=2,
        )
        signals_json = json.dumps(signals, ensure_ascii=False, indent=2)
        return (
            self._prompt_template
            .replace("{{ENTITY_A}}", a_json)
            .replace("{{ENTITY_B}}", b_json)
            .replace("{{SCORE}}", f"{score:.3f}")
            .replace("{{SIGNALS}}", signals_json)
        )

    def _parse_response(self, raw: str) -> dict:
        """Parse LLM JSON response. Falls back to UNCLEAR on parse error."""
        # Strip markdown fences
        text = raw
        if "```" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {
                "llm_says": "UNCLEAR",
                "confidence": 0.0,
                "reasoning": raw[:500],
                "signals_for": [],
                "signals_against": [],
                "raw_response": raw,
            }

        verdict = str(data.get("verdict", "UNCLEAR")).upper()
        if verdict not in ("MERGE", "SEPARATE", "UNCLEAR"):
            verdict = "UNCLEAR"

        return {
            "llm_says": verdict,
            "confidence": float(data.get("confidence", 0.0)),
            "reasoning": str(data.get("reasoning", "")),
            "signals_for": list(data.get("signals_for", [])),
            "signals_against": list(data.get("signals_against", [])),
            "raw_response": raw,
        }
