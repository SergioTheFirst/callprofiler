# -*- coding: utf-8 -*-
"""Система доверия: уровень 1-5 + формула confidence 1-100 (vozrast.md §7, Ф4 плана age.md).

Ширина итогового интервала — не отдельная формула, а прямое следствие
confidence (§7.4: "масса незнания = 1 - confidence/100 = ширина интервала"),
применяется в estimate_style.py.
"""
import math

_ESS0 = 10.0  # ess_proxy, при котором data-член формулы обнуляется (~ граница §7.1 level2/3)
# ponytail: стартовые коэффициенты (экспертные, не обученные) — калибровать на
# спот-чеке §15 (10-20 знакомых контактов на боксе), не трогать вслепую.
_A, _B, _C, _D = 1.5, 1.0, 0.8, 1.2


def normalized_entropy(p_group: dict) -> float:
    """H(P)/H_max ∈ [0,1]. 0 = один уверенный пик, 1 = равномерно (незнание)."""
    vals = [v for v in p_group.values() if v > 0]
    n = len(p_group) or 1
    if n <= 1:
        return 0.0
    h = -sum(v * math.log(v) for v in vals)
    h_max = math.log(n)
    return h / h_max if h_max > 0 else 0.0


def agreement_from_dist(p_group: dict) -> float:
    return 1.0 - normalized_entropy(p_group)


def confidence_level(n_conversations: int, total_tokens: int, conf: int) -> int:
    """§7.1: гейт «мало данных» -> level 1 безусловно; иначе по итоговому conf."""
    if n_conversations < 3 or total_tokens < 150:
        return 1
    if conf >= 80:
        return 5
    if conf >= 60:
        return 4
    if conf >= 35:
        return 3
    return 2


def confidence(n_conversations: int, total_tokens: int, agreement: float,
               marker_strength: float = 0.0, conflict: float = 0.0) -> tuple[int, int]:
    """§7.2: (confidence 1-100, level 1-5).

    ess_proxy — суррогат эффективного размера выборки без per-разговорных R_k
    (MVP агрегат-уровень): растёт и с числом разговоров, и с объёмом текста.

    `marker_strength` — 0.0 (нет валидного явного маркера) либо его
    confidence/100 (§7.2 MarkerBonus: сильный прямой маркер даёт больше
    бонуса, чем слабый relation-якорь — не плоский флаг).
    `conflict` — противоречия: маркер vs стиль ИЛИ внутренняя бимодальность
    (§7.2 Conflict; либо то и другое → всё равно 0/1, шкала не удваивается).
    """
    ess_proxy = max(1.0, min(n_conversations, total_tokens / 50.0))
    x = (_A * (math.log(ess_proxy) - math.log(_ESS0))
         + _B * (agreement - 0.5)
         + _C * marker_strength
         - _D * conflict)
    conf = 100.0 / (1.0 + math.exp(-x))
    conf = max(1, min(int(round(conf)), 100))
    level = confidence_level(n_conversations, total_tokens, conf)
    return conf, level
