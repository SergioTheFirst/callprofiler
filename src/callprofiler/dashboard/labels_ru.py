# -*- coding: utf-8 -*-
"""Русские ярлыки характеристики личности (презентационный слой дашборда).

Психопрофайлер и граф эмитят АНГЛИЙСКИЕ enum'ы (`choleric`, `achievement`,
`promise_breaker`, `high`, …) — они нужны книжным промптам biography и логике
цвета на фронте, менять их в источнике нельзя. Дашборд ПОКАЗЫВАЕТ их человеку,
поэтому здесь — единственная точка перевода в русский (доктрина дашборда:
«всё о личности — по-русски, фактологично»).

Все функции чистые (без БД), идемпотентные (повторный прогон по уже русскому
значению ничего не портит) и НЕ роняют структуру: неизвестное значение остаётся
как есть, а не превращается в пусто. `severity` НЕ переводим на месте ключа —
фронт красит паттерн по нему (`high`/`medium`/`positive`); вместо этого кладём
рядом `severity_label` для показа.
"""

from __future__ import annotations

import re
from typing import Any

# ── Словари enum → русский ──────────────────────────────────────────────
TEMPERAMENT = {
    "choleric": "холерик", "sanguine": "сангвиник",
    "phlegmatic": "флегматик", "melancholic": "меланхолик",
}
MOTIVATION = {
    "achievement": "достижение", "power": "власть",
    "affiliation": "привязанность", "security": "безопасность",
}
TREND = {
    "increasing": "учащается", "decreasing": "затухает", "stable": "стабильно",
    "insufficient_data": "мало данных", "unknown": "неизвестно",
}
SEVERITY = {
    "high": "высокая", "medium": "средняя", "low": "низкая",
    "positive": "надёжность",
}
PATTERN_NAME = {
    "promise_breaker": "нарушает обещания", "contradictory": "противоречив",
    "vague_communicator": "говорит размыто", "blame_shifter": "перекладывает вину",
    "emotionally_volatile": "эмоционально неустойчив", "reliable": "надёжный",
    "high_risk": "высокий риск", "neutral": "нейтрально",
}
ENTITY_TYPE = {
    "person": "человек", "company": "компания", "org": "организация",
    "project": "проект", "place": "место", "event": "событие",
}
FACT_TYPE = {
    "promise": "обещание", "debt": "долг", "task": "задача", "fact": "факт",
    "risk": "риск", "contradiction": "противоречие", "claim": "утверждение",
    "smalltalk": "беседа", "emotion_spike": "эмоциональный всплеск",
    "vagueness": "размытость", "blame_shift": "перекладывание вины",
}
EMOTIONAL = {
    "stable": "стабильный", "volatile": "неустойчивый",
    "escalating": "нарастающий", "calm": "спокойный", "neutral": "нейтральный",
}

# Подстановки в сгенерированных англоязычных `label` паттернов
# (psychology_profiler._extract_patterns — фиксированные фразы, можно заменять).
_LABEL_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"broken promises"), "нарушенных обещаний"),
    (re.compile(r"promises broken"), "обещаний нарушено"),
    (re.compile(r"contradictions in"), "противоречий в"),
    (re.compile(r"\bcalls\b"), "звонках"),
    (re.compile(r"vagueness signals"), "сигналов размытости"),
    (re.compile(r"blame-shift events"), "случаев перекладывания вины"),
    (re.compile(r"emotional spikes"), "эмоциональных всплесков"),
    (re.compile(r"avg_risk="), "средний риск="),
    (re.compile(r"bs_index="), "BS="),
    (re.compile(r"reliability="), "надёжность="),
]


def ru(mapping: dict[str, str], value: Any) -> Any:
    """Перевести строковое enum-значение; не-строки/неизвестное — без изменений."""
    if not isinstance(value, str):
        return value
    return mapping.get(value.strip().lower(), value)


def pattern_label(label: Any) -> Any:
    """Русифицировать сгенерированный английский label паттерна (по фразам)."""
    if not isinstance(label, str) or not label:
        return label
    out = label
    for rx, rep in _LABEL_SUBS:
        out = rx.sub(rep, out)
    return out


def _localize_patterns(patterns: Any) -> Any:
    for p in patterns or []:
        if not isinstance(p, dict):
            continue
        if p.get("severity") is not None and "severity_label" not in p:
            p["severity_label"] = ru(SEVERITY, p["severity"])  # ключ не трогаем
        if p.get("name") is not None:
            p["name"] = ru(PATTERN_NAME, p["name"])
        if p.get("label") is not None:
            p["label"] = pattern_label(p["label"])
    return patterns


def _localize_contradictions(rows: Any) -> Any:
    for c in rows or []:
        if isinstance(c, dict) and c.get("severity") is not None and "severity_label" not in c:
            c["severity_label"] = ru(SEVERITY, c["severity"])
    return rows


def _localize_temperament(t: Any) -> Any:
    if isinstance(t, dict) and t.get("type") is not None:
        t["type"] = ru(TEMPERAMENT, t["type"])
    return t


def _localize_motivation(m: Any) -> Any:
    if not isinstance(m, dict):
        return m
    for key in ("primary", "secondary"):
        if m.get(key) is not None:
            m[key] = ru(MOTIVATION, m[key])
    for drv in m.get("drivers") or []:
        if isinstance(drv, dict) and drv.get("driver") is not None:
            drv["driver"] = ru(MOTIVATION, drv["driver"])
    return m


def _localize_facts(facts: Any) -> Any:
    for f in facts or []:
        if isinstance(f, dict) and f.get("type") is not None:
            f["type"] = ru(FACT_TYPE, f["type"])
    return facts


def _localize_temporal(t: Any) -> Any:
    if isinstance(t, dict) and t.get("frequency_trend") is not None:
        t["frequency_trend"] = ru(TREND, t["frequency_trend"])
    return t


def localize_dossier(d: dict[str, Any]) -> dict[str, Any]:
    """In-place русификация досье (`get_person_dossier`). Идемпотентна."""
    if not isinstance(d, dict):
        return d
    _localize_temperament(d.get("temperament"))
    _localize_motivation(d.get("motivation"))
    _localize_patterns(d.get("patterns"))
    _localize_contradictions(d.get("contradictions"))
    _localize_facts(d.get("facts"))
    _localize_temporal(d.get("temporal"))
    return d


def localize_character(d: dict[str, Any]) -> dict[str, Any]:
    """In-place русификация профиля entity-модалки
    (`get_entity_profile` / `get_character_profile`). Идемпотентна."""
    if not isinstance(d, dict):
        return d
    _localize_temperament(d.get("temperament"))
    _localize_motivation(d.get("motivation"))
    _localize_patterns(d.get("patterns"))
    _localize_contradictions(d.get("contradictions"))
    if d.get("entity_type") is not None:
        d["entity_type_label"] = ru(ENTITY_TYPE, d["entity_type"])  # ключ не трогаем
    if d.get("emotional_pattern") is not None:
        d["emotional_pattern"] = ru(EMOTIONAL, d["emotional_pattern"])
    return d
