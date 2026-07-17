"""Tests for specificity-vs-vagueness feature (B2)."""
import statistics

from callprofiler.insight.features.base import Tier
from callprofiler.insight.features.specificity import compute_specificity


def test_specificity_concrete_sentence_is_high():
    segments = [{"speaker": "OTHER", "text": "завтра в 15:30 переведу 40 тысяч рублей"}]
    result = compute_specificity(segments)
    assert "specificity" in result
    feat = result["specificity"]
    assert abs(feat.value - (5 / 7 * 100)) < 0.01
    assert feat.support_n == 5
    assert feat.tier == Tier.ROBUST


def test_specificity_vague_sentence_is_zero():
    segments = [{"speaker": "OTHER", "text": "ну там посмотрим, как пойдёт, наверное"}]
    result = compute_specificity(segments)
    assert "specificity" in result
    feat = result["specificity"]
    assert feat.value == 0.0
    assert feat.support_n == 0


def test_specificity_month_and_weekday_prefix_hits():
    segments = [{"speaker": "OTHER", "text": "встретимся в понедельник в январе"}]
    result = compute_specificity(segments)
    feat = result["specificity"]
    assert feat.support_n == 2  # "понедельник" + "январе" (prefix-матч)
    assert abs(feat.value - (2 / 5 * 100)) < 0.01


def test_specificity_time_token_counts_numeric_and_time():
    # "15:30" — один токен, но два независимых хита (цифры + время)
    segments = [{"speaker": "OTHER", "text": "15:30"}]
    result = compute_specificity(segments)
    feat = result["specificity"]
    assert feat.support_n == 2
    assert feat.value == 200.0  # 2 хита / 1 токен * 100


def test_specificity_money_variants():
    segments = [{"speaker": "OTHER", "text": "рублей ₽ млн долларов евро"}]
    result = compute_specificity(segments)
    feat = result["specificity"]
    assert feat.support_n == 5  # каждый токен — money-хит


def test_specificity_filters_owner_speech():
    segments = [
        {"speaker": "OWNER", "text": "15:30 40000 рублей"},   # не должен считаться
        {"speaker": "OTHER", "text": "ну наверное как-то так"},
    ]
    result = compute_specificity(segments)
    feat = result["specificity"]
    assert feat.value == 0.0  # только речь OTHER пошла в расчёт


def test_specificity_fallback_when_no_owner_filtered_segments():
    segments = [{"speaker": "UNKNOWN", "text": "завтра в 15:30"}]
    result = compute_specificity(segments)
    assert result["specificity"].support_n == 2  # UNKNOWN не исключается (!= OWNER)


def test_specificity_empty_segments():
    assert compute_specificity([]) == {}


def test_specificity_empty_text():
    assert compute_specificity([{"speaker": "OTHER", "text": ""}]) == {}


def test_specificity_cohort_concrete_vs_vague_separate_by_one_sigma():
    """Когортный synth-тест: конкретные vs водянистые контакты разделяются по specificity."""
    def concrete_contact():
        return [{"speaker": "OTHER",
                  "text": "завтра в 15:30 переведу 40 тысяч рублей за январь"}]

    def vague_contact():
        return [{"speaker": "OTHER",
                  "text": "ну там посмотрим как пойдёт наверное скажем позже может быть"}]

    concrete_values = [compute_specificity(concrete_contact())["specificity"].value for _ in range(5)]
    vague_values = [compute_specificity(vague_contact())["specificity"].value for _ in range(5)]

    pooled = concrete_values + vague_values
    sigma = statistics.stdev(pooled) if len(set(pooled)) > 1 else 0.0
    mean_diff = statistics.mean(concrete_values) - statistics.mean(vague_values)
    assert mean_diff > max(sigma, 1.0)
