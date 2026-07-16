# -*- coding: utf-8 -*-
"""
tension.py — A7: детерминированные правила расхождения слоёв досье («Напряжения»).

Ровно 5 правил (STRATEGIC_PLAN §6), без творчества. Каждое читает пары осей
из `d["archetype"]["dims"]` (сырые z-score, распечатанные archetypes-fit) или
`d["evolution"]`/`d["indices"]["emotional_pattern"]`. Данных нет — правило
молча не срабатывает (никогда не гадать, никогда не падать).
"""

from __future__ import annotations

RISK_TREND_MIN_RISE = 15.0
Z_HIGH = 1.0
Z_LOW = -1.0
WARM_MARKERS = ("positive", "warm", "тёпл")


def _dim_z(dims: list[dict], name: str) -> float | None:
    for entry in dims:
        if entry.get("dim") == name:
            return entry.get("z")
    return None


def cross_layer_tensions(d: dict) -> list[dict]:
    """d — собранное досье (dict, ДО русской локализации). Возврат:
    [{phrase, evidence_a, evidence_b}], пусто если ни одно правило не сработало."""
    tensions: list[dict] = []
    dims = ((d.get("archetype") or {}).get("dims")) or []

    # 1. Подчёркнуто формален (vy_ratio) — но звонит ночью (night_ratio)
    vy_z = _dim_z(dims, "vy_ratio")
    night_z = _dim_z(dims, "night_ratio")
    if vy_z is not None and night_z is not None and vy_z > Z_HIGH and night_z > Z_HIGH:
        tensions.append({
            "phrase": "подчёркнуто формален — но звонит ночью",
            "evidence_a": f"формальность: z={vy_z:.2f}",
            "evidence_b": f"ночная активность: z={night_z:.2f}",
        })

    # 2. Уклончив (hedge_ratio) — но командует (directive_ratio)
    hedge_z = _dim_z(dims, "hedge_ratio")
    directive_z = _dim_z(dims, "directive_ratio")
    if hedge_z is not None and directive_z is not None and hedge_z > Z_HIGH and directive_z > Z_HIGH:
        tensions.append({
            "phrase": "уклончив в формулировках, но при этом командует",
            "evidence_a": f"хеджирование: z={hedge_z:.2f}",
            "evidence_b": f"директивность: z={directive_z:.2f}",
        })

    # 3. Тон тёплый (emotional_pattern), но риск растёт по годам (evolution)
    evolution = d.get("evolution") or []
    emotional_pattern = str((d.get("indices") or {}).get("emotional_pattern") or "").lower()
    if len(evolution) >= 2 and any(marker in emotional_pattern for marker in WARM_MARKERS):
        by_year = sorted(evolution, key=lambda e: e.get("year", 0))
        first_risk = by_year[0].get("avg_risk")
        last_risk = by_year[-1].get("avg_risk")
        if (first_risk is not None and last_risk is not None
                and last_risk > first_risk + RISK_TREND_MIN_RISE):
            tensions.append({
                "phrase": "тон тёплый, но напряжение разговоров растёт",
                "evidence_a": f"эмоц. паттерн: {emotional_pattern}",
                "evidence_b": (f"риск {by_year[0].get('year')}→{by_year[-1].get('year')}: "
                               f"{first_risk:.0f}→{last_risk:.0f}"),
            })

    # 4. Специфичен и уверен (spec:water, B2) — но слово держит редко (prom:keep_rate_other, B3)
    specificity_z = _dim_z(dims, "spec_water")
    kept_z = _dim_z(dims, "prom_keep_rate_other")
    if specificity_z is not None and kept_z is not None and specificity_z > Z_HIGH and kept_z < Z_LOW:
        tensions.append({
            "phrase": "говорит конкретно и уверенно, но слово держит редко",
            "evidence_a": f"специфичность: z={specificity_z:.2f}",
            "evidence_b": f"надёжность обещаний: z={kept_z:.2f}",
        })

    # 5. Сам звонит (outgoing_ratio низкий = инициирует контакт) — но сам же просит (req:asym, B5)
    outgoing_z = _dim_z(dims, "outgoing_ratio")
    request_z = _dim_z(dims, "req_asym")
    if outgoing_z is not None and request_z is not None and outgoing_z < Z_LOW and request_z > Z_HIGH:
        tensions.append({
            "phrase": "сам ищет контакта и сам же просит — похоже, вы ему нужнее",
            "evidence_a": f"инициация звонков: z={outgoing_z:.2f}",
            "evidence_b": f"баланс просьб: z={request_z:.2f}",
        })

    return tensions
