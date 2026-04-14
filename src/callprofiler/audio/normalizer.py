# -*- coding: utf-8 -*-
"""
normalizer.py — конвертация и нормализация аудио через ffmpeg.

Конвейер обработки:
  1. Конвертация в WAV 16kHz mono s16le
  2. Loudness normalization (EBU R128 / LUFS) — двухпроходный режим
     для стабильного уровня сигнала, критичного для качества ASR.

Почему важна нормализация уровня (LUFS):
  - Слишком тихие записи → Whisper пропускает сегменты или галлюцинирует
  - Слишком громкие → клиппинг → артефакты распознавания
  - Целевой уровень: -16 LUFS (рекомендация EBU R128 для речи),
    True Peak не выше -1.5 dBFS
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Проверка зависимостей при импорте модуля ──────────────────────────────────
_MISSING = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
if _MISSING:
    raise EnvironmentError(
        f"Не найдены в PATH: {', '.join(_MISSING)}. "
        "Установите ffmpeg (https://ffmpeg.org/download.html)."
    )

# ── Константы EBU R128 ────────────────────────────────────────────────────────
_TARGET_LUFS = -16.0   # интегральная громкость речи
_TRUE_PEAK   = -1.5    # максимальный пик (dBFS)
_LRA         = 11.0    # loudness range (рекомендуемый диапазон)

# Минимальный размер файла — защита от битых/пустых файлов
_MIN_FILE_BYTES = 1024


def normalize(
    src_path: str,
    dst_path: str,
    *,
    loudnorm: bool = True,
    sample_rate: int = 16000,
    channels: int = 1,
) -> None:
    """Конвертировать аудио в WAV PCM s16le с нормализацией громкости.

    Параметры:
        src_path  — входной файл (любой формат, поддерживаемый ffmpeg)
        dst_path  — выходной WAV-файл
        loudnorm  — применять двухпроходную LUFS-нормализацию (рекомендуется)
        sample_rate — частота дискретизации (по умолчанию 16 000 Гц для Whisper)
        channels  — каналы (1 = mono)

    Raises:
        FileNotFoundError  — если src_path не существует или слишком мал
        RuntimeError       — если ffmpeg завершился с ошибкой
    """
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(f"Файл не найден: {src_path}")
    if src.stat().st_size < _MIN_FILE_BYTES:
        raise FileNotFoundError(
            f"Файл подозрительно мал ({src.stat().st_size} байт), "
            f"возможно повреждён: {src_path}"
        )

    Path(dst_path).parent.mkdir(parents=True, exist_ok=True)

    if loudnorm:
        _normalize_two_pass(str(src), dst_path, sample_rate, channels)
    else:
        _convert_raw(str(src), dst_path, sample_rate, channels)

    logger.debug("normalize: %s → %s", src.name, Path(dst_path).name)


def get_duration_sec(wav_path: str) -> int:
    """Получить длительность аудиофайла в секундах через ffprobe.

    Raises:
        RuntimeError — если ffprobe не смог прочитать файл
    """
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
        raw = result.stdout.strip()
        if not raw:
            raise ValueError("ffprobe вернул пустой ответ")
        return int(float(raw))
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise RuntimeError(f"ffprobe не смог определить длину {wav_path}: {exc}") from exc


# ── Внутренние функции ────────────────────────────────────────────────────────

def _convert_raw(src: str, dst: str, sample_rate: int, channels: int) -> None:
    """Простая конвертация без нормализации (совместимо с batch_asr.py)."""
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-ac", str(channels),
        "-ar", str(sample_rate),
        "-sample_fmt", "s16",
        dst,
    ]
    _run_ffmpeg(cmd, src)


def _normalize_two_pass(src: str, dst: str, sample_rate: int, channels: int) -> None:
    """Двухпроходная EBU R128 loudness normalization.

    Проход 1: анализ громкости → JSON-метрики
    Проход 2: применение коррекции с точными параметрами
    """
    # ── Проход 1: анализ ──────────────────────────────────────────────────────
    pass1_filter = (
        f"loudnorm=I={_TARGET_LUFS}:TP={_TRUE_PEAK}:LRA={_LRA}:print_format=json"
    )
    cmd1 = [
        "ffmpeg", "-y", "-i", src,
        "-af", pass1_filter,
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd1,
            capture_output=True,
            text=True,
        )
        # loudnorm выводит JSON в stderr
        metrics = _extract_loudnorm_json(proc.stderr)
    except Exception as exc:
        logger.warning(
            "Проход 1 loudnorm не удался (%s), fallback к простой конвертации: %s",
            src, exc,
        )
        _convert_raw(src, dst, sample_rate, channels)
        return

    if metrics is None:
        logger.warning("Не удалось распарсить loudnorm JSON для %s, fallback", src)
        _convert_raw(src, dst, sample_rate, channels)
        return

    # ── Проход 2: нормализация с измеренными метриками ────────────────────────
    pass2_filter = (
        f"loudnorm=I={_TARGET_LUFS}:TP={_TRUE_PEAK}:LRA={_LRA}"
        f":measured_I={metrics['input_i']}"
        f":measured_TP={metrics['input_tp']}"
        f":measured_LRA={metrics['input_lra']}"
        f":measured_thresh={metrics['input_thresh']}"
        f":offset={metrics['target_offset']}"
        ":linear=true:print_format=none"
    )
    cmd2 = [
        "ffmpeg", "-y", "-i", src,
        "-af", pass2_filter,
        "-ac", str(channels),
        "-ar", str(sample_rate),
        "-sample_fmt", "s16",
        dst,
    ]
    _run_ffmpeg(cmd2, src)


def _extract_loudnorm_json(stderr: str) -> dict | None:
    """Извлечь JSON-блок из вывода ffmpeg loudnorm."""
    start = stderr.rfind("{")
    end = stderr.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(stderr[start:end])
    except json.JSONDecodeError:
        return None


def _run_ffmpeg(cmd: list[str], src: str) -> None:
    """Запустить ffmpeg и превратить ненулевой код в RuntimeError."""
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg завершился с кодом {exc.returncode} для файла: {src}"
        ) from exc
