# -*- coding: utf-8 -*-
"""
tests/test_graph_builder_transcript_gate.py — Gate C: graph builder loads transcript when None.

Validates:
  - If transcript_text is None → load from DB (transcripts table)
  - FactValidator receives transcript_text for verbatim quote checking
  - Non-verbatim quotes are rejected when transcript provided
  - Graceful degradation if no transcript rows exist
"""

from __future__ import annotations

import json

import pytest

from callprofiler.db.repository import Repository
from callprofiler.graph.builder import GraphBuilder
from callprofiler.graph.repository import apply_graph_schema


@pytest.fixture
def repo():
    """Create in-memory Repository with schema."""
    r = Repository(":memory:")
    r.init_db()
    return r


def _add_user(repo: Repository, user_id: str = "test_user") -> None:
    """Helper: add a user record."""
    repo.add_user(
        user_id=user_id,
        display_name="Test User",
        telegram_chat_id="0",
        incoming_dir="/tmp/in",
        sync_dir="/tmp/sync",
        ref_audio="/tmp/ref.wav",
    )


def _add_call(repo: Repository, call_id: int = 1, user_id: str = "test_user", contact_id: int = None) -> None:
    """Helper: add a call record (creates contact if needed)."""
    if contact_id is None:
        # Create a contact first
        contact_id = repo.get_or_create_contact(user_id, "+70000000001", "Test Contact")
    repo._get_conn().execute(
        """INSERT INTO calls (call_id, user_id, contact_id, source_filename, source_md5, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (call_id, user_id, contact_id, "test.mp3", "abc123", "done"),
    )
    repo._get_conn().commit()


def _add_analysis_v2(repo: Repository, call_id: int = 1, raw_response: str = "") -> None:
    """Helper: add a v2 analysis."""
    repo._get_conn().execute(
        """INSERT INTO analyses (call_id, priority, risk_score, summary, call_type,
                                 schema_version, raw_response)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (call_id, 50, 0, "test", "business", "v2", raw_response),
    )
    repo._get_conn().commit()


def _add_transcript(repo: Repository, call_id: int = 1, text: str = "sample text", speaker: str = "OTHER") -> None:
    """Helper: add a transcript segment."""
    repo._get_conn().execute(
        """INSERT INTO transcripts (call_id, speaker, text, start_ms, end_ms)
           VALUES (?, ?, ?, ?, ?)""",
        (call_id, speaker, text, 0, 5000),
    )
    repo._get_conn().commit()


