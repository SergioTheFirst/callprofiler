# -*- coding: utf-8 -*-
"""B5.3: морфосинтаксика по закрытым спискам (М3 предлоги + С3 союзы) — один голос."""
from callprofiler.insight.age_style import scorer
from callprofiler.insight.features.morphosyntax_age import (
    preposition_share, subordination_ratio)


def test_preposition_share():
    rich = "в доме на горе с видом по дороге за рекой".split()
    poor = "дом гора вид дорога река".split()
    assert preposition_share(rich).value > preposition_share(poor).value
    assert preposition_share(rich).support_n == len(rich)


def test_subordination_ratio():
    sub = "чтобы поскольку хотя который и".split()
    coord = "и а но или либо".split()
    assert subordination_ratio(sub).value > subordination_ratio(coord).value
    assert subordination_ratio(coord).value == 0.0
    assert subordination_ratio(["дом"]).support_n == 0


def test_scorer_combined_single_vote():
    feats = {"prep_share": {"z": 1.0, "support_n": 100},
             "subord_ratio": {"z": 1.0, "support_n": 10}}
    p, contrib, _ = scorer.score_contact(feats)
    assert "morphosyntax" in contrib
    assert "prep_share" not in contrib and "subord_ratio" not in contrib  # деконфликт
    assert contrib["morphosyntax"]["bin"] == "высокая"
    assert p["G5"] > p["G1"]  # сложная морфосинтаксика -> старше


def test_scorer_single_axis_still_votes():
    p, contrib, _ = scorer.score_contact({"prep_share": {"z": -1.0, "support_n": 100}})
    assert contrib["morphosyntax"]["bin"] == "низкая"
