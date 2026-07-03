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
    p_one, contrib_one, _ = scorer.score_contact(one)
    p_three, contrib_three, _ = scorer.score_contact(three)
    # B5.5: prior — всегда в contributions
    assert set(contrib_one.keys()) == {"life_stage", "diversity", "prior"}
    assert set(contrib_three.keys()) == {"life_stage", "diversity", "prior"}  # не 5 ключей
    for g in p_one:
        assert abs(p_one[g] - p_three[g]) < 0.05


def test_clean_profile_recovers_group():
    g2 = {  # молодёжный: вуз/сессия, сленг высокий, короткие слова, высокое "я"
        "life_stage": {"cluster": "вуз_сессия", "support_n": 50},
        "slang": {"raw": 15.0, "z": 1.2, "support_n": 200},
        "ch6": {"z": -1.2, "support_n": 200},
        "i_ratio": {"z": 1.0, "support_n": 40},
    }
    p2, _, _ = scorer.score_contact(g2)
    assert max(p2, key=p2.get) == "G2"

    g4 = {  # карьера, длинные слова, высокое лексическое разнообразие
        "life_stage": {"cluster": "карьера", "support_n": 50},
        "ch6": {"z": 1.0, "support_n": 200},
        "mattr": {"z": 0.7, "support_n": 200},
    }
    p4, _, _ = scorer.score_contact(g4)
    assert max(p4, key=p4.get) == "G4"

    g6 = {  # внуки/пенсия, архаизмы высокие, длинные слова, низкая доля "я"
        "life_stage": {"cluster": "внуки_пенсия", "support_n": 50},
        "archaism": {"raw": 20.0, "z": 1.8, "support_n": 200},
        "ch6": {"z": 1.5, "support_n": 200},
        "i_ratio": {"z": -1.0, "support_n": 40},
    }
    p6, _, _ = scorer.score_contact(g6)
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
    p, _, _ = scorer.score_contact(old_profile)
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


def test_score_contact_no_features_returns_prior():
    # B5.5: пустые фичи -> пул == популяционный приор (не uniform)
    from callprofiler.insight.age_style.tables import PRIOR_DIST
    p, contrib, conflict = scorer.score_contact({})
    assert set(contrib.keys()) == {"prior"}
    assert conflict is False
    assert all(abs(p[g] - PRIOR_DIST[g]) < 1e-9 for g in p)


def test_marker_reinforces_agreeing_style():
    # Маркер + стиль согласны (оба тянут к G6) -> маркер входит как голос,
    # итог остаётся G6, добавляется в contributions.
    g6 = {
        "life_stage": {"cluster": "внуки_пенсия", "support_n": 50},
        "archaism": {"raw": 20.0, "z": 1.8, "support_n": 200},
        "ch6": {"z": 1.5, "support_n": 200},
    }
    marker = {"birth_low": 1955, "birth_high": 1958, "confidence": 85}
    p, contrib, conflict = scorer.score_contact(g6, marker=marker, reference_year=2026)
    assert max(p, key=p.get) == "G6"
    assert conflict is False
    assert "marker" in contrib


def test_marker_wins_conflict_with_style():
    # Стиль уверенно молодой (G2), явный маркер говорит G6 -> маркер должен
    # ПОБЕДИТЬ (vozrast.md §7.1 "маркер побеждает"), и это помечается конфликтом.
    g2 = {
        "life_stage": {"cluster": "вуз_сессия", "support_n": 50},
        "slang": {"raw": 15.0, "z": 1.2, "support_n": 200},
        "ch6": {"z": -1.2, "support_n": 200},
        "i_ratio": {"z": 1.0, "support_n": 40},
    }
    p_style_only, _, _ = scorer.score_contact(g2)
    assert max(p_style_only, key=p_style_only.get) == "G2"  # предпосылка

    marker = {"birth_low": 1955, "birth_high": 1958, "confidence": 90}
    p, contrib, conflict = scorer.score_contact(g2, marker=marker, reference_year=2026)
    assert conflict is True
    assert max(p, key=p.get) == "G6"  # маркер перевесил стиль
    assert p["G6"] > p_style_only["G6"]  # стиль лишь слегка сдвигает, не отменяет


def test_marker_weak_relation_anchor_still_contributes():
    # Слабый маркер (низкая confidence, напр. relation-якорь) весит меньше,
    # но всё равно голосует — не игнорируется молча.
    marker = {"birth_low": 2004, "birth_high": 2006, "confidence": 25}  # age 20-22 @2026, solidly G2
    p, contrib, _ = scorer.score_contact({}, marker=marker, reference_year=2026)
    assert "marker" in contrib
    assert contrib["marker"]["weight"] > 0
    assert max(p, key=p.get) == "G2"  # только маркер голосует -> его группа побеждает


def test_marker_conflict_with_no_style_votes_is_false():
    # Пустой стиль (uniform) сравнивать с маркером бессмысленно -> conflict=False,
    # а не ложное срабатывание из-за произвольного argmax равномерного приора.
    marker = {"birth_low": 1955, "birth_high": 1958, "confidence": 85}
    _, _, conflict = scorer.score_contact({}, marker=marker, reference_year=2026)
    assert conflict is False
