# -*- coding: utf-8 -*-
"""
analyze/service.py — unified LLM analysis service for both bulk_enrich and orchestrator.

Single place that:
  1. Builds OpenAI-format messages from transcript + metadata + context.
  2. Calls LLMClient (with retry/memoization via ResilientLLMClient where available).
  3. Parses the response via response_parser.
  4. Returns a typed Analysis result.

Both bulk_enrich and Orchestrator._analyze_call should call this service
instead of duplicating prompt building, LLM invocation, and parsing logic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from callprofiler.analyze.llm_client import LLMClient
from callprofiler.analyze.output_budget import output_budget
from callprofiler.analyze.prompt_budget import estimate_tokens
from callprofiler.analyze.prompt_builder import PromptBuilder
from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.config import Config
from callprofiler.db.repository import Repository
from callprofiler.models import Analysis

log = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self, config: Config, repo: Repository) -> None:
        self.config = config
        self.repo = repo
        self.llm = LLMClient(base_url=config.models.llm_url)
        self.prompt_builder = PromptBuilder(config.prompts_dir)

    def analyze_one_call(
        self,
        call: dict[str, Any],
        segments: list[dict[str, Any]] | list[Any],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.3,
        prompt_version: str = "v001",
    ) -> Analysis:
        call_id = call["call_id"]
        user_id = call["user_id"]
        contact_id = call.get("contact_id")

        # Format transcript
        transcript_text = _format_transcript(segments)

        # Get context
        previous_summaries: list[str] = []
        if contact_id:
            prev_analyses = self.repo.get_recent_analyses(user_id, contact_id, limit=5)
            previous_summaries = [
                a.get("summary", "") for a in prev_analyses if a.get("summary")
            ]

        # Get metadata
        contact = self.repo.get_contact(user_id, contact_id) if contact_id else None
        metadata = {
            "contact_name": contact.get("display_name") if contact else None,
            "phone": contact.get("phone_e164") if contact else None,
            "call_datetime": call.get("call_datetime"),
            "direction": call.get("direction", "UNKNOWN"),
        }

        # Build prompt (returns str or dict with system/user keys)
        prompt = self.prompt_builder.build(
            transcript_text, metadata, previous_summaries, version=prompt_version
        )

        # Build messages
        if isinstance(prompt, dict) and "system" in prompt:
            messages = [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ]
        else:
            messages = [{"role": "user", "content": str(prompt)}]

        # Динамический бюджет вывода: длинные/ценные звонки получают больше
        # места под JSON, короткие не резервируют лишнее. Потолок — окно модели
        # минус оценка промпта (max_tokens — это потолок, не цель; KV-кэш
        # выделён на старте, так что это стоит времени, а не VRAM).
        if max_tokens is None:
            prompt_tokens = sum(estimate_tokens(m["content"]) for m in messages)
            budget = output_budget(
                transcript_chars=len(transcript_text),
                prompt_tokens=prompt_tokens,
                n_ctx=self.config.models.llm_n_ctx,
            )
        else:
            budget = max_tokens

        # Call LLM
        truncated = False
        try:
            result = self.llm.complete(
                messages=messages, temperature=temperature, max_tokens=budget
            )
            raw_response = result.text or ""
            truncated = result.truncated
            if truncated:
                log.warning(
                    "[AnalysisService] call_id=%s: вывод обрезан (max_tokens=%d) — "
                    "JSON может быть неполным",
                    call_id, budget,
                )
        except (ConnectionError, RuntimeError) as exc:
            log.error("[AnalysisService] LLM unavailable for call_id=%s: %s", call_id, exc)
            raw_response = ""

        # Parse response
        analysis = parse_llm_response(
            raw_response,
            model=self.config.models.llm_model,
            prompt_version=prompt_version,
        )

        # Пометить обрезку для ручного просмотра (pipeline.md → output_truncated),
        # не затирая более информативный parse_failed.
        if truncated and getattr(analysis, "parse_status", None) != "parse_failed":
            if hasattr(analysis, "parse_status"):
                analysis.parse_status = "output_truncated"

        return analysis


def _format_transcript(segments: list[dict[str, Any]] | list[Any]) -> str:
    """Format segments into text for the LLM prompt."""
    parts: list[str] = []
    for s in segments:
        if hasattr(s, "speaker") and hasattr(s, "text"):
            speaker = s.speaker.upper()
            role = "[me]" if speaker == "OWNER" else ("[s2]" if speaker == "OTHER" else "[?]")
            text = (s.text or "").strip()
            if text:
                parts.append(f"{role}: {text}")
        elif isinstance(s, dict):
            speaker = (s.get("speaker") or "UNKNOWN").upper()
            role = "[me]" if speaker == "OWNER" else ("[s2]" if speaker == "OTHER" else "[?]")
            text = (s.get("text") or "").strip()
            if text:
                parts.append(f"{role}: {text}")
    return "\n".join(parts)