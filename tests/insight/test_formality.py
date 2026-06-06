"""Tests for formality features."""
from callprofiler.insight.features.formality import compute_formality
from callprofiler.insight.features.base import Tier


def test_formality_vy_ratio():
    """Подсчёт формального обращения (вы)."""
    segments = [
        {"speaker": "OTHER", "text": "вы вас вам"},
    ]
    result = compute_formality(segments)
    assert "vy_ratio" in result
    feat = result["vy_ratio"]
    assert feat.value == 1.0  # все обращения на вы
    assert feat.tier == Tier.ROBUST


def test_formality_ty_ratio():
    """Подсчёт неформального обращения (ты)."""
    segments = [
        {"speaker": "OTHER", "text": "ты тебя тебе"},
    ]
    result = compute_formality(segments)
    assert "vy_ratio" in result
    feat = result["vy_ratio"]
    assert feat.value == 0.0  # все обращения на ты
    assert feat.support_n == 3


def test_formality_mixed():
    """Смешанный стиль обращения."""
    segments = [
        {"speaker": "OTHER", "text": "вы вас ты тебя"},
    ]
    result = compute_formality(segments)
    feat = result["vy_ratio"]
    assert feat.value == 2 / 4  # 2 вы из 4 обращений
    assert feat.support_n == 4


def test_formality_no_pronouns():
    """Отсутствие обращений (не добавляется фича)."""
    segments = [
        {"speaker": "OTHER", "text": "думаю скажу видимо"},
    ]
    result = compute_formality(segments)
    assert result == {}


def test_formality_filters_owner():
    """Речь OWNER не считается."""
    segments = [
        {"speaker": "OWNER", "text": "вы вы вы"},  # 3 вы, но OWNER
        {"speaker": "OTHER", "text": "ты ты"},     # 2 ты
    ]
    result = compute_formality(segments)
    feat = result["vy_ratio"]
    # Только речь OTHER считается
    assert feat.value == 0.0  # 0 вы из 2 ты
    assert feat.support_n == 2


def test_formality_fallback_all_segments():
    """Если нет речи OTHER, используются все сегменты."""
    segments = [
        {"speaker": "UNKNOWN", "text": "вы ты"},
    ]
    result = compute_formality(segments)
    feat = result["vy_ratio"]
    assert feat.value == 0.5  # 1 вы и 1 ты


def test_formality_empty_segments():
    """Пустой входный список."""
    result = compute_formality([])
    assert result == {}


def test_formality_no_text():
    """Сегменты без текста."""
    segments = [
        {"speaker": "OTHER", "text": ""},
    ]
    result = compute_formality(segments)
    assert result == {}
