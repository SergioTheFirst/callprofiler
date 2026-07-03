# -*- coding: utf-8 -*-
"""B4: KIN-арифметика — возраст контакта из информации о его родных."""
from callprofiler.insight.age_markers import extract_kin_signals

_DT = "2026-05-01 10:00:00"
_YEAR = 2026


def _sigs(text):
    return extract_kin_signals(text, _DT)


def test_kin_child_stage_ege():
    # «у дочки скоро ЕГЭ» -> ребёнку 16-18 -> контакту 36-58
    sigs = _sigs("у дочки скоро ЕГЭ, готовимся")
    assert [s.signal for s in sigs] == ["kin_child_stage"]
    s = sigs[0]
    assert (s.birth_low, s.birth_high) == (_YEAR - 18 - 40, _YEAR - 16 - 20)


def test_kin_child_age_digits():
    # «сыну 30 лет» -> контакту 50-70
    sigs = [s for s in _sigs("сыну 30 лет уже") if s.signal == "kin_child_age"]
    assert len(sigs) == 1
    assert (sigs[0].birth_low, sigs[0].birth_high) == (_YEAR - 30 - 40, _YEAR - 30 - 20)


def test_kin_child_age_small():
    sigs = [s for s in _sigs("дочке 5 лет исполнилось") if s.signal == "kin_child_age"]
    assert len(sigs) == 1
    assert (sigs[0].birth_low, sigs[0].birth_high) == (_YEAR - 5 - 40, _YEAR - 5 - 20)


def test_kin_parent_age():
    # «маме 85 лет» -> контакт = 85 - [18..40] лет
    sigs = [s for s in _sigs("маме 85 лет, помогаю ей") if s.signal == "kin_parent_age"]
    assert len(sigs) == 1
    assert (sigs[0].birth_low, sigs[0].birth_high) == (_YEAR - 85 + 18, _YEAR - 85 + 40)


def test_kin_foreign_children_rejected():
    # «у твоей дочки ЕГЭ» — родные ВЛАДЕЛЬЦА, не контакта -> 0 сигналов
    assert _sigs("у твоей дочки ЕГЭ скоро") == []
    assert _sigs("у вас сыну 30 лет") == []


def test_kin_mne_in_gap_rejected():
    # «дочь родилась, мне 30 лет» — возраст говорящего, не ребёнка
    assert [s for s in _sigs("дочь родилась мне 30 лет") if s.signal == "kin_child_age"] == []


def test_kin_grandchild_stage():
    sigs = [s for s in _sigs("внучка в школу пошла") if s.signal == "kin_grandchild"]
    assert len(sigs) == 1
    assert (sigs[0].birth_low, sigs[0].birth_high) == (_YEAR - 85, _YEAR - 50)


def test_kin_grandchild_vnukovo_rejected():
    assert [s for s in _sigs("прилетаю во Внуково в школу опоздаем")
            if s.signal == "kin_grandchild"] == []


def test_kin_signals_are_class2_markers():
    for s in _sigs("у дочки скоро ЕГЭ") + _sigs("маме 85 лет"):
        assert s.method == "marker"
