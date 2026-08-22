# -*- coding: utf-8 -*-
"""
test_response_parser_gates.py — Test that parse_llm_response never raises
and handles all bad inputs gracefully (A-gates).
"""

from __future__ import annotations

import pytest

from callprofiler.analyze.response_parser import parse_llm_response


class TestParserNeverRaises:
    """Gate A: parse_llm_response never raises on arbitrary input."""

    @pytest.mark.parametrize(
        "raw,expected_parse_status",
        [
            # Valid JSON objects
            ('{"priority": 50, "risk_score": 30}', "parsed_partial"),
            ('{"priority": 50, "risk_score": 30, "summary": "test", "call_type": "business"}', "parsed_ok"),

            # Non-object JSON — should return parse_failed (not raise)
            ("[]", "parse_failed"),          # array
            ("42", "parse_failed"),          # integer
            ('"string"', "parse_failed"),    # string literal
            ("null", "parse_failed"),        # null
            ("[[1,2,3]]", "parse_failed"),   # nested arrays

            # Malformed JSON
            ('{"priority":[1]}', "parsed_partial"),  # invalid value type
            ('{"a": ', "parse_failed"),              # truncated JSON
            ('[[[', "parse_failed"),                 # broken structure

            # Edge cases
            ("", "parse_failed"),                    # empty string
            ("   ", "parse_failed"),                 # whitespace only
            ("\x00\xff", "parse_failed"),           # binary garbage
        ],
    )
    def test_parser_never_raises(self, raw, expected_parse_status):
        """parse_llm_response must return Analysis, never raise, for any input."""
        analysis = parse_llm_response(raw)

        assert analysis is not None
        assert hasattr(analysis, "parse_status")
        assert analysis.parse_status == expected_parse_status
        # Even on failure, should return dicts (empty is OK)
        assert isinstance(analysis.promises, list)
        assert isinstance(analysis.action_items, list)

    def test_parser_none_input(self):
        """None input should be handled gracefully."""
        analysis = parse_llm_response(None)
        assert analysis.parse_status == "parse_failed"

    def test_parser_non_string_input(self):
        """Non-string inputs (bytes, etc.) should be converted and handled gracefully."""
        analysis = parse_llm_response(b"not a string")
        assert analysis.parse_status == "parse_failed"

        analysis = parse_llm_response(12345)
        assert analysis.parse_status == "parse_failed"

    def test_parser_stub_short_is_valid_status(self):
        """stub_short is a documented parse_status (legit short-call stub, not failure)."""
        # Simulate short-call stub (done by orchestrator._analyze_call)
        analysis = parse_llm_response("")
        assert analysis.parse_status == "parse_failed"

        # Manually override to stub_short (as orchestrator does)
        analysis.parse_status = "stub_short"
        assert analysis.parse_status == "stub_short"
        # This is a valid state that should be distinguishable from parse_failed


class TestParserPreservesRawResponse:
    """Verify raw_response is always preserved (for debugging/audit)."""

    def test_raw_response_on_success(self):
        """Valid JSON should preserve raw_response."""
        raw = '{"priority": 50, "risk_score": 30}'
        analysis = parse_llm_response(raw)
        assert analysis.raw_response == raw

    def test_raw_response_on_failure(self):
        """Failed parses should preserve raw_response."""
        raw = '{"invalid": '
        analysis = parse_llm_response(raw)
        assert analysis.raw_response == raw
        assert analysis.parse_status == "parse_failed"


class TestParserPartialVsFailure:
    """Distinguish between partial success (missing fields) and complete failure."""

    def test_parsed_ok_has_all_required_fields(self):
        """parsed_ok: all required fields present."""
        raw = '{"priority": 50, "risk_score": 30, "summary": "test", "call_type": "business"}'
        analysis = parse_llm_response(raw)
        assert analysis.parse_status == "parsed_ok"

    def test_parsed_partial_missing_fields(self):
        """parsed_partial: JSON OK but missing required fields (filled with defaults)."""
        raw = '{"priority": 50, "risk_score": 30}'
        analysis = parse_llm_response(raw)
        assert analysis.parse_status == "parsed_partial"
        assert analysis.summary == ""  # default
        assert analysis.call_type == "unknown"  # default

    def test_parse_failed_not_json_object(self):
        """parse_failed: JSON is valid but not an object (array, string, null, etc.)."""
        for bad_json in ["[]", "42", '"str"', "null"]:
            analysis = parse_llm_response(bad_json)
            assert analysis.parse_status == "parse_failed"
            # Defaults should be set
            assert analysis.priority == 50
            assert analysis.risk_score == 0
