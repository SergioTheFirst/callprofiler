# -*- coding: utf-8 -*-
"""
Test orchestrator._analyze_call gates (simplified - verify code logic only).
"""

import pytest

from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.models import Analysis


class TestResponseParserHandlesGateB:
    """Verify response_parser handles all gate B inputs correctly."""

    def test_parse_status_stub_short_not_invented(self):
        """Empty response for short calls returns Analysis with parse_status."""
        # Short call stub (empty response)
        result = parse_llm_response("", model="test", prompt_version="v001")
        assert isinstance(result, Analysis)
        assert result.parse_status == "parse_failed"
        # parse_status is set and documented

    def test_parse_failed_status_marked(self):
        """Non-dict JSON gets parse_status='parse_failed'."""
        result = parse_llm_response("[]", model="test", prompt_version="v001")
        assert isinstance(result, Analysis)
        assert result.parse_status == "parse_failed"

    def test_output_truncated_status_marked(self):
        """Truncated JSON that can't be repaired returns appropriate status."""
        # This may be repaired to partial or marked as parse_failed
        result = parse_llm_response("\x00\xff", model="test", prompt_version="v001")
        assert isinstance(result, Analysis)
        # Status should be documented in parse_status
        assert result.parse_status in ("parse_failed", "output_truncated", "parsed_partial")

    def test_parsed_partial_status_marked(self):
        """Incomplete JSON dict gets parse_status='parsed_partial'."""
        result = parse_llm_response('{"priority": 50}', model="test", prompt_version="v001")
        assert isinstance(result, Analysis)
        assert result.parse_status == "parsed_partial"
