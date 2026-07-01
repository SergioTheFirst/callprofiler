# -*- coding: utf-8 -*-
"""Доля «я» среди 1-го лица — М1 (vozrast.md §3.2, Ф2 плана age.md).

Закрытый список, без морфологии → tier=IMMUNE. Переиспользует словари I/WE из
`pronouns.py` (Жёсткое решение #3 плана: не плодить дубли лексики).

М2/М3 (POS-профиль/предлоги) — вне ядра §3.11 этого MVP: не входят в
weights.BASE_WEIGHTS, включатся при появлении pymorphy2 (age.md §Deferred).
"""
from .base import Feature, Tier
from .pronouns import I as _I_WORDS
from .pronouns import WE as _WE_WORDS


def pronoun_i_ratio(tokens: list[str]) -> Feature:
    """I / (I + We). ↓ с возрастом (Pennebaker & Stone 2003)."""
    i_count = sum(1 for t in tokens if t in _I_WORDS)
    we_count = sum(1 for t in tokens if t in _WE_WORDS)
    total = i_count + we_count
    if total == 0:
        return Feature(0.0, 0, Tier.IMMUNE)
    return Feature(i_count / total, total, Tier.IMMUNE)
