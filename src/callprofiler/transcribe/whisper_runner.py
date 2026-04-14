# -*- coding: utf-8 -*-
"""
whisper_runner.py — обёртка для faster-whisper large-v3.

Инкапсулирует загрузку, транскрибирование и выгрузку модели с корректным
управлением GPU-памятью (особенно важно для RTX 3060 12GB).
"""

from __future__ import annotations

import gc
import logging
from typing import TYPE_CHECKING

import torch

from callprofiler.models import Segment

if TYPE_CHECKING:
    from callprofiler.config import Config

logger = logging.getLogger(__name__)


class WhisperRunner:
    """Интерфейс к faster-whisper с управлением жизненным циклом модели.

    Использование:
        runner = WhisperRunner(config)
        runner.load()
        try:
            segments = runner.transcribe(wav_path)
        finally:
            runner.unload()
    """

    def __init__(self, config: Config) -> None:
        """Инициализировать runner с конфигурацией.

        Параметры:
            config  — Config объект с параметрами whisper
        """
        self.config = config
        self.model = None
        self._device = None

    def load(self) -> None:
        """Загрузить модель faster-whisper в GPU/CPU.

        Использует параметры из config:
          - whisper: название модели (обычно "large-v3")
          - whisper_device: "cuda" или "cpu"
          - whisper_compute: "float16" (cuda) или "int8" (cpu)

        Raises:
            RuntimeError  — если не удалось загрузить модель
        """
        if self.model is not None:
            logger.warning("Whisper уже загружен, пропуск повторной загрузки")
            return

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper не установлен. "
                "Установите: pip install faster-whisper"
            ) from exc

        # Выбрать устройство
        if torch.cuda.is_available() and self.config.models.whisper_device == "cuda":
            self._device = "cuda"
            compute_type = self.config.models.whisper_compute  # "float16" по умолчанию
            logger.info(
                "Whisper: %s (GPU: %s, compute: %s)",
                self.config.models.whisper,
                torch.cuda.get_device_name(0),
                compute_type,
            )
        else:
            self._device = "cpu"
            compute_type = "int8"  # int8 для CPU
            logger.info("Whisper: %s (CPU, compute: int8)", self.config.models.whisper)

        try:
            self.model = WhisperModel(
                self.config.models.whisper,
                device=self._device,
                compute_type=compute_type,
                cpu_threads=8,
                num_workers=2,
            )
            logger.info("Whisper загружен успешно")
        except Exception as exc:
            raise RuntimeError(f"Ошибка при загрузке Whisper: {exc}") from exc

    def transcribe(self, wav_path: str) -> list[Segment]:
        """Транскрибировать аудиофайл.

        Параметры:
            wav_path  — путь к WAV-файлу (предполагается, что 16kHz, mono)

        Возвращает:
            Список Segment с временами в миллисекундах и speaker='UNKNOWN'

        Raises:
            RuntimeError  — если модель не загружена или транскрибирование упало
        """
        if self.model is None:
            raise RuntimeError("Whisper не загружена. Вызовите load() сначала")

        logger.debug("Транскрибирование: %s", wav_path)

        try:
            # Вызов faster_whisper.transcribe()
            segments, info = self.model.transcribe(
                wav_path,
                language=self.config.models.whisper_language,
                beam_size=self.config.models.whisper_beam_size,
                best_of=5,
                temperature=0,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=400,
                    speech_pad_ms=200,
                    threshold=0.5,
                ),
                word_timestamps=True,
                condition_on_previous_text=True,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
            )

            # Конвертировать в список Segment (float сек → int мс)
            result: list[Segment] = []
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    # Пропустить пустые сегменты
                    continue

                result.append(
                    Segment(
                        start_ms=int(seg.start * 1000),
                        end_ms=int(seg.end * 1000),
                        text=text,
                        speaker="UNKNOWN",  # Роли назначаются потом в diarize
                    )
                )

            logger.info(
                "Транскрибирование завершено: %d сегментов из %s",
                len(result),
                wav_path,
            )
            return result

        except Exception as exc:
            logger.error("Ошибка при транскрибировании %s: %s", wav_path, exc)
            raise RuntimeError(f"Транскрибирование упало для {wav_path}: {exc}") from exc

    def unload(self) -> None:
        """Выгрузить модель и очистить GPU-память.

        Вызывает:
          - del self.model
          - gc.collect()
          - torch.cuda.empty_cache() (если GPU использовалась)

        Это критично для RTX 3060 12GB перед загрузкой других моделей.
        """
        if self.model is None:
            logger.debug("Whisper уже выгружена")
            return

        try:
            del self.model
            self.model = None
            gc.collect()

            if self._device == "cuda":
                torch.cuda.empty_cache()
                logger.info("Whisper выгружена, GPU-память очищена")
            else:
                logger.info("Whisper выгружена")

        except Exception as exc:
            logger.error("Ошибка при выгрузке Whisper: %s", exc)
