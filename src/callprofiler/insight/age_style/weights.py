# -*- coding: utf-8 -*-
"""Веса признаков: старт-веса, тиры, контекст-модуляция (vozrast.md §4.3/§4.5, Ф3 плана age.md)."""
from ..features.base import Tier

# Старт-вес = колонка §3.11 для реализованных признаков (Фаза 2 ядро).
BASE_WEIGHTS = {
    "life_stage": 0.95,   # Т1
    "realia": 0.90,       # Т2
    "slang": 0.85,        # Л1
    "archaism": 0.80,     # Л2
    "ch6": 0.80,
    "mattr": 0.80,        # Р3 — часть блока "diversity"
    "mtld": 0.75,         # Р4 — часть блока "diversity"
    "i_ratio": 0.70,      # М1
    "yule_k": 0.55,       # Р5 — часть блока "diversity"
    "vy_ratio": 0.60,     # Ст1
    "diversity": 0.78,    # объединённый голос Р3/Р4/Р5 (среднее их старт-весов)
    "discourse": 0.55,    # Д4 (B5.1)
    "kancelyarit": 0.50,  # Л6 (B5.2)
    "morphosyntax": 0.50, # М3/С3 (B5.3)
    "tempo": 0.50,        # Темп (B5.4)
    "prior": 0.25,        # Популяционный приор (B5.5)
    "prep_share": 0.40,   # М3 — часть morphosyntax
    "subord_ratio": 0.40, # С3 — часть morphosyntax
}

FEATURE_TIER = {
    "life_stage": Tier.IMMUNE, "realia": Tier.IMMUNE, "slang": Tier.IMMUNE,
    "archaism": Tier.IMMUNE, "i_ratio": Tier.IMMUNE,
    "ch6": Tier.ROBUST, "mattr": Tier.ROBUST, "mtld": Tier.ROBUST,
    "yule_k": Tier.ROBUST, "vy_ratio": Tier.ROBUST, "diversity": Tier.ROBUST,
    "discourse": Tier.ROBUST, "kancelyarit": Tier.ROBUST, "morphosyntax": Tier.ROBUST,
    "tempo": Tier.FRAGILE, "prep_share": Tier.IMMUNE, "subord_ratio": Tier.ROBUST,
    "prior": Tier.IMMUNE,
}

TIER_MULT = {Tier.IMMUNE: 1.0, Tier.ROBUST: 0.8, Tier.AFFECTIVE: 0.6, Tier.FRAGILE: 0.4}

# B5.5: вес популяционного приора в score_contact (всегда первым голосом)
PRIOR_WEIGHT = 0.25

# support_n, при котором support_factor достигает 1.0 (§4.3)
SUPPORT_N0 = {
    "ch6": 30, "mattr": 50, "mtld": 50, "yule_k": 50, "diversity": 50,
    "slang": 3, "archaism": 3, "i_ratio": 10, "vy_ratio": 5,  # B2: slang/archaism support_n = хиты теперь, не корпус
    "life_stage": 5, "realia": 10,
    "discourse": 6, "kancelyarit": 4, "morphosyntax": 30, "tempo": 10,  # B5
    "prep_share": 30, "subord_ratio": 6, "prior": 1,  # B5.3, B5.5
}

_BUSINESS_HINTS = ("business", "работ", "делов")
_PERSONAL_HINTS = ("personal", "семь", "личн")


def context_mod(feature_id: str, call_types: list | None) -> float:
    """§4.5: тема «работа» -> вниз сленг; «семья/личное» -> вверх Т1."""
    types_joined = " ".join(str(t).lower() for t in (call_types or []) if t)
    if feature_id == "slang" and any(h in types_joined for h in _BUSINESS_HINTS):
        return 0.5
    if feature_id == "kancelyarit" and any(h in types_joined for h in _BUSINESS_HINTS):
        return 0.6  # B5.2: профессия перебивает возраст (юристы/чиновники)
    if feature_id == "life_stage" and any(h in types_joined for h in _PERSONAL_HINTS):
        return 1.2
    return 1.0


def support_factor(support_n: int, feature_id: str) -> float:
    n0 = SUPPORT_N0.get(feature_id, 30)
    return min(support_n / n0, 1.0) if n0 > 0 else 1.0


def feature_weight(feature_id: str, support_n: int, call_types: list | None) -> float:
    base = BASE_WEIGHTS.get(feature_id, 0.0)
    tier_mult = TIER_MULT.get(FEATURE_TIER.get(feature_id), 1.0)
    return base * tier_mult * support_factor(support_n, feature_id) * context_mod(
        feature_id, call_types)
