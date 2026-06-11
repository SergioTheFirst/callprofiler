# -*- coding: utf-8 -*-
"""test_age_markers.py — Ф0/Ф1 плана возраста: детерминированные маркеры.

Все сигналы — интервалы ГОДА РОЖДЕНИЯ (возраст индексируется к дате звонка,
поэтому оценка не устаревает по мере прихода новых звонков).
"""
from callprofiler.insight.age_markers import (
    extract_marker_signals,
    extract_relation_signals,
)


def _one(text, dt="2021-03-15T10:00:00"):
    return extract_marker_signals(text, dt)


# ── Прямые маркеры ──────────────────────────────────────────────────────────

def test_direct_age_digits_indexed_to_call_date():
    sigs = _one("Да мне 45 лет, какие танцы")
    assert len(sigs) == 1
    s = sigs[0]
    assert s.signal == "direct_age"
    assert (s.birth_low, s.birth_high) == (1975, 1976)  # 2021 − 45 (±1 на ДР)
    assert s.confidence >= 85
    assert "мне 45 лет" in s.quote


def test_direct_age_word_number():
    sigs = _one("ну мне сорок пять лет уже")
    assert len(sigs) == 1
    assert sigs[0].signal == "direct_age"
    assert (sigs[0].birth_low, sigs[0].birth_high) == (1975, 1976)


def test_minutes_not_matched():
    assert _one("мне 45 минут ехать") == []
    assert _one("мне сорок минут ехать") == []


def test_birth_year_direct():
    sigs = _one("я вообще 1978 года рождения, не забывай")
    assert len(sigs) == 1
    s = sigs[0]
    assert s.signal == "birth_year"
    assert (s.birth_low, s.birth_high) == (1978, 1978)
    assert s.confidence >= 90


def test_pension_range():
    sigs = _one("да я уже на пенсии давно", dt="2024-01-10T09:00:00")
    assert len(sigs) == 1
    s = sigs[0]
    assert s.signal == "pension"
    assert (s.birth_low, s.birth_high) == (1944, 1964)  # 2024−80 .. 2024−60


def test_third_person_not_matched():
    assert _one("мама на пенсии уже") == []
    assert _one("сыну исполнилось 5 лет") == []


def test_ege_range():
    sigs = _one("завтра ЕГЭ сдаю, страшно", dt="2023-06-01T08:00:00")
    assert len(sigs) == 1
    assert sigs[0].signal == "school_exam"
    assert (sigs[0].birth_low, sigs[0].birth_high) == (2005, 2007)


def test_jubilee_first_person_only():
    sigs = _one("у меня же 50-летие в субботу, приходи", dt="2022-05-01T10:00:00")
    assert len(sigs) == 1
    assert sigs[0].signal == "jubilee"
    assert (sigs[0].birth_low, sigs[0].birth_high) == (1971, 1972)
    assert _one("50-летие завода отмечали всем цехом") == []


def test_no_date_no_signal():
    assert _one("мне 45 лет", dt="") == []
    assert _one("мне 45 лет", dt=None) == []


def test_empty_text():
    assert _one("") == []


# ── Ф1: реляционные якоря ───────────────────────────────────────────────────

def test_owner_says_mam_contact_is_parent():
    sigs = extract_relation_signals(
        owner_lines=[("привет, мам, как ты", "2024-02-01T10:00:00")],
        contact_lines=[], owner_birth_year=1980)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.signal == "rel_parent" and s.method == "relation"
    assert (s.birth_low, s.birth_high) == (1945, 1960)  # owner−35 .. owner−20
    assert s.confidence == 70


def test_classmate_symmetric_either_side():
    sigs = extract_relation_signals(
        owner_lines=[],
        contact_lines=[("мы же одноклассники с тобой", "2024-02-01T10:00:00")],
        owner_birth_year=1980)
    assert len(sigs) == 1
    assert sigs[0].signal == "rel_classmate"
    assert (sigs[0].birth_low, sigs[0].birth_high) == (1978, 1982)
    assert sigs[0].confidence == 85


def test_anchors_disabled_without_owner_year():
    sigs = extract_relation_signals(
        owner_lines=[("привет, мам", "2024-02-01")], contact_lines=[],
        owner_birth_year=0)
    assert sigs == []
