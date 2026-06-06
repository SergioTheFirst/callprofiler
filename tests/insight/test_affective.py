"""Unit tests for affective features."""
import pytest
from callprofiler.insight.features.affective import compute_affective
from callprofiler.insight.features.base import Tier


def test_affective_empty():
    """Empty analyses -> empty dict."""
    assert compute_affective([]) == {}


def test_affective_single_analysis():
    """Single analysis with risk_score and profanity_density."""
    analyses = [{"risk_score": 75, "profanity_density": 0.1}]
    result = compute_affective(analyses)

    assert "mean_risk" in result
    assert result["mean_risk"].value == 75.0
    assert result["mean_risk"].support_n == 1
    assert result["mean_risk"].tier == Tier.AFFECTIVE

    assert "max_risk" in result
    assert result["max_risk"].value == 75.0

    assert "profanity_mean" in result
    assert result["profanity_mean"].value == 0.1

    # volatility requires >= 2 values
    assert "risk_volatility" not in result


def test_affective_multiple_analyses():
    """Multiple analyses with varying risk scores."""
    analyses = [
        {"risk_score": 50, "profanity_density": 0.05},
        {"risk_score": 70, "profanity_density": 0.15},
        {"risk_score": 90, "profanity_density": 0.10},
    ]
    result = compute_affective(analyses)

    assert result["mean_risk"].value == pytest.approx(70.0, abs=0.01)
    assert result["max_risk"].value == 90.0
    assert result["profanity_mean"].value == pytest.approx(0.1, abs=0.01)

    # volatility should be present for >= 2 values
    assert "risk_volatility" in result
    assert result["risk_volatility"].value > 0


def test_affective_missing_fields():
    """Handle missing or None fields gracefully."""
    analyses = [
        {"risk_score": 50, "profanity_density": 0.05},
        {"risk_score": None, "profanity_density": 0.10},  # risk_score is None
        {"profanity_density": 0.15},  # no risk_score key
    ]
    result = compute_affective(analyses)

    # Should only count valid risk_scores
    assert result["mean_risk"].support_n == 1
    assert result["mean_risk"].value == 50.0

    # Should count all valid profanity_density values
    assert result["profanity_mean"].support_n == 3


def test_affective_volatility_requires_two():
    """risk_volatility only computed for >= 2 values."""
    # Single value
    analyses = [{"risk_score": 50, "profanity_density": 0.05}]
    result = compute_affective(analyses)
    assert "risk_volatility" not in result

    # Two values
    analyses = [
        {"risk_score": 50, "profanity_density": 0.05},
        {"risk_score": 60, "profanity_density": 0.10},
    ]
    result = compute_affective(analyses)
    assert "risk_volatility" in result
