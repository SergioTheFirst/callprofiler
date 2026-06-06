from datetime import datetime
from callprofiler.insight.features.base import Tier, Feature, parse_dt, tokenize, count_markers


def test_feature_holds_value_support_tier():
    f = Feature(0.5, 10, Tier.IMMUNE)
    assert f.value == 0.5 and f.support_n == 10 and f.tier == Tier.IMMUNE


def test_parse_dt_iso_space_and_t():
    assert parse_dt("2026-03-01 21:30:00") == datetime(2026, 3, 1, 21, 30, 0)
    assert parse_dt("2026-03-01T21:30:00") == datetime(2026, 3, 1, 21, 30, 0)


def test_parse_dt_none_and_garbage():
    assert parse_dt(None) is None
    assert parse_dt("") is None
    assert parse_dt("not a date") is None


def test_tokenize_basic():
    """Простые слова без пунктуации."""
    words = tokenize("привет мир")
    assert words == ["привет", "мир"]


def test_tokenize_lowercase():
    """Преобразование в нижний регистр."""
    words = tokenize("Привет МИРА")
    assert words == ["привет", "мира"]


def test_tokenize_punctuation():
    """Пунктуация отбрасывается."""
    words = tokenize("Привет, мир! Как дела?")
    assert words == ["привет", "мир", "как", "дела"]


def test_tokenize_cyrillic_latin():
    """Кириллица и латиница."""
    words = tokenize("hello привет test тест")
    assert words == ["hello", "привет", "test", "тест"]


def test_tokenize_empty():
    """Пустая строка."""
    words = tokenize("")
    assert words == []


def test_tokenize_none():
    """None обрабатывается как пустая строка."""
    words = tokenize(None)
    assert words == []


def test_count_markers_basic():
    """Базовый подсчёт маркеров."""
    words = ["наверное", "думаю", "может", "кажется"]
    markers = {"наверное", "может"}
    assert count_markers(words, markers) == 2


def test_count_markers_no_match():
    """Нет совпадений с маркерами."""
    words = ["думаю", "скажу"]
    markers = {"наверное", "может"}
    assert count_markers(words, markers) == 0


def test_count_markers_duplicates():
    """Повторения маркеров считаются."""
    words = ["может", "может", "наверное"]
    markers = {"может", "наверное"}
    assert count_markers(words, markers) == 3
