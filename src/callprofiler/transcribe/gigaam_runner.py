# -*- coding: utf-8 -*-
"""
gigaam_runner.py — GigaAM v3 RNN-T ASR backend (локальная in-process модель).

Грузит HF-модель из каталога ``config.models.gigaam_model_dir`` через
``transformers.AutoModel(trust_remote_code=True)`` и транскрибирует длинные
звонки СОБСТВЕННОЙ нарезкой фиксированными окнами (<25 c) — БЕЗ pyannote/VAD.
Каждое окно → ``forward`` + RNN-T greedy decode. Спикеры НЕ размечаются
(``speaker=UNKNOWN``); роли назначаются отдельным этапом диаризации, если он
включён (``features.enable_diarization``).

Почему своя нарезка, а не ``model.transcribe_longform``:
  встроенный longform тянет ``pyannote/segmentation-3.0`` (gated, нужен
  HF_TOKEN). Для первого рабочего прогона мы его не используем — отсюда
  фиксированные окна. Апгрейд на VAD-нарезку — отдельный шаг.

GPU-дисциплина (CONSTITUTION Ст.9.2-9.3):
  ``load()`` поднимает модель на cuda, ``unload()`` освобождает VRAM перед
  LLM-фазой. Никогда не держим GigaAM и llama-server в памяти одновременно.

Активация (configs/base.yaml):
    models:
      asr_backend: gigaam
      gigaam_model_dir: "C:\\models\\GigaAM-v3-rnnt"
      gigaam_device: cuda
      gigaam_chunk_sec: 20
      gigaam_overlap_sec: 0.0

Интерфейс совпадает с ASRRunner Protocol (load / unload / transcribe).
Тяжёлые импорты (torch/transformers) — ленивые, чтобы пакет импортировался
на машине без ML-стека.
"""
from __future__ import annotations

import gc
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.config import Config
    from callprofiler.models import Segment

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
# GigaAM.transcribe() бросает при длине > 25 c (LONGFORM_THRESHOLD).
# Держим максимум окна с запасом, даже если в конфиге задано больше.
_MAX_CHUNK_SEC = 24.0
# Хвост короче этого порога не транскрибируем (тишина/щелчок).
_MIN_TAIL_SEC = 0.1


