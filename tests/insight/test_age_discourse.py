# -*- coding: utf-8 -*-
"""B5.1: дискурс-репертуар (Д4) — молодёжные vs старшие филлеры."""
from callprofiler.insight.age_style import scorer
from callprofiler.insight.features.discourse_age import filler_repertoire


def test_young_repertoire():
    tokens = "ну типа короче жесть капец вообще".split()
    f = filler_repertoire(tokens)
    assert f.support_n >= 3
    assert f.value > 0.65


def test_old_repertoire():
    tokens = "значит понимаешь собственно допустим так".split()
    f = filler_repertoire(tokens)
    assert f.support_n >= 3
    assert f.value < 0.35


def test_bigram_old_filler():
    # «стало быть» — биграмма old-лексикона
    tokens = "стало быть значит понимаешь".split()
    f = filler_repertoire(tokens)
    assert f.support_n >= 3
    assert f.value < 0.35


def test_below_min_hits_no_vote():
    f = filler_repertoire("типа значит".split())
    assert f.support_n == 0


def test_scorer_discourse_vote():
    p, contrib, _ = scorer.score_contact(
        {"discourse": {"raw": 0.9, "support_n": 6}})
    assert "discourse" in contrib
    assert contrib["discourse"]["bin"] == "молодой"
    assert p["G2"] > p["G5"]  # молодой репертуар тянет вниз по возрасту
