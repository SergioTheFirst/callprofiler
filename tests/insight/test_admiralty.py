# -*- coding: utf-8 -*-
"""test_admiralty.py — A6: Admiralty-грейд источника + «лучшее время звонка» (чистые функции)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from callprofiler.insight.admiralty import grade_line, info_grade, source_grade
from callprofiler.insight.call_time import best_call_time


@pytest.mark.parametrize(
    "bs_label,kept_ratio,kept_n,expected",
    [
        ("reliable", None, 0, "B"),
        ("reliable", 0.9, 6, "A"),
        ("reliable", 0.9, 4, "B"),  # kept_n < 5 -> не дотягивает до A
        ("reliable", 0.7, 6, "B"),  # kept_ratio < 0.8 -> не дотягивает до A
        ("noisy", None, 0, "C"),
        ("risky", None, 0, "D"),
        ("unreliable", None, 0, "E"),
        ("critical", None, 0, "E"),
        ("uncalibrated", None, 0, "F"),
        (None, None, 0, "F"),
    ],
)
def test_source_grade(bs_label, kept_ratio, kept_n, expected):
    assert source_grade(bs_label, kept_ratio, kept_n) == expected


@pytest.mark.parametrize(
    "avg_confidence,expected",
    [
        (0.85, "2"),
        (0.8, "2"),
        (0.65, "3"),
        (0.6, "3"),
        (0.3, "4"),
        (None, "6"),
    ],
)
def test_info_grade(avg_confidence, expected):
    assert info_grade(avg_confidence) == expected


def test_grade_line_format():
    assert grade_line("B", "2") == "B2 — обычно надёжен, информация вероятно верна"
    assert grade_line("F", "6") == "F6 — данных мало, достоверность не оценить"


def _weekday_dt(index: int, hour: int) -> datetime:
    """i-й будний день (Mon-Fri) назад от сегодня, на заданном часе."""
    day = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    placed = 0
    delta = 0
    while placed <= index:
        delta += 1
        candidate = day - timedelta(days=delta)
        if candidate.weekday() < 5:
            placed += 1
    return day - timedelta(days=delta)


def _weekend_dt(index: int, hour: int) -> datetime:
    """i-й выходной день (Sat/Sun) назад от сегодня, на заданном часе."""
    day = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    placed = 0
    delta = 0
    while placed <= index:
        delta += 1
        candidate = day - timedelta(days=delta)
        if candidate.weekday() >= 5:
            placed += 1
    return day - timedelta(days=delta)


def test_best_call_time_weekday_day_majority():
    calls = [{"call_datetime": _weekday_dt(i, 10).isoformat(), "duration_sec": 60} for i in range(20)]
    assert best_call_time(calls) == "будни днём"


def test_best_call_time_support_gate_blocks_small_sample():
    calls = [{"call_datetime": _weekday_dt(i, 10).isoformat(), "duration_sec": 60} for i in range(5)]
    assert best_call_time(calls) is None


def test_best_call_time_no_calls():
    assert best_call_time([]) is None


def test_best_call_time_share_gate_blocks_even_three_way_split():
    """Top bucket has support >=8 but share (1/3) < 0.45 -> None."""
    day_calls = [{"call_datetime": _weekday_dt(i, 10).isoformat()} for i in range(9)]
    evening_calls = [{"call_datetime": _weekday_dt(i, 20).isoformat()} for i in range(9)]
    weekend_calls = [{"call_datetime": _weekend_dt(i, 12).isoformat()} for i in range(9)]
    assert best_call_time(day_calls + evening_calls + weekend_calls) is None


def test_best_call_time_night_bucket_any_day():
    calls = [{"call_datetime": _weekday_dt(i, 1).isoformat()} for i in range(10)]
    assert best_call_time(calls) == "ночью"
