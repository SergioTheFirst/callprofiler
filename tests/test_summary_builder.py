# -*- coding: utf-8 -*-
"""Tests for summary_builder — contact card rebuild + call_type weighting."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from callprofiler.db.repository import Repository
from callprofiler.aggregate.summary_builder import SummaryBuilder, _call_type_weight


class TestCallTypeWeight:
    def test_business_weight_1(self):
        assert _call_type_weight("business") == 1.0

    def test_personal_weight_07(self):
        assert _call_type_weight("personal") == 0.7

    def test_smalltalk_weight_01(self):
        assert _call_type_weight("smalltalk") == 0.1

    def test_short_weight_0(self):
        assert _call_type_weight("short") == 0.0

    def test_spam_weight_0(self):
        assert _call_type_weight("spam") == 0.0

    def test_unknown_weight_05(self):
        assert _call_type_weight("unknown") == 0.5

    def test_none_weight_1(self):
        assert _call_type_weight(None) == 1.0


class TestSummaryBuilder:
    def test_rebuild_contact_empty(self):
        with tempfile.TemporaryDirectory() as td:
            dbpath = str(Path(td) / "test.db")
            repo = Repository(dbpath)
            repo.init_db()
            repo.add_user("u1", "Test", None, "/tmp/in", "/tmp/out", "/tmp/ref.wav")
            cid = repo.get_or_create_contact("u1", "+70001112233", "Test")

            sb = SummaryBuilder(repo)
            sb.rebuild_contact("u1", cid)

            summary = repo.get_contact_summary("u1", cid)
            repo.close()
            assert summary is None or summary.get("total_calls") == 0

    def test_rebuild_contact_with_call(self):
        with tempfile.TemporaryDirectory() as td:
            dbpath = str(Path(td) / "test.db")
            repo = Repository(dbpath)
            repo.init_db()
            repo.add_user("u1", "Test", None, "/tmp/in", "/tmp/out", "/tmp/ref.wav")
            cid = repo.get_or_create_contact("u1", "+70001112233", "Test")
            call_id = repo.create_call("u1", cid, "inbound", datetime.now(), "test.ogg", "md5a", "/tmp/test.ogg")
            from callprofiler.models import Segment
            repo.save_transcripts(call_id, [Segment(start_ms=0, end_ms=5000, text="Hello", speaker="OWNER")])
            analysis = type("obj", (), {
                "priority": 50, "risk_score": 30, "summary": "test",
                "action_items": [], "promises": [],
                "flags": {}, "key_topics": [],
                "raw_response": "{}", "model": "stub", "prompt_version": "v001",
                "call_type": "business",
                "parse_status": "ok", "canonical_json": "{}", "schema_version": "v2",
                "profanity_count": 0, "profanity_density": 0.0,
            })()
            repo.save_analysis(call_id, analysis)

            sb = SummaryBuilder(repo)
            sb.rebuild_contact("u1", cid)

            summary = repo.get_contact_summary("u1", cid)
            repo.close()
            assert summary is not None
            assert summary.get("total_calls") == 1
            assert summary.get("global_risk") == 30

    def test_rebuild_isolation(self):
        with tempfile.TemporaryDirectory() as td:
            dbpath = str(Path(td) / "test.db")
            repo = Repository(dbpath)
            repo.init_db()
            repo.add_user("u1", "A", None, "/a/in", "/a/out", "/a/ref")
            repo.add_user("u2", "B", None, "/b/in", "/b/out", "/b/ref")
            c1 = repo.get_or_create_contact("u1", "+70000000001", "Contact1")
            c2 = repo.get_or_create_contact("u2", "+70000000002", "Contact2")

            call1 = repo.create_call("u1", c1, "outbound", datetime.now(), "a.ogg", "md5_u1", "/tmp/a.ogg")
            call2 = repo.create_call("u2", c2, "outbound", datetime.now(), "b.ogg", "md5_u2", "/tmp/b.ogg")

            from callprofiler.models import Segment
            repo.save_transcripts(call1, [Segment(start_ms=0, end_ms=5000, text="hello", speaker="OWNER")])
            repo.save_transcripts(call2, [Segment(start_ms=0, end_ms=5000, text="world", speaker="OWNER")])

            a = type("obj", (), {
                "priority": 50, "risk_score": 80, "summary": "test",
                "action_items": [], "promises": [],
                "flags": {}, "key_topics": [],
                "raw_response": "{}", "model": "stub", "prompt_version": "v001",
                "call_type": "business", "parse_status": "ok",
                "canonical_json": "{}", "schema_version": "v2",
                "profanity_count": 0, "profanity_density": 0.0,
            })()
            repo.save_analysis(call1, a)
            repo.save_analysis(call2, a)

            sb = SummaryBuilder(repo)
            sb.rebuild_contact("u1", c1)

            s1 = repo.get_contact_summary("u1", c1)
            assert int(s1.get("global_risk") or 0) == 80

            # u2 summary should still be empty (not rebuilt)
            s2 = repo.get_contact_summary("u2", c2)
            repo.close()
            assert s2 is None or int(s2.get("total_calls") or 0) == 0
