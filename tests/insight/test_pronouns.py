"""Tests for pronoun features."""
from callprofiler.insight.features.pronouns import compute_pronouns
from callprofiler.insight.features.base import Tier


def test_pronouns_we_ratio():
    """Подсчёт мы-местоимений."""
    segments = [
        {"speaker": "OTHER", "text": "мы нас наш"},
    ]
    result = compute_pronouns(segments)
    assert "we_ratio" in result
    feat = result["we_ratio"]
    assert feat.value == 3 / 3  # 3 мы из 3 слов
    assert feat.tier == Tier.ROBUST


def test_pronouns_i_ratio():
    """Подсчёт я-местоимений."""
    segments = [
        {"speaker": "OTHER", "text": "я меня мой"},
    ]
    result = compute_pronouns(segments)
    assert "i_ratio" in result
    feat = result["i_ratio"]
    assert feat.value == 3 / 3  # 3 я из 3 слов


def test_pronouns_combined():
    """Оба местоимения в одном сегменте."""
    segments = [
        {"speaker": "OTHER", "text": "мы я нам мне"},
    ]
    result = compute_pronouns(segments)
    we_feat = result["we_ratio"]
    i_feat = result["i_ratio"]
    assert we_feat.value == 2 / 4  # 2 мы из 4
    assert i_feat.value == 2 / 4  # 2 я из 4
    assert we_feat.support_n == 4
    assert i_feat.support_n == 4


def test_pronouns_filters_owner():
    """Речь OWNER не считается."""
    segments = [
        {"speaker": "OWNER", "text": "мы мы я я"},  # 2 мы, 2 я, но OWNER
        {"speaker": "OTHER", "text": "мы я"},        # 1 мы, 1 я
    ]
    result = compute_pronouns(segments)
    we_feat = result["we_ratio"]
    i_feat = result["i_ratio"]
    # Только речь OTHER считается
    assert we_feat.value == 0.5  # 1 мы из 2
    assert i_feat.value == 0.5  # 1 я из 2


def test_pronouns_fallback_all_segments():
    """Если нет речи OTHER, используются все сегменты."""
    segments = [
        {"speaker": "UNKNOWN", "text": "мы я я"},
    ]
    result = compute_pronouns(segments)
    we_feat = result["we_ratio"]
    i_feat = result["i_ratio"]
    assert we_feat.value == 1 / 3  # 1 мы из 3
    assert i_feat.value == 2 / 3  # 2 я из 3


def test_pronouns_empty_segments():
    """Пустой входный список."""
    result = compute_pronouns([])
    assert result == {}


def test_pronouns_no_text():
    """Сегменты без текста."""
    segments = [
        {"speaker": "OTHER", "text": ""},
    ]
    result = compute_pronouns(segments)
    assert result == {}


def test_pronouns_no_pronouns():
    """Нет местоимений в тексте."""
    segments = [
        {"speaker": "OTHER", "text": "думаю скажу видимо"},
    ]
    result = compute_pronouns(segments)
    we_feat = result["we_ratio"]
    i_feat = result["i_ratio"]
    assert we_feat.value == 0.0
    assert i_feat.value == 0.0