class TestGraphBuilderTranscriptGate:
    """Gate C: graph builder loads transcript for fact validation."""

    def test_loads_transcript_when_none(self, repo):
        """If transcript_text=None, load from transcripts table."""
        _add_user(repo)
        _add_call(repo)
        _add_transcript(repo, text="[me]: hello\n[s2]: how are you")
        _add_analysis_v2(
            repo,
            raw_response=json.dumps({
                "entities": [{"type": "PERSON", "canonical_name": "John", "normalized_key": "john",
                             "aliases": ["john"], "entity_key": "PERSON::john"}],
                "relations": [],
                "structured_facts": [{
                    "entity_key": "PERSON::john",
                    "fact_type": "fact",
                    "quote": "how are you",  # This IS in the transcript
                    "confidence": 0.8,
                }],
            }),
        )

        apply_graph_schema(repo._get_conn())
        builder = GraphBuilder(repo._get_conn())
        result = builder.update_from_call(call_id=1, transcript_text=None)

        assert result is True, "update_from_call should succeed when transcript is loaded"
        stats = builder.get_stats()
        assert stats["facts_inserted"] == 1, "Fact should be inserted (quote found)"

    def test_rejects_nonverbatim_quote_when_transcript_provided(self, repo):
        """If transcript provided, non-verbatim quotes are rejected."""
        _add_user(repo)
        _add_call(repo)
        transcript = "[me]: hello\n[s2]: how are you today"
        _add_transcript(repo, text=transcript)
        _add_analysis_v2(
            repo,
            raw_response=json.dumps({
                "entities": [{"type": "PERSON", "canonical_name": "John", "normalized_key": "john",
                             "aliases": [], "entity_key": "PERSON::john"}],
                "relations": [],
                "structured_facts": [{
                    "entity_key": "PERSON::john",
                    "fact_type": "fact",
                    "quote": "completely different text not in transcript",
                    "confidence": 0.9,
                }],
            }),
        )

        apply_graph_schema(repo._get_conn())
        builder = GraphBuilder(repo._get_conn())
        result = builder.update_from_call(call_id=1, transcript_text=transcript)

        assert result is True
        stats = builder.get_stats()
        assert stats["facts_rejected"] >= 1, "Non-verbatim quote should be rejected"

    def test_graceful_degradation_no_transcript_rows(self, repo):
        """If no transcript rows exist, validator warns but doesn't crash."""
        _add_user(repo)
        _add_call(repo)
        # NO transcript added
        _add_analysis_v2(
            repo,
            raw_response=json.dumps({
                "entities": [{"type": "PERSON", "canonical_name": "John", "normalized_key": "john",
                             "aliases": [], "entity_key": "PERSON::john"}],
                "relations": [],
                "structured_facts": [{
                    "entity_key": "PERSON::john",
                    "fact_type": "fact",
                    "quote": "some quote",
                    "confidence": 0.8,
                }],
            }),
        )

        apply_graph_schema(repo._get_conn())
        builder = GraphBuilder(repo._get_conn())
        result = builder.update_from_call(call_id=1, transcript_text=None)

        assert result is True
        stats = builder.get_stats()
        assert stats["facts_total"] >= 0

    def test_transcript_text_parameter_honored(self, repo):
        """If transcript_text provided as parameter, use it (don't load from DB)."""
        _add_user(repo)
        _add_call(repo)
        _add_transcript(repo, text="[me]: database text")
        provided_transcript = "[me]: parameter text\n[s2]: how are you"
        _add_analysis_v2(
            repo,
            raw_response=json.dumps({
                "entities": [{"type": "PERSON", "canonical_name": "John", "normalized_key": "john",
                             "aliases": [], "entity_key": "PERSON::john"}],
                "relations": [],
                "structured_facts": [{
                    "entity_key": "PERSON::john",
                    "fact_type": "fact",
                    "quote": "how are you",
                    "confidence": 0.8,
                }],
            }),
        )

        apply_graph_schema(repo._get_conn())
        builder = GraphBuilder(repo._get_conn())
        result = builder.update_from_call(call_id=1, transcript_text=provided_transcript)

        assert result is True
        stats = builder.get_stats()
        assert stats["facts_inserted"] == 1, "Fact should be inserted using parameter transcript"

    def test_verbatim_quote_accepted(self, repo):
        """Quote that's verbatim in transcript → fact inserted."""
        _add_user(repo)
        _add_call(repo)
        transcript = "[me]: i think we should go forward\n[s2]: i agree completely"
        _add_transcript(repo, text=transcript)
        _add_analysis_v2(
            repo,
            raw_response=json.dumps({
                "entities": [{"type": "PERSON", "canonical_name": "Boss", "normalized_key": "boss",
                             "aliases": [], "entity_key": "PERSON::boss"}],
                "relations": [],
                "structured_facts": [{
                    "entity_key": "PERSON::boss",
                    "fact_type": "fact",
                    "quote": "i agree completely",
                    "confidence": 0.85,
                }],
            }),
        )

        apply_graph_schema(repo._get_conn())
        builder = GraphBuilder(repo._get_conn())
        result = builder.update_from_call(call_id=1)

        assert result is True
        stats = builder.get_stats()
        assert stats["facts_inserted"] == 1, "Verbatim quote should be accepted"

    def test_short_quote_rejected(self, repo):
        """Quote < MIN_QUOTE_LEN (8 chars) → rejected by validator."""
        _add_user(repo)
        _add_call(repo)
        _add_transcript(repo, text="[me]: hi ok")
        _add_analysis_v2(
            repo,
            raw_response=json.dumps({
                "entities": [{"type": "PERSON", "canonical_name": "John", "normalized_key": "john",
                             "aliases": [], "entity_key": "PERSON::john"}],
                "relations": [],
                "structured_facts": [{
                    "entity_key": "PERSON::john",
                    "fact_type": "fact",
                    "quote": "hi",
                    "confidence": 0.9,
                }],
            }),
        )

        apply_graph_schema(repo._get_conn())
        builder = GraphBuilder(repo._get_conn())
        result = builder.update_from_call(call_id=1)

        stats = builder.get_stats()
        assert stats["facts_rejected"] >= 1, "Short quote should be rejected"
