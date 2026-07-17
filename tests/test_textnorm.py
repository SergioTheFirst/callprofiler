# -*- coding: utf-8 -*-
"""test_textnorm.py — Fable §4.1: нормализованный quote-гейт."""
from __future__ import annotations

from callprofiler.textnorm import norm_quote


def test_lowercases():
    assert norm_quote("ПРИВЕТ") == "привет"


def test_yo_to_ye():
    assert norm_quote("ещё раз") == "еще раз"


def test_strips_punctuation():
    assert norm_quote("привет, как дела?!") == "привет как дела"


def test_collapses_whitespace():
    assert norm_quote("привет   \n  мир") == "привет мир"


def test_empty_and_none_safe():
    assert norm_quote("") == ""
    assert norm_quote(None) == ""


def test_matches_across_asr_punctuation_variance():
    quote = "я перезвоню завтра"
    chunk = "он сказал: «Я перезвоню, завтра!» — и повесил трубку."
    assert norm_quote(quote) in norm_quote(chunk)
