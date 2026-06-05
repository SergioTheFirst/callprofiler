# -*- coding: utf-8 -*-
"""Атомарная запись normalize() + явный формат -f wav.

Регресс (2026-06-05): атомарная запись стала писать выход во временный
``{dst}.part``; ffmpeg выбирает мукс по расширению → ``.part`` неизвестно →
``AVERROR(EINVAL)`` (код -22 / 4294967274 на Windows) → нормализация падала
там, где раньше проходила. Фикс — форсировать ``-f wav``. Тест гоняет реальный
ffmpeg (skip, если его нет), т.к. баг именно в выборе мукса.
"""
import shutil

import pytest

from callprofiler.audio.normalizer import normalize

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg не установлен")


def _make_source(path) -> None:
    import subprocess

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-f", "mp3", str(path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _is_wav(path) -> bool:
    with open(path, "rb") as f:
        head = f.read(12)
    return head[:4] == b"RIFF" and head[8:12] == b"WAVE"


@pytest.mark.parametrize("loudnorm", [True, False])
def test_normalize_writes_wav_atomically(tmp_path, loudnorm):
    src = tmp_path / "8(495)651-07-97(84956510797)_20240703160047.mp3"
    _make_source(src)
    # dst как в pipeline: имя с источником, расширение .wav (temp = .wav.part)
    dst = tmp_path / "226__8_495_651-07-97_84956510797_20240703160047.wav"

    normalize(str(src), str(dst), loudnorm=loudnorm)

    assert dst.exists(), "выходной wav не создан"
    assert _is_wav(dst), "выход не RIFF/WAVE"
    assert not (tmp_path / f"{dst.name}.part").exists(), ".part не подчищен"
