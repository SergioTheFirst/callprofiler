"""Tests for lexical accommodation asymmetry (B6)."""
import statistics

from callprofiler.insight.features.base import Tier
from callprofiler.insight.features.accommodation import compute_accommodation


def _w(i: int) -> str:
    """Уникальное контентное слово (только буквы, len>=4) для индекса i."""
    a = chr(97 + i // 26)
    b = chr(97 + i % 26)
    return f"word{a}{b}xx"


def test_other_accommodates_owner_value_positive():
    owner_words = [_w(i) for i in range(40)]
    shared = owner_words[:12]
    other_only = [_w(i) for i in range(100, 108)]
    other_words = shared + other_only  # 20 слов, 12 общих с owner
    segments = [
        {"call_id": 1, "speaker": "OWNER", "text": " ".join(owner_words)},
        {"call_id": 1, "speaker": "OTHER", "text": " ".join(other_words)},
    ]
    result = compute_accommodation(segments)
    assert "accommodation" in result
    feat = result["accommodation"]
    assert feat.value > 0  # align_contact=12/20=0.6 > align_owner=12/40=0.3
    assert feat.support_n == 1
    assert feat.tier == Tier.AFFECTIVE


def test_owner_accommodates_other_value_negative():
    other_words = [_w(i) for i in range(40)]
    shared = other_words[:12]
    owner_only = [_w(i) for i in range(200, 208)]
    owner_words = shared + owner_only  # 20 слов, 12 общих с other
    segments = [
        {"call_id": 1, "speaker": "OWNER", "text": " ".join(owner_words)},
        {"call_id": 1, "speaker": "OTHER", "text": " ".join(other_words)},
    ]
    result = compute_accommodation(segments)
    assert result["accommodation"].value < 0  # align_contact=12/40=0.3 < align_owner=12/20=0.6


def test_short_call_dropped():
    segments = [
        {"call_id": 1, "speaker": "OWNER", "text": "мало слов тут совсем"},
        {"call_id": 1, "speaker": "OTHER", "text": "тоже мало слов здесь"},
    ]
    assert compute_accommodation(segments) == {}


def test_mixed_short_and_qualifying_calls_counts_only_qualifying():
    owner_words = [_w(i) for i in range(40)]
    shared = owner_words[:12]
    other_only = [_w(i) for i in range(100, 108)]
    other_words = shared + other_only
    segments = [
        {"call_id": 1, "speaker": "OWNER", "text": "коротко тут совсем мало"},
        {"call_id": 1, "speaker": "OTHER", "text": "и здесь тоже мало слов"},
        {"call_id": 2, "speaker": "OWNER", "text": " ".join(owner_words)},
        {"call_id": 2, "speaker": "OTHER", "text": " ".join(other_words)},
    ]
    result = compute_accommodation(segments)
    assert result["accommodation"].support_n == 1


def test_empty_segments_no_feature():
    assert compute_accommodation([]) == {}


def test_cohort_accommodating_vs_dominant_separate_by_one_sigma():
    """Когортный synth: «подстраивающиеся» vs «доминирующие» разделяются по accommodation."""
    def accommodating_contact(call_id):
        owner_words = [_w(i) for i in range(40)]
        shared = owner_words[:14]
        other_only = [_w(i) for i in range(300, 306)]
        other_words = shared + other_only  # 20
        return [
            {"call_id": call_id, "speaker": "OWNER", "text": " ".join(owner_words)},
            {"call_id": call_id, "speaker": "OTHER", "text": " ".join(other_words)},
        ]

    def dominant_contact(call_id):
        other_words = [_w(i) for i in range(400, 440)]
        shared = other_words[:8]
        owner_only = [_w(i) for i in range(500, 512)]
        owner_words = shared + owner_only  # 20
        return [
            {"call_id": call_id, "speaker": "OWNER", "text": " ".join(owner_words)},
            {"call_id": call_id, "speaker": "OTHER", "text": " ".join(other_words)},
        ]

    acc_values = [compute_accommodation(accommodating_contact(i))["accommodation"].value
                  for i in range(5)]
    dom_values = [compute_accommodation(dominant_contact(i))["accommodation"].value
                  for i in range(5, 10)]

    pooled = acc_values + dom_values
    sigma = statistics.stdev(pooled) if len(set(pooled)) > 1 else 0.0
    mean_diff = statistics.mean(acc_values) - statistics.mean(dom_values)
    assert mean_diff > max(sigma, 0.01)
