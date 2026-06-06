"""Unit tests for topical features."""
import json
import pytest
from callprofiler.insight.features.topical import compute_topical
from callprofiler.insight.features.base import Tier


def test_topical_empty():
    """Empty analyses -> empty dict."""
    assert compute_topical([]) == {}


def test_topical_no_topics():
    """Analyses without key_topics -> empty dict."""
    analyses = [
        {"risk_score": 50},
        {"profanity_density": 0.1},
    ]
    assert compute_topical(analyses) == {}


def test_topical_single_topic():
    """Single topic -> diversity=1.0, focus=1.0."""
    analyses = [
        {"key_topics": ["договор"]},
    ]
    result = compute_topical(analyses)

    assert "topic_diversity" in result
    assert result["topic_diversity"].value == 1.0  # 1 unique / 1 total

    assert "topic_focus" in result
    assert result["topic_focus"].value == pytest.approx(1.0)  # Herfindahl (1/1)^2


def test_topical_multiple_same_topics():
    """Multiple calls with same topic -> focus=1.0, diversity=1.0."""
    analyses = [
        {"key_topics": ["договор", "договор"]},
        {"key_topics": ["договор"]},
    ]
    result = compute_topical(analyses)

    # 1 unique topic / 3 total mentions
    assert result["topic_diversity"].value == pytest.approx(1.0 / 3.0, abs=0.01)

    # Herfindahl: (3/3)^2 = 1.0
    assert result["topic_focus"].value == pytest.approx(1.0)


def test_topical_diverse_topics():
    """Multiple different topics -> diversity > focus."""
    analyses = [
        {"key_topics": ["договор", "оплата", "сроки"]},
        {"key_topics": ["договор", "сделка"]},
        {"key_topics": ["оплата"]},
    ]
    result = compute_topical(analyses)

    # 4 unique topics / 6 total mentions
    expected_diversity = 4.0 / 6.0
    assert result["topic_diversity"].value == pytest.approx(expected_diversity, abs=0.01)

    # Herfindahl: (2/6)^2 + (2/6)^2 + (1/6)^2 + (1/6)^2
    expected_focus = (2/6)**2 + (2/6)**2 + (1/6)**2 + (1/6)**2
    assert result["topic_focus"].value == pytest.approx(expected_focus, abs=0.01)

    # diversity should be higher than focus for diverse topics
    assert result["topic_diversity"].value > result["topic_focus"].value


def test_topical_json_string_topics():
    """key_topics can be JSON-encoded string."""
    analyses = [
        {"key_topics": json.dumps(["договор", "оплата"])},
        {"key_topics": ["сроки"]},
    ]
    result = compute_topical(analyses)

    # 3 unique topics / 3 total mentions
    assert result["topic_diversity"].value == pytest.approx(1.0, abs=0.01)


def test_topical_broken_json():
    """Broken JSON in key_topics is skipped gracefully."""
    analyses = [
        {"key_topics": '["договор", "оплата"'},  # Missing ]
        {"key_topics": ["сроки"]},
    ]
    result = compute_topical(analyses)

    # Only the valid one should be counted
    assert result["topic_diversity"].value == 1.0  # 1 unique / 1 total
    assert result["topic_focus"].value == pytest.approx(1.0)


def test_topical_support_n():
    """Support_n is total_topic_mentions."""
    analyses = [
        {"key_topics": ["договор", "оплата"]},
        {"key_topics": ["сроки", "договор", "сделка"]},
    ]
    result = compute_topical(analyses)

    # 5 total mentions
    assert result["topic_diversity"].support_n == 5
    assert result["topic_focus"].support_n == 5


def test_topical_tier():
    """All topical features are AFFECTIVE tier."""
    analyses = [
        {"key_topics": ["договор", "оплата"]},
    ]
    result = compute_topical(analyses)

    for feat in result.values():
        assert feat.tier == Tier.AFFECTIVE
