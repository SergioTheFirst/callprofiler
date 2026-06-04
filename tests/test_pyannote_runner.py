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


class TestLoadPretrainedCompat:
    """_load_pretrained: совместимость use_auth_token (3.3.x) vs token (3.4+/4.x)."""

    def test_new_pyannote_falls_back_to_token_kwarg(self):
        from callprofiler.diarize.pyannote_runner import _load_pretrained
        seen = {}

        def new_loader(model_id, token=None):  # нет use_auth_token → TypeError
            seen["token"] = token
            return f"OK:{model_id}"

        out = _load_pretrained(new_loader, "pyannote/x", "hf_abc")
        assert out == "OK:pyannote/x"
        assert seen["token"] == "hf_abc"

    def test_old_pyannote_uses_use_auth_token(self):
        from callprofiler.diarize.pyannote_runner import _load_pretrained
        seen = {}

        def old_loader(model_id, use_auth_token=None):
            seen["use_auth_token"] = use_auth_token
            return f"OK:{model_id}"

        out = _load_pretrained(old_loader, "pyannote/y", "hf_xyz")
        assert out == "OK:pyannote/y"
        assert seen["use_auth_token"] == "hf_xyz"

    def test_empty_token_becomes_none(self):
        from callprofiler.diarize.pyannote_runner import _load_pretrained
        seen = {}

        def new_loader(model_id, token=None):
            seen["token"] = token
            return "OK"

        _load_pretrained(new_loader, "m", "")
        assert seen["token"] is None


class TestInMemoryAudio:
    """Аудио передаётся pyannote в памяти ({waveform, sample_rate}) — обход
    torchcodec. Тесты используют только numpy+torch (без pyannote/librosa)."""

    def _runner(self):
        import numpy as np
        from callprofiler.diarize.pyannote_runner import PyannoteRunner
        cfg = MagicMock()
        cfg.hf_token = "t"
        runner = PyannoteRunner(cfg)
        runner.ref_embedding = np.array([1.0, 0.0])
        return runner

    def test_waveform_dict_shape_and_type(self):
        import numpy as np
        import torch
        runner = self._runner()
        with patch(
            "callprofiler.diarize.pyannote_runner._read_mono16k",
            return_value=np.zeros(1600, dtype=np.float32),
        ):
            d = runner._waveform_dict("x.wav")
        assert set(d) == {"waveform", "sample_rate"}
        assert d["sample_rate"] == 16000
        assert isinstance(d["waveform"], torch.Tensor)
        assert tuple(d["waveform"].shape) == (1, 1600)

    def test_embedding_from_dict_is_l2_normalized(self):
        import numpy as np
        runner = self._runner()
        runner.inference = MagicMock(return_value=np.array([3.0, 4.0]))
        emb = runner._embedding_from_dict({"waveform": None, "sample_rate": 16000})
        # 3-4-5 → L2 norm == 1
        assert abs(float(np.linalg.norm(emb)) - 1.0) < 1e-6

    def test_diarize_feeds_dict_not_path(self):
        import numpy as np
        runner = self._runner()

        seg_a = MagicMock(start=0.0, end=1.0, duration=1.0)
        seg_b = MagicMock(start=1.0, end=2.0, duration=1.0)
        diar = MagicMock()
        diar.itertracks.return_value = [
            (seg_a, None, "SPK0"),
            (seg_b, None, "SPK1"),
        ]
        runner.pipeline = MagicMock(return_value=diar)
        runner.inference = MagicMock(return_value=np.array([1.0, 0.0]))

        with patch(
            "callprofiler.diarize.pyannote_runner._read_mono16k",
            return_value=np.ones(32000, dtype=np.float32),
        ):
            out = runner.diarize("x.wav")

        # pyannote вызван с dict (in-memory), НЕ со строкой-путём
        passed = runner.pipeline.call_args[0][0]
        assert isinstance(passed, dict)
        assert "waveform" in passed and passed["sample_rate"] == 16000
        # роли назначены, oба спикера в выводе
        assert out and {s["speaker"] for s in out} == {"OWNER", "OTHER"}

    def test_find_owner_label_in_memory(self):
        import numpy as np
        runner = self._runner()
        # OWNER похож на ref [1,0]; OTHER ортогонален [0,1]
        runner.inference = MagicMock(
            side_effect=[np.array([0.0, 1.0]), np.array([1.0, 0.0])]
        )
        samples = np.ones(32000, dtype=np.float32)
        raw_segs = {"SPK0": [(0.0, 1.0)], "SPK1": [(1.0, 2.0)]}
        owner = runner._find_owner_label(samples, 16000, raw_segs)
        assert owner == "SPK1"
