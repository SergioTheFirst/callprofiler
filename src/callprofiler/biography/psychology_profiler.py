# -*- coding: utf-8 -*-
"""
biography/psychology_profiler.py — one-shot psychology profile from Knowledge Graph data.

Aggregates pre-computed DB data (entity_metrics, events, calls, relations) and
calls the LLM once for behavioral interpretation. No raw transcript reads.

Three-layer contract:
  Layer 1 (Extraction): done by GraphBuilder — entities/events/facts in DB
  Layer 2 (Aggregation): this module reads deterministic aggregates
  Layer 3 (Interpretation): ONE LLM call per profile

Integration:
  CLI: person-profile --user USER_ID ENTITY_ID
       profile-all    --user USER_ID [--limit N]
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from callprofiler.graph.repository import GraphRepository

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent.parent.parent / "configs" / "prompts" / "psychology_profile.txt"
_FALLBACK_PROMPT_PATH = Path(__file__).parent / ".." / ".." / ".." / ".." / "configs" / "prompts" / "psychology_profile.txt"


def _load_prompt_template() -> str:
    for p in (_PROMPT_PATH, _FALLBACK_PROMPT_PATH):
        resolved = p.resolve()
        if resolved.exists():
            return resolved.read_text(encoding="utf-8")
    raise FileNotFoundError(f"psychology_profile.txt not found (tried {_PROMPT_PATH})")


class PsychologyProfiler:
    """Generate a psychology profile for a graph entity via one LLM call.

    Usage:
        profiler = PsychologyProfiler(conn, llm_url)
        profile = profiler.build_profile(entity_id=42, user_id="serhio")
        # profile["interpretation"] contains 3-paragraph prose
    """

    def __init__(self, conn: sqlite3.Connection, llm_url: str = "http://127.0.0.1:8080/v1/chat/completions") -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.llm_url = llm_url
        self._grepo = GraphRepository(conn)

    # ── Public ────────────────────────────────────────────────────────────

    def build_profile(self, entity_id: int, user_id: str) -> dict:
        """Build and return a psychology profile dict for entity_id.

        Returns:
            dict with keys: entity_id, canonical_name, entity_type, metrics,
            patterns, temporal, social, evolution, top_facts, interpretation
        Returns empty dict if entity not found.
        """
        entity_row = self.conn.execute(
            "SELECT * FROM entities WHERE id=? AND user_id=?", (entity_id, user_id)
        ).fetchone()
        if not entity_row:
            log.warning("entity_id=%d not found for user=%s", entity_id, user_id)
            return {}

        entity = dict(entity_row)
        metrics_row = self.conn.execute(
            "SELECT * FROM entity_metrics WHERE entity_id=?", (entity_id,)
        ).fetchone()
        metrics = dict(metrics_row) if metrics_row else {}

        call_times = self._get_call_times(entity_id, user_id)
        temporal = self._analyze_temporal(call_times)
        patterns_data = self._extract_patterns(entity_id, metrics)
        social = self._analyze_social(entity_id, user_id)
        evolution = self._build_evolution(entity_id, user_id)
        top_facts = self._get_top_facts(entity_id, user_id)
        signature = self._compute_source_signature(
            entity=entity,
            metrics=metrics,
            patterns=patterns_data,
            temporal=temporal,
            social=social,
            evolution=evolution,
            top_facts=top_facts,
        )
        cached = self._load_cached_profile(entity_id, user_id, signature)
        if cached:
            cached["_cache_hit"] = True
            return cached

        interpretation = self._interpret(
            entity,
            metrics,
            patterns_data,
            temporal,
            top_facts,
            social=social,
            evolution=evolution,
        )

        profile = {
            "entity_id": entity_id,
            "canonical_name": entity["canonical_name"],
            "entity_type": entity["entity_type"],
            "aliases": json.loads(entity.get("aliases") or "[]"),
            "metrics": metrics,
            "patterns": patterns_data,
            "temporal": temporal,
            "social": social,
            "evolution": evolution,
            "top_facts": top_facts,
            "interpretation": interpretation,
        }
        self._save_profile(entity_id, user_id, profile, signature)
        return profile

    # ── Private aggregation ───────────────────────────────────────────────

    def _get_call_times(self, entity_id: int, user_id: str) -> list[str]:
        """Return sorted list of call_datetime strings for this entity."""
        rows = self.conn.execute(
            """SELECT DISTINCT c.call_datetime
               FROM events ev
               JOIN calls c ON c.call_id = ev.call_id
               WHERE ev.entity_id=? AND ev.user_id=?
               ORDER BY c.call_datetime""",
            (entity_id, user_id),
        ).fetchall()
        return [r["call_datetime"] for r in rows if r["call_datetime"]]

    def _analyze_temporal(self, call_times: list[str]) -> dict:
        """Compute temporal activity stats from call timestamps."""
        if not call_times:
            return {
                "avg_calls_per_week": 0.0,
                "preferred_hours": [],
                "preferred_days": [],
                "contact_span_days": 0,
                "frequency_trend": "unknown",
            }

        from datetime import datetime

        parsed = []
        for t in call_times:
            try:
                parsed.append(datetime.fromisoformat(t[:19]))
            except (ValueError, TypeError):
                pass

        if not parsed:
            return {
                "avg_calls_per_week": 0.0,
                "preferred_hours": [],
                "preferred_days": [],
                "contact_span_days": 0,
                "frequency_trend": "unknown",
            }

        parsed.sort()
        span_days = (parsed[-1] - parsed[0]).days or 1
        weeks = max(span_days / 7.0, 1.0)
        avg_calls_per_week = round(len(parsed) / weeks, 2)

        hour_counts: dict[int, int] = {}
        day_counts: dict[int, int] = {}
        for dt in parsed:
            hour_counts[dt.hour] = hour_counts.get(dt.hour, 0) + 1
            day_counts[dt.weekday()] = day_counts.get(dt.weekday(), 0) + 1

        preferred_hours = sorted(hour_counts, key=lambda h: -hour_counts[h])[:3]
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        preferred_days = [day_names[d] for d in sorted(day_counts, key=lambda d: -day_counts[d])[:3]]

        # Trend: compare first half vs second half call frequency
        mid = len(parsed) // 2
        if mid >= 2:
            first_half_rate = mid / max((parsed[mid - 1] - parsed[0]).days, 1)
            second_half_rate = (len(parsed) - mid) / max((parsed[-1] - parsed[mid]).days, 1)
            if second_half_rate > first_half_rate * 1.2:
                trend = "increasing"
            elif second_half_rate < first_half_rate * 0.8:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "avg_calls_per_week": avg_calls_per_week,
            "preferred_hours": preferred_hours,
            "preferred_days": preferred_days,
            "contact_span_days": span_days,
            "frequency_trend": trend,
        }

    def _extract_patterns(self, entity_id: int, metrics: dict) -> list[dict]:
        """Return behavioral pattern list with severity from entity_metrics."""
        total_calls = max(int(metrics.get("total_calls", 0) or 0), 1)
        total_promises = max(int(metrics.get("total_promises", 0) or 0), 1)
        broken = int(metrics.get("broken_promises", 0) or 0)
        contradictions = int(metrics.get("contradictions", 0) or 0)
        vagueness = int(metrics.get("vagueness_count", 0) or 0)
        blame = int(metrics.get("blame_shift_count", 0) or 0)
        emotional = int(metrics.get("emotional_spikes", 0) or 0)
        avg_risk = float(metrics.get("avg_risk", 0) or 0)
        bs_index = float(metrics.get("bs_index", 0) or 0)

        patterns = []

        def _add(name: str, ratio: float, threshold: float, label: str) -> None:
            if ratio >= threshold:
                severity = "high" if ratio >= threshold * 1.5 else "medium"
                patterns.append({"name": name, "severity": severity, "ratio": round(ratio, 3), "label": label})

        _add("promise_breaker", broken / total_promises, 0.4,
             f"{broken}/{int(metrics.get('total_promises', 0) or 0)} promises broken")
        _add("contradictory", contradictions / total_calls, 0.2,
             f"{contradictions} contradictions in {total_calls} calls")
        _add("vague_communicator", vagueness / total_calls, 0.2,
             f"{vagueness} vagueness signals")
        _add("blame_shifter", blame / total_calls, 0.15,
             f"{blame} blame-shift events")
        _add("emotionally_volatile", emotional / total_calls, 0.2,
             f"{emotional} emotional spikes")

        if not patterns:
            if broken == 0 and int(metrics.get("total_promises", 0) or 0) >= 3:
                patterns.append({"name": "reliable", "severity": "positive",
                                  "ratio": 0.0, "label": "0 broken promises"})
        if avg_risk >= 70:
            patterns.append({"name": "high_risk", "severity": "high",
                              "ratio": round(avg_risk / 100, 3), "label": f"avg_risk={avg_risk:.0f}"})

        reliability_index = round(1.0 - min(bs_index / 100.0, 1.0), 3)
        return patterns if patterns else [
            {"name": "neutral", "severity": "low", "ratio": 0.0,
             "label": f"bs_index={bs_index:.1f}, reliability={reliability_index}"}
        ]

    def _analyze_social(self, entity_id: int, user_id: str) -> dict:
        """Return org links, open promises, conflict count, centrality."""
        org_rows = self.conn.execute(
            """SELECT e2.canonical_name, e2.entity_type, r.relation_type, r.weight
               FROM relations r
               JOIN entities e2 ON e2.id = r.dst_entity_id
               WHERE r.src_entity_id=? AND r.user_id=?
                 AND e2.entity_type IN ('org', 'company', 'project')
               ORDER BY r.weight DESC LIMIT 5""",
            (entity_id, user_id),
        ).fetchall()
        related_orgs = [
            {"name": r["canonical_name"], "type": r["entity_type"],
             "relation": r["relation_type"], "weight": round(r["weight"], 3)}
            for r in org_rows
        ]

        open_promises = self.conn.execute(
            """SELECT COUNT(*) FROM events
               WHERE entity_id=? AND user_id=? AND event_type='promise' AND status='open'""",
            (entity_id, user_id),
        ).fetchone()[0]

        conflict_count = self.conn.execute(
            """SELECT COUNT(*) FROM events
               WHERE entity_id=? AND user_id=? AND event_type='contradiction'""",
            (entity_id, user_id),
        ).fetchone()[0]

        centrality = self.conn.execute(
            """SELECT COUNT(DISTINCT dst_entity_id) FROM relations
               WHERE src_entity_id=? AND user_id=?""",
            (entity_id, user_id),
        ).fetchone()[0]

        return {
            "related_orgs": related_orgs,
            "open_promises": int(open_promises or 0),
            "conflict_count": int(conflict_count or 0),
            "centrality": int(centrality or 0),
        }

    def _build_evolution(self, entity_id: int, user_id: str) -> list[dict]:
        """Return yearly avg_risk buckets for this entity."""
        rows = self.conn.execute(
            """SELECT SUBSTR(c.call_datetime, 1, 4) as year,
                      AVG(a.risk_score) as avg_risk,
                      COUNT(DISTINCT ev.call_id) as calls
               FROM events ev
               JOIN calls c ON c.call_id = ev.call_id
               LEFT JOIN analyses a ON a.call_id = ev.call_id
               WHERE ev.entity_id=? AND ev.user_id=?
               GROUP BY year
               ORDER BY year""",
            (entity_id, user_id),
        ).fetchall()
        return [
            {"year": r["year"], "avg_risk": round(float(r["avg_risk"] or 0), 1), "calls": int(r["calls"])}
            for r in rows
        ]

    def _get_top_facts(self, entity_id: int, user_id: str) -> list[dict]:
        """Return up to 5 most recent high-confidence facts with verbatim quotes."""
        rows = self.conn.execute(
            """SELECT ev.event_type, ev.quote, ev.payload, ev.confidence, c.call_datetime
               FROM events ev
               LEFT JOIN calls c ON c.call_id = ev.call_id
               WHERE ev.entity_id=? AND ev.user_id=?
                 AND ev.fact_id IS NOT NULL AND ev.quote IS NOT NULL
                 AND ev.confidence >= 0.6
               ORDER BY c.call_datetime DESC LIMIT 5""",
            (entity_id, user_id),
        ).fetchall()
        return [
            {
                "type": r["event_type"],
                "quote": r["quote"] or "",
                "value": r["payload"] or "",
                "confidence": r["confidence"],
                "date": (r["call_datetime"] or "")[:10],
            }
            for r in rows
        ]

    # ── LLM interpretation ────────────────────────────────────────────────

    def _interpret(
        self,
        entity: dict,
        metrics: dict,
        patterns: list[dict],
        temporal: dict,
        top_facts: list[dict],
        *,
        social: dict,
        evolution: list[dict],
    ) -> str | None:
        """Call LLM once to synthesize a 3-paragraph psychology profile.

        Returns the profile text, or None if LLM is unavailable.
        Non-fatal — caller should handle None gracefully.
        """
        try:
            template = _load_prompt_template()
        except FileNotFoundError as e:
            log.warning("Prompt template not found: %s", e)
            return None

        patterns_text = "\n".join(
            f"  - {p['name']} ({p['severity']}): {p['label']}" for p in patterns
        ) or "  - no significant patterns detected"

        evolution_text = "\n".join(
            f"  {e['year']}: avg_risk={e['avg_risk']}, calls={e['calls']}" for e in evolution
        ) or "  (no evolution data)"

        facts_text = "\n".join(
            f"  [{f['date']}] {f['type']}: \"{f['quote'][:120]}\"" for f in top_facts[:5]
        ) or "  (no verbatim quotes available)"

        aliases = json.loads(entity.get("aliases") or "[]")

        prompt = template.format(
            canonical_name=entity.get("canonical_name", "Unknown"),
            entity_type=entity.get("entity_type", "person"),
            aliases=", ".join(aliases) if aliases else "none",
            bs_index=round(float(metrics.get("bs_index", 0) or 0), 1),
            avg_risk=round(float(metrics.get("avg_risk", 0) or 0), 1),
            total_calls=int(metrics.get("total_calls", 0) or 0),
            total_promises=int(metrics.get("total_promises", 0) or 0),
            broken_promises=int(metrics.get("broken_promises", 0) or 0),
            contradictions=int(metrics.get("contradictions", 0) or 0),
            vagueness_count=int(metrics.get("vagueness_count", 0) or 0),
            blame_shift_count=int(metrics.get("blame_shift_count", 0) or 0),
            emotional_spikes=int(metrics.get("emotional_spikes", 0) or 0),
            patterns=patterns_text,
            avg_calls_per_week=temporal.get("avg_calls_per_week", 0),
            preferred_hours=", ".join(str(h) + ":00" for h in temporal.get("preferred_hours", [])) or "n/a",
            preferred_days=", ".join(temporal.get("preferred_days", [])) or "n/a",
            contact_span_days=temporal.get("contact_span_days", 0),
            frequency_trend=temporal.get("frequency_trend", "unknown"),
            related_orgs=", ".join(o["name"] for o in social.get("related_orgs", [])) or "none",
            open_promises=social.get("open_promises", 0),
            conflict_count=social.get("conflict_count", 0),
            centrality=social.get("centrality", 0),
            evolution=evolution_text,
            top_facts=facts_text,
        )

        try:
            import requests
            resp = requests.post(
                self.llm_url,
                json={
                    "model": "local",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                    "max_tokens": 600,
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.warning("LLM call failed for entity_id=%s: %s", entity.get("id"), e)
            return None

    def _compute_source_signature(
        self,
        *,
        entity: dict,
        metrics: dict,
        patterns: list[dict],
        temporal: dict,
        social: dict,
        evolution: list[dict],
        top_facts: list[dict],
    ) -> str:
        payload = {
            "canonical_name": entity.get("canonical_name"),
            "entity_type": entity.get("entity_type"),
            "aliases": json.loads(entity.get("aliases") or "[]"),
            "metrics": metrics,
            "patterns": patterns,
            "temporal": temporal,
            "social": social,
            "evolution": evolution,
            "top_facts": top_facts,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _load_cached_profile(self, entity_id: int, user_id: str, signature: str) -> dict[str, Any] | None:
        row = self._grepo.get_entity_profile(user_id, entity_id, profile_type="psychology")
        if not row:
            return None
        if row.get("source_signature") != signature:
            return None
        if not row.get("interpretation"):
            return None
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        payload["interpretation"] = row.get("interpretation")
        return payload

    def _save_profile(
        self,
        entity_id: int,
        user_id: str,
        profile: dict[str, Any],
        signature: str,
    ) -> None:
        interpretation = profile.get("interpretation")
        summary = ""
        if isinstance(interpretation, str) and interpretation.strip():
            summary = interpretation.strip().split("\n\n", 1)[0][:400]
        self._grepo.upsert_entity_profile(
            user_id=user_id,
            entity_id=entity_id,
            profile_type="psychology",
            summary=summary,
            interpretation=interpretation if isinstance(interpretation, str) else None,
            payload=profile,
            source_signature=signature,
            model="local",
            source="llm",
        )
