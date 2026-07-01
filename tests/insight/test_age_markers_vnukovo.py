# -*- coding: utf-8 -*-
"""test_age_markers_vnukovo.py — "Внуково" (аэропорт) != "внуки" (Ф0 плана age.md)."""
from callprofiler.insight.age_markers import extract_marker_signals

_DT = "2021-03-15T10:00:00"


def _grandkids(text, dt=_DT):
    return [s for s in extract_marker_signals(text, dt) if s.signal == "grandkids"]


def test_vnukovo_airport_not_grandkids():
    assert _grandkids("встречаю рейс в Внуково") == []
    assert _grandkids("еду в аэропорт Внуково") == []
    assert _grandkids("прилетаю во Внуково завтра") == []
    assert _grandkids("вылет из Внукова в семь утра") == []


def test_real_grandkids_still_detected():
    assert len(_grandkids("у меня трое внуков")) == 1
    assert len(_grandkids("нянчу внучку по выходным")) == 1
