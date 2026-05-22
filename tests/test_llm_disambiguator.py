import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from callprofiler.graph.llm_disambiguator import LLMDisambiguator


_FAKE_TEMPLATE = "Entity A: {{ENTITY_A}}\nEntity B: {{ENTITY_B}}\nScore: {{SCORE}}\nSignals: {{SIGNALS}}"


@pytest.fixture
def disambiguator():
    with patch.object(
        LLMDisambiguator,
        "_load_prompt",
        return_value=_FAKE_TEMPLATE,
    ):
        return LLMDisambiguator(llm_url="http://test-llm/v1/completions", timeout=30)


def _make_entity(name="Alice", entity_type="PERSON", call_count=3):
    return {
        "canonical_name": name,
        "aliases": [],
        "entity_type": entity_type,
        "call_count": call_count,
        "metrics": {"bs_index": 0.8},
    }


def _make_mock_post(verdict, confidence=0.9, reasoning="test"):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "verdict": verdict,
                        "confidence": confidence,
                        "reasoning": reasoning,
                        "signals_for": [],
                        "signals_against": [],
                    }),
                }
            }
        ],
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


class TestGrayZone:
    def test_below_range(self, disambiguator):
        assert disambiguator.in_gray_zone(0.49) is False

    def test_lower_boundary(self, disambiguator):
        assert disambiguator.in_gray_zone(0.50) is True

    def test_upper_boundary(self, disambiguator):
        assert disambiguator.in_gray_zone(0.64) is True

    def test_above_range(self, disambiguator):
        assert disambiguator.in_gray_zone(0.65) is False


class TestBuildPrompt:
    def test_replaces_placeholders(self, disambiguator):
        entity_a = _make_entity("Alice")
        entity_b = _make_entity("Bob")
        signals = {"shared_number": True}
        prompt = disambiguator._build_prompt(entity_a, entity_b, 0.600, signals)
        assert '"Alice"' in prompt
        assert '"Bob"' in prompt
        assert "0.600" in prompt
        assert "shared_number" in prompt


class TestDisambiguatePair:
    @patch("callprofiler.graph.llm_disambiguator.requests.post")
    def test_merge(self, mock_post, disambiguator):
        mock_post.return_value = _make_mock_post("MERGE")
        result = disambiguator.disambiguate_pair(
            _make_entity("E1"), _make_entity("E2"), 0.600, {}
        )
        assert result["llm_says"] == "MERGE"
        assert result["confidence"] == 0.9

    @patch("callprofiler.graph.llm_disambiguator.requests.post")
    def test_separate(self, mock_post, disambiguator):
        mock_post.return_value = _make_mock_post("SEPARATE")
        result = disambiguator.disambiguate_pair(
            _make_entity("E1"), _make_entity("E2"), 0.550, {}
        )
        assert result["llm_says"] == "SEPARATE"

    @patch("callprofiler.graph.llm_disambiguator.requests.post")
    def test_unclear(self, mock_post, disambiguator):
        mock_post.return_value = _make_mock_post("UNCLEAR", confidence=0.0)
        result = disambiguator.disambiguate_pair(
            _make_entity("E1"), _make_entity("E2"), 0.510, {}
        )
        assert result["llm_says"] == "UNCLEAR"

    @patch("callprofiler.graph.llm_disambiguator.requests.post")
    def test_unknown_verdict_normalized_to_unclear(self, mock_post, disambiguator):
        mock_post.return_value = _make_mock_post("MAYBE", confidence=0.5)
        result = disambiguator.disambiguate_pair(
            _make_entity("E1"), _make_entity("E2"), 0.520, {}
        )
        assert result["llm_says"] == "UNCLEAR"

    @patch("callprofiler.graph.llm_disambiguator.requests.post")
    def test_request_exception_returns_unclear(self, mock_post, disambiguator):
        mock_post.side_effect = requests.RequestException("Connection refused")
        result = disambiguator.disambiguate_pair(
            _make_entity("E1"), _make_entity("E2"), 0.530, {}
        )
        assert result["llm_says"] == "UNCLEAR"
        assert result["confidence"] == 0.0
        assert "Connection refused" in result["reasoning"]

    def test_outside_gray_zone_raises(self, disambiguator):
        with pytest.raises(ValueError):
            disambiguator.disambiguate_pair(
                _make_entity("E1"), _make_entity("E2"), 0.70, {}
            )


class TestParseResponse:
    def test_strips_json_markdown_fence(self, disambiguator):
        raw = '```json\n{"verdict":"MERGE","confidence":0.8}\n```'
        result = disambiguator._parse_response(raw)
        assert result["llm_says"] == "MERGE"
        assert result["confidence"] == 0.8

    def test_strips_generic_markdown_fence(self, disambiguator):
        raw = '```\n{"verdict":"SEPARATE","confidence":0.7}\n```'
        result = disambiguator._parse_response(raw)
        assert result["llm_says"] == "SEPARATE"

    def test_invalid_json_returns_unclear(self, disambiguator):
        raw = "not json"
        result = disambiguator._parse_response(raw)
        assert result["llm_says"] == "UNCLEAR"
        assert result["confidence"] == 0.0
        assert result["raw_response"] == raw

    def test_missing_verdict_returns_unclear(self, disambiguator):
        raw = '{"confidence":0.5}'
        result = disambiguator._parse_response(raw)
        assert result["llm_says"] == "UNCLEAR"

    def test_default_fields_populated(self, disambiguator):
        raw = '{"verdict":"MERGE"}'
        result = disambiguator._parse_response(raw)
        assert result["llm_says"] == "MERGE"
        assert result["confidence"] == 0.0
        assert result["reasoning"] == ""
        assert result["signals_for"] == []
        assert result["signals_against"] == []
