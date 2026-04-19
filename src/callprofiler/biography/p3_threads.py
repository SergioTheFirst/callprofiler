# -*- coding: utf-8 -*-
"""
p3_threads.py — Pass 3: Thread Builder.

For each recurring entity (mention_count >= MIN_MENTIONS), pull its
chronological scenes and ask the LLM to write a 2-4 paragraph thread
summary plus a per-scene tension curve. Stored in bio_threads.
"""

from __future__ import annotations

import logging
import time

from callprofiler.biography.json_utils import extract_json
from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.prompts import build_thread_prompt
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p3_threads"
MIN_MENTIONS = 2
MAX_SCENES_PER_THREAD = 30


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
) -> dict:
    entities = bio.get_entities_for_user(user_id, min_mentions=MIN_MENTIONS)
    log.info("[p3_threads] user=%s candidate_entities=%d", user_id, len(entities))

    bio.start_checkpoint(user_id, PASS_NAME, len(entities) or 1)

    processed = 0
    failed = 0
    began = time.monotonic()

    for e in entities:
        entity_id = int(e["entity_id"])
        name = e["canonical_name"]
        etype = e["entity_type"]

        scenes = bio.get_scenes_for_entity(entity_id)
        # If too many, keep top by importance, re-sort chronologically.
        if len(scenes) > MAX_SCENES_PER_THREAD:
            top = sorted(
                scenes, key=lambda s: int(s.get("importance") or 0), reverse=True
            )[:MAX_SCENES_PER_THREAD]
            scenes = sorted(top, key=lambda s: s.get("call_datetime") or "")

        if len(scenes) < MIN_MENTIONS:
            processed += 1
            bio.tick_checkpoint(user_id, PASS_NAME, f"entity:{entity_id}")
            continue

        messages = build_thread_prompt(name, etype, scenes)
        response = llm.call(
            user_id=user_id,
            pass_name=PASS_NAME,
            context_key=f"thread:entity:{entity_id}",
            messages=messages,
            temperature=0.35,
            max_tokens=2500,
        )
        data = extract_json(response) if response else None

        if not isinstance(data, dict):
            failed += 1
            bio.tick_checkpoint(
                user_id, PASS_NAME, f"entity:{entity_id}",
                processed_delta=1, failed_delta=1,
            )
            continue

        title = (data.get("title") or f"{name}")[:200]
        summary = data.get("summary") or ""
        curve = data.get("tension_curve") or []
        if not isinstance(curve, list):
            curve = []

        scene_ids = [int(s["scene_id"]) for s in scenes]
        start_date = scenes[0].get("call_datetime")
        end_date = scenes[-1].get("call_datetime")

        bio.upsert_thread(
            user_id=user_id,
            entity_id=entity_id,
            title=title,
            scene_ids=scene_ids,
            start_date=start_date,
            end_date=end_date,
            summary=summary,
            tension_curve=curve,
        )
        processed += 1
        bio.tick_checkpoint(user_id, PASS_NAME, f"entity:{entity_id}")

    bio.finish_checkpoint(user_id, PASS_NAME, "done")
    stats = {
        "entities": len(entities),
        "threads_written": processed - failed,
        "failed": failed,
        "elapsed_sec": round(time.monotonic() - began, 1),
    }
    log.info("[p3_threads] done %s", stats)
    return stats
