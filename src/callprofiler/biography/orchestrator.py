# -*- coding: utf-8 -*-
"""
orchestrator.py — top-level runner for the 8-pass biography pipeline.

Designed for multi-day runs. Every pass is resumable via bio_checkpoints,
every LLM call memoized via bio_llm_calls. Crashes, power cuts, model
swaps — a re-run skips work already done and continues.

Usage:
    bio = BiographyRepo(host_repo)
    llm_core = LLMClient(config.models.llm_url)
    rllm = ResilientLLMClient(llm_core, bio, model_name="qwen3.5-9b")
    orch = Orchestrator(user_id, bio, rllm)
    orch.run_all()

Or a subset:
    orch.run_passes(["p1_scene", "p2_entities"])
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from callprofiler.biography import (
    p1_scene,
    p2_entities,
    p3_threads,
    p3b_behavioral,
    p4_arcs,
    p5_portraits,
    p6_chapters,
    p7_book,
    p8_editorial,
    p8b_doc_dedup,
    p9_yearly,
)
from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)


PassRunner = Callable[..., dict]


class Orchestrator:
    PASSES: dict[str, PassRunner] = {
        "p1_scene":        p1_scene.run,
        "p2_entities":     p2_entities.run,
        "p3_threads":      p3_threads.run,
        "p3b_behavioral":  p3b_behavioral.run,
        "p4_arcs":         p4_arcs.run,
        "p5_portraits":    p5_portraits.run,
        "p6_chapters":     p6_chapters.run,
        "p8_editorial":    p8_editorial.run,
        "p8b_doc_dedup":   p8b_doc_dedup.run,
        "p7_book":         p7_book.run,
        "p9_yearly":       p9_yearly.run,
    }

    # Canonical execution order:
    # behavioral engine (p3b) enriches portraits (p5) and chapters (p6)
    # edit chapters (p8) → cross-chapter dedup (p8b) → assemble book (p7) → yearly (p9)
    ORDER = [
        "p1_scene", "p2_entities", "p3_threads", "p3b_behavioral",
        "p4_arcs", "p5_portraits", "p6_chapters",
        "p8_editorial", "p8b_doc_dedup", "p7_book",
        "p9_yearly",
    ]

    def __init__(
        self,
        user_id: str,
        bio: BiographyRepo,
        llm: ResilientLLMClient,
    ) -> None:
        self.user_id = user_id
        self.bio = bio
        self.llm = llm

    def run_all(self, **pass_kwargs) -> dict:
        return self.run_passes(self.ORDER, **pass_kwargs)

    def run_passes(self, passes: list[str], **pass_kwargs) -> dict:
        results: dict[str, dict] = {}
        overall_start = time.monotonic()
        for name in passes:
            if name not in self.PASSES:
                log.warning("unknown pass: %s", name)
                continue
            log.info("=" * 60)
            log.info("  PASS %s  user=%s", name, self.user_id)
            log.info("=" * 60)
            kw = pass_kwargs.get(name, {}) or {}
            if name in ("p5_portraits", "p6_chapters"):
                kw.setdefault("graph_conn", self.bio.conn)
            try:
                results[name] = self.PASSES[name](
                    user_id=self.user_id, bio=self.bio, llm=self.llm, **kw,
                )
            except Exception as exc:  # noqa: BLE001 — multi-day resilience
                log.exception("pass %s crashed: %s", name, exc)
                results[name] = {"error": str(exc)}
                # Mark checkpoint failed but continue to next pass.
                try:
                    self.bio.finish_checkpoint(self.user_id, name, "failed")
                except Exception:  # noqa: BLE001
                    pass
        results["_total_sec"] = round(time.monotonic() - overall_start, 1)
        log.info("=" * 60)
        log.info("  BIOGRAPHY PIPELINE DONE in %.1f sec", results["_total_sec"])
        log.info("=" * 60)
        return results

    def status(self) -> list[dict]:
        """Return per-pass checkpoint status for monitoring."""
        out: list[dict] = []
        for name in self.ORDER:
            cp = self.bio.get_checkpoint(self.user_id, name)
            out.append({
                "pass": name,
                "status": (cp or {}).get("status", "not_started"),
                "processed": (cp or {}).get("processed_items", 0),
                "total": (cp or {}).get("total_items", 0),
                "failed": (cp or {}).get("failed_items", 0),
                "last_item_key": (cp or {}).get("last_item_key"),
                "updated_at": (cp or {}).get("updated_at"),
            })
        return out
