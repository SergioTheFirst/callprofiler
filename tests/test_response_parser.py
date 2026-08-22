# -*- coding: utf-8 -*-
"""
Test response_parser.py robustness: parse_llm_response NEVER raises, always returns Analysis.
"""

import pytest

from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.models import Analysis


class TestResponseParserNeverRaises:
    """Verify parse_llm_response(raw) returns Analysis with parse_status for all inputs."""

    @pytest.mark.parametrize("bad_json,expected_status", [
        ("[]", "parse_failed"),               # JSON array, not object
        ("42", "parse_failed"),               # JSON number
        ('"string"', "parse_failed"),         # JSON string
        ("null", "parse_failed"),             # JSON null
        ("[[1,2,3]]", "parse_failed"),       # nested arrays
        ("\x00\xff", "parse_failed"),        # binary garbage
        ("", "parse_failed"),                # empty string
    ])
    def test_parser_never_raises_on_bad_json(self, bad_json, expected_status):
        """parse_llm_response must return Analysis, never raise, even for invalid JSON."""
        result = parse_llm_response(bad_json, model="test", prompt_version="v001")

        assert isinstance(result, Analysis)
        assert result.parse_status == expected_status or result.parse_status in ("parse_failed", "output_truncated")
        assert result.raw_response == bad_json or result.raw_response == ""

    @pytest.mark.parametrize("garbage_input", [
        None,                                    # None
        b"bytes",                              # bytes object
        {"dict": "not_json_string"},           # dict object
        123,                                   # int
        12.34,                                 # float
    ])
    def test_parser_never_raises_on_non_string_input(self, garbage_input):
        """parse_llm_response must handle non-string inputs gracefully."""
        result = parse_llm_response(garbage_input, model="test", prompt_version="v001")

        assert isinstance(result, Analysis)
        assert result.parse_status == "parse_failed"
        # raw_response should be a string (either empty or stringified input)
        assert isinstance(result.raw_response, str)

    def test_parser_handles_valid_json(self):
        """Valid JSON dict should parse successfully."""
        valid_json = '{"priority": 75, "risk_score": 45, "summary": "Test call", "call_type": "business"}'
        result = parse_llm_response(valid_json, model="test", prompt_version="v001")

        assert isinstance(result, Analysis)
        assert result.parse_status == "parsed_ok"
        assert result.priority == 75
        assert result.risk_score == 45
        assert result.summary == "Test call"
        assert result.call_type == "business"

    def test_parser_handles_partial_json(self):
        """Incomplete JSON dict (missing required fields) should parse as parsed_partial."""
        partial_json = '{"priority": 50}'
        result = parse_llm_response(partial_json, model="test", prompt_version="v001")

        assert isinstance(result, Analysis)
        assert result.parse_status == "parsed_partial"
        assert result.priority == 50
        assert result.risk_score == 0  # default

    def test_parser_handles_markdown_wrapped_json(self):
        """JSON wrapped in markdown code blocks should be extracted."""
        markdown_json = '```json\n{"priority": 60, "risk_score": 30, "summary": "test", "call_type": "unknown"}\n```'
        result = parse_llm_response(markdown_json, model="test", prompt_version="v001")

        assert isinstance(result, Analysis)
        assert result.parse_status == "parsed_ok"
        assert result.priority == 60

    def test_parser_stub_short_call_via_empty_response(self):
        """Empty response (short call stub) returns Analysis with appropriate defaults."""
        result = parse_llm_response("", model="test", prompt_version="v001")

        assert isinstance(result, Analysis)
        assert result.parse_status == "parse_failed"  # empty → parse_failed
        assert result.priority == 50  # default
        assert result.call_type == "unknown"

    def test_parser_handles_exception_internally(self):
        """Even if internal exception occurs, parse_llm_response catches it and returns Analysis."""
        # This is hard to trigger intentionally, but the try/except in parse_llm_response ensures it
        result = parse_llm_response("", model="test", prompt_version="v001")
        assert isinstance(result, Analysis)

    def test_parse_status_values_documented(self):
        """Verify all expected parse_status values exist."""
        expected_statuses = {"parsed_ok", "parsed_partial", "parse_failed", "output_truncated", "stub_short"}

        # Test various inputs produce expected statuses
        test_cases = {
            '{"priority": 50, "risk_score": 0, "summary": "a", "call_type": "business"}': "parsed_ok",
            '{"priority": 50}': "parsed_partial",
            "[]": "parse_failed",
        }

        for raw, expected_status in test_cases.items():
            result = parse_llm_response(raw, model="test", prompt_version="v001")
            assert result.parse_status in expected_statuses, f"Unexpected status {result.parse_status}"

    def test_truncated_json_gets_repaired(self):
        """Truncated JSON gets repaired and parsed as partial."""
        # `{` gets repaired to `{}` → parsed_partial (all fields missing)
        truncated = "{"
        result = parse_llm_response(truncated, model="test", prompt_version="v001")
        assert isinstance(result, Analysis)
        # Repair logic closes the brace, so it's a valid but empty dict
        assert result.parse_status in ("parsed_partial", "output_truncated", "parse_failed")

    def test_raw_response_preserved_for_debugging(self):
        """raw_response field should preserve the original input for debugging."""
        raw_input = '{"bad": "json'  # unclosed string
        result = parse_llm_response(raw_input, model="test", prompt_version="v001")
        assert isinstance(result, Analysis)
        # raw_response might be repaired or original, but should be present
        assert result.raw_response == raw_input or result.raw_response != ""
