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
