# -*- coding: utf-8 -*-
"""test_orchestrator_roles.py — выбор пути транскрибации по ролям.

_asr_transcribe: GigaAM + turns → transcribe_turns; иначе flat (+assign_speakers).
pyannote/GigaAM не требуются (asr_runner подменяется фейком).
"""
import sys

from callprofiler.config import Config
from callprofiler.pipeline.orchestrator import Orchestrator


class _Repo:
    pass


class _ASRWithTurns:
    def __init__(self):
        self.flat_called = False
        self.turns_seen = None

    def transcribe_turns(self, norm_path, turns):
        self.turns_seen = turns
        return ["TURNS"]

    def transcribe(self, norm_path):
        self.flat_called = True
        return ["FLAT"]


class _ASRFlatOnly:
    def transcribe(self, norm_path):
        return ["FLAT"]


def test_uses_transcribe_turns_when_turns_and_supported():
    o = Orchestrator(Config(), _Repo())
    o.asr_runner = _ASRWithTurns()
    turns = [{"start_ms": 0, "end_ms": 1000, "speaker": "OWNER"}]

    out = o._asr_transcribe("norm.wav", turns)

    assert out == ["TURNS"]
    assert o.asr_runner.turns_seen == turns
    assert o.asr_runner.flat_called is False


def test_flat_when_no_turns():
    o = Orchestrator(Config(), _Repo())
    o.asr_runner = _ASRWithTurns()

    out = o._asr_transcribe("norm.wav", [])

    assert out == ["FLAT"]
    assert o.asr_runner.flat_called is True


def test_diarize_turns_returns_empty_when_disabled():
    cfg = Config()
    cfg.features.enable_diarization = False
    o = Orchestrator(cfg, _Repo())

    assert o._diarize_turns(1, "norm.wav", "ref.wav") == []
    assert o.pyannote_runner is None  # pyannote не трогали


def test_diarize_turns_returns_empty_when_no_ref(tmp_path):
    cfg = Config()
    cfg.features.enable_diarization = True
    o = Orchestrator(cfg, _Repo())

    # ref_audio не существует → [] без загрузки pyannote
    assert o._diarize_turns(1, "norm.wav", str(tmp_path / "missing.wav")) == []
    assert o.pyannote_runner is None
    assert "no_ref" in o._diag_warned


def test_diarize_turns_warns_when_pyannote_missing(tmp_path, monkeypatch):
    """ref есть, но стек ролей не установлен → [] + явный warning 'no_pyannote'.

    Раньше ImportError pyannote сваливался в один невнятный warning; теперь
    причина называется один раз с командой установки. ImportError форсим через
    sys.modules, чтобы тест был детерминирован и на боксе (где pyannote стоит).
    """
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"x")
    cfg = Config()
    cfg.features.enable_diarization = True
    cfg.hf_token = "hf_present"
    o = Orchestrator(cfg, _Repo())
    monkeypatch.setitem(sys.modules, "callprofiler.diarize.pyannote_runner", None)

    assert o._diarize_turns(1, "norm.wav", str(ref)) == []
    assert "no_pyannote" in o._diag_warned


def test_diarize_turns_warns_when_token_empty(tmp_path, monkeypatch):
    """ref есть, но HF_TOKEN пуст → предупреждение 'no_token' (gated → 401)."""
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"x")
    cfg = Config()
    cfg.features.enable_diarization = True
    cfg.hf_token = ""
    o = Orchestrator(cfg, _Repo())
    monkeypatch.setitem(sys.modules, "callprofiler.diarize.pyannote_runner", None)

    o._diarize_turns(1, "norm.wav", str(ref))
    assert "no_token" in o._diag_warned


def test_warn_once_dedups_by_key():
    o = Orchestrator(Config(), _Repo())
    o._warn_once("k", "msg %s", 1)
    o._warn_once("k", "msg %s", 2)
    assert o._diag_warned == {"k"}


# ── _diarize_batch: pyannote грузится ОДИН раз на батч (узкое место масштаба) ──

class _RepoStatus:
    def update_call_status(self, *a, **k):
        pass


class _FakePyannote:
    def __init__(self):
        self.load_calls = 0
        self.diarize_calls = 0
        self.unload_calls = 0

    def load(self, ref_audio):
        self.load_calls += 1

    def diarize(self, norm_path):
        self.diarize_calls += 1
        return [{"start_ms": 0, "end_ms": 100, "speaker": "OWNER"}]

    def unload(self):
        self.unload_calls += 1


def test_diarize_batch_loads_once_for_group(tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"x")
    cfg = Config()
    cfg.features.enable_diarization = True
    cfg.hf_token = "hf"
    o = Orchestrator(cfg, _RepoStatus())
    fake = _FakePyannote()
    o.pyannote_runner = fake  # подставляем заранее → код не импортирует/создаёт
    calls = [{"call_id": i, "user_id": "me", "_norm_path": f"{i}.wav"} for i in (1, 2, 3)]

    turns_map = o._diarize_batch(calls, {"me": {"ref_audio": str(ref)}})

    assert fake.load_calls == 1   # ОДНА загрузка на 3 звонка (не 3)
    assert fake.diarize_calls == 3
    # pyannote НЕ выгружается внутри _diarize_batch — остаётся резидентной для
    # ко-резидентности с GigaAM ВНУТРИ Фазы 2 (GPU-sequential: оба уходят из
    # VRAM до Фазы 3/LLM). Выгрузка делегирована _unload_models().
    assert fake.unload_calls == 0
    assert set(turns_map) == {1, 2, 3}
    assert all(turns_map[i] for i in (1, 2, 3))

    # Контракт выгрузки: _unload_models() освобождает VRAM до LLM-фазы (Qwen
    # Q8_0 ~10GB + ASR/pyannote ~5GB > 12GB на RTX 3060 → иначе OOM).
    o._unload_models()
    assert fake.unload_calls == 1


def test_diarize_batch_disabled_no_load():
    cfg = Config()
    cfg.features.enable_diarization = False
    o = Orchestrator(cfg, _RepoStatus())
    fake = _FakePyannote()
    o.pyannote_runner = fake
    out = o._diarize_batch(
        [{"call_id": 1, "user_id": "me", "_norm_path": "1.wav"}],
        {"me": {"ref_audio": "r"}},
    )
    assert out == {1: []}
    assert fake.load_calls == 0


def test_diarize_batch_no_ref_skips_without_load(tmp_path):
    cfg = Config()
    cfg.features.enable_diarization = True
    cfg.hf_token = "hf"
    o = Orchestrator(cfg, _RepoStatus())
    fake = _FakePyannote()
    o.pyannote_runner = fake
    out = o._diarize_batch(
        [{"call_id": 1, "user_id": "me", "_norm_path": "1.wav"}],
        {"me": {"ref_audio": str(tmp_path / "missing.wav")}},
    )
    assert out == {1: []}
    assert fake.load_calls == 0
    assert "no_ref" in o._diag_warned
