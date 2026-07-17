"""Specificity-vs-vagueness axis (B2, ozalupennieStrategic5.md).

Doctrine note (recorded in decisions.md at execution time): canonicalized entity
hits are NOT counted in v1 — that would require threading an alias-set through
the feature-router signature; deferred until a real need appears (YAGNI).
"""
import re

from .base import Feature, Tier, normalize_lemma

_RE_NUM = re.compile(r"\d")
_MONTHS = {"январ", "феврал", "март", "апрел", "мая", "мае", "июн", "июл",
           "август", "сентябр", "октябр", "ноябр", "декабр"}
_WDAYS = {"понедельник", "вторник", "сред", "четверг", "пятниц", "суббот", "воскресень"}
_RE_MONEY = re.compile(r"(руб|₽|тыс|тысяч|млн|миллион|долла|евро)", re.IGNORECASE)
_RE_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")


def compute_specificity(segments: list[dict], reference_now=None) -> dict[str, Feature]:
    """Доля токенов речи КОНТАКТА, несущих числа/даты/деньги/время.

    Args:
        segments: list[{"speaker": str, "text": str}]
        reference_now: не используется.

    Считает на whitespace-токенах (не ``base.tokenize()`` — тот вырезает цифры
    целиком регексом ``[а-яёa-z]+``, а числа здесь и есть главный сигнал).
    Категории НЕ эксклюзивны: один токен («15:30») может дать и numeric-,
    и time-хит одновременно — это усиливает сигнал специфичности, не баг.

    Returns:
        {specificity: Feature} если есть речь контакта, иначе {}.
    """
    contact_segments = [s for s in segments if s.get("speaker") != "OWNER"]
    if not contact_segments:
        contact_segments = segments
    if not contact_segments:
        return {}

    tokens = []
    for seg in contact_segments:
        tokens.extend((seg.get("text") or "").split())

    total_tokens = len(tokens)
    if total_tokens == 0:
        return {}

    hits = 0
    for tok in tokens:
        norm = normalize_lemma(tok.lower())
        if _RE_NUM.search(tok):
            hits += 1
        if any(norm.startswith(m) for m in _MONTHS) or any(norm.startswith(w) for w in _WDAYS):
            hits += 1
        if _RE_MONEY.search(tok):
            hits += 1
        if _RE_TIME.search(tok):
            hits += 1

    return {
        "specificity": Feature(
            value=hits / total_tokens * 100,
            support_n=hits,
            tier=Tier.ROBUST,
        )
    }
