# -*- coding: utf-8 -*-
"""test_age_scorer.py — Ф3 плана age.md: таблицы + скорер + правила (офлайн)."""
from callprofiler.insight.age_style import rules, scorer, tables


def test_tables_rows_normalized():
    for name, table in tables.TABLES.items():
        for bin_label, dist in table.items():
            s = sum(dist.values())
            assert abs(s - 1.0) < 1e-6, f"{name}/{bin_label}: Σ={s}"
            assert set(dist.keys()) == set(tables.GROUP_CODES)


def test_readability_counted_once():
    # Один и тот же сигнал разнообразия (тянет к молодым) через 1 меру vs 3
    # коррелированные меры -> ОДИН голос "diversity" в contributions, итоговый
    # пул почти не меняется (не утроенный вес).
    anchor = {"life_stage": {"cluster": "карьера", "support_n": 50}}
    one = {**anchor, "mattr": {"z": -1.5, "support_n": 100}}
    three = {**anchor,
             "mattr": {"z": -1.5, "support_n": 100},
             "mtld": {"z": -1.5, "support_n": 100},
             "yule_k": {"z": 1.5, "support_n": 100}}  # ↓-признак, инвертируется -> тот же сигнал
    p_one, contrib_one = scorer.score_contact(one)
    p_three, contrib_three = scorer.score_contact(three)
    assert set(contrib_one.keys()) == {"life_stage", "diversity"}
    assert set(contrib_three.keys()) == {"life_stage", "diversity"}  # не 4 ключа
    for g in p_one:
        assert abs(p_one[g] - p_three[g]) < 0.05


def test_clean_profile_recovers_group():
    g2 = {  # молодёжный: вуз/сессия, сленг высокий, короткие слова, высокое "я"
        "life_stage": {"cluster": "вуз_сессия", "support_n": 50},
        "slang": {"raw": 15.0, "z": 1.2, "support_n": 200},
        "ch6": {"z": -1.2, "support_n": 200},
        "i_ratio": {"z": 1.0, "support_n": 40},
    }
    p2, _ = scorer.score_contact(g2)
    assert max(p2, key=p2.get) == "G2"

    g4 = {  # карьера, длинные слова, высокое лексическое разнообразие
        "life_stage": {"cluster": "карьера", "support_n": 50},
        "ch6": {"z": 1.0, "support_n": 200},
        "mattr": {"z": 0.7, "support_n": 200},
    }
    p4, _ = scorer.score_contact(g4)
    assert max(p4, key=p4.get) == "G4"

    g6 = {  # внуки/пенсия, архаизмы высокие, длинные слова, низкая доля "я"
        "life_stage": {"cluster": "внуки_пенсия", "support_n": 50},
        "archaism": {"raw": 20.0, "z": 1.8, "support_n": 200},
        "ch6": {"z": 1.5, "support_n": 200},
        "i_ratio": {"z": -1.0, "support_n": 40},
    }
    p6, _ = scorer.score_contact(g6)
    assert max(p6, key=p6.get) == "G6"


def test_slang_absence_neutral():
    # "нет" бин симметричен G1/G6 (не благоприятствует молодым)
    dist_none = tables.TABLES["slang"]["нет"]
    assert dist_none["G1"] == dist_none["G6"]
    assert dist_none["G1"] < tables.TABLES["slang"]["высокая"]["G1"]

    # Отсутствие сленга в пуле не должно переворачивать argmax пожилого профиля
    old_profile = {
        "life_stage": {"cluster": "внуки_пенсия", "support_n": 50},
        "archaism": {"raw": 20.0, "z": 1.8, "support_n": 200},
        "slang": {"raw": 0.0, "z": None, "support_n": 200},
    }
    p, _ = scorer.score_contact(old_profile)
    assert max(p, key=p.get) == "G6"


def test_gate_low_data():
    assert rules.gate_enough_data(n_conversations=2, total_tokens=500) is False
    assert rules.gate_enough_data(n_conversations=5, total_tokens=50) is False
    assert rules.gate_enough_data(n_conversations=3, total_tokens=150) is True


def test_edge_bonus_and_bimodal():
    assert rules.edge_bonus("школа_егэ") > 0
    assert rules.edge_bonus("карьера") == 0.0
    peaked_conflict = {"G1": 0.40, "G2": 0.05, "G3": 0.05, "G4": 0.05, "G5": 0.05, "G6": 0.40}
    unimodal = {"G1": 0.05, "G2": 0.10, "G3": 0.60, "G4": 0.15, "G5": 0.07, "G6": 0.03}
    assert rules.sanity_bimodal(peaked_conflict) is True
    assert rules.sanity_bimodal(unimodal) is False


def test_score_contact_no_features_returns_uniform():
    p, contrib = scorer.score_contact({})
    assert contrib == {}
    assert all(abs(v - 1.0 / 6) < 1e-9 for v in p.values())
