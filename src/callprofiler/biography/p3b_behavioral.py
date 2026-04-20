# -*- coding: utf-8 -*-
"""
p3b_behavioral.py — Pass 3b: Behavioral Pattern Engine.

Deterministic, no LLM. Computes behavioral signals per PERSON entity from
existing bio_scenes + calls data. Runs after p3_threads, before p4_arcs.

Outputs (into bio_behavior_patterns per entity):
  - trust_score (0-100)
  - volatility (std dev of scene importance)
  - dependency (fraction of owner-initiated calls = initiator_out_ratio)
  - role_type: initiator | responder | mixed
  - conflict_count

Also logs contradiction pairs (bio_contradictions) for high-importance conflict
scenes spaced ≥14 days apart for the same entity.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime

from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p3b_behavioral"

MIN_SCENES = 2
CONFLICT_SCENE_TYPES = frozenset({"conflict"})
CONFLICT_TONES = frozenset({"tense", "angry"})
CONTRADICTION_MIN_IMPORTANCE = 40
CONTRADICTION_MIN_DAYS = 14


def _std_dev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    n = len(values)
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / n)


def _day_delta(dt1: str | None, dt2: str | None) -> int:
    if not dt1 or not dt2:
        return 0
    try:
        fmt = "%Y-%m-%d"
        d1 = datetime.strptime(dt1[:10], fmt)
        d2 = datetime.strptime(dt2[:10], fmt)
        return abs((d2 - d1).days)
    except (ValueError, TypeError):
        return 0


def _compute_trust_score(
    conflict_count: int,
    call_count: int,
    promise_kept: int,
    promise_broken: int,
    avg_importance: float,
) -> float:
    base = 50.0
    if call_count:
        conflict_ratio = conflict_count / call_count
        base -= conflict_ratio * 30
    base += promise_kept * 3
    base -= promise_broken * 8
    if avg_importance > 65:
        base += 8
    return max(0.0, min(100.0, base))


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
) -> dict:
    entities = bio.get_entities_for_user(user_id, entity_type="PERSON", min_mentions=2)
    log.info("[p3b] entities_to_process=%d", len(entities))
    bio.start_checkpoint(user_id, PASS_NAME, len(entities) or 1)
    began = time.monotonic()
    computed = 0
    contradictions_found = 0

    for entity in entities:
        entity_id = int(entity["entity_id"])
        contact_id = entity.get("contact_id")

        scenes = bio.get_scenes_for_entity(entity_id)
        if len(scenes) < MIN_SCENES:
            bio.tick_checkpoint(user_id, PASS_NAME, f"entity:{entity_id}")
            continue

        conflict_count = sum(
            1 for s in scenes
            if s.get("scene_type") in CONFLICT_SCENE_TYPES
            or s.get("emotional_tone") in CONFLICT_TONES
        )

        importance_vals = [
            float(s.get("importance") or 0) for s in scenes
            if s.get("importance")
        ]
        volatility = _std_dev(importance_vals)
        avg_importance = (
            sum(importance_vals) / len(importance_vals) if importance_vals else 0.0
        )

        call_count = len(scenes)
        initiator_out_ratio = 0.5
        if contact_id:
            calls = bio.get_calls_for_contact(int(contact_id), user_id)
            if calls:
                call_count = len(calls)
                outbound = sum(
                    1 for c in calls
                    if (c.get("direction") or "").lower() in (
                        "outgoing", "out", "outbound"
                    )
                )
                initiator_out_ratio = outbound / call_count

        if initiator_out_ratio > 0.65:
            role_type = "initiator"
        elif initiator_out_ratio < 0.35:
            role_type = "responder"
        else:
            role_type = "mixed"

        trust_score = _compute_trust_score(
            conflict_count, call_count, 0, 0, avg_importance
        )

        bio.upsert_behavior_pattern(
            user_id=user_id,
            entity_id=entity_id,
            contact_id=int(contact_id) if contact_id else None,
            trust_score=round(trust_score, 1),
            volatility=round(volatility, 1),
            dependency=round(initiator_out_ratio, 3),
            role_type=role_type,
            call_count=call_count,
            conflict_count=conflict_count,
            initiator_out_ratio=round(initiator_out_ratio, 3),
        )

        # Contradiction detection: look for conflict scenes far apart in time.
        conflict_scenes = sorted(
            [
                s for s in scenes
                if (
                    s.get("scene_type") in CONFLICT_SCENE_TYPES
                    and int(s.get("importance") or 0) >= CONTRADICTION_MIN_IMPORTANCE
                )
            ],
            key=lambda s: s.get("call_datetime") or "",
        )
        if len(conflict_scenes) >= 2:
            s1 = conflict_scenes[0]
            s2 = conflict_scenes[-1]
            delta = _day_delta(s1.get("call_datetime"), s2.get("call_datetime"))
            if delta >= CONTRADICTION_MIN_DAYS:
                imp_max = max(
                    int(s1.get("importance") or 0),
                    int(s2.get("importance") or 0),
                )
                severity = "high" if imp_max >= 70 else "medium"
                bio.upsert_contradiction(
                    user_id=user_id,
                    entity_id=entity_id,
                    contact_id=int(contact_id) if contact_id else None,
                    call_id_1=int(s1["call_id"]),
                    call_id_2=int(s2["call_id"]),
                    quote_1=(s1.get("key_quote") or s1.get("synopsis") or "")[:400],
                    quote_2=(s2.get("key_quote") or s2.get("synopsis") or "")[:400],
                    delta_days=delta,
                    severity=severity,
                    contradiction_type="behavior",
                )
                contradictions_found += 1

        computed += 1
        log.debug(
            "[p3b] entity:%d trust=%.1f volatility=%.1f role=%s conflicts=%d",
            entity_id, trust_score, volatility, role_type, conflict_count,
        )
        bio.tick_checkpoint(user_id, PASS_NAME, f"entity:{entity_id}")

    bio.finish_checkpoint(user_id, PASS_NAME, "done")
    stats = {
        "entities_processed": computed,
        "contradictions_found": contradictions_found,
        "elapsed_sec": round(time.monotonic() - began, 1),
    }
    log.info("[p3b] done %s", stats)
    return stats
