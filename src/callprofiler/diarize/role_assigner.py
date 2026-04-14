# -*- coding: utf-8 -*-
"""
role_assigner.py — назначение ролей спикеров для сегментов транскрипции.

Сопоставляет временные интервалы из диаризации (OWNER/OTHER) с сегментами
текста из Whisper по принципу максимального пересечения (overlap).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.models import Segment

logger = logging.getLogger(__name__)


def assign_speakers(
    segments: list[Segment],
    diarization: list[dict],
) -> list[Segment]:
    """Назначить роли спикеров (OWNER/OTHER) сегментам транскрипции.

    Алгоритм:
      1. Для каждого сегмента текста найти диаризационный интервал
         с максимальным пересечением (overlap)
      2. Если пересечений нет — взять ближайший по времени интервал
      3. Скопировать роль спикера в сегмент

    Параметры:
        segments     — список Segment (start_ms, end_ms, text, speaker='UNKNOWN')
        diarization  — список dict (start_ms, end_ms, speaker='OWNER'|'OTHER')
                       из PyannoteRunner.diarize()

    Возвращает:
        Новый список Segment с назначенными ролями (исходные не меняются)

    Примеры:
        >>> segs = [Segment(0, 1000, "Hello", "UNKNOWN")]
        >>> dias = [{"start_ms": 500, "end_ms": 1500, "speaker": "OWNER"}]
        >>> result = assign_speakers(segs, dias)
        >>> result[0].speaker
        'OWNER'
    """
    if not segments:
        logger.debug("assign_speakers: пусто (нет сегментов)")
        return []

    if not diarization:
        logger.warning("assign_speakers: диаризация пуста, все сегменты остаются UNKNOWN")
        return list(segments)

    result = []

    for seg in segments:
        seg_start = seg.start_ms
        seg_end = seg.end_ms

        # Найти диаризационный интервал с максимальным пересечением
        best_speaker = "UNKNOWN"
        best_overlap = 0.0

        for dia in diarization:
            dia_start = dia["start_ms"]
            dia_end = dia["end_ms"]

            # Вычислить overlap (пересечение интервалов)
            overlap = max(
                0.0,
                min(seg_end, dia_end) - max(seg_start, dia_start),
            )

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = dia["speaker"]

        # Если нет пересечения — взять ближайший по времени интервал
        if best_overlap == 0.0 and diarization:
            closest_dia = min(
                diarization,
                key=lambda d: min(
                    abs(seg_start - d["end_ms"]),
                    abs(seg_end - d["start_ms"]),
                ),
            )
            best_speaker = closest_dia["speaker"]
            logger.debug(
                "assign_speakers: сегмент [%d-%d] не перекрывается, fallback к ближайшему",
                seg_start,
                seg_end,
            )

        # Создать новый Segment с назначенной ролью (исходный не меняется)
        result.append(
            type(seg)(
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                text=seg.text,
                speaker=best_speaker,
            )
        )

    logger.info("assign_speakers: назначены роли для %d сегментов", len(result))
    return result
