"""Pronouns features: first-person and collective pronouns."""
from .base import Feature, Tier, tokenize, count_markers

WE = {"мы", "нас", "нам", "нами", "наш", "наша", "наше", "наши"}
I = {"я", "меня", "мне", "мной", "мой", "моя", "моё", "мое", "мои"}


def compute_pronouns(segments: list[dict], reference_now=None) -> dict[str, Feature]:
    """Считает we_ratio и i_ratio (местоимения 1-го лица).

    Args:
        segments: list[{"speaker": str, "text": str}]
        reference_now: не используется

    Returns:
        {we_ratio, i_ratio: Feature} по речи контакта.
        Пустой вход или 0 слов → {}.
    """
    # Фильтруем речь контакта: speaker != "OWNER"; если нет — fallback на все
    contact_segments = [s for s in segments if s.get("speaker") != "OWNER"]
    if not contact_segments:
        contact_segments = segments

    if not contact_segments:
        return {}

    all_words = []
    for seg in contact_segments:
        text = seg.get("text", "")
        words = tokenize(text)
        all_words.extend(words)

    if not all_words:
        return {}

    we_count = count_markers(all_words, WE)
    i_count = count_markers(all_words, I)
    total_words = len(all_words)

    result = {}

    result["we_ratio"] = Feature(
        value=we_count / total_words if total_words > 0 else 0.0,
        support_n=total_words,
        tier=Tier.ROBUST
    )

    result["i_ratio"] = Feature(
        value=i_count / total_words if total_words > 0 else 0.0,
        support_n=total_words,
        tier=Tier.ROBUST
    )

    return result
