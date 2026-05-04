# -*- coding: utf-8 -*-
"""
p2_entities.py — Pass 2: Entity Resolver.

Collects every `named_entities[*]` mention from bio_scenes, groups by
(entity_type, normalized name), then sends the per-type list to the LLM
to merge aliases into canonical entities. Writes to bio_entities and
re-populates bio_scene_entities.

Chunking: a user can accumulate thousands of mentions; we send up to
CHUNK_SIZE mentions per LLM call and union the results. Canonical
matching across chunks uses find_entity_by_alias (case-insensitive) so
re-runs don't re-split.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from callprofiler.biography.json_utils import extract_json
from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.prompts import PROMPT_VERSION, build_entity_prompt
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p2_entities"
CHUNK_SIZE = 80
VALID_TYPES = {"PERSON", "PLACE", "COMPANY", "PROJECT", "EVENT"}


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
) -> dict:
    scenes = bio.get_scenes_for_user(user_id, min_importance=0)
    log.info("[p2_entities] user=%s scenes=%d", user_id, len(scenes))

    # 1) Collect raw mentions grouped by type.
    mentions_by_type: dict[str, list[dict]] = defaultdict(list)
    # Index: (type, normalized_surface) -> list of scene_ids observed
    scene_index: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)

    for sc in scenes:
        scene_id = int(sc["scene_id"])
        for ent in sc.get("named_entities") or []:
            if not isinstance(ent, dict):
                continue
            name = (ent.get("name") or "").strip()
            etype = (ent.get("type") or "").strip().upper()
            mention = (ent.get("mention") or name).strip()
            if not name or etype not in VALID_TYPES:
                continue
            key = (etype, name.lower())
            scene_index[key].append((scene_id, mention))
            mentions_by_type[etype].append({
                "name": name,
                "context": (sc.get("synopsis") or "")[:180],
            })

    total_types = sum(1 for v in mentions_by_type.values() if v)
    bio.start_checkpoint(user_id, PASS_NAME, total_types or 1)

    # Resume support: skip already-completed types
    completed_items = bio.get_completed_items(user_id, PASS_NAME)
    log.info("[p2_entities] completed_items=%s", completed_items)

    processed = 0
    failed = 0
    created = 0
    linked = 0
    began = time.monotonic()

    for etype, mentions in mentions_by_type.items():
        item_key = f"type:{etype}"
        if item_key in completed_items:
            log.info("[p2_entities] SKIP %s (already done)", item_key)
            processed += 1
            continue
        # deduplicate surface forms per chunk to save tokens
        deduped: dict[str, dict] = {}
        for m in mentions:
            key = m["name"].strip().lower()
            if key and key not in deduped:
                deduped[key] = m
        uniq = list(deduped.values())
        log.info("[p2_entities] type=%s unique_mentions=%d", etype, len(uniq))

        canonicalized: list[dict] = []
        for i in range(0, len(uniq), CHUNK_SIZE):
            chunk = uniq[i : i + CHUNK_SIZE]
            ctx_key = f"entities:{etype}:chunk{i//CHUNK_SIZE}"
            messages = build_entity_prompt(etype, chunk)
            response = llm.call(
                user_id=user_id,
                pass_name=PASS_NAME,
                context_key=ctx_key,
                messages=messages,
                temperature=0.2,
                max_tokens=3800,
            )
            data = extract_json(response) if response else None
            if not isinstance(data, dict):
                log.warning("[p2_entities] parse failed %s", ctx_key)
                failed += 1
                continue
            ents = data.get("entities") or []
            if not isinstance(ents, list):
                failed += 1
                continue
            for e in ents:
                if isinstance(e, dict) and e.get("canonical"):
                    canonicalized.append(e)

        # 2) Upsert canonical entities; merge with existing rows.
        for e in canonicalized:
            canonical = (e.get("canonical") or "").strip()
            if not canonical:
                continue
            aliases = [a for a in (e.get("aliases") or []) if isinstance(a, str) and a.strip()]
            # Ensure canonical is in aliases for alias lookup later.
            if canonical not in aliases:
                aliases.insert(0, canonical)

            # Reuse existing entity if any alias already maps somewhere.
            existing = None
            for a in aliases:
                existing = bio.find_entity_by_alias(user_id, etype, a)
                if existing:
                    break
            if existing:
                entity_id = bio.upsert_entity(
                    user_id=user_id,
                    canonical_name=existing["canonical_name"],
                    entity_type=etype,
                    aliases=aliases,
                    role=e.get("role"),
                    description=e.get("description"),
                )
            else:
                entity_id = bio.upsert_entity(
                    user_id=user_id,
                    canonical_name=canonical,
                    entity_type=etype,
                    aliases=aliases,
                    role=e.get("role"),
                    description=e.get("description"),
                )
                created += 1

            # 3) Link this entity to every scene whose mention matches an alias.
            for alias in aliases:
                lookup_key = (etype, alias.strip().lower())
                for (scene_id, mention_text) in scene_index.get(lookup_key, []):
                    bio.link_scene_entity(scene_id, entity_id, mention_text)
                    linked += 1

        processed += 1
        bio.tick_checkpoint(
            user_id, PASS_NAME, f"type:{etype}",
            processed_delta=1,
            failed_delta=0,
            notes=f"created={created} linked={linked}",
        )

    # 4) Recompute stats (first_seen, last_seen, mention_count, importance).
    bio.refresh_entity_stats(user_id)
    bio.finish_checkpoint(user_id, PASS_NAME, "done")

    stats = {
        "scene_count": len(scenes),
        "types_processed": processed,
        "chunks_failed": failed,
        "entities_created": created,
        "scene_links": linked,
        "elapsed_sec": round(time.monotonic() - began, 1),
    }
    log.info("[p2_entities] done %s", stats)
    return stats
