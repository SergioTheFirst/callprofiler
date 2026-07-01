# -*- coding: utf-8 -*-
"""Лексические возрастные признаки — Л1/Л2/Т1/Т2 (vozrast.md §3.1/§3.8, Ф2 плана age.md).

Матч по лексиконам через token.startswith(стем) — без pymorphy2 (Жёсткое
решение #4: numpy+regex only). Т1/Т2 несут кластер/год, не скаляр — Feature
не подходит, возвращаются отдельные структуры (dict/tuple).
"""
from collections import Counter

from ..age_style.lexicons import load_lexicon
from .base import Feature, Tier, normalize_lemma

_PER_MILLE = 1000


def _stem_hit(token: str, stems: tuple) -> bool:
    return any(token.startswith(s) for s in stems)


def _density(tokens: list[str], stems: tuple) -> Feature:
    if not tokens:
        return Feature(0.0, 0, Tier.IMMUNE)
    norm = [normalize_lemma(t) for t in tokens]
    hits = sum(1 for t in norm if _stem_hit(t, stems))
    return Feature(hits * _PER_MILLE / len(norm), len(norm), Tier.IMMUNE)


def slang_density(tokens: list[str]) -> Feature:
    """Л1: молодёжный/интернет-сленг на 1000 слов. ↓ с возрастом, однонаправленный."""
    stems = tuple(row[0] for row in load_lexicon("slang"))
    return _density(tokens, stems)


def archaism_density(tokens: list[str]) -> Feature:
    """Л2: архаизмы/советизмы на 1000 слов. ↑ с возрастом, однонаправленный."""
    stems = tuple(row[0] for row in load_lexicon("archaisms"))
    return _density(tokens, stems)


def life_stage_profile(tokens: list[str]) -> dict:
    """Т1: доминирующий кластер жизненного этапа (ключ строки Т-Л6) + плотность.

    Returns:
        {"cluster": str|None, "density": Feature}
    """
    rows = load_lexicon("life_stage")
    norm = [normalize_lemma(t) for t in tokens]
    counts: Counter = Counter()
    for t in norm:
        for stem, cluster in rows:
            if t.startswith(stem):
                counts[cluster] += 1
                break
    if not counts or not norm:
        return {"cluster": None, "density": Feature(0.0, 0, Tier.IMMUNE)}
    cluster, hits = counts.most_common(1)[0]
    return {"cluster": cluster, "density": Feature(hits / len(norm), len(norm), Tier.IMMUNE)}


def realia_birth_year(tokens: list[str]) -> tuple[int, int] | None:
    """Т2: доминирующая поколенческая реалия → (birth_low, birth_high), либо None."""
    rows = load_lexicon("realia_by_epoch")
    norm = [normalize_lemma(t) for t in tokens]
    counts: Counter = Counter()
    for t in norm:
        for stem, lo, hi in rows:
            if t.startswith(stem):
                counts[(int(lo), int(hi))] += 1
                break
    if not counts:
        return None
    return counts.most_common(1)[0][0]
