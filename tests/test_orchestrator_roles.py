# -*- coding: utf-8 -*-
"""test_orchestrator_roles.py — выбор пути транскрибации по ролям.

_asr_transcribe: GigaAM + turns → transcribe_turns; иначе flat (+assign_speakers).
pyannote/GigaAM не требуются (asr_runner подменяется фейком).
"""
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
