# -*- coding: utf-8 -*-
"""Дискурс-репертуар (Д4): молодежные vs старшие коннекторы."""
from ..age_style.lexicons import load_lexicon
from .base import Feature, Tier
from .lexical_age import lexicon_hits


def filler_repertoire(tokens_norm: list[str]) -> Feature:
    """Д4: доля молодежных филлеров в общем пуле филлеров.

    young/total: молодой (share>0.65), смешанный (0.35..0.65), старший (share<0.35).
    Если total < 3 → Feature(0.0, 0, ROBUST) (нет голоса).
    """
    young_stems = tuple(row[0] for row in load_lexicon("fillers_young"))
    old_stems = tuple(row[0] for row in load_lexicon("fillers_old"))

    young_hits = lexicon_hits(tokens_norm, young_stems)
    old_hits = lexicon_hits(tokens_norm, old_stems)
    total = young_hits + old_hits

    if total < 3:
        return Feature(0.0, 0, Tier.ROBUST)

    share = young_hits / total
    return Feature(share, total, Tier.ROBUST)
