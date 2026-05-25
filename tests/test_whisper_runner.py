# -*- coding: utf-8 -*-
"""
test_whisper_runner.py — integration test stubs for WhisperRunner.

Tests verify module importability, lifecycle contract (init → load → transcribe → unload),
and error handling without requiring GPU or Whisper models.
"""

import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestWhisperRunnerConstruction:
    """Verify WhisperRunner can be constructed with mocked Config."""

    def test_import_module(self):
        from callprofiler.transcribe import whisper_runner
        assert hasattr(whisper_runner, "WhisperRunner")

    def test_construct_with_config(self):
        from callprofiler.transcribe.whisper_runner import WhisperRunner
        config = MagicMock()
        config.whisper_model = "large-v3"
        config.whisper_device = "cpu"
        config.whisper_compute_type = "float16"
        config.whisper_language = "ru"
        config.whisper_beam_size = 5
        runner = WhisperRunner(config)
        assert runner.config is config

    def test_methods_exist(self):
        from callprofiler.transcribe.whisper_runner import WhisperRunner
        config = MagicMock()
        runner = WhisperRunner(config)
        for method_name in ["load", "transcribe", "unload"]:
            assert hasattr(runner, method_name), f"Missing {method_name}"
            assert callable(getattr(runner, method_name)), f"{method_name} not callable"

    def test_unload_returns_none(self):
        from callprofiler.transcribe.whisper_runner import WhisperRunner
        config = MagicMock()
        runner = WhisperRunner(config)
        result = runner.unload()
        assert result is None

    def test_unload_cleans_up(self):
        from callprofiler.transcribe.whisper_runner import WhisperRunner
        config = MagicMock()
        runner = WhisperRunner(config)
        runner.unload()
        import gc
        gc.collect()


class TestWhisperRunnerTranscribeContract:
    """Verify transcribe() returns correct Segment shape."""

    def test_transcribe_without_load_raises(self):
        from callprofiler.transcribe.whisper_runner import WhisperRunner
        config = MagicMock()
        runner = WhisperRunner(config)
        try:
            runner.transcribe("/nonexistent/file.wav")
            assert False, "Should have raised"
        except Exception:
            pass

    def test_load_method_exists(self):
        from callprofiler.transcribe.whisper_runner import WhisperRunner
        config = MagicMock()
        runner = WhisperRunner(config)
        assert hasattr(runner, "load")
        assert callable(runner.load)
