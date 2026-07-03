# -*- coding: utf-8 -*-
"""B6: реалии v2 — reminiscence-bump эпохи, пересечение интервалов, биграммы."""
from callprofiler.insight.features.lexical_age import realia_birth_year


def test_dominant_epoch_two_hits():
    assert realia_birth_year(["пейджер", "и", "пейджер"]) == (1960, 1982)


def test_intersection_of_single_hits():
    # дискотека (1945-1980) + пейджер (1960-1982) -> пересечение (1960, 1980)
    assert realia_birth_year(["дискотеку", "пейджер"]) == (1960, 1980)


def test_disjoint_single_hits_none():
    # пейджер (1960-1982) + тикток (1990-2012) не пересекаются -> None
    assert realia_birth_year(["пейджер", "тикток"]) is None


def test_single_hit_none():
    assert realia_birth_year(["пейджер", "давай", "завтра"]) is None


def test_bigram_laskovy_may():
    # биграмма «ласковый май» датирует; одиночное «ласковый» — нет (P1)
    assert realia_birth_year(["ласковый", "май", "дискотеку"]) == (1968, 1980)
    assert realia_birth_year(["ласковый", "голос", "дискотеку"]) is None
