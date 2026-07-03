# -*- coding: utf-8 -*-
"""B5.4: темп речи (слов/сек) из таймстампов сегментов."""
from callprofiler.insight.age_style import scorer
from callprofiler.insight.features.tempo_age import words_per_sec


def test_rate_computed():
    fast = words_per_sec([(30, 10_000), (30, 10_000)])  # 3.0 слов/сек
    slow = words_per_sec([(12, 10_000), (12, 10_000)])  # 1.2 слов/сек
    assert abs(fast.value - 3.0) < 1e-9
    assert abs(slow.value - 1.2) < 1e-9
    assert fast.value > slow.value
    assert fast.support_n == 2


def test_invalid_segments_skipped():
    f = words_per_sec([(30, 0), (30, None), (30, 400_000), (10, 5_000)])
    assert f.support_n == 1
    assert abs(f.value - 2.0) < 1e-9


def test_empty_no_vote():
    assert words_per_sec([]).support_n == 0


def test_scorer_tempo_bins():
    p_fast, c_fast, _ = scorer.score_contact({"tempo": {"z": 1.0, "support_n": 10}})
    p_slow, c_slow, _ = scorer.score_contact({"tempo": {"z": -1.0, "support_n": 10}})
    assert c_fast["tempo"]["bin"] == "быстрый"
    assert c_slow["tempo"]["bin"] == "медленный"
    assert p_fast["G2"] > p_slow["G2"]  # быстрая речь -> моложе
    assert p_slow["G6"] > p_fast["G6"]
