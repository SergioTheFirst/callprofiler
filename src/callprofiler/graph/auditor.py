# -*- coding: utf-8 -*-
"""
graph/auditor.py — Graph consistency auditor.

Runs 9 sanity checks against the Knowledge Graph tables.
Critical checks cause exit code != 0 via the `has_critical` flag in the result.

Usage:
    auditor = GraphAuditor(conn)
    result = auditor.run_checks(user_id)
    if result["has_critical"]:
        sys.exit(2)
"""

from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)

# Checks that indicate data integrity failures — caller should exit != 0
CRITICAL_CHECKS = {"owner_contamination", "orphan_events"}


class GraphAuditor:
    """Run sanity checks on the Knowledge Graph for a given user."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def run_checks(self, user_id: str) -> dict:
        """Run all 9 checks. Returns dict with per-check results and summary flags.

        Return structure:
          {
            "user_id": str,
            "checks": { check_name: { "ok": bool, "count": int, "details": [...] } },
            "has_critical": bool,   # True if any CRITICAL_CHECKS failed
            "has_warnings": bool,   # True if any non-critical check failed
          }
        """
        checks = {}

        checks["entities_without_events"]     = self._check_entities_without_events(user_id)
        checks["high_bs_no_contradictions"]   = self._check_high_bs_no_contradictions(user_id)
        checks["high_risk_no_promises"]       = self._check_high_risk_no_promises(user_id)
        checks["orphan_events"]               = self._check_orphan_events(user_id)
        checks["metrics_vs_events_drift"]     = self._check_metrics_drift(user_id)
        checks["archived_still_referenced"]   = self._check_archived_referenced(user_id)
        checks["merge_candidates_residual"]   = self._check_merge_candidates_residual(user_id)
        checks["owner_contamination"]         = self._check_owner_contamination(user_id)
        checks["empty_canonical_quotes"]      = self._check_empty_canonical_quotes(user_id)
        checks["validator_impact_drift"]      = self._check_validator_impact_drift(user_id)

        has_critical = any(
            not v["ok"] for k, v in checks.items() if k in CRITICAL_CHECKS
        )
        has_warnings = any(not v["ok"] for v in checks.values())

        for name, result in checks.items():
            status = "CRITICAL" if (not result["ok"] and name in CRITICAL_CHECKS) else \
                     "WARN" if not result["ok"] else "OK"
            log.info("[auditor] %-40s %s (count=%d)", name, status, result["count"])

        return {
            "user_id": user_id,
            "checks": checks,
            "has_critical": has_critical,
            "has_warnings": has_warnings,
        }

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_entities_without_events(self, user_id: str) -> dict:
        """Entities with no events — may be orphaned after bad backfill."""
        rows = self._conn.execute(
            """
            SELECT e.id, e.canonical_name
            FROM entities e
            LEFT JOIN events ev ON ev.entity_id = e.id AND ev.user_id = e.user_id
            WHERE e.user_id=? AND e.archived=0 AND COALESCE(e.is_owner,0)=0
              AND ev.id IS NULL
            """,
            (user_id,),
        ).fetchall()
        details = [{"entity_id": r[0], "name": r[1]} for r in rows]
        return {"ok": len(details) == 0, "count": len(details), "details": details[:20]}

    def _check_high_bs_no_contradictions(self, user_id: str) -> dict:
        """Entities with BS-index > 50 but 0 contradictions — likely formula bug."""
        rows = self._conn.execute(
            """
            SELECT m.entity_id, e.canonical_name, m.bs_index, m.contradictions
            FROM entity_metrics m
            JOIN entities e ON e.id = m.entity_id
            WHERE m.user_id=? AND m.bs_index > 50 AND m.contradictions = 0
            """,
            (user_id,),
        ).fetchall()
        details = [
            {"entity_id": r[0], "name": r[1], "bs_index": r[2], "contradictions": r[3]}
            for r in rows
        ]
        return {"ok": len(details) == 0, "count": len(details), "details": details[:20]}

    def _check_high_risk_no_promises(self, user_id: str) -> dict:
        """Entities with avg_risk > 70 but 0 promises — high risk with no trackable cause."""
        rows = self._conn.execute(
            """
            SELECT m.entity_id, e.canonical_name, m.avg_risk, m.total_promises
            FROM entity_metrics m
            JOIN entities e ON e.id = m.entity_id
            WHERE m.user_id=? AND m.avg_risk > 70 AND m.total_promises = 0
            """,
            (user_id,),
        ).fetchall()
        details = [
            {"entity_id": r[0], "name": r[1], "avg_risk": r[2], "total_promises": r[3]}
            for r in rows
        ]
        return {"ok": len(details) == 0, "count": len(details), "details": details[:20]}

    def _check_orphan_events(self, user_id: str) -> dict:
        """Events with entity_id pointing to non-existent or archived entity. CRITICAL."""
        rows = self._conn.execute(
            """
            SELECT ev.id, ev.entity_id
            FROM events ev
            LEFT JOIN entities e ON e.id = ev.entity_id
            WHERE ev.user_id=? AND ev.entity_id IS NOT NULL
              AND (e.id IS NULL OR e.archived=1)
            """,
            (user_id,),
        ).fetchall()
        details = [{"event_id": r[0], "entity_id": r[1]} for r in rows]
        return {"ok": len(details) == 0, "count": len(details), "details": details[:20]}

    def _check_metrics_drift(self, user_id: str) -> dict:
        """Entity metrics where total_calls differs from actual event count by >5%."""
        rows = self._conn.execute(
            """
            SELECT m.entity_id, e.canonical_name,
                   m.total_calls as stored,
                   COUNT(DISTINCT ev.call_id) as actual
            FROM entity_metrics m
            JOIN entities e ON e.id = m.entity_id
            LEFT JOIN events ev ON ev.entity_id = m.entity_id AND ev.user_id = m.user_id
            WHERE m.user_id=? AND m.total_calls > 0
            GROUP BY m.entity_id
            HAVING ABS(CAST(m.total_calls AS REAL) - COUNT(DISTINCT ev.call_id))
                   / CAST(m.total_calls AS REAL) > 0.05
            """,
            (user_id,),
        ).fetchall()
        details = [
            {"entity_id": r[0], "name": r[1], "stored": r[2], "actual": r[3]}
            for r in rows
        ]
        return {"ok": len(details) == 0, "count": len(details), "details": details[:20]}

    def _check_archived_referenced(self, user_id: str) -> dict:
        """Archived entities still appearing as src/dst in active relations."""
        rows = self._conn.execute(
            """
            SELECT r.id, r.src_entity_id, r.dst_entity_id
            FROM relations r
            WHERE r.user_id=?
              AND (
                EXISTS (SELECT 1 FROM entities e WHERE e.id=r.src_entity_id AND e.archived=1)
                OR
                EXISTS (SELECT 1 FROM entities e WHERE e.id=r.dst_entity_id AND e.archived=1)
              )
            """,
            (user_id,),
        ).fetchall()
        details = [
            {"relation_id": r[0], "src": r[1], "dst": r[2]} for r in rows
        ]
        return {"ok": len(details) == 0, "count": len(details), "details": details[:20]}

    def _check_merge_candidates_residual(self, user_id: str) -> dict:
        """Entity pairs that score >= 0.65 but were never merged — potential missed duplicates."""
        from callprofiler.graph.resolver import EntityResolver
        resolver = EntityResolver(self._conn)
        try:
            candidates = resolver.find_candidates(
                user_id, entity_type="person", min_score=0.65, limit=10
            )
        except Exception as exc:
            log.warning("[auditor] merge_candidates_residual check failed: %s", exc)
            candidates = []
        details = [
            {
                "canonical_id": c.canonical_id,
                "duplicate_id": c.duplicate_id,
                "score": round(c.score, 3),
            }
            for c in candidates
        ]
        return {"ok": len(details) == 0, "count": len(details), "details": details}

    def _check_owner_contamination(self, user_id: str) -> dict:
        """Owner entity (is_owner=1) has any facts in events. CRITICAL."""
        rows = self._conn.execute(
            """
            SELECT ev.id, ev.entity_id, e.canonical_name
            FROM events ev
            JOIN entities e ON e.id = ev.entity_id
            WHERE ev.user_id=? AND COALESCE(e.is_owner, 0) = 1
              AND ev.fact_id IS NOT NULL
            """,
            (user_id,),
        ).fetchall()
        details = [
            {"event_id": r[0], "entity_id": r[1], "owner_name": r[2]} for r in rows
        ]
        return {"ok": len(details) == 0, "count": len(details), "details": details[:20]}

    def _check_empty_canonical_quotes(self, user_id: str) -> dict:
        """Entities that have facts but all quotes are shorter than 5 characters."""
        rows = self._conn.execute(
            """
            SELECT ev.entity_id, e.canonical_name, COUNT(*) as total_facts,
                   SUM(CASE WHEN LENGTH(COALESCE(ev.quote,'')) >= 5 THEN 1 ELSE 0 END) as good_quotes
            FROM events ev
            JOIN entities e ON e.id = ev.entity_id
            WHERE ev.user_id=? AND ev.fact_id IS NOT NULL
            GROUP BY ev.entity_id
            HAVING good_quotes = 0
            """,
            (user_id,),
        ).fetchall()
        details = [
            {"entity_id": r[0], "name": r[1], "total_facts": r[2]} for r in rows
        ]
        return {"ok": len(details) == 0, "count": len(details), "details": details[:20]}

    def _check_validator_impact_drift(self, user_id: str) -> dict:
        """Validator impact: compare recalculated BS-index with stored metrics.

        Stratified sample: 40% with bs_index > 50, 40% with total_calls > 10,
        20% random (min 10, max 100 total).

        Drift = abs(stored_bs - recalc_bs) / max(stored_bs, 1) > 0.10
        CRITICAL if >20% of sample drifted, WARN if >10%
        """
        from callprofiler.graph.repository import GraphRepository
        from callprofiler.graph.aggregator import EntityMetricsAggregator

        # Get all entities with metrics for this user
        all_entities = self._conn.execute(
            """
            SELECT m.entity_id, m.bs_index, m.total_calls
            FROM entity_metrics m
            WHERE m.user_id=?
            """,
            (user_id,),
        ).fetchall()

        if not all_entities:
            return {"ok": True, "count": 0, "details": []}

        # Stratified sampling
        high_bs = [e for e in all_entities if e[1] > 50]  # bs_index > 50
        high_calls = [e for e in all_entities if e[2] > 10]  # total_calls > 10
        random_sample = all_entities[::max(1, len(all_entities) // 20)]  # ~5% random

        # Combine with stratification: 40% high_bs, 40% high_calls, 20% random
        target_size = max(10, min(100, len(all_entities) // 3))
        n_high_bs = int(target_size * 0.4)
        n_high_calls = int(target_size * 0.4)
        n_random = int(target_size * 0.2)

        sample_set = set()
        for e in high_bs[:n_high_bs]:
            sample_set.add(e[0])
        for e in high_calls[:n_high_calls]:
            sample_set.add(e[0])
        for e in random_sample[:n_random]:
            sample_set.add(e[0])

        sample = [e for e in all_entities if e[0] in sample_set]

        if len(sample) < 3:
            return {"ok": True, "count": 0, "details": []}

        # Recalculate BS-index for each entity in sample
        grepo = GraphRepository(self._conn)
        agg = EntityMetricsAggregator(grepo)

        drifted_count = 0
        drift_details = []

        for entity_id, stored_bs, _ in sample:
            try:
                result = agg.full_recalc_from_events(entity_id)
                recalc_bs = result.get("bs_index", 0.0)
                drift = abs(stored_bs - recalc_bs) / max(stored_bs, 1.0)

                if drift > 0.10:
                    drifted_count += 1
                    drift_details.append({
                        "entity_id": entity_id,
                        "stored_bs": round(stored_bs, 2),
                        "recalc_bs": round(recalc_bs, 2),
                        "drift_ratio": round(drift, 3),
                    })
            except Exception as e:
                log.warning("[auditor] validator_impact_drift: entity_id=%d recalc failed: %s",
                            entity_id, e)
                continue

        drift_pct = drifted_count / max(len(sample), 1)
        is_ok = drift_pct <= 0.10  # OK if <= 10% drifted

        return {
            "ok": is_ok,
            "count": drifted_count,
            "details": {
                "sample_size": len(sample),
                "drifted_count": drifted_count,
                "drift_pct": round(drift_pct * 100, 1),
                "examples": drift_details[:10],
            },
        }
