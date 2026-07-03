# -*- coding: utf-8 -*-
"""Тесты для Ф5: маркер-гарды + мягкий конфликт (fixager.md 5.5)."""
from callprofiler.insight.age_markers import extract_marker_signals
from callprofiler.insight.age_estimate import _aggregate, AgeSignal


def test_pension_future_not_marker():
    """'выйду на пенсию через пять лет', 'накоплю до пенсии' → 0 pension-сигналов.

    Будущее, не факт текущего возраста.
    """
    # Контакт 40-летний говорит о выходе в будущем
    signals = extract_marker_signals("выйду на пенсию через пять лет", "2025-01-01")
    pension_signals = [s for s in signals if s.signal == "pension"]
    assert len(pension_signals) == 0, f"pension в будущем должна быть отсечена, got {len(pension_signals)}"

    # Тот же для накопления
    signals = extract_marker_signals("накоплю денег до пенсии", "2025-01-01")
    pension_signals = [s for s in signals if s.signal == "pension"]
    assert len(pension_signals) == 0, f"накоп до пенсии должен быть отсечен"


def test_pension_real_detected():
    """'я на пенсии уже три года' → pension-сигнал."""
    signals = extract_marker_signals("я на пенсии уже три года", "2025-01-01")
    pension_signals = [s for s in signals if s.signal == "pension"]
    assert len(pension_signals) > 0, f"реальная пенсия должна быть обнаружена, got {len(pension_signals)}"


def test_ege_of_child_rejected():
    """'у дочки скоро ЕГЭ', 'сын сдаёт ЕГЭ' → 0 school_exam-сигналов (третье лицо)."""
    signals = extract_marker_signals("у дочки скоро ЕГЭ завтра", "2025-01-01")
    ege_signals = [s for s in signals if s.signal == "school_exam"]
    assert len(ege_signals) == 0, f"ЕГЭ у дочки должен быть отсечен, got {len(ege_signals)}"

    signals = extract_marker_signals("сын сдаёт ЕГЭ", "2025-01-01")
    ege_signals = [s for s in signals if s.signal == "school_exam"]
    assert len(ege_signals) == 0, f"ЕГЭ сына должен быть отсечен"


def test_ege_self_detected():
    """'завтра сдаю ЕГЭ' → school_exam-сигнал."""
    signals = extract_marker_signals("завтра сдаю ЕГЭ", "2025-01-01")
    ege_signals = [s for s in signals if s.signal == "school_exam"]
    assert len(ege_signals) > 0, f"собственный ЕГЭ должен быть обнаружен"


def test_aggregate_lowclass_conflict_soft():
    """Мягкий конфликт: direct 90 + конфликтующий stage 60 → conf == 80, не обвал.

    Прямой маркер (класс 3) не обесценивается ложным этапным (класс 2).
    """
    # Контакт говорит: «мне 45 лет», но потом спорит: «студент в универе»
    direct_45 = AgeSignal(1979, 1980, 90, "мне 45 лет", "direct_age", "2025-01-01", "marker")
    student_17 = AgeSignal(2007, 2008, 65, "в университете", "student", "2025-01-01", "marker")

    # direct_45 (класс 3) → bl=1979, bh=1980
    # student_17 (класс 2) НЕ перекрывается → конфликт низшего класса
    # Ожидание: conf = 90 + 10*0 - 10*1 = 80 (не 60+10=70)
    result = _aggregate([direct_45, student_17])
    assert result is not None
    # direct_45 — базовый, student_17 спорит
    # conf = 90 (base) + 10*0 (никто не согласен) - 10*1 (1 конфликт) = 80
    assert result["confidence"] == 80, f"conf должна быть 80 при мягком конфликте, got {result['confidence']}"
    # Интервал от direct (высший класс) остаётся неизменён
    assert result["birth_low"] == 1979 and result["birth_high"] == 1980
