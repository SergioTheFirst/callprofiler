# -*- coding: utf-8 -*-
"""Длина слова в слогах — Ч6 (vozrast.md §3.4/§11.2, Ф2 плана age.md).

Единственный устойчивый читаемостный признак на транскрипте: не требует границ
предложений (в отличие от Флеша/ARI/Ч1-Ч5 — FRAGILE, ОТЛОЖЕНЫ, §Deferred).
"""
import numpy as np

from .base import Feature, Tier

_VOWELS = set("аеёиоуыэюя")


def mean_syllables_per_word(tokens: list[str]) -> Feature:
    """Слоги = число гласных в слове (§11.2). ↑ с возрастом."""
    if not tokens:
        return Feature(0.0, 0, Tier.ROBUST)
    syllables = [sum(1 for ch in tok if ch in _VOWELS) for tok in tokens]
    return Feature(float(np.mean(syllables)), len(tokens), Tier.ROBUST)
