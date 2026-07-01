# -*- coding: utf-8 -*-
"""Лексическое разнообразие, length-invariant (Р3/Р4/Р5, vozrast.md §3.5, Ф2 плана age.md)."""
from collections import Counter

import numpy as np

from .base import Feature, Tier

_MIN_TOKENS = 50


def mattr(tokens: list[str], window: int = 50) -> Feature:
    """Moving-Average TTR: средний TTR по скользящему окну — не зависит от длины текста."""
    n = len(tokens)
    if n < window:
        return Feature(0.0, 0, Tier.ROBUST)
    ratios = [len(set(tokens[i:i + window])) / window for i in range(n - window + 1)]
    return Feature(float(np.mean(ratios)), n, Tier.ROBUST)


def _mtld_factors(seq: list[str], threshold: float) -> float:
    factors = 0.0
    types: set[str] = set()
    count = 0
    for tok in seq:
        count += 1
        types.add(tok)
        if len(types) / count <= threshold:
            factors += 1.0
            types, count = set(), 0
    if count > 0:
        ttr = len(types) / count
        factors += (1.0 - ttr) / (1.0 - threshold)
    return factors


def mtld(tokens: list[str], threshold: float = 0.72) -> Feature:
    """MTLD: средняя длина отрезка, держащего TTR выше порога — length-robust."""
    n = len(tokens)
    if n < _MIN_TOKENS:
        return Feature(0.0, 0, Tier.ROBUST)
    fwd = _mtld_factors(tokens, threshold)
    bwd = _mtld_factors(list(reversed(tokens)), threshold)
    factors = (fwd + bwd) / 2.0
    value = n / factors if factors > 0 else float(n)
    return Feature(float(value), n, Tier.ROBUST)


def yule_k(tokens: list[str]) -> Feature:
    """Индекс Юла K: концентрация словаря по распределению частот лемм. ↓ с возрастом."""
    n = len(tokens)
    if n < _MIN_TOKENS:
        return Feature(0.0, 0, Tier.ROBUST)
    freqs = Counter(tokens)
    freq_of_freq = Counter(freqs.values())
    s = sum((i ** 2) * v for i, v in freq_of_freq.items())
    k = 10000.0 * (s - n) / (n ** 2)
    return Feature(float(k), n, Tier.ROBUST)
