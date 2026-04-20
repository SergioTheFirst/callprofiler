# -*- coding: utf-8 -*-
"""
p5_portraits.py — Pass 5: Portrait Writer.

For each significant PERSON (or COMPANY/PLACE if important), write a deep
character sketch using the thread summary + top scenes. Stored in
bio_portraits, keyed by entity_id.
"""

from __future__ import annotations

import logging
import time

from callprofiler.biography.json_utils import extract_json
from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.prompts import build_portrait_prompt
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p5_portraits"
MIN_MENTIONS = 3
MAX_PORTRAITS = 80
TOP_SCENES = 15


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
) -> dict:
    # Index threads by entity.
    threads_by_entity: dict[int, dict] = {}
    for t in bio.get_threads_for_user(user_id):
        eid = t.get("entity_id")
        if eid is not None:
            threads_by_entity[int(eid)] = t

    # Candidates: top entities sorted by importance/mentions.
    candidates = bio.get_entities_for_user(user_id, min_mentions=MIN_MENTIONS)
    candidates = [e for e in candidates
                  if e.get("entity_type") in ("PERSON", "COMPANY", "PLACE")]
    candidates = candidates[:MAX_PORTRAITS]
    log.info("[p5_portraits] candidates=%d", len(candidates))

    bio.start_checkpoint(user_id, PASS_NAME, len(candidates) or 1)
    began = time.monotonic()
    written = 0
    failed = 0

    for e in candidates:
        entity_id = int(e["entity_id"])
        name = e["canonical_name"]
        etype = e["entity_type"]
        role = e.get("role")
        thread = threads_by_entity.get(entity_id)

        all_scenes = bio.get_scenes_for_entity(entity_id)
        # Pick top by importance, preserve chronology.
        top = sorted(all_scenes, key=lambda s: int(s.get("importance") or 0),
                     reverse=True)[:TOP_SCENES]
        top.sort(key=lambda s: s.get("call_datetime") or "")
        if not top:
            bio.tick_checkpoint(user_id, PASS_NAME, f"entity:{entity_id}")
            continue

        behavior = bio.get_behavior_pattern_for_entity(user_id, entity_id)
        messages = build_portrait_prompt(
            entity_name=name,
            entity_type=etype,
            role=role,
            thread_summary=(thread or {}).get("summary"),
            scenes=top,
            behavior=behavior,
        )
        response = llm.call(
            user_id=user_id,
            pass_name=PASS_NAME,
            context_key=f"portrait:entity:{entity_id}",
            messages=messages,
            temperature=0.5,
            max_tokens=2500,
        )
        data = extract_json(response) if response else None
        if not isinstance(data, dict):
            failed += 1
            bio.tick_checkpoint(user_id, PASS_NAME, f"entity:{entity_id}",
                                processed_delta=1, failed_delta=1)
            continue

        prose = data.get("prose") or ""
        traits = data.get("traits") or []
        if not isinstance(traits, list):
            traits = []
        relationship = data.get("relationship") or ""
        pivotal_idx = data.get("pivotal_scene_indices") or []
        pivotal_scenes: list[int] = []
        if isinstance(pivotal_idx, list):
            for pi in pivotal_idx:
                try:
                    pos = int(pi)
                except (TypeError, ValueError):
                    continue
                if 0 <= pos < len(top):
                    pivotal_scenes.append(int(top[pos]["scene_id"]))

        bio.upsert_portrait(
            user_id=user_id,
            entity_id=entity_id,
            prose=prose,
            traits=[str(t)[:60] for t in traits][:8],
            relationship=relationship[:200],
            pivotal_scenes=pivotal_scenes,
        )
        written += 1
        bio.tick_checkpoint(user_id, PASS_NAME, f"entity:{entity_id}")

    bio.finish_checkpoint(user_id, PASS_NAME, "done")
    stats = {
        "candidates": len(candidates),
        "portraits_written": written,
        "failed": failed,
        "elapsed_sec": round(time.monotonic() - began, 1),
    }
    log.info("[p5_portraits] done %s", stats)
    return stats
