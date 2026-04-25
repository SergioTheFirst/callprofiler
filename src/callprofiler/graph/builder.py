# -*- coding: utf-8 -*-
"""
graph/builder.py — GraphBuilder: populate Knowledge Graph from v2 analyses.

Reads LLM-generated entities/relations/structured_facts from analyses.raw_response,
applies anti-noise filters, and writes to graph tables. Only processes
analyses with schema_version='v2'.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3

from callprofiler.graph.aggregator import EntityMetricsAggregator
from callprofiler.graph.config import (
    FACT_ID_ALGORITHM,
    FACT_ID_LENGTH,
    MIN_FACT_CONFIDENCE,
    MIN_QUOTE_LENGTH,
    RELATION_DECAY_DAYS,
)
from callprofiler.graph.repository import GraphRepository, apply_graph_schema
from callprofiler.graph.validator import FactValidator

log = logging.getLogger(__name__)


class GraphBuilder:
    """Populate Knowledge Graph tables from a single analysis (v2 only).

    Usage:
        conn = sqlite3.connect(db_path)
        apply_graph_schema(conn)
        builder = GraphBuilder(conn)
        builder.update_from_call(call_id)
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._repo = GraphRepository(conn)
        self._aggregator = EntityMetricsAggregator(self._repo)
        self._validator = FactValidator()
        self._stats: dict[str, int] = {"facts_total": 0, "facts_inserted": 0, "facts_rejected": 0}

    def reset_stats(self) -> None:
        """Reset accumulated fact counters. Call before each replay run."""
        self._stats = {"facts_total": 0, "facts_inserted": 0, "facts_rejected": 0}

    def get_stats(self) -> dict[str, int]:
        """Return a snapshot of accumulated fact counters."""
        return dict(self._stats)

    def update_from_call(self, call_id: int, transcript_text: str | None = None) -> bool:
        """Process one call's analysis into the graph.

        Args:
            call_id: Call to process
            transcript_text: Optional full transcript (for enhanced fact validation)

        Returns True if entities were written, False if skipped.
        Skips silently for v1 analyses or missing/malformed data.

        Validation (Этап 2 — FACT VALIDATOR):
        - Quote length >= 8 chars
        - Quote found in transcript via rolling window (ratio >= 0.72)
        - Speaker attribution detection ([me] vs [s2])
        - Semantic checks (future markers, negations, vagueness)
        """
        try:
            return self._update(call_id, transcript_text=transcript_text)
        except Exception:
            log.exception("[graph] update_from_call failed for call_id=%d", call_id)
            return False

    def _update(self, call_id: int, transcript_text: str | None = None) -> bool:
        row = self._conn.execute(
            """SELECT a.raw_response, a.schema_version,
                      c.user_id, c.contact_id, c.call_datetime
               FROM analyses a
               JOIN calls c ON c.call_id = a.call_id
               WHERE a.call_id = ?""",
            (call_id,),
        ).fetchone()

        if not row:
            log.debug("[graph] call_id=%d: no analysis found, skipping", call_id)
            return False

        schema_version = row["schema_version"] or "v1"
        if schema_version != "v2":
            log.debug("[graph] call_id=%d: schema_version=%s, skipping", call_id, schema_version)
            return False

        raw = row["raw_response"] or ""
        if not raw:
            log.debug("[graph] call_id=%d: empty raw_response, skipping", call_id)
            return False

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("[graph] call_id=%d: invalid JSON in raw_response: %s", call_id, exc)
            return False

        user_id = row["user_id"]
        contact_id = row["contact_id"]
        call_datetime = row["call_datetime"]

        # ── 1. Upsert entities ────────────────────────────────────────────
        entity_id_by_key: dict[str, int] = {}
        for ent in parsed.get("entities", []):
            nkey = ent.get("normalized_key", "").strip()
            cname = ent.get("canonical_name", "").strip()
            etype = ent.get("type", "").strip()
            if not nkey or not cname or not etype:
                continue
            try:
                eid = self._repo.upsert_entity(
                    user_id=user_id,
                    entity_type=etype,
                    canonical_name=cname,
                    normalized_key=nkey,
                    aliases=ent.get("aliases") or [],
                    attributes=ent.get("attributes") or {},
                )
                entity_id_by_key[nkey] = eid
            except Exception:
                log.exception("[graph] call_id=%d: upsert_entity failed for key=%s", call_id, nkey)

        # ── 2. Upsert relations with time-decay ───────────────────────────
        for rel in parsed.get("relations", []):
            src_key = rel.get("src_key", "")
            dst_key = rel.get("dst_key", "")
            rtype = rel.get("relation_type", "").strip()
            if not src_key or not dst_key or not rtype:
                continue
            src_id = entity_id_by_key.get(src_key)
            dst_id = entity_id_by_key.get(dst_key)
            if not src_id or not dst_id:
                log.debug(
                    "[graph] call_id=%d: relation %s→%s skipped (entity not found)",
                    call_id, src_key, dst_key,
                )
                continue
            try:
                self._repo.upsert_relation_with_decay(
                    user_id=user_id,
                    src_id=src_id,
                    dst_id=dst_id,
                    relation_type=rtype,
                    confidence=float(rel.get("confidence", 1.0)),
                    call_id=call_id,
                    call_datetime=call_datetime,
                    decay_days=RELATION_DECAY_DAYS,
                )
            except Exception:
                log.exception(
                    "[graph] call_id=%d: upsert_relation failed for %s→%s",
                    call_id, src_key, dst_key,
                )

        # ── 3. Anti-noise filter + upsert facts ───────────────────────────
        for fact in parsed.get("structured_facts", []):
            quote = (fact.get("quote") or "").strip()
            confidence = float(fact.get("confidence", 0.0))

            # Confidence check (original filter)
            if confidence < MIN_FACT_CONFIDENCE:
                continue

            self._stats["facts_total"] += 1

            # Run enhanced validator (Этап 2)
            validation = self._validator.validate(fact, transcript_text)
            if not validation["valid"]:
                for error in validation["errors"]:
                    log.debug("[graph] call_id=%d: fact rejected: %s", call_id, error)
                self._stats["facts_rejected"] += 1
                continue
            for warning in validation["warnings"]:
                log.debug("[graph] call_id=%d: fact warning: %s", call_id, warning)

            entity_key = fact.get("entity_key", "")
            entity_id = entity_id_by_key.get(entity_key)

            fact_type = fact.get("fact_type", "fact")
            fact_key = f"{fact_type}|{entity_id}|{quote}"
            fact_id = _hash(fact_key)

            try:
                self._repo.upsert_fact(
                    user_id=user_id,
                    call_id=call_id,
                    contact_id=contact_id,
                    entity_id=entity_id,
                    fact_id=fact_id,
                    event_type=fact_type,
                    quote=quote,
                    value=fact.get("value"),
                    polarity=_int_or_none(fact.get("polarity")),
                    intensity=_float_or_none(fact.get("intensity")),
                    confidence=confidence,
                    start_ms=_int_or_none(fact.get("start_ms")),
                    end_ms=_int_or_none(fact.get("end_ms")),
                )
                self._stats["facts_inserted"] += 1
            except Exception:
                log.exception(
                    "[graph] call_id=%d: upsert_fact failed for fact_id=%s", call_id, fact_id
                )
                self._stats["facts_rejected"] += 1

        # ── 4. Recalculate metrics for affected entities ───────────────────
        if entity_id_by_key:
            self._aggregator.recalc_for_entities(
                list(entity_id_by_key.values()), user_id
            )
            self._conn.commit()
            log.debug(
                "[graph] call_id=%d: wrote %d entities, committed",
                call_id, len(entity_id_by_key),
            )

        return bool(entity_id_by_key)


# ── helpers ──────────────────────────────────────────────────────────────────

def _hash(text: str) -> str:
    h = hashlib.new(FACT_ID_ALGORITHM)
    h.update(text.encode("utf-8"))
    return h.hexdigest()[:FACT_ID_LENGTH]


def _int_or_none(val) -> int | None:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None
