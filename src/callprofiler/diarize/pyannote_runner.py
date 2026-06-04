# -*- coding: utf-8 -*-
"""
pyannote_runner.py — диаризация (разделение ролей спикеров) с референсным эмбеддингом.

Использует:
  - pyannote.audio 3.3.x / 4.x (speaker-diarization-3.1 + embedding models)
  - Reference embedding (голос владельца) для маппинга OWNER/OTHER
  - Cosine similarity для идентификации спикера

Аудио передаётся pyannote ТОЛЬКО в памяти (``{waveform, sample_rate}``).
pyannote.audio 4.x по умолчанию декодирует файл по пути через ``torchcodec``,
чьи DLL на Windows часто не грузятся (``Could not load libtorchcodec``) — тогда
диаризация падает и роли остаются UNKNOWN. Подавая тензор напрямую, мы обходим
torchcodec целиком (см. ``_read_mono16k`` / ``_waveform_dict``).

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


def _load_pretrained(loader, model_id: str, token: str):
    """``from_pretrained`` совместимо с разными версиями pyannote.audio.

    pyannote 3.3.x ждёт ``use_auth_token=``; 3.4+/4.x переименовали аргумент в
    ``token=`` (``Pipeline.from_pretrained() got an unexpected keyword argument
    'use_auth_token'``). Пробуем сначала ``use_auth_token``, при ``TypeError`` —
    ``token``. Пустой токен → ``None`` (для уже скачанных / негейтед моделей).
    """
    auth = token or None
    try:
        return loader(model_id, use_auth_token=auth)
    except TypeError:
        return loader(model_id, token=auth)


def _read_mono16k(path: str) -> np.ndarray:
    """Прочитать аудио → mono float32 numpy @ 16 кГц, БЕЗ torchcodec.

    Нормализованные звонки уже 16 кГц mono → читаем ``soundfile`` (без
    torchcodec). Прочие форматы и ресемпл — ``librosa`` (тянет soundfile/
    audioread, тоже не torchcodec). Это и есть обход битого libtorchcodec на
    Windows: pyannote получает готовый тензор, а не путь к файлу.
    """
    try:
        import soundfile as sf

        data, sr = sf.read(path, dtype="float32", always_2d=True)  # [T, ch]
        samples = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
    except Exception:  # noqa: BLE001 — fallback на librosa (mp3/прочее/нет sf)
        import librosa

        samples, sr = librosa.load(path, sr=None, mono=True)
        samples = np.asarray(samples, dtype=np.float32)

    if int(sr) != _SAMPLE_RATE:
        import librosa

        samples = librosa.resample(
            np.asarray(samples, dtype=np.float32),
            orig_sr=int(sr),
            target_sr=_SAMPLE_RATE,
        )
    return np.asarray(samples, dtype=np.float32)


def _extract_annotation(result):
    """Достать pyannote ``Annotation`` (объект с ``.itertracks``) из вывода
    пайплайна, устойчиво к версии.

    pyannote 3.x возвращает ``Annotation`` напрямую. pyannote 4.x возвращает
    обёртку ``DiarizeOutput`` (namedtuple-подобную), где диаризация лежит в одном
    из полей (``speaker_diarization`` и т.п.) — у самой обёртки ``.itertracks``
    нет (отсюда ``AttributeError: 'DiarizeOutput' object has no attribute
    'itertracks'``). Ищем поле с ``Annotation`` не угадывая жёстко имя.
    """
    if hasattr(result, "itertracks"):
        return result
    for attr in (
        "speaker_diarization",
        "diarization",
        "exclusive_speaker_diarization",
        "prediction",
        "annotation",
        "output",
    ):
        obj = getattr(result, attr, None)
        if obj is not None and hasattr(obj, "itertracks"):
            return obj
    # namedtuple/dataclass — перебрать поля и найти похожее на Annotation
    for attr in getattr(result, "_fields", ()):
        obj = getattr(result, attr, None)
        if hasattr(obj, "itertracks"):
            return obj
    if isinstance(result, (tuple, list)):
        for obj in result:
            if hasattr(obj, "itertracks"):
                return obj
    raise RuntimeError(
        f"Не нашёл Annotation в выводе диаризации (тип {type(result).__name__}; "
        f"поля: {getattr(result, '_fields', None)})"
    )


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
            emb_model = _load_pretrained(
                Model.from_pretrained, "pyannote/embedding", self.config.hf_token
            )
            self.inference = Inference(emb_model, window="whole")
            self.inference.to(self._device)

            # Загрузить диаризационный pipeline (для разделения спикеров)
            logger.debug("Загрузка pyannote/speaker-diarization-3.1...")
            self.pipeline = _load_pretrained(
                Pipeline.from_pretrained,
                "pyannote/speaker-diarization-3.1",
                self.config.hf_token,
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
            # Аудио в память → pyannote не зовёт torchcodec (битый на Windows).
            file_dict = self._waveform_dict(wav_path)
            samples = file_dict["waveform"].squeeze(0).cpu().numpy()

            # Запустить speaker-diarization pipeline (min/max 2 speaker).
            # pyannote 4.x отдаёт DiarizeOutput-обёртку → достаём Annotation.
            diar_out = self.pipeline(file_dict, min_speakers=2, max_speakers=2)
            annotation = _extract_annotation(diar_out)

            # Сырые сегменты из pipeline: {label: [(start, end), ...]}
            raw_segs = {}
            for turn, _, lbl in annotation.itertracks(yield_label=True):
                # Фильтр: пропустить очень короткие (< 400мс)
                if turn.duration >= 0.4:
                    raw_segs.setdefault(lbl, []).append(
                        (round(turn.start, 3), round(turn.end, 3))
                    )

            if not raw_segs:
                logger.warning("Диаризация: пусто (нет сегментов >= 400мс)")
                return []

            # Для каждого спикера вычислить эмбеддинг и найти наиболее похожего на ref
            owner_label = self._find_owner_label(samples, _SAMPLE_RATE, raw_segs)

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

    def _waveform_dict(self, path: str) -> dict:
        """Загрузить аудио в память → ``{waveform: Tensor[1,T] float32,
        sample_rate}``. Обходит torchcodec (см. модульный docstring)."""
        samples = _read_mono16k(path)
        wav = torch.from_numpy(np.ascontiguousarray(samples)).float().unsqueeze(0)
        return {"waveform": wav, "sample_rate": _SAMPLE_RATE}

    def _embedding_from_dict(self, file_dict: dict) -> np.ndarray:
        """Embedding из in-memory ``{waveform, sample_rate}``, L2-нормированный."""
        emb = np.array(self.inference(file_dict)).squeeze()
        norm = np.linalg.norm(emb)
        return emb / norm if norm > 1e-9 else emb

    def _get_embedding(self, wav_path: str) -> np.ndarray:
        """Вычислить нормализованный embedding для аудиофайла (по пути).

        Аудио грузится в память и передаётся pyannote как
        ``{waveform, sample_rate}`` — torchcodec не вызывается.
        """
        return self._embedding_from_dict(self._waveform_dict(wav_path))

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

    def _find_owner_label(self, samples: np.ndarray, sr: int, raw_segs: dict) -> str:
        """Найти label спикера, наиболее похожего на ref_embedding (OWNER).

        Алгоритм:
          1. Для каждого label конкатенировать его сегменты (in-memory срезы)
          2. Вычислить embedding через pyannote (без torchcodec/temp-файлов)
          3. Вернуть label с максимальной cosine similarity к ref_embedding

        Параметры:
            samples   — всё аудио в памяти (mono float32 @ ``sr``)
            sr        — частота дискретизации ``samples``
            raw_segs  — {label: [(start_sec, end_sec), ...]}

        Возвращает:
            label спикера, наиболее похожего на ref_embedding (или первый/`unknown`).
        """
        min_len = int(0.1 * sr)
        label_embeddings: dict = {}

        for lbl, segs in raw_segs.items():
            chunks = [
                samples[int(s * sr) : int(e * sr)]
                for s, e in segs
                if int(e * sr) > int(s * sr)
            ]
            if not chunks:
                logger.warning("Label %s имеет пустые фрагменты, пропуск", lbl)
                continue
            cat = np.concatenate(chunks)
            if cat.size < min_len:
                continue
            try:
                wav = torch.from_numpy(np.ascontiguousarray(cat)).float().unsqueeze(0)
                label_embeddings[lbl] = self._embedding_from_dict(
                    {"waveform": wav, "sample_rate": int(sr)}
                )
            except Exception as exc:  # noqa: BLE001 — один label не валит диаризацию
                logger.warning("Ошибка embedding для label %s: %s", lbl, exc)
                continue

        if not label_embeddings:
            logger.warning("Не удалось вычислить embeddings ни для одного label")
            return next(iter(raw_segs), "unknown")

        owner_label = max(
            label_embeddings,
            key=lambda lbl: float(np.dot(label_embeddings[lbl], self.ref_embedding)),
        )
        similarity = float(np.dot(label_embeddings[owner_label], self.ref_embedding))
        logger.info("OWNER identified: %s (similarity=%.3f)", owner_label, similarity)
        return owner_label
