# -*- coding: utf-8 -*-
"""Гейты/санити-правила (vozrast.md §5.3, Ф3 плана age.md). Версионируется
через RULES_VERSION (tables.py) — бамп при смене любого порога здесь.
"""
from .tables import GROUP_CODES

_MIN_CONVERSATIONS = 3
_MIN_TOKENS = 150
_PEAK_MIN_PROB = 0.15
_EDGE_CLUSTERS = ("школа_егэ", "внуки_пенсия")
_EDGE_BONUS = 10.0


def gate_enough_data(n_conversations: int, total_tokens: int) -> bool:
    """§7.3: <3 разговоров ИЛИ <150 слов -> недостаточно (level 1, без точки)."""
    return n_conversations >= _MIN_CONVERSATIONS and total_tokens >= _MIN_TOKENS


def sanity_bimodal(p_group: dict) -> bool:
    """§5.3: два несмежных пика (>=2 групп между ними) -> конфликт, не
    усреднять в ложную середину — вызывающий код должен расширить интервал."""
    vals = [p_group.get(g, 0.0) for g in GROUP_CODES]
    peaks = []
    for i, v in enumerate(vals):
        left = vals[i - 1] if i > 0 else -1.0
        right = vals[i + 1] if i < len(vals) - 1 else -1.0
        if v > left and v > right and v >= _PEAK_MIN_PROB:
            peaks.append(i)
    if len(peaks) < 2:
        return False
    return (peaks[-1] - peaks[0]) >= 2


def edge_bonus(life_stage_cluster: str | None) -> float:
    """§5.3: школа/ЕГЭ или внуки/пенсия -> бонус доверия (компенсация
    регрессии к среднему на краях шкалы, Nguyen 2013)."""
    return _EDGE_BONUS if life_stage_cluster in _EDGE_CLUSTERS else 0.0
