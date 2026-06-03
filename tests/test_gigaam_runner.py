# -*- coding: utf-8 -*-
"""
test_gigaam_runner.py — нарезка фиксированными окнами в GigaAMRunner.

Модель не грузим: подменяем self._asr фейком (prepare_wav/forward/decoding/head),
поэтому тест не требует transformers/ffmpeg/GPU — только torch (для torch.full).
"""
import pytest

torch = pytest.importorskip("torch")

from callprofiler.config import Config, ModelsConfig  # noqa: E402
from callprofiler.transcribe.gigaam_runner import GigaAMRunner  # noqa: E402


class _FakeDecoding:
    def decode(self, head, encoded, enc_len):
        return ["распознанный текст"]


class _FakeASR:
    """Имитация GigaAMASR: ровно те методы, что зовёт runner.transcribe."""

    def __init__(self, total_samples: int) -> None:
        self._t = total_samples
        self.decoding = _FakeDecoding()
        self.head = None

    def prepare_wav(self, path):
        return torch.zeros(1, self._t), torch.tensor([self._t])

    def forward(self, seg, length):
        return ("ENC", int(seg.shape[-1]))


def _runner(total_samples, chunk_sec=10.0, overlap_sec=0.0):
    cfg = Config()
    cfg.models = ModelsConfig(
        gigaam_chunk_sec=chunk_sec, gigaam_overlap_sec=overlap_sec
    )
    r = GigaAMRunner(cfg)
    r._asr = _FakeASR(total_samples)  # имитируем загруженную модель
    return r


def test_transcribe_windows_25s(tmp_path):
    f = tmp_path / "call.wav"
    f.write_bytes(b"\x00")
    r = _runner(16000 * 25, chunk_sec=10, overlap_sec=0)

    segs = r.transcribe(str(f))

    assert len(segs) == 3
    assert [s.start_ms for s in segs] == [0, 10000, 20000]
    assert [s.end_ms for s in segs] == [10000, 20000, 25000]
    assert all(s.speaker == "UNKNOWN" for s in segs)
    assert all(s.text == "распознанный текст" for s in segs)


def test_transcribe_single_window_short(tmp_path):
    f = tmp_path / "c.wav"
    f.write_bytes(b"\x00")
    r = _runner(16000 * 5, chunk_sec=20)

    segs = r.transcribe(str(f))

    assert len(segs) == 1
    assert segs[0].start_ms == 0
    assert segs[0].end_ms == 5000


def test_transcribe_empty_audio(tmp_path):
    f = tmp_path / "c.wav"
    f.write_bytes(b"\x00")
    assert _runner(0).transcribe(str(f)) == []


def test_transcribe_requires_load(tmp_path):
    f = tmp_path / "c.wav"
    f.write_bytes(b"\x00")
    r = GigaAMRunner(Config())  # _asr is None
    with pytest.raises(RuntimeError):
        r.transcribe(str(f))


def test_transcribe_missing_file():
    with pytest.raises(RuntimeError):
        _runner(16000).transcribe("C:\\nope\\missing.wav")
