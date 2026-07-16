# -*- coding: utf-8 -*-
"""test_tension.py — A7: 5 детерминированных правил cross_layer_tensions."""
from callprofiler.insight.tension import cross_layer_tensions


def _dims(*pairs):
    return [{"dim": name, "z": z} for name, z in pairs]


def test_empty_dossier_no_tensions():
    assert cross_layer_tensions({}) == []


def test_no_dims_no_evolution_no_crash():
    d = {"archetype": {}, "evolution": [], "indices": {}}
    assert cross_layer_tensions(d) == []


def test_rule1_formal_but_calls_at_night():
    d = {"archetype": {"dims": _dims(("vy_ratio", 1.5), ("night_ratio", 1.2))}}
    out = cross_layer_tensions(d)
    assert len(out) == 1
    assert "формален" in out[0]["phrase"]


def test_rule1_does_not_fire_on_single_high_dim():
    d = {"archetype": {"dims": _dims(("vy_ratio", 1.5), ("night_ratio", 0.2))}}
    assert cross_layer_tensions(d) == []


def test_rule2_hedges_but_directive():
    d = {"archetype": {"dims": _dims(("hedge_ratio", 1.3), ("directive_ratio", 1.1))}}
    out = cross_layer_tensions(d)
    assert len(out) == 1
    assert "командует" in out[0]["phrase"]


def test_rule3_warm_tone_but_rising_risk():
    d = {
        "archetype": {"dims": []},
        "indices": {"emotional_pattern": "warm"},
        "evolution": [
            {"year": "2024", "avg_risk": 20.0, "calls": 3},
            {"year": "2026", "avg_risk": 40.0, "calls": 5},
        ],
    }
    out = cross_layer_tensions(d)
    assert len(out) == 1
    assert "напряжение" in out[0]["phrase"]


def test_rule3_does_not_fire_when_rise_below_threshold():
    d = {
        "archetype": {"dims": []},
        "indices": {"emotional_pattern": "warm"},
        "evolution": [
            {"year": "2024", "avg_risk": 20.0, "calls": 3},
            {"year": "2026", "avg_risk": 25.0, "calls": 5},
        ],
    }
    assert cross_layer_tensions(d) == []


def test_rule3_does_not_fire_without_warm_marker():
    d = {
        "archetype": {"dims": []},
        "indices": {"emotional_pattern": "tense"},
        "evolution": [
            {"year": "2024", "avg_risk": 20.0, "calls": 3},
            {"year": "2026", "avg_risk": 60.0, "calls": 5},
        ],
    }
    assert cross_layer_tensions(d) == []


def test_rule4_specific_but_breaks_promises():
    d = {"archetype": {"dims": _dims(("spec_water", 1.4), ("prom_keep_rate_other", -1.3))}}
    out = cross_layer_tensions(d)
    assert len(out) == 1
    assert "держит редко" in out[0]["phrase"]


def test_rule5_initiates_but_asks():
    d = {"archetype": {"dims": _dims(("outgoing_ratio", -1.4), ("req_asym", 1.2))}}
    out = cross_layer_tensions(d)
    assert len(out) == 1
    assert "нужнее" in out[0]["phrase"]


def test_multiple_rules_fire_together():
    d = {
        "archetype": {"dims": _dims(
            ("vy_ratio", 1.5), ("night_ratio", 1.2),
            ("hedge_ratio", 1.3), ("directive_ratio", 1.1),
        )},
        "indices": {"emotional_pattern": None},
        "evolution": [],
    }
    out = cross_layer_tensions(d)
    assert len(out) == 2


def test_each_tension_has_phrase_and_two_evidence_fields():
    d = {"archetype": {"dims": _dims(("vy_ratio", 2.0), ("night_ratio", 2.0))}}
    out = cross_layer_tensions(d)
    assert out[0].keys() == {"phrase", "evidence_a", "evidence_b"}
