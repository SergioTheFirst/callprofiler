# -*- coding: utf-8 -*-
"""
p4_arcs.py — Pass 4: Arc Detector.

Scans the whole scene corpus in chronological batches and asks the LLM to
identify multi-scene arcs (problems, projects, relationships, life events).
Arcs are stored in bio_arcs and cleared on every run (they are fully
derivable).

Batch strategy: we only look at scenes with importance >= MIN_IMPORTANCE
and feed them to the LLM in overlapping windows. The LLM returns arcs
with scene_indices referring to positions in the window; we map those
back to scene_ids and normalize entity_names to entity_ids.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from callprofiler.biography.json_utils import extract_json
from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.prompts import build_arc_prompt
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p4_arcs"
MIN_IMPORTANCE = 25
WINDOW_SIZE = 60
WINDOW_STRIDE = 45  # overlap of 15 scenes


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
    fresh: bool = True,
) -> dict:
    scenes = [
        s for s in bio.get_scenes_for_user(user_id, min_importance=MIN_IMPORTANCE)
        if s.get("status") == "ok"
    ]
    log.info("[p4_arcs] user=%s candidate_scenes=%d", user_id, len(scenes))

    if fresh:
        bio.clear_arcs(user_id)

    # Index entities by canonical name + alias for back-ref.
    all_entities = bio.get_entities_for_user(user_id, min_mentions=1)
    name_to_id: dict[str, int] = {}
    for e in all_entities:
        key = (e.get("canonical_name") or "").strip().lower()
        if key:
            name_to_id[key] = int(e["entity_id"])
        for a in e.get("aliases") or []:
            if isinstance(a, str):
                name_to_id[a.strip().lower()] = int(e["entity_id"])

    if not scenes:
        bio.finish_checkpoint(user_id, PASS_NAME, "done")
        return {"windows": 0, "arcs": 0, "elapsed_sec": 0}

    windows: list[list[dict]] = []
    i = 0
    while i < len(scenes):
        win = scenes[i : i + WINDOW_SIZE]
        if win:
            windows.append(win)
        if i + WINDOW_SIZE >= len(scenes):
            break
        i += WINDOW_STRIDE

    bio.start_checkpoint(user_id, PASS_NAME, len(windows))
    began = time.monotonic()
    arcs_written = 0
    failed = 0
    seen_titles: set[str] = set()

    for wi, win in enumerate(windows):
        ctx_key = f"arcs:window:{wi}"
        messages = build_arc_prompt(win)
        response = llm.call(
            user_id=user_id,
            pass_name=PASS_NAME,
            context_key=ctx_key,
            messages=messages,
            temperature=0.3,
            max_tokens=2800,
        )
        data = extract_json(response) if response else None
        if not isinstance(data, dict):
            failed += 1
            bio.tick_checkpoint(user_id, PASS_NAME, ctx_key,
                                processed_delta=1, failed_delta=1)
            continue

        arc_list = data.get("arcs") or []
        if not isinstance(arc_list, list):
            failed += 1
            bio.tick_checkpoint(user_id, PASS_NAME, ctx_key,
                                processed_delta=1, failed_delta=1)
            continue

        for a in arc_list:
            if not isinstance(a, dict):
                continue
            title = (a.get("title") or "").strip()
            if not title:
                continue
            dedup_key = title.lower()
            if dedup_key in seen_titles:
                continue

            indices = a.get("scene_indices") or []
            scene_ids: list[int] = []
            if isinstance(indices, list):
                for idx in indices:
                    try:
                        pos = int(idx)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= pos < len(win):
                        scene_ids.append(int(win[pos]["scene_id"]))
            if len(scene_ids) < 2:
                continue

            entity_names = a.get("entity_names") or []
            entity_ids: list[int] = []
            if isinstance(entity_names, list):
                seen: set[int] = set()
                for n in entity_names:
                    if not isinstance(n, str):
                        continue
                    eid = name_to_id.get(n.strip().lower())
                    if eid and eid not in seen:
                        seen.add(eid)
                        entity_ids.append(eid)

            # Derive dates from the chosen scenes if LLM didn't supply them.
            scene_dates = [
                s.get("call_datetime") for s in win
                if int(s["scene_id"]) in scene_ids and s.get("call_datetime")
            ]
            start_date = a.get("start_date") or (min(scene_dates) if scene_dates else None)
            end_date = a.get("end_date") or (max(scene_dates) if scene_dates else None)

            importance = int(a.get("importance") or 0)
            importance = max(0, min(100, importance))

            bio.insert_arc(
                user_id=user_id,
                title=title[:200],
                arc_type=(a.get("arc_type") or "project"),
                start_date=start_date,
                end_date=end_date,
                status=(a.get("status") or "ongoing"),
                synopsis=(a.get("synopsis") or ""),
                scene_ids=scene_ids,
                entity_ids=entity_ids,
                outcome=(a.get("outcome") or ""),
                importance=importance,
            )
            seen_titles.add(dedup_key)
            arcs_written += 1

        bio.tick_checkpoint(user_id, PASS_NAME, ctx_key, processed_delta=1)

    bio.finish_checkpoint(user_id, PASS_NAME, "done")
    stats = {
        "windows": len(windows),
        "arcs": arcs_written,
        "windows_failed": failed,
        "elapsed_sec": round(time.monotonic() - began, 1),
    }
    log.info("[p4_arcs] done %s", stats)
    return stats
