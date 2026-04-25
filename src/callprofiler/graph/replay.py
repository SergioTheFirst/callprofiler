# -*- coding: utf-8 -*-
"""
graph/replay.py — Safe replay of graph layer from v2 analyses.

Idempotent reconstruction of entities/relations/entity_metrics from scratch.
All operations are derived from analyses.raw_response (schema_version='v2').
"""

from __future__ import annotations

import json
import logging
from typing import Any

from callprofiler.db.repository import Repository
from callprofiler.graph.aggregator import EntityMetricsAggregator
from callprofiler.graph.builder import GraphBuilder
from callprofiler.graph.repository import GraphRepository

log = logging.getLogger(__name__)


class GraphReplayer:
    """Rebuild graph layer from v2 analyses. Safe, idempotent, traceable."""

    def __init__(self, db_repo: Repository, graph_repo: GraphRepository) -> None:
        self._db_repo = db_repo
        self._graph_repo = graph_repo
        self._builder = GraphBuilder(graph_repo._conn)
        self._aggregator = EntityMetricsAggregator(graph_repo)

    def replay(
        self,
        user_id: str,
        limit: int | None = None,
    ) -> dict:
        """
        Rebuild graph layer for user_id from v2 analyses.

        Args:
            user_id: User identifier
            limit: Max calls to process (for testing/partial replay)

        Returns:
            Stats dict with counts and assertions
        """
        conn = self._graph_repo._conn

        # Step 1: Clear derived tables (safe — derived from analyses only)
        log.info("[replay] clearing derived tables for user_id=%s", user_id)
        conn.execute("DELETE FROM entity_metrics WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM relations WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM entities WHERE user_id=? AND archived=0", (user_id,))

        # Step 2: Clear graph columns in events (only v2, preserve v1)
        log.info("[replay] clearing graph columns in events (v2 only)")
        conn.execute(
            """UPDATE events
               SET entity_id=NULL, fact_id=NULL, quote=NULL,
                   polarity=NULL, intensity=NULL, start_ms=NULL, end_ms=NULL
               WHERE user_id=? AND call_id IN (
                   SELECT id FROM calls WHERE user_id=? AND id IN (
                       SELECT DISTINCT call_id FROM analyses
                       WHERE schema_version='v2' AND user_id=?
                   )
               )""",
            (user_id, user_id, user_id),
        )
        conn.commit()

        # Step 3: Fetch v2 analyses for processing
        rows = conn.execute(
            """SELECT c.user_id, a.call_id, a.raw_response
               FROM analyses a
               JOIN calls c ON c.call_id = a.call_id
               WHERE c.user_id=? AND a.schema_version='v2'
               ORDER BY a.call_id ASC""",
            (user_id,),
        ).fetchall()

        if not rows:
            log.warning("[replay] no v2 analyses found for user_id=%s", user_id)
            return {
                "user_id": user_id,
                "calls_processed": 0,
                "entities_count": 0,
                "relations_count": 0,
                "facts_count": 0,
                "rejected_facts": 0,
                "avg_bs_index": None,
                "warnings": ["no v2 analyses to replay"],
            }

        if limit:
            rows = rows[:limit]

        stats = {
            "calls_processed": 0,
            "entities_count": 0,
            "relations_count": 0,
            "facts_count": 0,
            "rejected_facts": 0,
            "facts_before_filter": 0,
        }

        # Step 4: Replay each analysis
        for idx, (_, call_id, raw_response_str) in enumerate(rows):
            try:
                raw = json.loads(raw_response_str)
            except (json.JSONDecodeError, ValueError) as e:
                log.warning(
                    "[replay] call_id=%d: JSON parse failed: %s",
                    call_id,
                    e,
                )
                stats["rejected_facts"] += 1
                continue

            # Get transcript for this call (fallback to None if not available)
            transcript_text = None
            try:
                segments = self._db_repo.get_transcript(call_id)
                if segments:
                    transcript_text = " ".join(seg.text for seg in segments if seg.text)
            except Exception as e:
                log.debug("[replay] call_id=%s: could not fetch transcript: %s", call_id, e)

            # Update graph from raw_response
            try:
                self._builder.update_from_call(call_id, transcript_text=transcript_text)
            except Exception as e:
                log.error(
                    "[replay] call_id=%s: graph update failed: %s",
                    call_id,
                    e,
                    exc_info=True,
                )
                continue

            stats["calls_processed"] += 1

            # Log progress every 100 calls
            if (idx + 1) % 100 == 0:
                current_entities = conn.execute(
                    "SELECT COUNT(*) FROM entities WHERE user_id=?", (user_id,)
                ).fetchone()[0]
                current_relations = conn.execute(
                    "SELECT COUNT(*) FROM relations WHERE user_id=?", (user_id,)
                ).fetchone()[0]
                current_facts = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE user_id=? AND fact_id IS NOT NULL",
                    (user_id,),
                ).fetchone()[0]
                log.info(
                    "[replay] processed %d calls → %d entities, %d relations, %d facts",
                    stats["calls_processed"],
                    current_entities,
                    current_relations,
                    current_facts,
                )

        # Step 5: Recalculate metrics for all entities
        log.info("[replay] recalculating metrics for all entities")
        all_entity_ids = conn.execute(
            "SELECT id FROM entities WHERE user_id=?", (user_id,)
        ).fetchall()

        for (entity_id,) in all_entity_ids:
            try:
                self._aggregator.full_recalc_from_events(entity_id)
            except Exception as e:
                log.error(
                    "[replay] entity_id=%d: metrics recalc failed: %s",
                    entity_id,
                    e,
                    exc_info=True,
                )

        # Final counts
        stats["entities_count"] = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        stats["relations_count"] = conn.execute(
            "SELECT COUNT(*) FROM relations WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        stats["facts_count"] = conn.execute(
            "SELECT COUNT(*) FROM events WHERE user_id=? AND fact_id IS NOT NULL",
            (user_id,),
        ).fetchone()[0]

        # Assertions
        warnings = []
        if stats["calls_processed"] > 0 and stats["facts_count"] == 0:
            warnings.append("ASSERT FAILED: facts_count=0 after processing calls")
        if stats["calls_processed"] < 5 and stats["entities_count"] == 0:
            warnings.append(f"WARNING: {stats['entities_count']} entities after {stats['calls_processed']} calls")

        # Check orphan events (events.entity_id pointing to non-existent entity)
        orphan_count = conn.execute(
            """SELECT COUNT(*) FROM events e
               WHERE e.user_id=? AND e.entity_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM entities WHERE id=e.entity_id)""",
            (user_id,),
        ).fetchone()[0]
        if orphan_count > 0:
            warnings.append(f"ASSERT FAILED: orphan_events={orphan_count}")

        # Check owner contamination
        owner_with_bs = conn.execute(
            """SELECT COUNT(*) FROM entities e
               WHERE e.user_id=? AND e.is_owner=1
               AND EXISTS (SELECT 1 FROM entity_metrics m WHERE m.entity_id=e.id AND m.bs_index > 0)""",
            (user_id,),
        ).fetchone()[0]
        if owner_with_bs > 0:
            warnings.append(f"ASSERT FAILED: owner_contamination={owner_with_bs} (owner entities with bs_index>0)")

        # Compute avg_bs_index
        avg_bs = conn.execute(
            "SELECT AVG(bs_index) FROM entity_metrics WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        stats["avg_bs_index"] = round(avg_bs, 2) if avg_bs else None

        stats["warnings"] = warnings
        return stats
