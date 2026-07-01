# -*- coding: utf-8 -*-
"""test_age_features.py — Ф2 плана age.md: возрастные стилометрические признаки (офлайн)."""
import random

from callprofiler.insight.features import diversity_age, lexical_age, morphosyntax_age, readability_age


def _repeat_vocab(n, pool_size=40, seed=0):
    rng = random.Random(seed)
    pool = [f"слово{i}" for i in range(pool_size)]
    return [rng.choice(pool) for _ in range(n)]


def test_mattr_length_invariant():
    f200 = diversity_age.mattr(_repeat_vocab(200))
    f800 = diversity_age.mattr(_repeat_vocab(800))
    assert f200.support_n == 200 and f800.support_n == 800
    assert abs(f200.value - f800.value) < 0.05


def test_mtld_yule_support_gating():
    short = ["слово"] * 10
    assert diversity_age.mtld(short).support_n == 0
    assert diversity_age.yule_k(short).support_n == 0
    long_tokens = _repeat_vocab(200)
    assert diversity_age.mtld(long_tokens).support_n == 200
    assert diversity_age.yule_k(long_tokens).support_n == 200
    assert diversity_age.mtld(long_tokens).value > 0
    mono = ["слово"] * 200  # один тип -> максимальная концентрация словаря
    assert diversity_age.yule_k(mono).value > diversity_age.yule_k(long_tokens).value


def test_syllables_ru():
    # слоги = число гласных букв (vozrast.md §11.2); "программирование" = 7 гласных
    assert readability_age.mean_syllables_per_word(["программирование"]).value == 7
    assert readability_age.mean_syllables_per_word(["дом"]).value == 1


def test_pronoun_i_ratio():
    tokens_i_heavy = ["я", "думаю", "мне", "кажется", "мой", "друг"]
    tokens_we_heavy = ["мы", "решили", "наш", "план", "нам", "подходит"]
    f_i = morphosyntax_age.pronoun_i_ratio(tokens_i_heavy)
    f_we = morphosyntax_age.pronoun_i_ratio(tokens_we_heavy)
    assert f_i.value > 0.6
    assert f_we.value < 0.4
    assert morphosyntax_age.pronoun_i_ratio(["дом", "работа"]).support_n == 0


def test_slang_density_youth_high():
    youth = "это такой кринж вообще база чил рофл вайб краш".split()
    adult = "необходимо рассмотреть данный вопрос совместно с коллегами".split()
    assert lexical_age.slang_density(youth).value > lexical_age.slang_density(adult).value
    assert lexical_age.slang_density(adult).value == 0.0


def test_archaism_density_old_high():
    old = "давеча аккурат сберкнижка талоны партком оное".split()
    young = "телефон приложение созвон интернет вопрос".split()
    assert lexical_age.archaism_density(old).value > lexical_age.archaism_density(young).value
    assert lexical_age.archaism_density(young).value == 0.0


def test_life_stage_maps_group():
    # Т-Л6 (vozrast.md §4.2): "школа/ЕГЭ" argmax G1 (0.80); "внуки/пенсия/поликлиника" argmax G6 (0.55)
    school = "готовлюсь сдавать егэ после школы уроки продлёнка".split()
    grandkids = "нянчу внуков хожу в поликлинику пенсия огород".split()
    school_profile = lexical_age.life_stage_profile(school)
    old_profile = lexical_age.life_stage_profile(grandkids)
    assert school_profile["cluster"] == "школа_егэ"
    assert old_profile["cluster"] == "внуки_пенсия"
    assert school_profile["density"].support_n == len(school)
    assert lexical_age.life_stage_profile([])["cluster"] is None


def test_realia_birth_year():
    old = "помню дискотеку кассету пейджер".split()
    young = "смотрю тикток твич аниме".split()
    neutral = "хорошо давай встретимся завтра".split()
    lo_o, hi_o = lexical_age.realia_birth_year(old)
    lo_y, hi_y = lexical_age.realia_birth_year(young)
    assert hi_o < lo_y  # старая реалия -> год рождения раньше молодой
    assert lexical_age.realia_birth_year(neutral) is None
