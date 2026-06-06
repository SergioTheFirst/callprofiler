"""Аффективная подпись контакта (риск/матерные слова). Тир AFFECTIVE (из LLM-анализа)."""
import statistics

from .base import Feature, Tier


def compute_affective(analyses, reference_now=None):
    """Извлекает аффективные фичи из анализов звонков.

    Args:
        analyses: list[dict] с ключами risk_score (0-100), profanity_density (float)
        reference_now: не используется, для совместимости сигнатуры

    Returns:
        {name: Feature} с mean_risk, risk_volatility, max_risk, profanity_mean
    """
    if not analyses:
        return {}

    risk_scores = [a.get("risk_score", 0) for a in analyses if a.get("risk_score") is not None]
    profanity_densities = [a.get("profanity_density", 0.0) for a in analyses if a.get("profanity_density") is not None]

    out = {}
    n = len(analyses)

    # mean_risk
    if risk_scores:
        mean_risk = statistics.fmean(risk_scores)
        out["mean_risk"] = Feature(mean_risk, len(risk_scores), Tier.AFFECTIVE)

    # risk_volatility (pstdev, 0 если < 2 значений)
    if len(risk_scores) >= 2:
        volatility = statistics.pstdev(risk_scores)
        out["risk_volatility"] = Feature(volatility, len(risk_scores), Tier.AFFECTIVE)

    # max_risk
    if risk_scores:
        max_risk = float(max(risk_scores))
        out["max_risk"] = Feature(max_risk, len(risk_scores), Tier.AFFECTIVE)

    # profanity_mean
    if profanity_densities:
        mean_prof = statistics.fmean(profanity_densities)
        out["profanity_mean"] = Feature(mean_prof, len(profanity_densities), Tier.AFFECTIVE)

    return out
