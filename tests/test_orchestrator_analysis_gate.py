# -*- coding: utf-8 -*-
"""
tests/test_orchestrator_analysis_gate.py — Gate B: orchestrator never invents analyses on failure.

Validates:
  - LLM ConnectionError/RuntimeError → status='error', save_analysis NOT called, return
  - parse_failed/parsed_partial/output_truncated result → status='error', save_analysis NOT called, return
  - parsed_ok → save_analysis called
  - Short-call stub → parse_status='stub_short', saved (legit)
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.models import Analysis, Segment


class TestOrchestratorAnalysisGate:
    """Gate B: orchestrator LLM response → save decision."""

    @pytest.fixture
    def config(self):
        """Mock config."""
        cfg = MagicMock()
        cfg.models.llm_model = "test-model"
        cfg.models.llm_url = "http://localhost:8080/v1"
        cfg.models.prompt_max_chars = 10000
        cfg.models.llm_n_ctx = 16000
        cfg.features.llm_json_mode = False
        cfg.prompts_dir = "/fake/prompts"
        return cfg

    @pytest.fixture
    def repo(self):
        """Mock repository."""
        repo = MagicMock()
        repo._get_conn = MagicMock(return_value=MagicMock())
        repo.update_call_status = MagicMock()
        repo.save_analysis = MagicMock()
        return repo

    @pytest.fixture
    def orchestrator(self, config, repo):
        """Create orchestrator with mocked dependencies."""
        from callprofiler.pipeline.orchestrator import Orchestrator

        with patch("callprofiler.pipeline.orchestrator.PromptBuilder"):
            orch = Orchestrator(config, repo)
        return orch

    def _make_call(self, call_id=1, user_id="test_user"):
        """Helper to create a call dict."""
        return {
            "call_id": call_id,
            "user_id": user_id,
            "contact_id": 100,
            "call_datetime": "2026-08-22T10:00:00",
            "direction": "INCOMING",
            "duration_sec": 300,
        }

    def _make_segments(self, text="hello world this is a much longer test call that exceeds fifty characters for sure", speaker="OTHER"):
        """Helper to create segments. Default text >50 chars to avoid short-call stub path."""
        return [
            Segment(
                speaker=speaker,
                text=text,
                start_ms=0,
                end_ms=5000,
            )
        ]

    def test_short_call_gets_stub_short(self, orchestrator, repo):
        """Short call → parse_status='stub_short' (legitimate stub, not error)."""
        call = self._make_call()
        segments = self._make_segments(text="hi")  # <50 chars

        with patch("callprofiler.pipeline.orchestrator.uow_for"):
            orchestrator._analyze_call(call["call_id"], call, segments)

        # Should save the analysis
        assert repo.save_analysis.called, "save_analysis should be called for short-call stub"
        saved_analysis = repo.save_analysis.call_args[0][2]
        assert saved_analysis.parse_status == "stub_short"
        assert saved_analysis.call_type == "short"

    def test_llm_connection_error_no_save(self, orchestrator, repo, config):
        """LLM ConnectionError → update_call_status('error'), save_analysis NOT called."""
        call = self._make_call()
        segments = self._make_segments()  # >50 chars, will try LLM

        with patch("callprofiler.analyze.service.AnalysisService") as mock_svc_class:
            mock_svc = MagicMock()
            mock_svc.analyze_one_call.side_effect = ConnectionError("LLM unreachable")
            mock_svc_class.return_value = mock_svc

            orchestrator._analyze_call(call["call_id"], call, segments)

        # Should update status to error
        assert repo.update_call_status.called, "update_call_status should be called on ConnectionError"
        call_args = repo.update_call_status.call_args
        assert call_args[0][2] == "error", f"Expected status='error', got {call_args[0]}"

        # Should NOT save analysis
        assert not repo.save_analysis.called, "save_analysis should NOT be called on LLM error"

    def test_llm_runtime_error_no_save(self, orchestrator, repo):
        """LLM RuntimeError → update_call_status('error'), save_analysis NOT called."""
        call = self._make_call()
        segments = self._make_segments()

        with patch("callprofiler.analyze.service.AnalysisService") as mock_svc_class:
            mock_svc = MagicMock()
            mock_svc.analyze_one_call.side_effect = RuntimeError("LLM crash")
            mock_svc_class.return_value = mock_svc

            orchestrator._analyze_call(call["call_id"], call, segments)

        assert repo.update_call_status.called
        assert not repo.save_analysis.called, "save_analysis should NOT be called on RuntimeError"

    def test_parse_failed_no_save(self, orchestrator, repo):
        """parse_failed result → update_call_status('error'), save_analysis NOT called."""
        call = self._make_call()
        segments = self._make_segments()

        with patch("callprofiler.analyze.service.AnalysisService") as mock_svc_class:
            mock_svc = MagicMock()
            analysis = parse_llm_response("not json")
            assert analysis.parse_status == "parse_failed"
            mock_svc.analyze_one_call.return_value = analysis
            mock_svc_class.return_value = mock_svc

            orchestrator._analyze_call(call["call_id"], call, segments)

        assert repo.update_call_status.called
        call_args = repo.update_call_status.call_args
        assert call_args[0][2] == "error"
        assert not repo.save_analysis.called, "save_analysis should NOT be called on parse_failed"

    def test_parsed_partial_no_save(self, orchestrator, repo):
        """parsed_partial result → update_call_status('error'), save_analysis NOT called."""
        call = self._make_call()
        segments = self._make_segments()

        with patch("callprofiler.analyze.service.AnalysisService") as mock_svc_class:
            mock_svc = MagicMock()
            # Create a valid JSON that's missing required fields
            analysis = parse_llm_response('{"priority": 70}')
            assert analysis.parse_status == "parsed_partial"
            mock_svc.analyze_one_call.return_value = analysis
            mock_svc_class.return_value = mock_svc

            orchestrator._analyze_call(call["call_id"], call, segments)

        assert repo.update_call_status.called
        assert not repo.save_analysis.called, "save_analysis should NOT be called on parsed_partial"

    def test_output_truncated_no_save(self, orchestrator, repo):
        """output_truncated result → update_call_status('error'), save_analysis NOT called."""
        call = self._make_call()
        segments = self._make_segments()

        with patch("callprofiler.analyze.service.AnalysisService") as mock_svc_class:
            mock_svc = MagicMock()
            # Simulate truncated output
            analysis = Analysis(
                priority=50,
                risk_score=0,
                summary="truncated",
                call_type="unknown",
                parse_status="output_truncated",
                raw_response='{"priority": 50,',  # Truncated JSON
            )
            mock_svc.analyze_one_call.return_value = analysis
            mock_svc_class.return_value = mock_svc

            orchestrator._analyze_call(call["call_id"], call, segments)

        assert repo.update_call_status.called
        assert not repo.save_analysis.called, "save_analysis should NOT be called on output_truncated"

    def test_parsed_ok_saves(self, orchestrator, repo):
        """parsed_ok result → save_analysis called."""
        call = self._make_call()
        segments = self._make_segments()

        with patch("callprofiler.analyze.service.AnalysisService") as mock_svc_class:
            mock_svc = MagicMock()
            analysis = parse_llm_response(
                '{"priority": 70, "risk_score": 45, "summary": "good", "call_type": "business"}'
            )
            assert analysis.parse_status == "parsed_ok"
            mock_svc.analyze_one_call.return_value = analysis
            mock_svc_class.return_value = mock_svc

            with patch("callprofiler.pipeline.orchestrator.uow_for"):
                orchestrator._analyze_call(call["call_id"], call, segments)

        assert repo.save_analysis.called, "save_analysis should be called on parsed_ok"
        assert not repo.update_call_status.called or repo.update_call_status.call_args[0][2] != "error"
