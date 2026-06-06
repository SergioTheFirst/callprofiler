"""Tests for linguistic features."""
from callprofiler.insight.features.linguistic import compute_linguistic
from callprofiler.insight.features.base import Tier


def test_linguistic_hedge_ratio():
    """Подсчёт хедж-маркеров."""
    segments = [
        {"speaker": "OTHER", "text": "может кажется наверное вроде думаю"},
    ]
    result = compute_linguistic(segments)
    assert "hedge_ratio" in result
    feat = result["hedge_ratio"]
    assert feat.value == 4 / 5  # 4 хедж-слова из 5 (может, кажется, наверное, вроде)
    assert feat.tier == Tier.ROBUST


def test_linguistic_directive_ratio():
    """Подсчёт директив-маркеров."""
    segments = [
        {"speaker": "OTHER", "text": "сделай нужно надо"},
    ]
    result = compute_linguistic(segments)
    assert "directive_ratio" in result
    feat = result["directive_ratio"]
    assert feat.value == 3 / 3  # все слова — директивы
    assert feat.tier == Tier.ROBUST


def test_linguistic_question_ratio():
    """Подсчёт вопросов."""
    segments = [
        {"speaker": "OTHER", "text": "как дела?"},
        {"speaker": "OTHER", "text": "что нового"},
        {"speaker": "OTHER", "text": "готово?"},
    ]
    result = compute_linguistic(segments)
    assert "question_ratio" in result
    feat = result["question_ratio"]
    assert feat.value == 2 / 3  # 2 вопроса из 3 сегментов
    assert feat.support_n == 3


def test_linguistic_lexical_ttr():
    """Type-Token Ratio (лексическое разнообразие)."""
    segments = [
        {"speaker": "OTHER", "text": "кот кот собака"},
    ]
    result = compute_linguistic(segments)
    assert "lexical_ttr" in result
    feat = result["lexical_ttr"]
    assert feat.value == 2 / 3  # 2 уникальных слова из 3


def test_linguistic_mean_turn_words():
    """Среднее слов в реплике контакта."""
    segments = [
        {"speaker": "OTHER", "text": "привет мир"},  # 2 слова
        {"speaker": "OTHER", "text": "как дела"},     # 2 слова
    ]
    result = compute_linguistic(segments)
    assert "mean_turn_words" in result
    feat = result["mean_turn_words"]
    assert feat.value == 4 / 2  # 4 слова / 2 реплики
    assert feat.support_n == 2


def test_linguistic_filters_owner():
    """Речь OWNER не считается в фичи контакта."""
    segments = [
        {"speaker": "OWNER", "text": "может быть может"},  # 3 хедж-слова, но OWNER
        {"speaker": "OTHER", "text": "наверное наверно"},   # 2 хедж-слова
    ]
    result = compute_linguistic(segments)
    feat = result["hedge_ratio"]
    # Только речь OTHER считается
    assert feat.value == 2 / 2  # 2 хедж-слова из 2 слов в речи OTHER
    assert feat.support_n == 2


def test_linguistic_fallback_all_segments():
    """Если нет речи OTHER, используются все сегменты."""
    segments = [
        {"speaker": "UNKNOWN", "text": "может наверное кажется думаю"},
    ]
    result = compute_linguistic(segments)
    feat = result["hedge_ratio"]
    # Используются все сегменты, т.к. нет OTHER
    assert feat.value == 3 / 4  # 3 хедж-слова из 4 (может, наверное, кажется)
    assert feat.support_n == 4


def test_linguistic_empty_segments():
    """Пустой входный список."""
    result = compute_linguistic([])
    assert result == {}


def test_linguistic_no_text():
    """Сегменты без текста (тишина)."""
    segments = [
        {"speaker": "OTHER", "text": ""},
    ]
    result = compute_linguistic(segments)
    assert result == {}
