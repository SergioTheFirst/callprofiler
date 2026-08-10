# -*- coding: utf-8 -*-
"""test_pyannote_ref_isolation.py — регресс T-10 (S0): утечка ref_embedding
между профилями при смене ref_audio без выгрузки модели pyannote.

pyannote не зависит от ref_audio — только ref_embedding. ``load()`` теперь
идемпотентен ПО REF (fingerprint = путь+размер+mtime), не по факту загрузки:
тот же ref → no-op; другой ref → модель не перезагружается, эмбеддинг
пересобирается. Мокаются pipeline/_build_ref_embedding — GPU/модели не нужны.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# S0-регресс (T-10) на уровне САМОГО runner'а — требует torch по существу.
# ВАЖНО: часть той же защиты (сторож отпечатка в _diarize_batch) продублирована
# в test_orchestrator_roles.py, который torch НЕ требует и потому работает и в
# облаке. Полное покрытие S0 — только там, где ML-стек установлен.
pytest.importorskip("torch", reason="ML-стек недоступен (cloud-прогон)")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from callprofiler.config import Config
from callprofiler.pipeline.orchestrator import Orchestrator


def _runner(tmp_path):
    from callprofiler.diarize.pyannote_runner import PyannoteRunner
    cfg = MagicMock()
    cfg.hf_token = "t"
    cfg.models.pyannote_batch_size = 32
    r = PyannoteRunner(cfg)
    r.pipeline = MagicMock()  # уже "загружен"
    r.inference = MagicMock()
    return r


def _write(tmp_path, name, content=b"x"):
    p = tmp_path / name
    p.write_bytes(content)
    return str(p)


class TestRefFingerprintIsolation:
    def test_two_refs_a_then_b_embedding_matches_requested_ref(self, tmp_path):
        ref_a = _write(tmp_path, "a.wav", b"AAAA")
        ref_b = _write(tmp_path, "b.wav", b"BBBBBB")
        r = _runner(tmp_path)

        with patch.object(r, "_build_ref_embedding", side_effect=["EMB_A", "EMB_B"]) as m:
            r.load(ref_a)
            assert r.ref_embedding == "EMB_A"
            r.load(ref_b)
            assert r.ref_embedding == "EMB_B"
        assert m.call_count == 2

    def test_two_refs_b_then_a_embedding_matches_requested_ref(self, tmp_path):
        ref_a = _write(tmp_path, "a.wav", b"AAAA")
        ref_b = _write(tmp_path, "b.wav", b"BBBBBB")
        r = _runner(tmp_path)

        with patch.object(r, "_build_ref_embedding", side_effect=["EMB_B", "EMB_A"]) as m:
            r.load(ref_b)
            assert r.ref_embedding == "EMB_B"
            r.load(ref_a)
            assert r.ref_embedding == "EMB_A"
        assert m.call_count == 2

    def test_repeat_load_same_ref_no_second_embedding_build(self, tmp_path):
        ref_a = _write(tmp_path, "a.wav", b"AAAA")
        r = _runner(tmp_path)

        with patch.object(r, "_build_ref_embedding", return_value="EMB_A") as m:
            r.load(ref_a)
            r.load(ref_a)
        assert m.call_count == 1

    def test_ref_switch_does_not_reload_model(self, tmp_path):
        ref_a = _write(tmp_path, "a.wav", b"AAAA")
        ref_b = _write(tmp_path, "b.wav", b"BBBBBB")
        r = _runner(tmp_path)
        pipeline_before = r.pipeline

        with patch.object(r, "_build_ref_embedding", side_effect=["EMB_A", "EMB_B"]):
            r.load(ref_a)
            r.load(ref_b)

        assert r.pipeline is pipeline_before  # не пересоздан

    def test_unload_resets_fingerprint_and_embedding(self, tmp_path):
        ref_a = _write(tmp_path, "a.wav", b"AAAA")
        r = _runner(tmp_path)
        with patch.object(r, "_build_ref_embedding", return_value="EMB_A"):
            r.load(ref_a)

        r.unload()

        assert r.ref_fingerprint is None
        assert r.ref_embedding is None

    def test_missing_ref_raises_fnf_even_when_pipeline_loaded(self, tmp_path):
        ref_a = _write(tmp_path, "a.wav", b"AAAA")
        r = _runner(tmp_path)
        with patch.object(r, "_build_ref_embedding", return_value="EMB_A"):
            r.load(ref_a)

        try:
            r.load(str(tmp_path / "missing.wav"))
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass


# ── _diarize_batch: разные группы должны диаризоваться СВОИМ эмбеддингом ──

class _RepoStatus:
    def update_call_status(self, *a, **k):
        pass


class _FakePyannoteFingerprinted:
    """Фейк, повторяющий контракт реального runner'а: load() меняет
    ref_fingerprint/ref_embedding под запрошенный ref."""

    def __init__(self):
        self.load_calls = 0
        self.unload_calls = 0
        self.ref_fingerprint = None
        self.ref_embedding = None
        self.diarize_seen_embeddings = []

    def load(self, ref_audio):
        from callprofiler.diarize.pyannote_runner import _ref_fingerprint
        self.load_calls += 1
        self.ref_fingerprint = _ref_fingerprint(ref_audio)
        self.ref_embedding = f"EMB[{ref_audio}]"

    def diarize(self, norm_path):
        self.diarize_seen_embeddings.append(self.ref_embedding)
        return [{"start_ms": 0, "end_ms": 100, "speaker": "OWNER"}]

    def unload(self):
        self.unload_calls += 1


def test_diarize_batch_two_groups_each_uses_own_embedding(tmp_path):
    ref_a = _write(tmp_path, "a.wav")
    ref_b = _write(tmp_path, "b.wav")
    cfg = Config()
    cfg.features.enable_diarization = True
    cfg.hf_token = "hf"
    o = Orchestrator(cfg, _RepoStatus())
    fake = _FakePyannoteFingerprinted()
    o.pyannote_runner = fake

    calls = [
        {"call_id": 1, "user_id": "ua", "_norm_path": "1.wav"},
        {"call_id": 2, "user_id": "ub", "_norm_path": "2.wav"},
    ]
    users = {"ua": {"ref_audio": ref_a}, "ub": {"ref_audio": ref_b}}

    turns_map = o._diarize_batch(calls, users)

    assert fake.load_calls == 2
    assert fake.diarize_seen_embeddings == [f"EMB[{ref_a}]", f"EMB[{ref_b}]"]
    assert turns_map[1] and turns_map[2]


def test_diarize_batch_fingerprint_mismatch_skips_group_unknown(tmp_path):
    """Если load() не выставил ожидаемый fingerprint (симулируем баг реального
    класса) — группа пропускается, роли остаются UNKNOWN, диаризация звонков
    группы НЕ вызывается чужим эталоном."""
    ref_a = _write(tmp_path, "a.wav")
    cfg = Config()
    cfg.features.enable_diarization = True
    cfg.hf_token = "hf"
    o = Orchestrator(cfg, _RepoStatus())

    fake = _FakePyannoteFingerprinted()
    # Симулируем баг: load() не обновляет fingerprint (как старый код).
    fake.load = lambda ref_audio: setattr(fake, "load_calls", fake.load_calls + 1)
    o.pyannote_runner = fake

    calls = [{"call_id": 1, "user_id": "ua", "_norm_path": "1.wav"}]
    users = {"ua": {"ref_audio": ref_a}}

    turns_map = o._diarize_batch(calls, users)

    assert turns_map == {1: []}  # роли UNKNOWN, диаризация НЕ выполнена
    assert fake.diarize_seen_embeddings == []
