# -*- coding: utf-8 -*-
"""
llm_client.py — resilient memoizing wrapper around callprofiler.analyze.LLMClient.

Every prompt is hashed (MD5 of messages + temp + max_tokens + model). If that
hash was previously answered with status='ok' in bio_llm_calls, the cached
response is returned without contacting the server. Fresh calls are logged
to bio_llm_calls regardless of outcome (cached/ok/retry/failed).

Retry policy: up to N attempts with exponential backoff. Failures do not raise;
they return None so the orchestrator can mark the item as 'failed' in its
checkpoint and continue the pass.

This is the core enabler of multi-day runs: after a crash/restart, every pass
picks up where it stopped without redoing any completed LLM work.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from callprofiler.analyze.llm_client import LLMClient
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)


def prompt_hash(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    model: str,
) -> str:
    payload = json.dumps(
        {
            "messages": messages,
            "temperature": round(float(temperature), 4),
            "max_tokens": int(max_tokens),
            "model": model or "",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


class ResilientLLMClient:
    """Memoize + retry wrapper around the plain LLMClient."""

    def __init__(
        self,
        llm: LLMClient,
        bio_repo: BiographyRepo,
        model_name: str = "qwen3.5-9b",
        max_retries: int = 4,
        backoff_base_sec: float = 5.0,
    ) -> None:
        self.llm = llm
        self.repo = bio_repo
        self.model_name = model_name
        self.max_retries = max_retries
        self.backoff_base_sec = backoff_base_sec

    def call(
        self,
        user_id: str,
        pass_name: str,
        context_key: str,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1500,
        force_refresh: bool = False,
    ) -> str | None:
        """Return LLM completion text (cached when possible), None on permanent failure."""
        phash = prompt_hash(messages, temperature, max_tokens, self.model_name)

        if not force_refresh:
            cached = self.repo.get_cached_llm(phash)
            if cached and cached.get("response"):
                log.debug(
                    "LLM cache HIT pass=%s ctx=%s hash=%s",
                    pass_name, context_key, phash[:8],
                )
                self.repo.log_llm_call(
                    user_id=user_id,
                    pass_name=pass_name,
                    context_key=context_key,
                    prompt_hash=phash,
                    prompt_preview=_preview(messages),
                    response=cached["response"],
                    duration_sec=0.0,
                    status="cached",
                    error=None,
                    model=self.model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return cached["response"]

        last_error: str | None = None
        for attempt in range(1, self.max_retries + 1):
            started = time.monotonic()
            try:
                response = self.llm.generate(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                elapsed = time.monotonic() - started
            except Exception as exc:  # noqa: BLE001 — never break a multi-day run
                elapsed = time.monotonic() - started
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning(
                    "LLM call raised (attempt %d/%d) pass=%s ctx=%s err=%s",
                    attempt, self.max_retries, pass_name, context_key, last_error,
                )
                self.repo.log_llm_call(
                    user_id=user_id,
                    pass_name=pass_name,
                    context_key=context_key,
                    prompt_hash=phash,
                    prompt_preview=_preview(messages),
                    response=None,
                    duration_sec=elapsed,
                    status="retry",
                    error=last_error,
                    model=self.model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                self._sleep_backoff(attempt)
                continue

            if response:
                self.repo.log_llm_call(
                    user_id=user_id,
                    pass_name=pass_name,
                    context_key=context_key,
                    prompt_hash=phash,
                    prompt_preview=_preview(messages),
                    response=response,
                    duration_sec=elapsed,
                    status="ok",
                    error=None,
                    model=self.model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response

            # response is None: server returned something unparseable or timed out.
            last_error = "empty response"
            log.warning(
                "LLM returned None (attempt %d/%d) pass=%s ctx=%s",
                attempt, self.max_retries, pass_name, context_key,
            )
            self.repo.log_llm_call(
                user_id=user_id,
                pass_name=pass_name,
                context_key=context_key,
                prompt_hash=phash,
                prompt_preview=_preview(messages),
                response=None,
                duration_sec=elapsed,
                status="retry",
                error=last_error,
                model=self.model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            self._sleep_backoff(attempt)

        # All retries exhausted.
        self.repo.log_llm_call(
            user_id=user_id,
            pass_name=pass_name,
            context_key=context_key,
            prompt_hash=phash,
            prompt_preview=_preview(messages),
            response=None,
            duration_sec=0.0,
            status="failed",
            error=last_error or "exhausted retries",
            model=self.model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return None

    def _sleep_backoff(self, attempt: int) -> None:
        delay = self.backoff_base_sec * (2 ** (attempt - 1))
        log.info("LLM backoff sleep=%.1fs before next attempt", delay)
        time.sleep(delay)


def _preview(messages: list[dict]) -> str:
    try:
        # last user message is usually the informative one
        for m in reversed(messages):
            if m.get("role") == "user":
                return str(m.get("content", ""))[:400]
        return json.dumps(messages, ensure_ascii=False)[:400]
    except Exception:  # noqa: BLE001
        return ""
