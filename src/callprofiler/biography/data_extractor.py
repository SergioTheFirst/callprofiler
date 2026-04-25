# -*- coding: utf-8 -*-
"""
biography/data_extractor.py — Graph-to-biography bridge.

Reads pre-computed Knowledge Graph data (entity_metrics, events, relations)
and returns structured profiles used by the biography chapter writer (p6_chapters).

No LLM calls here — pure SQL aggregation + deterministic pattern detection.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

log = logging.getLogger(__name__)


def get_entity_profile_from_graph(entity_id: int, conn: sqlite3.Connection) -> dict:
    """Return a structured profile for a graph entity.

    Reads: entities, entity_metrics, events (top facts + conflicts), relations.
    Does NOT read raw transcripts — uses quote fields already extracted.

    Returns dict with keys:
      entity_id, canonical_name, entity_type, aliases,
      metrics, top_facts, conflicts, promise_chain, top_relations,
      timeline, evolution
    """
    conn.row_factory = sqlite3.Row

    entity_row = conn.execute(
        "SELECT * FROM entities WHERE id=?", (entity_id,)
    ).fetchone()
    if not entity_row:
        return {}

    user_id = entity_row["user_id"]
    metrics_row = conn.execute(
        "SELECT * FROM entity_metrics WHERE entity_id=?", (entity_id,)
    ).fetchone()
    metrics = dict(metrics_row) if metrics_row else {}

    # Top facts (promises + contradictions), most recent first
    fact_rows = conn.execute(
        """SELECT ev.event_type, ev.quote, ev.payload, ev.confidence,
                  c.call_datetime, ev.polarity, ev.intensity
           FROM events ev
           LEFT JOIN calls c ON c.call_id = ev.call_id
           WHERE ev.entity_id=? AND ev.user_id=?
             AND ev.fact_id IS NOT NULL
             AND ev.event_type IN ('promise', 'contradiction', 'fact')
           ORDER BY c.call_datetime DESC
           LIMIT 20""",
        (entity_id, user_id),
    ).fetchall()
    top_facts = [
        {
            "type": r["event_type"],
            "quote": r["quote"] or "",
            "value": r["payload"] or "",
            "confidence": r["confidence"],
            "date": (r["call_datetime"] or "")[:10],
            "polarity": r["polarity"],
        }
        for r in fact_rows
    ]

    # Conflicts (contradictions only)
    conflicts = [f for f in top_facts if f["type"] == "contradiction"]

    # Promise chain: open (not fulfilled) promises in chronological order
    promise_rows = conn.execute(
        """SELECT ev.quote, ev.payload, ev.status, c.call_datetime
           FROM events ev
           LEFT JOIN calls c ON c.call_id = ev.call_id
           WHERE ev.entity_id=? AND ev.user_id=?
             AND ev.event_type = 'promise'
           ORDER BY c.call_datetime""",
        (entity_id, user_id),
    ).fetchall()
    promise_chain = [
        {
            "quote": r["quote"] or "",
            "value": r["payload"] or "",
            "status": r["status"] or "open",
            "date": (r["call_datetime"] or "")[:10],
        }
        for r in promise_rows
    ]

    # Top relations (by weight DESC)
    rel_rows = conn.execute(
        """SELECT r.relation_type, r.weight, r.call_count,
                  e2.canonical_name as other_name, e2.entity_type as other_type
           FROM relations r
           JOIN entities e2 ON e2.id = r.dst_entity_id
           WHERE r.src_entity_id=? AND r.user_id=?
           ORDER BY r.weight DESC
           LIMIT 10""",
        (entity_id, user_id),
    ).fetchall()
    top_relations = [
        {
            "relation": r["relation_type"],
            "with": r["other_name"],
            "with_type": r["other_type"],
            "weight": round(r["weight"], 3),
            "call_count": r["call_count"],
        }
        for r in rel_rows
    ]

    # Timeline: distinct call dates (month-level)
    timeline_rows = conn.execute(
        """SELECT DISTINCT SUBSTR(c.call_datetime, 1, 7) as ym
           FROM events ev
           JOIN calls c ON c.call_id = ev.call_id
           WHERE ev.entity_id=? AND ev.user_id=?
           ORDER BY ym""",
        (entity_id, user_id),
    ).fetchall()
    timeline = [r["ym"] for r in timeline_rows]

    # Evolution: BS-index and avg_risk over time (quarterly buckets)
    evolution_rows = conn.execute(
        """SELECT SUBSTR(c.call_datetime, 1, 7) as ym,
                  AVG(a.risk_score) as avg_risk,
                  COUNT(DISTINCT ev.call_id) as calls
           FROM events ev
           JOIN calls c ON c.call_id = ev.call_id
           LEFT JOIN analyses a ON a.call_id = ev.call_id
           WHERE ev.entity_id=? AND ev.user_id=?
           GROUP BY ym
           ORDER BY ym""",
        (entity_id, user_id),
    ).fetchall()
    evolution = [
        {
            "month": r["ym"],
            "avg_risk": round(float(r["avg_risk"] or 0), 1),
            "calls": r["calls"],
        }
        for r in evolution_rows
    ]

    aliases = json.loads(entity_row["aliases"] or "[]")

    return {
        "entity_id": entity_id,
        "canonical_name": entity_row["canonical_name"],
        "entity_type": entity_row["entity_type"],
        "aliases": aliases,
        "metrics": metrics,
        "top_facts": top_facts,
        "conflicts": conflicts,
        "promise_chain": promise_chain,
        "top_relations": top_relations,
        "timeline": timeline,
        "evolution": evolution,
    }


def get_behavioral_patterns(entity_id: int, conn: sqlite3.Connection) -> dict:
    """Deterministic behavioral pattern detection from entity_metrics ratios.

    Returns dict with boolean/textual pattern labels, derived purely from
    stored counters — no LLM, no heuristics beyond documented thresholds.

    Patterns detected:
      - promise_breaker: broken/total_promises >= 0.4
      - contradictory:   contradictions/total_calls >= 0.2
      - vague_communicator: vagueness/total_calls >= 0.2
      - blame_shifter:   blame_shift/total_calls >= 0.15
      - emotionally_volatile: emotional_spikes/total_calls >= 0.2
      - reliable:        broken=0 AND total_promises >= 3
      - high_risk:       avg_risk >= 70
    """
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM entity_metrics WHERE entity_id=?", (entity_id,)
    ).fetchone()
    if not row:
        return {"entity_id": entity_id, "patterns": [], "raw": {}}

    m = dict(row)
    total_calls    = max(int(m.get("total_calls", 0) or 0), 1)
    total_promises = max(int(m.get("total_promises", 0) or 0), 1)
    broken         = int(m.get("broken_promises", 0) or 0)
    contradictions = int(m.get("contradictions", 0) or 0)
    vagueness      = int(m.get("vagueness_count", 0) or 0)
    blame_shifts   = int(m.get("blame_shift_count", 0) or 0)
    emotional      = int(m.get("emotional_spikes", 0) or 0)
    avg_risk       = float(m.get("avg_risk", 0) or 0)

    patterns = []
    if broken / total_promises >= 0.4:
        patterns.append("promise_breaker")
    if contradictions / total_calls >= 0.2:
        patterns.append("contradictory")
    if vagueness / total_calls >= 0.2:
        patterns.append("vague_communicator")
    if blame_shifts / total_calls >= 0.15:
        patterns.append("blame_shifter")
    if emotional / total_calls >= 0.2:
        patterns.append("emotionally_volatile")
    if broken == 0 and int(m.get("total_promises", 0) or 0) >= 3:
        patterns.append("reliable")
    if avg_risk >= 70:
        patterns.append("high_risk")

    return {
        "entity_id": entity_id,
        "patterns": patterns,
        "raw": {
            "broken_ratio": round(broken / total_promises, 3),
            "contradiction_density": round(contradictions / total_calls, 3),
            "vagueness_density": round(vagueness / total_calls, 3),
            "blame_density": round(blame_shifts / total_calls, 3),
            "emotional_density": round(emotional / total_calls, 3),
            "avg_risk": round(avg_risk, 1),
            "bs_index": round(float(m.get("bs_index", 0) or 0), 1),
        },
    }


def get_social_position(entity_id: int, conn: sqlite3.Connection) -> dict:
    """Describe this entity's social/org position from relations.

    Returns:
      - org_links: companies/projects this entity is linked to
      - promise_chains: how many active promise chains involve this entity
      - conflict_count: number of contradiction events
      - centrality: number of distinct entities this one is related to
    """
    conn.row_factory = sqlite3.Row

    entity_row = conn.execute(
        "SELECT user_id FROM entities WHERE id=?", (entity_id,)
    ).fetchone()
    if not entity_row:
        return {}
    user_id = entity_row["user_id"]

    # Org links (company/project relations)
    org_rows = conn.execute(
        """SELECT e2.canonical_name, e2.entity_type, r.relation_type, r.weight
           FROM relations r
           JOIN entities e2 ON e2.id = r.dst_entity_id
           WHERE r.src_entity_id=? AND r.user_id=?
             AND e2.entity_type IN ('org', 'company', 'project')
           ORDER BY r.weight DESC
           LIMIT 10""",
        (entity_id, user_id),
    ).fetchall()
    org_links = [
        {
            "name": r["canonical_name"],
            "type": r["entity_type"],
            "relation": r["relation_type"],
            "weight": round(r["weight"], 3),
        }
        for r in org_rows
    ]

    # Active promise chains
    promise_count = conn.execute(
        """SELECT COUNT(*) FROM events
           WHERE entity_id=? AND user_id=? AND event_type='promise' AND status='open'""",
        (entity_id, user_id),
    ).fetchone()[0]

    # Conflict count
    conflict_count = conn.execute(
        """SELECT COUNT(*) FROM events
           WHERE entity_id=? AND user_id=? AND event_type='contradiction'""",
        (entity_id, user_id),
    ).fetchone()[0]

    # Centrality: distinct entities connected via relations
    centrality = conn.execute(
        """SELECT COUNT(DISTINCT dst_entity_id) FROM relations
           WHERE src_entity_id=? AND user_id=?""",
        (entity_id, user_id),
    ).fetchone()[0]

    return {
        "entity_id": entity_id,
        "org_links": org_links,
        "open_promises": int(promise_count or 0),
        "conflict_count": int(conflict_count or 0),
        "centrality": int(centrality or 0),
    }
