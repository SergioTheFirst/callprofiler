# -*- coding: utf-8 -*-
"""Регресс-тесты для Ф1: точный матч лексиконов (fixager.md 1.6)."""
from callprofiler.insight.features.lexical_age import (
    slang_density, archaism_density, life_stage_profile, realia_birth_year
)


def test_exact_match_stems():
    """Точные формы не должны матчиться с основанными на startswith вариантами.

    Примеры: 'база' в 'базаре', 'чил' в 'чили', 'краш' в 'крашеный'.
    """
    # 'базаре' не должно триггерить =база (хотя оно in слэнге)
    tokens_bazaar = ["мы", "были", "на", "базаре"]
    result = slang_density(tokens_bazaar)
    assert result.value == 0.0, f"базаре не должно триггерить =база, got {result.value}"

    # 'чили' не должно триггерить =чил
    tokens_chili = ["острый", "чили", "перец"]
    result = slang_density(tokens_chili)
    assert result.value == 0.0, f"чили не должно триггерить =чил, got {result.value}"

    # 'крашеный' не должно триггерить =краш
    tokens_painted = ["деревянный", "крашеный", "забор"]
    result = slang_density(tokens_painted)
    assert result.value == 0.0, f"крашеный не должно триггерить =краш, got {result.value}"


def test_akkuratno_not_archaism():
    """'аккуратно' не должно триггерить =аккурат (наречие vs архаизм точная форма)."""
    tokens = ["сделай", "аккуратно", "пожалуйста"]
    result = archaism_density(tokens)
    assert result.value == 0.0, f"аккуратно не должно триггерить =аккурат, got {result.value}"


def test_dialog_not_realia():
    """'диалог' удалён из realia_by_epoch, не должно быть сигнала."""
    tokens = ["у", "нас", "был", "диалог"]
    result = realia_birth_year(tokens)
    assert result is None, f"диалог удалён, ожидаем None, got {result}"


def test_serial_not_life_stage():
    """'сериал' удалён из life_stage, не должно быть кластера."""
    tokens = ["смотрю", "сериал", "каждый", "день"]
    result = life_stage_profile(tokens)
    assert result["cluster"] is None, f"сериал удалён, ожидаем None, got {result['cluster']}"


def test_real_slang_detected():
    """Реальный молодёжный сленг должен быть обнаружен."""
    tokens = ["это", "кринж", "и", "зашквар"]
    result = slang_density(tokens)
    assert result.value > 0, f"кринж+зашквар должны дать плотность > 0, got {result.value}"


def test_real_archaism_detected():
    """Реальные архаизмы должны быть обнаружены."""
    tokens = ["давеча", "в", "собесе"]
    result = archaism_density(tokens)
    assert result.value > 0, f"давеча+собес должны дать плотность > 0, got {result.value}"
