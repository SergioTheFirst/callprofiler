"""Тематическая подпись контакта (разнообразие тем). Тир AFFECTIVE (из LLM-анализа)."""
import json
from collections import Counter

from .base import Feature, Tier


def compute_topical(analyses, reference_now=None):
    """Извлекает тематические фичи из анализов звонков.

    Args:
        analyses: list[dict] с ключом key_topics (JSON-строка или список)
        reference_now: не используется, для совместимости сигнатуры

    Returns:
        {name: Feature} с topic_diversity, topic_focus или {}
    """
    if not analyses:
        return {}

    all_topics = []
    for a in analyses:
        topics = a.get("key_topics")
        if not topics:
            continue

        # Распарсить JSON-строку если нужно
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except (json.JSONDecodeError, ValueError):
                # Битый JSON — пропускаем
                continue

        # Убедиться что список
        if isinstance(topics, list):
            all_topics.extend(topics)

    if not all_topics:
        return {}

    out = {}
    total_mentions = len(all_topics)
    uniq_topics = len(set(all_topics))

    # topic_diversity = uniq / total
    diversity = uniq_topics / total_mentions if total_mentions > 0 else 0.0
    out["topic_diversity"] = Feature(diversity, total_mentions, Tier.AFFECTIVE)

    # topic_focus = Herfindahl = sum((cnt_i/total)^2)
    # 1.0 = одна тема, ниже = разнообразнее
    counter = Counter(all_topics)
    herfindahl = sum((cnt / total_mentions) ** 2 for cnt in counter.values())
    out["topic_focus"] = Feature(herfindahl, total_mentions, Tier.AFFECTIVE)

    return out
