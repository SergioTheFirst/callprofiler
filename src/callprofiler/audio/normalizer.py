# -*- coding: utf-8 -*-
"""
normalizer.py — конвертация аудио через ffmpeg.
"""

import shutil
import subprocess

if not shutil.which("ffmpeg"):
    raise EnvironmentError("ffmpeg не найден в PATH")

if not shutil.which("ffprobe"):
    raise EnvironmentError("ffprobe не найден в PATH")


def normalize(src_path: str, dst_path: str) -> None:
    """Конвертировать аудио в WAV 16kHz mono s16. Raises RuntimeError on failure."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", src_path,
                "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
                dst_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed for {src_path}: {e}") from e


def get_duration_sec(wav_path: str) -> int:
    """Получить длительность файла в секундах через ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                wav_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return int(float(result.stdout.strip()))
    except (subprocess.CalledProcessError, ValueError) as e:
        raise RuntimeError(f"ffprobe failed for {wav_path}: {e}") from e
