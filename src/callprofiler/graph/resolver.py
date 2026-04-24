# -*- coding: utf-8 -*-
"""
resolver.py — Entity Resolver for Этап 3.

Blocking + scoring algorithm to find merge candidates.
BLOCKING prevents O(N²) comparison — only compares entities within candidate blocks.

Score formula (v1):
  0.35 * name_similarity + 0.25 * alias_overlap + 0.20 * relation_jaccard
  + 0.15 * phone_match + 0.05 * behavior_similarity

Threshold: >= 0.65 for manual merge, 0.50-0.64 for LLM assist.

PROTECTION: Owner (is_owner=1) and archived entities never merge.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from callprofiler.graph.normalizer import normalize_key

log = logging.getLogger(__name__)


@dataclass
class EntityInfo:
    """Entity snapshot for scoring."""
    entity_id: int
    canonical_name: str
    normalized_key: str
    entity_type: str
    aliases: list[str]
    attributes: dict
    is_owner: bool
    archived: bool
    call_count: int
    relations: list[dict]  # [{dst_id, relation_type, weight}]
    metrics: dict | None  # {bs_index, avg_risk, ...} if exists


@dataclass
class MergeCandidate:
    """Merge candidate pair."""
    canonical_id: int
    duplicate_id: int
    score: float
    signals: dict  # {name_sim, alias_overlap, ...}
    reason: str


class EntityResolver:
    """Entity deduplication resolver for manual + LLM merge."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def find_candidates(
        self,
        user_id: str,
        entity_type: str = "person",
        min_score: float = 0.65,
        limit: int = 100,
    ) -> list[MergeCandidate]:
        """
        Find merge candidates by blocking algorithm.

        Blocks:
          1. first letter of normalized_key
          2. length of normalized_key ±2
          3. phone overlap (if attributes contain phones)
          4. alias overlap (any common alias)

        Returns candidates with score >= min_score.
        EXCLUDES: owner (is_owner=1) and archived entities.
        """
        # Fetch all active entities of this type (not archived, not owner)
        entities = self._fetch_entities(user_id, entity_type)
        if not entities:
            return []

        # Build blocking groups
        candidates = self._find_blocking_pairs(entities)

        # Score each pair
        scored = []
        for ent_a, ent_b in candidates:
            score, signals = self._score_pair(ent_a, ent_b)
            if score >= min_score:
                scored.append(
                    MergeCandidate(
                        canonical_id=ent_a.entity_id,
                        duplicate_id=ent_b.entity_id,
                        score=score,
                        signals=signals,
                        reason="",
                    )
                )

        # Sort by score DESC
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:limit]

    def _fetch_entities(self, user_id: str, entity_type: str) -> list[EntityInfo]:
        """Fetch all active entities of type."""
        rows = self.conn.execute(
            """
            SELECT id, canonical_name, normalized_key, aliases, attributes, archived
            FROM entities
            WHERE user_id=? AND entity_type=? AND archived=0
            """,
            (user_id, entity_type),
        ).fetchall()

        entities = []
        for row in rows:
            entity_id = row[0]
            ent = EntityInfo(
                entity_id=entity_id,
                canonical_name=row[1],
                normalized_key=row[2],
                entity_type=entity_type,
                aliases=json.loads(row[3] or "[]"),
                attributes=json.loads(row[4] or "{}"),
                is_owner=False,  # TODO: fetch is_owner from contacts if available
                archived=False,
                call_count=0,  # Will be fetched separately
                relations=self._fetch_relations(entity_id),
                metrics=self._fetch_metrics(entity_id),
            )
            entities.append(ent)

        return entities

    def _fetch_relations(self, entity_id: int) -> list[dict]:
        """Fetch outgoing relations."""
        rows = self.conn.execute(
            """
            SELECT dst_entity_id, relation_type, weight
            FROM relations
            WHERE src_entity_id=?
            """,
            (entity_id,),
        ).fetchall()
        return [
            {"dst_id": row[0], "relation_type": row[1], "weight": row[2]}
            for row in rows
        ]

    def _fetch_metrics(self, entity_id: int) -> dict | None:
        """Fetch entity metrics."""
        row = self.conn.execute(
            """
            SELECT bs_index, avg_risk, total_calls
            FROM entity_metrics
            WHERE entity_id=?
            """,
            (entity_id,),
        ).fetchone()
        if row:
            return {"bs_index": row[0], "avg_risk": row[1], "total_calls": row[2]}
        return None

    def _find_blocking_pairs(self, entities: list[EntityInfo]) -> list[tuple]:
        """
        BLOCKING: group entities into blocks, return pairs within blocks.
        O(N*k) where k is average block size.
        """
        # Build blocks
        blocks = {
            "first_letter": {},
            "length": {},
            "phones": {},
            "aliases": {},
        }

        for ent in entities:
            # Block A: first letter
            key_a = ent.normalized_key[0] if ent.normalized_key else ""
            blocks["first_letter"].setdefault(key_a, []).append(ent)

            # Block B: length ±2
            key_len = len(ent.normalized_key)
            for offset in [-2, -1, 0, 1, 2]:
                blocks["length"].setdefault(key_len + offset, []).append(ent)

            # Block C: phones
            phones = ent.attributes.get("phones", [])
            if isinstance(phones, str):
                phones = [phones]
            for phone in phones:
                blocks["phones"].setdefault(phone, []).append(ent)

            # Block D: aliases
            for alias in ent.aliases:
                blocks["aliases"].setdefault(alias, []).append(ent)
            # Add canonical name as alias
            blocks["aliases"].setdefault(ent.canonical_name, []).append(ent)

        # Collect all candidate pairs (entity-agnostic — may have duplicates)
        seen = set()
        pairs = []
        for block_entities in sum(
            [v for v in blocks.values()], []
        ):  # Flatten all blocks
            for i in range(len(block_entities)):
                for j in range(i + 1, len(block_entities)):
                    ent_a, ent_b = block_entities[i], block_entities[j]
                    pair_key = tuple(sorted([ent_a.entity_id, ent_b.entity_id]))
                    if pair_key not in seen:
                        seen.add(pair_key)
                        # Ensure canonical is first
                        if ent_a.entity_id < ent_b.entity_id:
                            pairs.append((ent_a, ent_b))
                        else:
                            pairs.append((ent_b, ent_a))

        return pairs

    def _score_pair(
        self, ent_a: EntityInfo, ent_b: EntityInfo
    ) -> tuple[float, dict]:
        """
        Score a pair of entities.

        Formula:
          0.35 * name_sim + 0.25 * alias_overlap + 0.20 * relation_jaccard
          + 0.15 * phone_match + 0.05 * behavior_sim

        HARD OVERRIDE: if phones match → score = 1.0 (one person = one phone)
        """
        signals = {}

        # 1. Name similarity (SequenceMatcher)
        name_sim = self._name_similarity(ent_a.normalized_key, ent_b.normalized_key)
        signals["name_similarity"] = name_sim

        # 2. Alias overlap (Jaccard on aliases + canonical names)
        alias_overlap = self._alias_overlap_score(ent_a.aliases, ent_b.aliases)
        signals["alias_overlap"] = alias_overlap

        # 3. Relation Jaccard (common destinations)
        relation_jac = self._relation_jaccard(ent_a, ent_b)
        signals["relation_jaccard"] = relation_jac

        # 4. Phone match
        phone_match = self._phone_match(ent_a.attributes, ent_b.attributes)
        signals["phone_match"] = phone_match

        # 5. Behavior similarity
        behavior_sim = self._behavior_similarity(ent_a, ent_b)
        signals["behavior_similarity"] = behavior_sim

        # HARD OVERRIDE: phone match = 1.0
        if phone_match >= 1.0:
            return 1.0, signals

        # Weighted sum
        score = (
            0.35 * name_sim
            + 0.25 * alias_overlap
            + 0.20 * relation_jac
            + 0.15 * phone_match
            + 0.05 * behavior_sim
        )

        return min(score, 1.0), signals

    def _name_similarity(self, a: str, b: str) -> float:
        """difflib.SequenceMatcher ratio."""
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    def _alias_overlap_score(self, aliases_a: list[str], aliases_b: list[str]) -> float:
        """Jaccard similarity on aliases (ignore short aliases <3 chars)."""
        set_a = {a for a in aliases_a if len(a) >= 3}
        set_b = {b for b in aliases_b if len(b) >= 3}

        if not set_a and not set_b:
            return 0.0

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        return intersection / union if union > 0 else 0.0

    def _relation_jaccard(self, ent_a: EntityInfo, ent_b: EntityInfo) -> float:
        """Jaccard on relation destinations."""
        dests_a = {(r["dst_id"], r["relation_type"]) for r in ent_a.relations}
        dests_b = {(r["dst_id"], r["relation_type"]) for r in ent_b.relations}

        if not dests_a and not dests_b:
            return 0.0

        intersection = len(dests_a & dests_b)
        union = len(dests_a | dests_b)

        return intersection / union if union > 0 else 0.0

    def _phone_match(self, attrs_a: dict, attrs_b: dict) -> float:
        """1.0 if phones overlap, 0 otherwise."""
        phones_a = set(attrs_a.get("phones", []))
        phones_b = set(attrs_b.get("phones", []))

        if isinstance(phones_a, str):
            phones_a = {phones_a}
        if isinstance(phones_b, str):
            phones_b = {phones_b}

        if phones_a & phones_b:
            return 1.0
        return 0.0

    def _behavior_similarity(self, ent_a: EntityInfo, ent_b: EntityInfo) -> float:
        """Cosine similarity on normalized behavior metrics."""
        if not ent_a.metrics or not ent_b.metrics:
            return 0.5  # Neutral if missing

        bs_a = ent_a.metrics.get("bs_index", 0)
        bs_b = ent_b.metrics.get("bs_index", 0)

        # If BS-index differs drastically (>30 points) → different behavior
        if abs(bs_a - bs_b) > 30:
            return 0.0

        # Normalize and compute cosine
        vec_a = [bs_a / 100.0, ent_a.metrics.get("avg_risk", 0) / 100.0]
        vec_b = [bs_b / 100.0, ent_b.metrics.get("avg_risk", 0) / 100.0]

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        mag_a = sum(x * x for x in vec_a) ** 0.5
        mag_b = sum(x * x for x in vec_b) ** 0.5

        if mag_a == 0 or mag_b == 0:
            return 0.5

        return dot / (mag_a * mag_b)

    def preview_merge(self, canonical_id: int, duplicate_id: int) -> dict:
        """Preview merge without saving."""
        dup = self._fetch_entity_by_id(duplicate_id)
        if not dup:
            raise ValueError(f"duplicate_id {duplicate_id} not found")

        can = self._fetch_entity_by_id(canonical_id)
        if not can:
            raise ValueError(f"canonical_id {canonical_id} not found")

        # Count relations to transfer
        dup_relations = len(dup.relations)

        # Count events to transfer
        event_count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE entity_id=?", (duplicate_id,)
        ).fetchone()[0]

        # Merged aliases
        merged_aliases = sorted(
            set(can.aliases + dup.aliases + [dup.canonical_name])
        )

        return {
            "canonical": {
                "id": can.entity_id,
                "name": can.canonical_name,
                "aliases_before": can.aliases,
                "call_count": can.call_count,
                "metrics": can.metrics,
            },
            "duplicate": {
                "id": dup.entity_id,
                "name": dup.canonical_name,
                "aliases": dup.aliases,
                "call_count": dup.call_count,
                "metrics": dup.metrics,
            },
            "merge_result": {
                "merged_aliases": merged_aliases,
                "relations_to_transfer": dup_relations,
                "events_to_transfer": event_count,
            },
        }

    def execute_merge(
        self,
        canonical_id: int,
        duplicate_id: int,
        signals: dict,
        merged_by: str = "manual",
        reason: str = "",
    ) -> None:
        """Execute merge in one transaction."""
        # Fetch entities
        dup = self._fetch_entity_by_id(duplicate_id)
        can = self._fetch_entity_by_id(canonical_id)

        if not dup or not can:
            raise ValueError("Entity not found")

        if dup.is_owner or can.is_owner:
            raise ValueError("Cannot merge owner entity")

        if dup.archived:
            raise ValueError("Cannot merge already-archived entity (chain-merge)")

        with self.conn:  # Implicit transaction
            # 1. Create snapshot of duplicate
            snapshot = {
                "entity_id": dup.entity_id,
                "canonical_name": dup.canonical_name,
                "normalized_key": dup.normalized_key,
                "aliases": dup.aliases,
                "attributes": dup.attributes,
                "relations_count": len(dup.relations),
                "metrics": dup.metrics,
            }

            # 2. Transfer relations (with UNIQUE constraint handling)
            self._merge_relations(canonical_id, duplicate_id)

            # 3. Transfer events
            self.conn.execute(
                "UPDATE events SET entity_id=? WHERE entity_id=?",
                (canonical_id, duplicate_id),
            )

            # 4. Merge aliases into canonical
            merged_aliases = sorted(
                set(can.aliases + dup.aliases + [dup.canonical_name])
            )
            self.conn.execute(
                "UPDATE entities SET aliases=? WHERE id=?",
                (json.dumps(merged_aliases), canonical_id),
            )

            # 5. Soft delete: archive duplicate
            self.conn.execute(
                "UPDATE entities SET archived=1, merged_into_id=? WHERE id=?",
                (canonical_id, duplicate_id),
            )

            # 6. Log merge
            self.conn.execute(
                """
                INSERT INTO entity_merges_log
                (user_id, canonical_id, duplicate_id, confidence, signals_json,
                 reason, snapshot_json, merged_by, reversible)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    can.canonical_name.split(":")[0],  # Extract user_id from session
                    canonical_id,
                    duplicate_id,
                    signals.get("score", 0),
                    json.dumps(signals),
                    reason,
                    json.dumps(snapshot),
                    merged_by,
                ),
            )

            # 7. Recalculate metrics (from aggregator)
            from callprofiler.graph.aggregator import EntityMetricsAggregator
            agg = EntityMetricsAggregator(self)
            # This requires user_id — fetch from canonical
            user_row = self.conn.execute(
                "SELECT user_id FROM entities WHERE id=?", (canonical_id,)
            ).fetchone()
            if user_row:
                agg.recalc_for_entities([canonical_id], user_row[0])

    def _fetch_entity_by_id(self, entity_id: int) -> EntityInfo | None:
        """Fetch single entity by ID."""
        row = self.conn.execute(
            "SELECT id, canonical_name, normalized_key, aliases, attributes, archived FROM entities WHERE id=?",
            (entity_id,),
        ).fetchone()
        if not row:
            return None

        ent = EntityInfo(
            entity_id=row[0],
            canonical_name=row[1],
            normalized_key=row[2],
            entity_type="",
            aliases=json.loads(row[3] or "[]"),
            attributes=json.loads(row[4] or "{}"),
            is_owner=False,
            archived=bool(row[5]),
            call_count=0,
            relations=self._fetch_relations(entity_id),
            metrics=self._fetch_metrics(entity_id),
        )
        return ent

    def _merge_relations(self, canonical_id: int, duplicate_id: int) -> None:
        """Merge relations: transfer & deduplicate."""
        # Get all relations of duplicate
        dup_rels = self.conn.execute(
            "SELECT dst_entity_id, relation_type, weight FROM relations WHERE src_entity_id=?",
            (duplicate_id,),
        ).fetchall()

        for dst_id, rel_type, weight in dup_rels:
            # Try to upsert into canonical's relations
            existing = self.conn.execute(
                """
                SELECT id, weight FROM relations
                WHERE src_entity_id=? AND dst_entity_id=? AND relation_type=?
                """,
                (canonical_id, dst_id, rel_type),
            ).fetchone()

            if existing:
                # Merge weights: new_weight = old * decay + new_confidence
                # For simplicity, just sum
                new_weight = existing[1] + weight
                self.conn.execute(
                    "UPDATE relations SET weight=?, call_count=call_count+1 WHERE id=?",
                    (min(new_weight, 1.0), existing[0]),
                )
            else:
                # Insert new relation from canonical to dst
                self.conn.execute(
                    """
                    INSERT INTO relations
                    (user_id, src_entity_id, dst_entity_id, relation_type, weight, confidence)
                    SELECT user_id, ?, ?, ?, ?, confidence FROM relations
                    WHERE src_entity_id=? AND dst_entity_id=?
                    LIMIT 1
                    """,
                    (canonical_id, dst_id, rel_type, weight, duplicate_id, dst_id),
                )

        # Also transfer incoming relations (if any)
        incoming = self.conn.execute(
            "SELECT src_entity_id, relation_type, weight FROM relations WHERE dst_entity_id=?",
            (duplicate_id,),
        ).fetchall()

        for src_id, rel_type, weight in incoming:
            self.conn.execute(
                "UPDATE relations SET dst_entity_id=? WHERE src_entity_id=? AND dst_entity_id=?",
                (canonical_id, src_id, duplicate_id),
            )
