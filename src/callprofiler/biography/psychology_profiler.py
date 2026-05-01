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
        temperament = self._classify_temperament(temporal, entity_id, user_id)
        big_five = self._estimate_big_five(metrics, temporal, social, entity_id)
        motivation = self._detect_motivation(entity_id, user_id, social)
        network = self._analyze_network(entity_id, user_id)
        signature = self._compute_source_signature(
            entity=entity,
            metrics=metrics,
            patterns=patterns_data,
            temporal=temporal,
            social=social,
            evolution=evolution,
            top_facts=top_facts,
            temperament=temperament,
            big_five=big_five,
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
            temperament=temperament,
            big_five=big_five,
            motivation=motivation,
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
            "temperament": temperament,
            "big_five": big_five,
            "motivation": motivation,
            "network": network,
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

    # ── Psychological classifiers ─────────────────────────────────────────

    def _classify_temperament(self, temporal: dict, entity_id: int, user_id: str) -> dict:
        """Hippocrates-Galen temperament from call frequency and emotional tone variance."""
        c_per_w = temporal.get("avg_calls_per_week", 0) or 0
        trend = temporal.get("frequency_trend", "unknown")

        # Energy: call frequency × trend
        if c_per_w >= 3 or trend == "increasing":
            energy = "high"
        elif c_per_w >= 1:
            energy = "medium"
        else:
            energy = "low"

        # Reactivity: emotional tone variance from events
        rows = self.conn.execute(
            """SELECT ev.polarity FROM events ev
               WHERE ev.entity_id=? AND ev.user_id=?
                 AND ev.polarity IS NOT NULL""",
            (entity_id, user_id),
        ).fetchall()
        vals = [r["polarity"] for r in rows if r["polarity"] is not None]
        if len(vals) >= 3:
            avg = sum(vals) / len(vals)
            variance = sum((v - avg) ** 2 for v in vals) / len(vals)
            reactivity = "high" if variance > 0.3 else ("moderate" if variance > 0.1 else "slow")
        else:
            reactivity = "moderate"

        # Classical 4-type mapping
        if energy == "high" and reactivity == "high":
            ttype = "choleric"
        elif energy == "high":
            ttype = "sanguine"
        elif reactivity == "high":
            ttype = "melancholic"
        else:
            ttype = "phlegmatic"

        return {
            "energy": energy,
            "reactivity": reactivity,
            "type": ttype,
            "calls_per_week": round(c_per_w, 2),
        }

    def _estimate_big_five(self, metrics: dict, temporal: dict, social: dict, entity_id: int) -> dict:
        """Big Five (OCEAN) estimation from entity_metrics + relations."""
        tc = max(int(metrics.get("total_calls", 0) or 0), 1)
        tp = max(int(metrics.get("total_promises", 0) or 0), 1)
        broken = int(metrics.get("broken_promises", 0) or 0)
        contra = int(metrics.get("contradictions", 0) or 0)
        blame = int(metrics.get("blame_shift_count", 0) or 0)
        emotional = int(metrics.get("emotional_spikes", 0) or 0)
        vagueness = int(metrics.get("vagueness_count", 0) or 0)
        bs = float(metrics.get("bs_index", 0) or 0)
        avg_risk = float(metrics.get("avg_risk", 0) or 0)

        # Extraversion: high call volume + initiator ratio from social position
        extraversion = min(1.0, 0.4 + (tc / 20) * 0.4 + (1 - float(metrics.get("dependency", 0.5) or 0.5)) * 0.2)

        # Neuroticism: volatility signals
        neuroticism = min(1.0, (emotional / tc) * 0.6 + (avg_risk / 100) * 0.4)

        # Conscientiousness: promise reliability
        promise_ratio = 1.0 - broken / tp if tp > 0 else 0.7
        conscientiousness = min(1.0, promise_ratio * 0.8 + (1.0 - vagueness / tc) * 0.2)

        # Agreeableness: inverse of blame-shift, adjusted by conflict count
        agreeableness = min(1.0, (1.0 - blame / tc) * 0.7 + (1.0 - min(social.get("conflict_count", 0) / tc, 1.0)) * 0.3)

        # Openness: diversity of themes/entities
        open_rows = self.conn.execute(
            "SELECT COUNT(DISTINCT dst_entity_id) FROM relations WHERE src_entity_id=?",
            (entity_id,),
        ).fetchone()
        diversity = int(open_rows[0] or 0) if open_rows else 0
        openness = min(1.0, 0.3 + (diversity / 10) * 0.7)

        return {
            "openness": round(openness, 2),
            "conscientiousness": round(conscientiousness, 2),
            "extraversion": round(extraversion, 2),
            "agreeableness": round(agreeableness, 2),
            "neuroticism": round(neuroticism, 2),
        }

    def _detect_motivation(self, entity_id: int, user_id: str, social: dict) -> dict:
        """McClelland's three needs + security from behavioral signals."""
        rows = self.conn.execute(
            """SELECT COUNT(*) as cnt FROM events
               WHERE entity_id=? AND user_id=? AND event_type='promise' AND status='open'""",
            (entity_id, user_id),
        ).fetchone()
        open_promises = int(rows["cnt"] or 0)

        # Achievement: many promises, high follow-through (promise chain depth)
        promise_rows = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE entity_id=? AND user_id=? AND event_type='promise'",
            (entity_id, user_id),
        ).fetchone()
        total_promises = int(promise_rows[0] or 0)

        achievement_weight = min(1.0, open_promises / 5) * 0.5 + min(1.0, total_promises / 10) * 0.5

        # Power: high initiator ratio + blame shifting
        power_weight = min(1.0, 0.3 + (social.get("conflict_count", 0) / 10) * 0.7)

        # Affiliation: high centrality + contact span
        affiliation_weight = min(1.0, social.get("centrality", 0) / 8)

        # Security: high risk_score, legal_risk mentions
        risk_rows = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE entity_id=? AND user_id=? AND event_type='risk'",
            (entity_id, user_id),
        ).fetchone()
        risk_count = int(risk_rows[0] or 0)
        security_weight = min(1.0, risk_count / 5)

        drivers = []
        if achievement_weight > 0.3:
            drivers.append({"driver": "achievement", "weight": round(achievement_weight, 2)})
        if power_weight > 0.2:
            drivers.append({"driver": "power", "weight": round(power_weight, 2)})
        if affiliation_weight > 0.2:
            drivers.append({"driver": "affiliation", "weight": round(affiliation_weight, 2)})
        if security_weight > 0.1:
            drivers.append({"driver": "security", "weight": round(security_weight, 2)})

        drivers.sort(key=lambda d: -d["weight"])
        primary = drivers[0]["driver"] if drivers else "unknown"

        return {"drivers": drivers, "primary": primary}

    def _analyze_network(self, entity_id: int, user_id: str) -> dict:
        """Compute entity's position in the social network graph."""
        # Centrality: number of distinct connected entities
        centrality = self.conn.execute(
            "SELECT COUNT(DISTINCT dst_entity_id) FROM relations WHERE src_entity_id=? AND user_id=?",
            (entity_id, user_id),
        ).fetchone()[0]

        # Most connected entities (top relations)
        rel_rows = self.conn.execute(
            """SELECT e2.canonical_name as name, r.relation_type as rel, r.weight
               FROM relations r
               JOIN entities e2 ON e2.id = r.dst_entity_id
               WHERE r.src_entity_id=? AND r.user_id=?
               ORDER BY r.weight DESC LIMIT 8""",
            (entity_id, user_id),
        ).fetchall()
        top_connections = [
            {"name": r["name"], "relation": r["rel"], "weight": round(float(r["weight"]), 3)}
            for r in rel_rows
        ]

        # Density: total connections / possible connections (approximation)
        total_entities = self.conn.execute(
            "SELECT COUNT(*) FROM entities WHERE user_id=? AND archived=0",
            (user_id,),
        ).fetchone()[0]
        density = round(centrality / max(total_entities - 1, 1), 3)

        # Is bridge? Connects entities that don't connect to each other
        bridge_score = 0.0
        if centrality >= 3 and len(top_connections) >= 2:
            names = [c["name"] for c in top_connections[:5]]
            placeholders = ",".join("?" * len(names))
            cross_edges = self.conn.execute(
                f"""SELECT COUNT(*) FROM relations r
                    JOIN entities e1 ON e1.id = r.src_entity_id
                    JOIN entities e2 ON e2.id = r.dst_entity_id
                    WHERE e1.canonical_name IN ({placeholders})
                      AND e2.canonical_name IN ({placeholders})
                      AND r.user_id = ?""",
                (*names, *names, user_id),
            ).fetchone()[0]
            max_edges = len(names) * (len(names) - 1) / 2
            bridge_score = round(1.0 - min(cross_edges / max(max_edges, 1), 1.0), 2)

        return {
            "centrality": int(centrality or 0),
            "density": density,
            "bridge_score": bridge_score,
            "top_connections": top_connections,
        }

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
        temperament: dict | None = None,
        big_five: dict | None = None,
        motivation: dict | None = None,
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
            temperament_energy=(temperament or {}).get("energy", "unknown"),
            temperament_reactivity=(temperament or {}).get("reactivity", "unknown"),
            temperament_type=(temperament or {}).get("type", "unknown"),
            bigfive_o=(big_five or {}).get("openness", 0),
            bigfive_c=(big_five or {}).get("conscientiousness", 0),
            bigfive_e=(big_five or {}).get("extraversion", 0),
            bigfive_a=(big_five or {}).get("agreeableness", 0),
            bigfive_n=(big_five or {}).get("neuroticism", 0),
            motivation_primary=(motivation or {}).get("primary", "unknown"),
            motivation_drivers=", ".join(d["driver"] for d in (motivation or {}).get("drivers", [])) or "none",
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
        temperament: dict | None = None,
        big_five: dict | None = None,
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
            "temperament": temperament,
            "big_five": big_five,
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
