# -*- coding: utf-8 -*-
"""
graph/aggregator.py — deterministic EntityMetrics recalculation.

All computation is pure Python arithmetic over SQL aggregates.
No LLM calls here. When calibration data is available, bump
BS_FORMULA_VERSION and add a new _bs_v2_logistic() branch.
"""

from __future__ import annotations

import logging

from callprofiler.graph.config import BS_FORMULA_VERSION
from callprofiler.graph.repository import GraphRepository

log = logging.getLogger(__name__)


class EntityMetricsAggregator:
    """Recompute entity_metrics rows from events aggregates.

    Called by GraphBuilder after writing new facts, and by graph-backfill CLI.
    """

    def __init__(self, repo: GraphRepository) -> None:
        self._repo = repo

    def recalc_for_entities(self, entity_ids: list[int], user_id: str) -> None:
        for eid in entity_ids:
            try:
                self._recalc_one(eid, user_id)
            except Exception:
                log.exception("[aggregator] recalc failed for entity_id=%d", eid)

    def _recalc_one(self, entity_id: int, user_id: str) -> None:
        counts = self._repo.count_facts_by_type(entity_id, user_id)
        total_calls = self._repo.count_distinct_calls(entity_id, user_id)
        avg_risk = self._repo.avg_risk_for_entity(entity_id, user_id)
        last_dt = self._repo.last_interaction_for_entity(entity_id, user_id)

        total_promises = counts.get("promise", 0)
        broken = counts.get("broken_promise", 0)
        # overdue tracked separately via deadline; not available here without joins
        fulfilled = counts.get("fulfilled_promise", 0)
        contradictions = counts.get("contradiction", 0)
        # vagueness and blame_shift stored as event_type='fact' but differentiated
        # via the original fact_type in fact_id; we use raw event counts here.
        vagueness = counts.get("vagueness", 0)
        blame_shifts = counts.get("blame_shift", 0)
        emotional_spikes = counts.get("emotion_spike", 0)

        bs_index = self._bs_v1_linear(
            total_promises=total_promises,
            broken=broken,
            total_calls=total_calls,
            contradictions=contradictions,
            vagueness=vagueness,
            blame_shifts=blame_shifts,
            emotional_spikes=emotional_spikes,
        )

        self._repo.upsert_entity_metrics(
            entity_id=entity_id,
            user_id=user_id,
            total_calls=total_calls,
            total_promises=total_promises,
            fulfilled_promises=fulfilled,
            broken_promises=broken,
            overdue_promises=0,
            contradictions=contradictions,
            vagueness_count=vagueness,
            blame_shift_count=blame_shifts,
            emotional_spikes=emotional_spikes,
            avg_risk=avg_risk,
            bs_index=bs_index,
            bs_formula_version=BS_FORMULA_VERSION,
            last_interaction=last_dt,
        )

    @staticmethod
    def _bs_v1_linear(
        total_promises: int,
        broken: int,
        total_calls: int,
        contradictions: int,
        vagueness: int,
        blame_shifts: int,
        emotional_spikes: int,
    ) -> float:
        """Linear BS-index formula v1.

        Weights: broken_ratio=0.40, contradiction=0.20,
                 vagueness=0.15, blame_shift=0.15, emotional=0.10.

        All raw counters stored in entity_metrics so a future v2_logistic
        can be computed without re-scanning events.
        """
        safe_p = max(total_promises, 1)
        safe_c = max(total_calls, 1)

        broken_ratio         = broken        / safe_p
        contradiction_dens   = min(contradictions   / safe_c, 1.0)
        vagueness_dens       = min(vagueness         / safe_c, 1.0)
        blame_dens           = min(blame_shifts       / safe_c, 1.0)
        emotional_dens       = min(emotional_spikes   / safe_c, 1.0)

        bs_raw = (
            0.40 * broken_ratio
            + 0.20 * contradiction_dens
            + 0.15 * vagueness_dens
            + 0.15 * blame_dens
            + 0.10 * emotional_dens
        )
        return min(bs_raw * 100.0, 100.0)
