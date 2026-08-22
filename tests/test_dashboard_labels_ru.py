# -*- coding: utf-8 -*-
"""Русификация характеристики личности (dashboard/labels_ru.py).

Чистый офлайн-тест (без БД/GPU): проверяет, что весь видимый человеку
словарь характеристики переводится в русский, `severity`-ключ сохраняется
для покраски, а перевод идемпотентен и не роняет неизвестные значения.
"""
import re

from callprofiler.dashboard import labels_ru as L

_CYR = re.compile(r"[а-яА-ЯёЁ]")


def test_enum_maps_cover_profiler_vocabulary():
    # TEMPERAMENT and MOTIVATION have been removed from psychology_profiler
    assert not hasattr(L, "TEMPERAMENT"), "TEMPERAMENT should be removed"
    assert not hasattr(L, "MOTIVATION"), "MOTIVATION should be removed"
    assert {"high", "medium", "low", "positive"} <= set(L.SEVERITY)
    for name in ("promise_breaker", "contradictory", "vague_communicator",
                 "blame_shifter", "emotionally_volatile", "reliable",
                 "high_risk", "neutral"):
        assert name in L.PATTERN_NAME
        assert _CYR.search(L.PATTERN_NAME[name])


def test_ru_unknown_value_passes_through():
    # Test with SEVERITY enum (TEMPERAMENT and MOTIVATION removed)
    assert L.ru(L.SEVERITY, "high") == "высокая"
    assert L.ru(L.SEVERITY, "HIGH") == "высокая"          # регистр ключа не важен
    assert L.ru(L.SEVERITY, "высокая") == "высокая"       # уже русское — без изменений
    assert L.ru(L.SEVERITY, "alien") == "alien"           # неизвестное не теряется
    assert L.ru(L.SEVERITY, None) is None


def test_pattern_label_translates_generated_english():
    assert L.pattern_label("5/10 promises broken") == "5/10 обещаний нарушено"
    assert L.pattern_label("3 contradictions in 12 calls") == "3 противоречий в 12 звонках"
    assert L.pattern_label("avg_risk=72") == "средний риск=72"
    assert "BS=" in L.pattern_label("bs_index=41.0, reliability=0.59")
    assert L.pattern_label(None) is None


def test_localize_character_full_profile():
    prof = {
        "entity_type": "person",
        "emotional_pattern": "volatile",
        "patterns": [{"name": "promise_breaker", "severity": "high",
                      "label": "5/10 promises broken"}],
        "contradictions": [{"quote_1": "a", "quote_2": "b", "severity": "medium"}],
    }
    out = L.localize_character(prof)
    # temperament and motivation should not be present
    assert "temperament" not in out, "temperament should be removed"
    assert "motivation" not in out, "motivation should be removed"
    assert out["entity_type"] == "person"                     # ключ сохранён
    assert out["entity_type_label"] == "человек"
    assert out["emotional_pattern"] == "неустойчивый"
    p = out["patterns"][0]
    assert p["severity"] == "high"                            # ключ для цвета сохранён
    assert p["severity_label"] == "высокая"
    assert p["name"] == "нарушает обещания"
    assert "обещаний нарушено" in p["label"]
    assert out["contradictions"][0]["severity_label"] == "средняя"


def test_localize_dossier_and_idempotent():
    dossier = {
        "patterns": [{"name": "reliable", "severity": "positive", "label": "0 broken promises"}],
        "facts": [{"quote": "q", "type": "promise"}],
        "temporal": {"frequency_trend": "increasing", "avg_calls_per_week": 2.0},
        "contradictions": [],
    }
    out = L.localize_dossier(dossier)
    # temperament and motivation should not be present
    assert "temperament" not in out, "temperament should be removed"
    assert "motivation" not in out, "motivation should be removed"
    assert out["patterns"][0]["severity_label"] == "надёжность"
    assert out["patterns"][0]["name"] == "надёжный"
    assert out["facts"][0]["type"] == "обещание"
    assert out["temporal"]["frequency_trend"] == "учащается"
    assert out["temporal"]["avg_calls_per_week"] == 2.0
    # идемпотентность: второй прогон ничего не ломает
    again = L.localize_dossier(out)
    assert again["patterns"][0]["name"] == "надёжный"
    assert again["patterns"][0]["severity"] == "positive"


def test_localize_handles_empty_and_missing_sections():
    assert L.localize_dossier({}) == {}
    assert L.localize_character({"patterns": [], "contradictions": None}) is not None
