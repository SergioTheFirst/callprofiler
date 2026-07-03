# -*- coding: utf-8 -*-
"""B5/B7: новые оси (discourse, kancelyarit, morphosyntax, tempo, prior)."""
import pytest
from callprofiler.insight.features.discourse_age import filler_repertoire
from callprofiler.insight.features.tempo_age import words_per_sec
from callprofiler.insight.features.morphosyntax_age import preposition_share, subordination_ratio
from callprofiler.insight.age_style.tables import PRIOR_DIST, TABLES


def test_prior_dist_normalized():
    """B5.5: PRIOR_DIST должен быть нормирован (Σ=1)."""
    s = sum(PRIOR_DIST.values())
    assert abs(s - 1.0) < 1e-6, f"PRIOR_DIST sum={s}"


def test_tables_v2_all_normalized():
    """B7: все таблицы нормированы."""
    for name, table in TABLES.items():
        for bin_label, dist in table.items():
            s = sum(dist.values())
            assert abs(s - 1.0) < 1e-6, f"{name}/{bin_label}: sum={s}"


def test_discourse_young():
    """B5.1: молодежные филлеры."""
    tokens = ["типа", "короче", "типа", "жесть"]
    feat = filler_repertoire(tokens)
    assert feat.value > 0.65  # молодой (value = share)


def test_tempo_words_per_sec():
    """B5.4: темп речи."""
    seg_stats = [(100, 10000), (100, 10000)]  # 100 слов, 10 сек
    feat = words_per_sec(seg_stats)
    assert feat.value == 10.0  # 10 слов/сек


def test_preposition_share():
    """B5.3: доля предлогов."""
    tokens = ["в", "доме", "на", "столе", "это"]
    feat = preposition_share(tokens)
    assert feat.value > 0  # есть предлоги


def test_subordination_ratio():
    """B5.3: подчинительные союзы."""
    tokens = ["если", "то", "потому", "что", "это", "и", "то"]
    feat = subordination_ratio(tokens)
    assert feat.value > 0  # есть подчинительные
