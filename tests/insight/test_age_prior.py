# -*- coding: utf-8 -*-
"""B5.5: популяционный приор — слабый голос-регуляризатор (гасит ложные G1/G2)."""
from callprofiler.insight.age_style import scorer
from callprofiler.insight.age_style.tables import PRIOR_DIST


def test_empty_features_pool_equals_prior():
    p, contrib, conflict = scorer.score_contact({})
    assert set(contrib.keys()) == {"prior"}
    assert conflict is False
    for g in p:
        assert abs(p[g] - PRIOR_DIST[g]) < 1e-9


def test_prior_does_not_override_strong_signal():
    p, contrib, _ = scorer.score_contact(
        {"life_stage": {"cluster": "внуки_пенсия", "support_n": 50}})
    assert max(p, key=p.get) == "G6"  # сильный сигнал побеждает слабый приор


def test_prior_dampens_g1():
    # приор G1=0.01: без иных сигналов G1 почти исключён
    p, _, _ = scorer.score_contact({})
    assert p["G1"] < 0.05


def test_marker_only_no_conflict_against_prior():
    # только prior в стиле -> сравнивать маркер не с чем -> conflict False
    marker = {"birth_low": 1955, "birth_high": 1958, "confidence": 85}
    _, contrib, conflict = scorer.score_contact({}, marker=marker, reference_year=2026)
    assert conflict is False
    assert "marker" in contrib
