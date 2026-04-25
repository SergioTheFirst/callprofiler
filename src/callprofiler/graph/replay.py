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
from callprofiler.graph.auditor import GraphAuditor
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

        Collects per-fact stats (total/inserted/rejected), runs GraphAuditor
        after rebuild, and saves a graph_replay_runs row for posterity.

        Args:
            user_id: User identifier
            limit: Max calls to process (for testing/partial replay)

        Returns:
            Stats dict with counts, rejection_rate, audit_critical, and warnings
        """
        conn = self._graph_repo._conn
        self._builder.reset_stats()

        # Step 1: Clear graph columns in events FIRST (to break FK references)
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

        # Step 2: Clear derived tables (safe — derived from analyses only)
        log.info("[replay] clearing derived tables for user_id=%s", user_id)
        conn.execute("DELETE FROM entity_metrics WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM relations WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM entities WHERE user_id=? AND archived=0", (user_id,))
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
                "facts_total": 0,
                "facts_inserted": 0,
                "facts_rejected": 0,
                "rejection_rate": 0.0,
                "avg_bs_index": None,
                "audit_critical": 0,
                "warnings": ["no v2 analyses to replay"],
            }

        if limit:
            rows = rows[:limit]

        calls_processed = 0

        # Step 4: Replay each analysis
        for idx, (_, call_id, raw_response_str) in enumerate(rows):
            try:
                json.loads(raw_response_str)
            except (json.JSONDecodeError, ValueError) as e:
                log.warning("[replay] call_id=%d: JSON parse failed: %s", call_id, e)
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
                    call_id, e, exc_info=True,
                )
                continue

            calls_processed += 1

            # Log progress every 100 calls
            if (idx + 1) % 100 == 0:
                bstats = self._builder.get_stats()
                current_entities = conn.execute(
                    "SELECT COUNT(*) FROM entities WHERE user_id=?", (user_id,)
                ).fetchone()[0]
                log.info(
                    "[replay][%d] entities=%d facts_inserted=%d rejected=%d rate=%.1f%%",
                    calls_processed,
                    current_entities,
                    bstats["facts_inserted"],
                    bstats["facts_rejected"],
                    (bstats["facts_rejected"] / max(bstats["facts_total"], 1)) * 100,
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
                    entity_id, e, exc_info=True,
                )

        # Collect final DB counts
        entities_count = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        relations_count = conn.execute(
            "SELECT COUNT(*) FROM relations WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        facts_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE user_id=? AND fact_id IS NOT NULL",
            (user_id,),
        ).fetchone()[0]
        avg_bs_raw = conn.execute(
            "SELECT AVG(bs_index) FROM entity_metrics WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        avg_bs_index = round(avg_bs_raw, 2) if avg_bs_raw else None

        # Collect builder stats
        bstats = self._builder.get_stats()
        facts_total = bstats["facts_total"]
        facts_inserted = bstats["facts_inserted"]
        facts_rejected = bstats["facts_rejected"]
        rejection_rate = facts_rejected / facts_total if facts_total > 0 else 0.0

        # Step 6: Run auditor
        auditor = GraphAuditor(conn)
        audit_result = auditor.run_checks(user_id)
        audit_critical = 1 if audit_result["has_critical"] else 0

        # Step 7: Save replay run to DB
        try:
            self._graph_repo.save_replay_run(
                user_id=user_id,
                calls_processed=calls_processed,
                facts_total=facts_total,
                facts_inserted=facts_inserted,
                facts_rejected=facts_rejected,
                entities_count=entities_count,
                avg_bs_index=avg_bs_index,
                audit_critical=audit_critical,
            )
        except Exception as e:
            log.warning("[replay] failed to save replay run record: %s", e)

        # Step 8: Assertions + warnings
        warnings = []

        if calls_processed > 0 and facts_inserted == 0:
            warnings.append("ASSERT FAILED: facts_inserted=0 after processing calls")

        if calls_processed > 0 and rejection_rate >= 0.90:
            warnings.append(
                f"ASSERT FAILED: rejection_rate={rejection_rate:.1%} >= 0.90 "
                f"— validator may be broken"
            )

        if audit_critical:
            for name, check in audit_result["checks"].items():
                if not check["ok"] and name in ("owner_contamination", "orphan_events"):
                    warnings.append(
                        f"ASSERT FAILED: audit.{name} count={check['count']}"
                    )

        if calls_processed > 0 and facts_total > 0:
            if rejection_rate > 0.60:
                warnings.append(
                    f"WARN: rejection_rate={rejection_rate:.1%} > 60% — "
                    f"validator too aggressive, check thresholds"
                )
            elif rejection_rate < 0.05 and facts_total > 10:
                warnings.append(
                    f"WARN: rejection_rate={rejection_rate:.1%} < 5% — "
                    f"validator too weak, hallucinations may pass"
                )

        return {
            "user_id": user_id,
            "calls_processed": calls_processed,
            "entities_count": entities_count,
            "relations_count": relations_count,
            "facts_count": facts_count,
            "facts_total": facts_total,
            "facts_inserted": facts_inserted,
            "facts_rejected": facts_rejected,
            "rejection_rate": round(rejection_rate, 4),
            "avg_bs_index": avg_bs_index,
            "audit_critical": audit_critical,
            "audit_result": audit_result,
            "warnings": warnings,
        }