class GigaAMRunner:
    """GigaAM v3 RNN-T — локальная модель, нарезка фиксированными окнами.

    Реализует протокол :class:`ASRRunner` (load / unload / transcribe).
    """

    def __init__(self, config: "Config") -> None:
        self.config = config
        self._model = None  # GigaAMModel (HF-обёртка)
        self._asr = None    # GigaAMASR: prepare_wav / forward / decoding / head

    # ── lifecycle ──────────────────────────────────────────────────────
    def load(self) -> None:
        """Загрузить модель на GPU. Идемпотентно."""
        if self._model is not None:
            return

        model_dir = getattr(self.config.models, "gigaam_model_dir", "")
        if not model_dir:
            raise RuntimeError(
                "GigaAM не настроен: задайте models.gigaam_model_dir в configs/base.yaml."
            )
        if not Path(model_dir).exists():
            raise RuntimeError(f"Каталог модели GigaAM не найден: {model_dir}")

        import torch

        # torch 2.6: from_pretrained грузит pytorch_model.bin через torch.load,
        # которому по умолчанию ставят weights_only=True → падает на конфиге.
        # Временно снимаем ограничение только на время загрузки (см. CLAUDE.md).
        _orig_load = torch.load

        def _patched_load(*a, **k):
            k.setdefault("weights_only", False)
            return _orig_load(*a, **k)

        # transformers trust_remote_code сканирует ВСЕ import'ы в modeling_gigaam.py
        # (даже внутри функций — get_imports() regex ловит и отступы) и падает, если
        # отсутствует опциональный пакет. В GigaAM это `from pyannote.audio import ...`
        # внутри get_pipeline() (longform VAD) — нам он НЕ нужен (своя нарезка окнами).
        # Подменяем check_imports на get_relative_imports: пропускаем проверку внешних
        # пакетов, сохраняя резолв относительных модулей → грузим без установки pyannote.
        _dmu = None
        _orig_check = None
        try:
            import transformers.dynamic_module_utils as _dmu  # type: ignore
            _orig_check = getattr(_dmu, "check_imports", None)
            _rel = getattr(_dmu, "get_relative_imports", None)
            if _orig_check is not None and _rel is not None:
                _dmu.check_imports = _rel
        except Exception:  # noqa: BLE001 — best-effort, не критично
            _dmu = None

        torch.load = _patched_load
        try:
            from transformers import AutoModel

            model = AutoModel.from_pretrained(model_dir, trust_remote_code=True)
        finally:
            torch.load = _orig_load
            if _dmu is not None and _orig_check is not None:
                _dmu.check_imports = _orig_check

        device = getattr(self.config.models, "gigaam_device", "cuda") or "cuda"
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA недоступна — GigaAM на CPU (будет медленно)")
            device = "cpu"

        model = model.to(device).eval()
        self._model = model
        self._asr = model.model  # GigaAMASR (nn.Module внутри HF-обёртки)
        logger.info("GigaAMRunner загружен: %s (device=%s)", model_dir, device)

    def unload(self) -> None:
        """Освободить VRAM перед LLM-фазой. Идемпотентно."""
        if self._model is None:
            return
        self._model = None
        self._asr = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 — выгрузка не должна ронять pipeline
            pass
        gc.collect()
        logger.info("GigaAMRunner выгружен (VRAM освобождена)")

    # ── transcription ──────────────────────────────────────────────────
    def transcribe(self, wav_path: str) -> list["Segment"]:
        """Транскрибировать WAV нарезкой фиксированными окнами.

        Возвращает сегменты со ``speaker=UNKNOWN`` и тайм-кодами в мс.
        Не бросает на сбое отдельного окна — пропускает его и продолжает.

        Raises:
            RuntimeError — если модель не загружена или файл отсутствует.
        """
        if self._asr is None:
            raise RuntimeError("GigaAMRunner не загружен. Сначала вызовите load().")

        wav_file = Path(wav_path)
        if not wav_file.exists():
            raise RuntimeError(f"Аудиофайл не найден: {wav_path}")

        import torch

        from callprofiler.models import Segment

        asr = self._asr
        # prepare_wav: ffmpeg → 16 кГц моно, тензор [1, T] на device/dtype модели.
        wav, _ = asr.prepare_wav(str(wav_file))
        total = int(wav.shape[-1])
        if total <= 0:
            logger.warning("Пустое аудио: %s", wav_path)
            return []

        chunk_sec = float(getattr(self.config.models, "gigaam_chunk_sec", 20.0) or 20.0)
        chunk_sec = max(1.0, min(chunk_sec, _MAX_CHUNK_SEC))
        overlap_sec = float(getattr(self.config.models, "gigaam_overlap_sec", 0.0) or 0.0)
        overlap_sec = max(0.0, min(overlap_sec, chunk_sec / 2.0))

        chunk = int(chunk_sec * _SAMPLE_RATE)
        step = max(1, chunk - int(overlap_sec * _SAMPLE_RATE))
        min_tail = int(_MIN_TAIL_SEC * _SAMPLE_RATE)

        segments: list[Segment] = []
        start = 0
        while start < total:
            end = min(start + chunk, total)
            seg_wav = wav[:, start:end]
            n = int(seg_wav.shape[-1])
            if n < min_tail:
                break

            length = torch.full([1], n, device=seg_wav.device)
            try:
                encoded, encoded_len = asr.forward(seg_wav, length)
                text = asr.decoding.decode(asr.head, encoded, encoded_len)[0]
            except Exception as exc:  # noqa: BLE001 — окно не должно ронять звонок
                logger.warning(
                    "GigaAM: окно [%d:%d] упало (%s), пропуск", start, end, exc
                )
                if end >= total:
                    break
                start += step
                continue

            text = (text or "").strip()
            if text:
                segments.append(
                    Segment(
                        start_ms=int(start * 1000 / _SAMPLE_RATE),
                        end_ms=int(end * 1000 / _SAMPLE_RATE),
                        text=text,
                        speaker="UNKNOWN",
                    )
                )

            if end >= total:
                break
            start += step

        logger.info("GigaAM: %d сегментов из %s", len(segments), wav_path)
        return segments
