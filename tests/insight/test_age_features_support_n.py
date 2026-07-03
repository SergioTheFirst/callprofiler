# -*- coding: utf-8 -*-
"""Тесты для Ф2: support_n = попадания, не корпус (fixager.md 2.4)."""
from callprofiler.insight.features.lexical_age import life_stage_profile, realia_birth_year


def test_life_stage_single_hit_rejected():
    """1×'школа' среди 500+ нейтральных токенов → cluster None (гейт <2).

    Родитель, один раз сказавший 'школа', отсекается.
    """
    neutral = ["было", "это", "то", "дело"] * 125  # ~500 токенов
    tokens = neutral + ["школа"]
    result = life_stage_profile(tokens)
    assert result["cluster"] is None, f"Один хит должен быть отсечен, got cluster={result['cluster']}"


def test_life_stage_two_distinct_stems_accepted():
    """Много разных стемов школа_егэ → cluster + support_n из попаданий, не len(tokens).

    2+ попадания И 2+ разных стема → открыть кластер.
    """
    tokens = ["школа", "урок", "школа", "экзамен", "нейтральный", "текст"]
    result = life_stage_profile(tokens)
    assert result["cluster"] == "школа_егэ", f"ожидаем школа_егэ, got {result['cluster']}"
    # support_n теперь = число попаданий (3: школа, урок, школа), не len(tokens) (6)
    assert result["density"].support_n == 3, f"ожидаем support_n=3, got {result['density'].support_n}"


def test_realia_single_hit_rejected():
    """1× реалия среди многих токенов → None (гейт <2 попаданий)."""
    tokens = ["слово", "другое", "слово", "пейджер", "далее", "еще"]
    result = realia_birth_year(tokens)
    assert result is None, f"Один хит реалии должен быть отсечен, got {result}"


def test_realia_two_hits_accepted():
    """2+ попадания одной реалии → интервал года рождения.

    Допущение: обе встречи должны быть из одного интервала.
    """
    tokens = ["пейджер", "давай", "пейджер", "еще"]
    result = realia_birth_year(tokens)
    assert result is not None, f"Два хита должны дать результат"
    # B6: эпоха пейджера пере-датирована по reminiscence bump
    assert result == (1960, 1982), f"пейджер → (1960, 1982), got {result}"
