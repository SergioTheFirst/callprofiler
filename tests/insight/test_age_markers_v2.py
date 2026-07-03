# -*- coding: utf-8 -*-
"""B3/B4: новые маркеры (born_in, since_year, school/uni/army_year) и KIN-арифметика."""
import pytest
from callprofiler.insight.age_markers import extract_marker_signals, extract_kin_signals, AgeSignal


def test_born_in():
    """B3: born_in — точное рождение."""
    sig = extract_marker_signals("я родилась в 1985 году", "2026-01-01")
    assert any(s.signal == "born_in" and s.birth_low == 1985 for s in sig)


def test_since_year_no_job_verb():
    """B3: since_year без глагола работы."""
    sig = extract_marker_signals("я с 85 года", "2026-01-01")
    assert any(s.signal == "since_year" for s in sig)


def test_since_year_with_job_verb_skip():
    """B3: since_year пропускается при 'работаю'."""
    sig = extract_marker_signals("я с 85 года работаю в IT", "2026-01-01")
    assert not any(s.signal == "since_year" for s in sig)


def test_school_finish_year():
    """B3: school_finish_year — год окончания."""
    sig = extract_marker_signals("школу закончил в 95-м", "2026-01-01")
    assert any(s.signal == "school_finish_year" for s in sig)


def test_kin_child_age():
    """B4: kin_child_age — возраст ребёнка."""
    sig = extract_kin_signals("дочке 10 лет", "2026-01-01")
    assert any(s.signal == "kin_child_age" for s in sig)


def test_kin_not_stranger_child():
    """B4: kin-гард — 'твоя дочка' пропускается."""
    sig = extract_kin_signals("у твоей дочки ЕГЭ", "2026-01-01")
    assert len(sig) == 0
