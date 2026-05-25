# -*- coding: utf-8 -*-
"""
test_pyannote_runner.py — integration test stubs for PyannoteRunner.

Tests verify module importability, lifecycle contract (init → load → diarize → unload),
and error handling without requiring GPU or pyannote models.
"""

import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestPyannoteRunnerConstruction:
    """Verify PyannoteRunner can be constructed with mocked Config."""

    def test_import_module(self):
        from callprofiler.diarize import pyannote_runner
        assert hasattr(pyannote_runner, "PyannoteRunner")

    def test_construct_with_config(self):
        from callprofiler.diarize.pyannote_runner import PyannoteRunner
        config = MagicMock()
        config.hf_token = "test-token"
        runner = PyannoteRunner(config)
        assert runner.config is config

    def test_initial_state(self):
        from callprofiler.diarize.pyannote_runner import PyannoteRunner
        config = MagicMock()
        runner = PyannoteRunner(config)
        assert runner.pipeline is None
        assert runner.inference is None
        assert runner.ref_embedding is None

    def test_methods_exist(self):
        from callprofiler.diarize.pyannote_runner import PyannoteRunner
        config = MagicMock()
        runner = PyannoteRunner(config)
        for method_name in ["load", "diarize", "unload"]:
            assert hasattr(runner, method_name), f"Missing {method_name}"
            assert callable(getattr(runner, method_name)), f"{method_name} not callable"

    def test_unload_returns_none(self):
        from callprofiler.diarize.pyannote_runner import PyannoteRunner
        config = MagicMock()
        runner = PyannoteRunner(config)
        result = runner.unload()
        assert result is None

    def test_load_raises_fnf_on_missing_ref(self):
        from callprofiler.diarize.pyannote_runner import PyannoteRunner
        config = MagicMock()
        runner = PyannoteRunner(config)
        try:
            runner.load("/nonexistent/ref_audio.wav")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass


class TestPyannoteRunnerPrivateMethods:
    """Verify private helper method signatures."""

    def test_get_embedding_exists(self):
        from callprofiler.diarize.pyannote_runner import PyannoteRunner
        config = MagicMock()
        runner = PyannoteRunner(config)
        assert hasattr(runner, "_get_embedding")
        assert callable(runner._get_embedding)

    def test_build_ref_embedding_exists(self):
        from callprofiler.diarize.pyannote_runner import PyannoteRunner
        config = MagicMock()
        runner = PyannoteRunner(config)
        assert hasattr(runner, "_build_ref_embedding")
        assert callable(runner._build_ref_embedding)

    def test_find_owner_label_exists(self):
        from callprofiler.diarize.pyannote_runner import PyannoteRunner
        config = MagicMock()
        runner = PyannoteRunner(config)
        assert hasattr(runner, "_find_owner_label")
        assert callable(runner._find_owner_label)
