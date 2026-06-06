"""Formality feature: formal (вы) vs informal (ты) pronouns."""
from .base import Feature, Tier, tokenize, count_markers

VY = {"вы", "вас", "вам", "вами", "ваш", "ваша", "ваше", "ваши"}
TY = {"ты", "тебя", "тебе", "тобой", "твой", "твоя", "твоё", "твое", "твои"}


def compute_formality(segments: list[dict], reference_now=None) -> dict[str, Feature]:
    """Считает vy_ratio (formal/informal pronoun balance).

    Args:
        segments: list[{"speaker": str, "text": str}]
        reference_now: не используется

    Returns:
        {vy_ratio: Feature} если есть vy или ty, иначе {}.
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

    vy_count = count_markers(all_words, VY)
    ty_count = count_markers(all_words, TY)
    total_pronouns = vy_count + ty_count

    if total_pronouns == 0:
        return {}

    return {
        "vy_ratio": Feature(
            value=vy_count / total_pronouns,
            support_n=total_pronouns,
            tier=Tier.ROBUST
        )
    }
