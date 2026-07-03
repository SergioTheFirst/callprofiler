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


# B5.3: Закрытые списки для морфосинтаксики (М3/С3)
_PREPS = {"в", "на", "с", "по", "за", "из", "у", "о", "об", "обо", "при", "для", "без", "до",
          "через", "между", "над", "под", "перед", "около", "среди", "против", "вокруг", "вдоль",
          "возле", "ради", "сквозь", "благодаря", "вопреки", "согласно", "насчет", "ввиду", "вследствие"}
_SUBORD = {"чтобы", "потому", "поскольку", "хотя", "однако", "впрочем", "причем", "причём",
           "который", "которая", "которые", "которых", "если", "когда", "пока", "дабы", "ибо"}
_COORD = {"и", "а", "но", "или", "либо", "да", "тоже", "также", "зато"}


def preposition_share(tokens: list[str]) -> Feature:
    """М3: доля предлогов / всего слов. ↑ с возрастом (IMMUNE)."""
    if not tokens:
        return Feature(0.0, 0, Tier.IMMUNE)
    prep_count = sum(1 for t in tokens if t in _PREPS)
    return Feature(prep_count / len(tokens), len(tokens), Tier.IMMUNE)


def subordination_ratio(tokens: list[str]) -> Feature:
    """С3: подчинительные / (подчинительные + сочинительные). ↑ с возрастом (ROBUST)."""
    subord_count = sum(1 for t in tokens if t in _SUBORD)
    coord_count = sum(1 for t in tokens if t in _COORD)
    total = subord_count + coord_count
    if total == 0:
        return Feature(0.0, 0, Tier.ROBUST)
    return Feature(subord_count / total, total, Tier.ROBUST)
