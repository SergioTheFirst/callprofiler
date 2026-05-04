# -*- coding: utf-8 -*-
"""
p5_portraits.py — Pass 5: Portrait Writer.

For each significant PERSON (or COMPANY/PLACE if important), write a deep
character sketch using the thread summary + top scenes. Stored in
bio_portraits, keyed by entity_id.
"""

from __future__ import annotations

import json
import logging
import time

from callprofiler.biography.json_utils import extract_json
from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.prompts import build_portrait_prompt
from callprofiler.biography.repo import BiographyRepo

try:
    from callprofiler.biography.data_extractor import get_entity_profile_from_graph
    _GRAPH_AVAILABLE = True
except ImportError:
    _GRAPH_AVAILABLE = False

log = logging.getLogger(__name__)

PASS_NAME = "p5_portraits"
MIN_MENTIONS = 3
MAX_PORTRAITS = 80
TOP_SCENES = 15


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
    graph_conn=None,
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
    done_ids = bio.get_completed_items(user_id, PASS_NAME)
    began = time.monotonic()
    written = 0
    failed = 0

    for e in candidates:
        entity_id = int(e["entity_id"])
        item_key = f"entity:{entity_id}"

        if item_key in done_ids:
            bio.tick_checkpoint(user_id, PASS_NAME, item_key,
                                notes="resumed")
            continue

        name = e["canonical_name"]
        etype = e["entity_type"]
        role = e.get("role")
        thread = threads_by_entity.get(entity_id)

        all_scenes = bio.get_scenes_for_entity(entity_id)
        # Deterministic sort for cache hit (importance-based selection breaks memoization)
        all_scenes.sort(key=lambda s: (s.get("call_datetime") or "", s.get("scene_id") or 0))
        top = all_scenes[:TOP_SCENES]
        if not top:
            bio.tick_checkpoint(user_id, PASS_NAME, f"entity:{entity_id}")
            continue

        behavior = bio.get_behavior_pattern_for_entity(user_id, entity_id)

        # Enrich with graph profile when available
        graph_profile: dict | None = None
        if _GRAPH_AVAILABLE and graph_conn is not None:
            try:
                geid = _resolve_graph_entity_id(
                    user_id=user_id,
                    canonical_name=name,
                    entity_type=etype,
                    contact_id=e.get("contact_id"),
                    graph_conn=graph_conn,
                )
                if geid is not None:
                    graph_profile = get_entity_profile_from_graph(geid, graph_conn)
            except Exception:
                pass

        if graph_profile and behavior:
            gm = graph_profile.get("metrics") or {}
            behavior.setdefault("bs_index", gm.get("bs_index"))
            behavior.setdefault("avg_risk", gm.get("avg_risk"))
            behavior.setdefault("total_calls", gm.get("total_calls"))

        # Load psychological profile from PsychologyProfiler when graph available
        temperament_data = None
        big_five_data = None
        motivation_data = None
        if _GRAPH_AVAILABLE and graph_conn is not None and graph_profile:
            geid = graph_profile.get("entity_id")
            if geid:
                temperament_data = graph_profile.get("temperament")
                big_five_data = graph_profile.get("big_five")
                motivation_data = graph_profile.get("motivation")

        messages = build_portrait_prompt(
            entity_name=name,
            entity_type=etype,
            role=role,
            thread_summary=(thread or {}).get("summary"),
            scenes=top,
            behavior=behavior,
            temperament=temperament_data,
            big_five=big_five_data,
            motivation=motivation_data,
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


def _resolve_graph_entity_id(
    *,
    user_id: str,
    canonical_name: str,
    entity_type: str,
    contact_id: int | None,
    graph_conn,
) -> int | None:
    entity_type_upper = entity_type.upper()

    if contact_id:
        row = graph_conn.execute(
            """SELECT e.id, COUNT(*) AS hits
               FROM entities e
               JOIN events ev ON ev.entity_id = e.id
               WHERE e.user_id = ? AND e.archived = 0
                 AND ev.contact_id = ?
                 AND (? = '' OR UPPER(e.entity_type) = ?)
               GROUP BY e.id
               ORDER BY hits DESC, e.updated_at DESC, e.id DESC
               LIMIT 1""",
            (user_id, contact_id, entity_type_upper, entity_type_upper),
        ).fetchone()
        if row:
            return int(row["id"])

    norm = "".join(ch.lower() for ch in canonical_name if ch.isalnum())
    if not norm:
        return None
    rows = graph_conn.execute(
        """SELECT id, canonical_name, aliases
           FROM entities
           WHERE user_id = ? AND archived = 0
             AND (? = '' OR UPPER(entity_type) = ?)
           ORDER BY updated_at DESC, id DESC""",
        (user_id, entity_type_upper, entity_type_upper),
    ).fetchall()
    for row in rows:
        if "".join(ch.lower() for ch in (row["canonical_name"] or "") if ch.isalnum()) == norm:
            return int(row["id"])
        try:
            aliases = json.loads(row["aliases"] or "[]")
        except json.JSONDecodeError:
            aliases = []
        for alias in aliases:
            if "".join(ch.lower() for ch in (alias or "") if ch.isalnum()) == norm:
                return int(row["id"])
    return None
