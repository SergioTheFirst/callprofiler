# -*- coding: utf-8 -*-
"""P(g) -> год рождения (vozrast.md §6, Ф4 плана age.md).

MVP: агрегат-уровень (одно P(g) на контакт, все разговоры уже слиты в Фазе 2).

ponytail: ось A по-разговорно + темперированный байес (vozrast.md §6.2) —
апгрейд-путь при калибровке (§15), если агрегат-уровень окажется недостаточным:
завести таблицу посылок (per-call P_k) + accumulate = произведение
правдоподобий Q(y) с показателем alpha*R_k. Пока не нужно — см. age.md §Deferred.
"""
from .tables import GROUP_CENTERS, GROUP_CODES


def _weighted_percentile(values: list, weights: list, q: float) -> float:
    """Взвешенный перцентиль методом nearest-rank по дискретным точкам."""
    pairs = sorted(zip(values, weights), key=lambda vw: vw[0])
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    target = q * total
    cum = 0.0
    for v, w in pairs:
        cum += w
        if cum >= target - 1e-12:
            return v
    return pairs[-1][0]


def to_birth_year(p_group: dict, reference_year: int) -> tuple[int, int, int]:
    """P(g) -> (birth_low, birth_high, birth_point) через проекцию центров
    групп на годы (§2.2) и взвешенные 10/50/90-перцентили (§6.1)."""
    values = [reference_year - GROUP_CENTERS[g] for g in GROUP_CODES]
    weights = [p_group.get(g, 0.0) for g in GROUP_CODES]
    low = _weighted_percentile(values, weights, 0.10)
    high = _weighted_percentile(values, weights, 0.90)
    point = _weighted_percentile(values, weights, 0.50)
    if low > high:
        low, high = high, low
    return int(round(low)), int(round(high)), int(round(point))
