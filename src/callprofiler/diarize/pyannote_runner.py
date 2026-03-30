# -*- coding: utf-8 -*-
"""
pyannote_runner.py — диаризация (разделение ролей спикеров) с референсным эмбеддингом.

Использует:
  - pyannote.audio 3.3.2 (speaker-diarization-3.1 + embedding models)
  - Reference embedding (голос владельца) для маппинга OWNER/OTHER
  - Cosine similarity для идентификации спикера

Управление GPU-памятью критично (pyannote ~1.5GB + inference ~0.5GB).
"""

from __future__ import annotations

import gc
import logging
import os
import tempfile
from typing import TYPE_CHECKING

import numpy as np
import torch

from callprofiler.audio.normalizer import normalize

if TYPE_CHECKING:
    from callprofiler.config import Config

logger = logging.getLogger(__name__)

# EBU R128 LUFS settings for normalization before embedding extraction
_LOUDNORM = True
_SAMPLE_RATE = 16000


class PyannoteRunner:
    """Интерфейс к pyannote.audio для диаризации с референсным эмбеддингом.

    Workflow:
        runner = PyannoteRunner(config)
        runner.load(ref_audio_path)
        try:
            diarization = runner.diarize(wav_path)  # → list[dict] with OWNER/OTHER
        finally:
            runner.unload()
    """

    def __init__(self, config: Config) -> None:
        """Инициализировать runner с конфигурацией.

        Параметры:
            config  — Config объект (для HF_TOKEN в будущем)
        """
        self.config = config
        self.pipeline = None
        self.inference = None
        self.ref_embedding = None
        self._device = None

    def load(self, ref_audio_path: str) -> None:
        """Загрузить pyannote моделей и построить reference embedding.

        Параметры:
            ref_audio_path  — путь к WAV/MP3 с образцом голоса владельца (OWNER)

        Raises:
            FileNotFoundError  — если ref_audio_path не существует
            RuntimeError       — если загрузка моделей упала
        """
        if self.pipeline is not None:
            logger.warning("Pyannote уже загружена, пропуск повторной загрузки")
            return

        if not os.path.isfile(ref_audio_path):
            raise FileNotFoundError(f"Эталон голоса не найден: {ref_audio_path}")

        try:
            from pyannote.audio import Pipeline, Model, Inference
        except ImportError as exc:
            raise RuntimeError(
                "pyannote.audio не установлена. "
                "Установите: pip install pyannote.audio"
            ) from exc

        # Определить device
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("Pyannote device: %s", self._device.type.upper())

        try:
            # Загрузить embedding модель (для cosine similarity)
            logger.debug("Загрузка pyannote/embedding...")
            emb_model = Model.from_pretrained(
                "pyannote/embedding",
                use_auth_token=self.config.hf_token,
            )
            self.inference = Inference(emb_model, window="whole")
            self.inference.to(self._device)

            # Загрузить диаризационный pipeline (для разделения спикеров)
            logger.debug("Загрузка pyannote/speaker-diarization-3.1...")
            self.pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=self.config.hf_token,
            )
            self.pipeline.to(self._device)

            logger.info("Pyannote модели загружены успешно")

        except Exception as exc:
            raise RuntimeError(f"Ошибка при загрузке pyannote: {exc}") from exc

        # Построить reference embedding
        logger.debug("Построение reference embedding из: %s", ref_audio_path)
        self.ref_embedding = self._build_ref_embedding(ref_audio_path)

    def diarize(self, wav_path: str) -> list[dict]:
        """Диаризировать аудиофайл, вернуть сегменты с ролями.

        Параметры:
            wav_path  — путь к WAV (16kHz, mono, нормализованный)

        Возвращает:
            Список дикт вида:
            {
                "start_ms": int,
                "end_ms": int,
                "speaker": "OWNER" | "OTHER"
            }
            Отсортирован по start_ms.

        Raises:
            RuntimeError  — если модель не загружена или диаризация упала
        """
        if self.pipeline is None or self.inference is None:
            raise RuntimeError("Pyannote не загружена. Вызовите load() сначала")

        if self.ref_embedding is None:
            raise RuntimeError("Reference embedding не построен. Вызовите load()")

        logger.debug("Диаризация: %s", wav_path)

        try:
            # Запустить speaker-diarization pipeline (min/max 2 speaker)
            diarization = self.pipeline(wav_path, min_speakers=2, max_speakers=2)

            # Сырые сегменты из pipeline: {label: [(start, end), ...]}
            raw_segs = {}
            for turn, _, lbl in diarization.itertracks(yield_label=True):
                # Фильтр: пропустить очень короткие (< 400мс)
                if turn.duration >= 0.4:
                    raw_segs.setdefault(lbl, []).append(
                        (round(turn.start, 3), round(turn.end, 3))
                    )

            if not raw_segs:
                logger.warning("Диаризация: пусто (нет сегментов >= 400мс)")
                return []

            # Для каждого спикера вычислить эмбеддинг и найти наиболее похожего на ref
            owner_label = self._find_owner_label(wav_path, raw_segs)

            # Конвертировать в output format (float сек → int мс, маппинг OWNER/OTHER)
            result = []
            for lbl, segs in raw_segs.items():
                speaker = "OWNER" if lbl == owner_label else "OTHER"
                for start_sec, end_sec in segs:
                    result.append({
                        "start_ms": int(start_sec * 1000),
                        "end_ms": int(end_sec * 1000),
                        "speaker": speaker,
                    })

            result.sort(key=lambda x: x["start_ms"])
            logger.info("Диаризация завершена: %d сегментов", len(result))
            return result

        except Exception as exc:
            logger.error("Ошибка при диаризации %s: %s", wav_path, exc)
            raise RuntimeError(f"Диаризация упала для {wav_path}: {exc}") from exc

    def unload(self) -> None:
        """Выгрузить модели и очистить GPU-память.

        Вызывает:
          - del self.pipeline, self.inference
          - gc.collect()
          - torch.cuda.empty_cache() (если GPU)
        """
        if self.pipeline is None and self.inference is None:
            logger.debug("Pyannote уже выгружена")
            return

        try:
            del self.pipeline
            del self.inference
            self.pipeline = None
            self.inference = None
            gc.collect()

            if self._device and self._device.type == "cuda":
                torch.cuda.empty_cache()
                logger.info("Pyannote выгружена, GPU-память очищена")
            else:
                logger.info("Pyannote выгружена")

        except Exception as exc:
            logger.error("Ошибка при выгрузке Pyannote: %s", exc)

    # ── Внутренние методы ──────────────────────────────────────────────────────

    def _get_embedding(self, wav_path: str) -> np.ndarray:
        """Вычислить embedding для аудиофайла и нормализовать его.

        Параметры:
            wav_path  — путь к WAV

        Возвращает:
            Normalized embedding (L2 norm = 1)
        """
        emb = np.array(self.inference(wav_path)).squeeze()
        norm = np.linalg.norm(emb)
        return emb / norm if norm > 1e-9 else emb

    def _build_ref_embedding(self, ref_audio_path: str) -> np.ndarray:
        """Построить reference embedding из образца голоса.

        Процесс:
          1. Нормализовать аудио (ffmpeg → 16kHz, mono)
          2. Вычислить embedding
          3. Удалить временный файл

        Параметры:
            ref_audio_path  — оригинальный файл (может быть MP3, M4A и т.д.)

        Возвращает:
            Normalized embedding vector
        """
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            ref_wav = tmp.name

        try:
            # Нормализовать в WAV 16kHz mono
            normalize(ref_audio_path, ref_wav, loudnorm=False)
            emb = self._get_embedding(ref_wav)
            logger.info("Reference embedding готов (dim=%d)", emb.shape[0])
            return emb
        finally:
            if os.path.exists(ref_wav):
                try:
                    os.remove(ref_wav)
                except Exception as exc:
                    logger.warning("Не удалось удалить temp файл %s: %s", ref_wav, exc)

    def _find_owner_label(self, wav_path: str, raw_segs: dict) -> str:
        """Найти label спикера, который наиболее похож на ref_embedding (OWNER).

        Алгоритм:
          1. Для каждого label (спикер) собрать все его аудиосегменты
          2. Конкатенировать и вычислить embedding
          3. Вычислить cosine similarity с ref_embedding
          4. Вернуть label с максимальной similarity

        Параметры:
            wav_path    — оригинальный аудиофайл
            raw_segs    — {label: [(start, end), ...]}

        Возвращает:
            label спикера, наиболее похожего на ref_embedding
        """
        import soundfile as sf

        # Загрузить полный аудиофайл
        try:
            wav_data, sr = __import__("librosa").load(
                wav_path, sr=_SAMPLE_RATE, mono=True
            )
        except Exception as exc:
            logger.error("Не удалось загрузить %s для extract speaker embeddings: %s",
                        wav_path, exc)
            # Fallback: вернуть первый label
            return list(raw_segs.keys())[0] if raw_segs else "unknown"

        # Для каждого label вычислить его embedding
        label_embeddings = {}
        temp_files = []

        try:
            for lbl, segs in raw_segs.items():
                # Вырезать фрагменты данного спикера
                chunks = [
                    wav_data[int(s * sr) : int(e * sr)]
                    for s, e in segs
                    if int(e * sr) > int(s * sr)
                ]

                if not chunks:
                    logger.warning("Label %s имеет пустые фрагменты, пропуск", lbl)
                    continue

                # Сохранить в временный файл
                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False
                ) as tmp:
                    tmp_path = tmp.name
                    temp_files.append(tmp_path)

                try:
                    sf.write(tmp_path, np.concatenate(chunks), sr)
                    emb = self._get_embedding(tmp_path)
                    label_embeddings[lbl] = emb
                except Exception as exc:
                    logger.warning("Ошибка при extract embedding для label %s: %s",
                                  lbl, exc)
                    continue

            # Найти label с максимальным cosine similarity
            if not label_embeddings:
                logger.warning("Не удалось вычислить embeddings ни для одного label")
                return list(raw_segs.keys())[0] if raw_segs else "unknown"

            owner_label = max(
                label_embeddings,
                key=lambda lbl: float(np.dot(label_embeddings[lbl], self.ref_embedding)),
            )
            similarity = float(
                np.dot(label_embeddings[owner_label], self.ref_embedding)
            )
            logger.info("OWNER identified: %s (similarity=%.3f)", owner_label, similarity)
            return owner_label

        finally:
            # Удалить временные файлы
            for tmp_path in temp_files:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception as exc:
                        logger.warning("Не удалось удалить temp файл %s: %s",
                                      tmp_path, exc)
