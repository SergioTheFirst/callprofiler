# -*- coding: utf-8 -*-
"""
admiralty.py — Admiralty-грейд источника для карточки (A6, oz5 §A6 п.2).

Чистое отображение поверх уже посчитанных метрик: BS-label контакта (graph)
+ средняя достоверность его events за 180 дней -> одна строка "B2 — обычно
надёжен, информация вероятно верна". Ничего не считает и не пишет в БД.
"""

from __future__ import annotations

SOURCE_PHRASES = {
    "A": "надёжен, слово держит",
    "B": "обычно надёжен",
    "C": "сигнал шумный",
    "D": "бывали срывы",
    "E": "ненадёжен",
    "F": "данных мало",
}

INFO_PHRASES = {
    "2": "информация вероятно верна",
    "3": "информация возможно верна",
    "4": "достоверность сомнительна",
    "6": "достоверность не оценить",
}

_KEPT_RATIO_MIN = 0.8
_KEPT_N_MIN = 5
_INFO_HIGH = 0.8
_INFO_MID = 0.6


def source_grade(bs_label: str | None, kept_ratio: float | None = None, kept_n: int = 0) -> str:
    """Буква источника A-F по BS-label контакта (граф) + опц. keep-rate обещаний (B3)."""
    if bs_label == "reliable":
        if kept_ratio is not None and kept_ratio >= _KEPT_RATIO_MIN and kept_n >= _KEPT_N_MIN:
            return "A"
        return "B"
    if bs_label == "noisy":
        return "C"
    if bs_label == "risky":
        return "D"
    if bs_label in ("unreliable", "critical"):
        return "E"
    return "F"


def info_grade(avg_confidence: float | None) -> str:
    """Цифра достоверности 2/3/4/6 по средней confidence events за 180 дней."""
    if avg_confidence is None:
        return "6"
    if avg_confidence >= _INFO_HIGH:
        return "2"
    if avg_confidence >= _INFO_MID:
        return "3"
    return "4"


def grade_line(src: str, info: str) -> str:
    return f"{src}{info} — {SOURCE_PHRASES[src]}, {INFO_PHRASES[info]}"
