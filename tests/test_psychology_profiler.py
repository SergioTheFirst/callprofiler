# -*- coding: utf-8 -*-
"""
test_psychology_profiler.py — tests for PsychologyProfiler.

Uses in-memory SQLite. No LLM calls (LLM is patched/offline, interpretation=None is OK).
"""

import json
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from callprofiler.db.repository import Repository
from callprofiler.biography.data_extractor import get_entity_profile_from_graph
from callprofiler.graph.repository import GraphRepository, apply_graph_schema
from callprofiler.biography.psychology_profiler import PsychologyProfiler


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_conn(user_id: str = "u1") -> sqlite3.Connection:
    """In-memory DB with full schema and a seeded user."""
    repo = Repository(":memory:")
    repo.init_db()
    repo.add_user(
        user_id=user_id,
        display_name="Test",
        telegram_chat_id="0",
        incoming_dir="/tmp/in",
        sync_dir="/tmp/sync",
        ref_audio="/tmp/ref.wav",
    )
    conn = repo._get_conn()
    apply_graph_schema(conn)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_entity(conn: sqlite3.Connection, user_id: str = "u1", name: str = "Vasya") -> int:
    """Insert a minimal entity + entity_metrics row; return entity id."""
    conn.execute(
        """INSERT INTO entities (user_id, canonical_name, normalized_key, entity_type, aliases, archived)
           VALUES (?, ?, ?, 'person', '[]', 0)""",
        (user_id, name, name.lower()),
    )
    eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO entity_metrics
           (entity_id, user_id, total_calls, total_promises, broken_promises,
            contradictions, vagueness_count, blame_shift_count, emotional_spikes,
            avg_risk, bs_index)
           VALUES (?, ?, 10, 5, 2, 1, 1, 0, 1, 45.0, 28.5)""",
        (eid, user_id),
    )
    conn.commit()
    return eid


def _add_call_row(conn: sqlite3.Connection, user_id: str, call_dt: str) -> int:
    """Insert a minimal calls row; return call_id."""
    conn.execute(
        """INSERT INTO calls (user_id, direction, call_datetime, source_filename, source_md5, status)
           VALUES (?, 'IN', ?, 'f.mp3', 'md5test', 'enriched')""",
        (user_id, call_dt),
    )
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    return cid


def _add_event(conn: sqlite3.Connection, entity_id: int, call_id: int, user_id: str,
               event_type: str = "fact", quote: str = "test quote") -> None:
    import hashlib
    fid = hashlib.sha256(f"{event_type}|{entity_id}|{quote}".encode()).hexdigest()[:16]
    conn.execute(
        """INSERT OR IGNORE INTO events
           (user_id, call_id, entity_id, event_type, payload, quote, confidence,
            fact_id, polarity, intensity)
           VALUES (?, ?, ?, ?, 'payload', ?, 0.8, ?, 0.0, 0.5)""",
        (user_id, call_id, entity_id, event_type, quote, fid),
    )
    conn.commit()


# ── tests ─────────────────────────────────────────────────────────────────────

class TestBuildProfileBasic:
    """build_profile() with a seeded entity."""

    def test_returns_expected_keys(self):
        conn = _make_conn()
        eid = _seed_entity(conn)
        profiler = PsychologyProfiler(conn, llm_url="http://localhost:9999/nowhere")
        profile = profiler.build_profile(eid, "u1")

        assert profile["entity_id"] == eid
        assert profile["canonical_name"] == "Vasya"
        assert profile["entity_type"] == "person"
        assert "metrics" in profile
        assert "patterns" in profile
        assert "temporal" in profile
        assert "social" in profile
        assert "evolution" in profile
        assert "top_facts" in profile
        # interpretation is None (LLM unreachable) — that's acceptable
        assert "interpretation" in profile

    def test_missing_entity_returns_empty(self):
        conn = _make_conn()
        profiler = PsychologyProfiler(conn)
        result = profiler.build_profile(entity_id=9999, user_id="u1")
        assert result == {}

    def test_user_isolation(self):
        """Entity belongs to u1; u2 should not find it."""
        repo = Repository(":memory:")
        repo.init_db()
        for uid in ("u1", "u2"):
            repo.add_user(
                user_id=uid, display_name="Test", telegram_chat_id="0",
                incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/ref.wav",
            )
        conn = repo._get_conn()
        apply_graph_schema(conn)
        conn.row_factory = sqlite3.Row
        eid = _seed_entity(conn, user_id="u1")
        profiler = PsychologyProfiler(conn)
        result = profiler.build_profile(eid, user_id="u2")
        assert result == {}


class TestAnalyzeTemporal:
    """_analyze_temporal() with various inputs."""

    def test_empty_returns_zeros(self):
        conn = _make_conn()
        profiler = PsychologyProfiler(conn)
        result = profiler._analyze_temporal([])
        assert result["avg_calls_per_week"] == 0.0
        assert result["contact_span_days"] == 0
        assert result["frequency_trend"] == "unknown"

    def test_single_call(self):
        conn = _make_conn()
        profiler = PsychologyProfiler(conn)
        result = profiler._analyze_temporal(["2026-01-01 10:00:00"])
        assert result["avg_calls_per_week"] >= 0
        assert isinstance(result["preferred_hours"], list)

    def test_multiple_calls_computes_span(self):
        conn = _make_conn()
        profiler = PsychologyProfiler(conn)
        times = ["2026-01-01 09:00:00", "2026-01-08 09:00:00", "2026-01-15 09:00:00"]
        result = profiler._analyze_temporal(times)
        assert result["contact_span_days"] == 14
        assert result["avg_calls_per_week"] > 0


class TestExtractPatterns:
    """_extract_patterns() with seeded metrics."""

    def test_promise_breaker_detected(self):
        conn = _make_conn()
        profiler = PsychologyProfiler(conn)
        metrics = {
            "total_calls": 10, "total_promises": 5, "broken_promises": 3,
            "contradictions": 0, "vagueness_count": 0, "blame_shift_count": 0,
            "emotional_spikes": 0, "avg_risk": 50.0, "bs_index": 40.0,
        }
        patterns = profiler._extract_patterns(1, metrics)
        names = [p["name"] for p in patterns]
        assert "promise_breaker" in names

    def test_reliable_detected_when_no_broken(self):
        conn = _make_conn()
        profiler = PsychologyProfiler(conn)
        metrics = {
            "total_calls": 10, "total_promises": 5, "broken_promises": 0,
            "contradictions": 0, "vagueness_count": 0, "blame_shift_count": 0,
            "emotional_spikes": 0, "avg_risk": 20.0, "bs_index": 5.0,
        }
        patterns = profiler._extract_patterns(1, metrics)
        names = [p["name"] for p in patterns]
        assert "reliable" in names

    def test_no_crash_on_zero_metrics(self):
        conn = _make_conn()
        profiler = PsychologyProfiler(conn)
        patterns = profiler._extract_patterns(1, {})
        assert isinstance(patterns, list)


class TestWithCallsAndFacts:
    """Integration: entity + calls + events → full profile without LLM."""

    def test_temporal_populated_from_events(self):
        conn = _make_conn()
        eid = _seed_entity(conn)
        for dt in ["2026-01-05 10:00:00", "2026-01-12 14:00:00", "2026-01-19 16:00:00"]:
            cid = _add_call_row(conn, "u1", dt)
            _add_event(conn, eid, cid, "u1", quote=f"quote at {dt}")

        profiler = PsychologyProfiler(conn, llm_url="http://localhost:9999/nowhere")
        profile = profiler.build_profile(eid, "u1")

        assert profile["temporal"]["contact_span_days"] > 0
        assert profile["temporal"]["avg_calls_per_week"] > 0

    def test_top_facts_populated(self):
        conn = _make_conn()
        eid = _seed_entity(conn)
        cid = _add_call_row(conn, "u1", "2026-01-05 10:00:00")
        _add_event(conn, eid, cid, "u1", event_type="promise", quote="I will deliver by Friday")

        profiler = PsychologyProfiler(conn, llm_url="http://localhost:9999/nowhere")
        profile = profiler.build_profile(eid, "u1")

        assert len(profile["top_facts"]) >= 1
        assert any(f["type"] == "promise" for f in profile["top_facts"])


class TestProfilePersistence:
    """Profiles are persisted and reused when source evidence is unchanged."""

    def test_profile_saved_to_entity_profiles(self, monkeypatch):
        conn = _make_conn()
        eid = _seed_entity(conn)
        profiler = PsychologyProfiler(conn)

        calls = {"count": 0}

        def fake_interpret(*args, **kwargs):
            calls["count"] += 1
            return "Strong summary paragraph.\n\nMore detail."

        monkeypatch.setattr(profiler, "_interpret", fake_interpret)
        profile = profiler.build_profile(eid, "u1")

        assert calls["count"] == 1
        row = conn.execute(
            """SELECT interpretation, summary, payload_json, source_signature
               FROM entity_profiles
               WHERE user_id='u1' AND entity_id=? AND profile_type='psychology'""",
            (eid,),
        ).fetchone()
        assert row is not None
        assert row["interpretation"].startswith("Strong summary")
        assert row["summary"] == "Strong summary paragraph."
        payload = json.loads(row["payload_json"])
        assert payload["entity_id"] == eid
        assert payload["canonical_name"] == profile["canonical_name"]
        assert row["source_signature"]

    def test_profile_cache_reuses_saved_interpretation(self, monkeypatch):
        conn = _make_conn()
        eid = _seed_entity(conn)
        profiler = PsychologyProfiler(conn)

        calls = {"count": 0}

        def fake_interpret(*args, **kwargs):
            calls["count"] += 1
            return "Reusable interpretation."

        monkeypatch.setattr(profiler, "_interpret", fake_interpret)
        first = profiler.build_profile(eid, "u1")
        second = profiler.build_profile(eid, "u1")

        assert first["interpretation"] == "Reusable interpretation."
        assert second["interpretation"] == "Reusable interpretation."
        assert second["_cache_hit"] is True
        assert calls["count"] == 1

    def test_data_extractor_reads_persisted_profile(self, monkeypatch):
        conn = _make_conn()
        eid = _seed_entity(conn)
        profiler = PsychologyProfiler(conn)

        def fake_interpret(*args, **kwargs):
            return "Entity bridge summary.\n\nNarrative detail."

        monkeypatch.setattr(profiler, "_interpret", fake_interpret)
        profiler.build_profile(eid, "u1")

        extracted = get_entity_profile_from_graph(eid, conn)

        assert extracted["psychology_summary"] == "Entity bridge summary."
        assert extracted["interpretation"].startswith("Entity bridge summary.")
        assert isinstance(extracted["psychology_patterns"], list)
