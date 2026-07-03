# -*- coding: utf-8 -*-
"""Внутри-контактный скоринг: признаки -> P(g) взвешенным линейным пулом
(vozrast.md §4.4, Ф3 плана age.md).

Вход `features` — dict уже Z-НОРМИРОВАННЫХ (внутри популяции пользователя,
`feature_store.assemble_matrix`+`standardize`, Ф4) значений на ОДИН контакт:

    {
      "ch6":      {"z": float, "support_n": int},
      "mattr":    {"z": float, "support_n": int},
      "mtld":     {"z": float, "support_n": int},
      "yule_k":   {"z": float, "support_n": int},   # ↓ с возрастом -> инвертируется
      "slang":    {"raw": float, "z": float|None, "support_n": int},
      "archaism": {"raw": float, "z": float|None, "support_n": int},
      "i_ratio":  {"z": float, "support_n": int},
      "vy_ratio": {"z": float, "support_n": int},
      "life_stage": {"cluster": str|None, "support_n": int},   # Т1 — прямой маппинг
      "realia":     {"year_range": (lo, hi)|None, "support_n": int},  # Т2 — прямой год
    }

Любой ключ можно опустить (фича не посчитана/не хватило данных).
"""
from .tables import GROUP_CODES, TABLES, bin_z_3, bin_z_5, uniform_dist, year_range_to_group_dist, PRIOR_DIST
from .weights import feature_weight, PRIOR_WEIGHT

SUPPORT_FLOOR = 2  # §4.4: признаки ниже порога не голосуют (не импутируются шумом)

_DIVERSITY_IDS = ("mattr", "mtld", "yule_k")

# ponytail: старт-коэффициент — валидный явный маркер обычно должен перевешивать
# СУММУ style-голосов целиком (vozrast.md §7.1 "маркер побеждает, стиль лишь
# слегка сдвигает интервал"), не один голос. Масштабируется его собственной
# confidence (слабый relation-якорь весит меньше сильного прямого маркера).
# Калибровать на спот-чеке §15, не трогать вслепую.
_MARKER_WEIGHT_COEF = 2.5


def _diversity_vote(features: dict, call_types: list | None):
    zs, ws = [], []
    for fid in _DIVERSITY_IDS:
        f = features.get(fid)
        if not f or f.get("z") is None or f.get("support_n", 0) < SUPPORT_FLOOR:
            continue
        z = -f["z"] if fid == "yule_k" else f["z"]  # Р5 инвертирован (↓ с возрастом)
        zs.append(z)
        ws.append(feature_weight(fid, f["support_n"], call_types))
    if not zs:
        return None
    combined_z = sum(zs) / len(zs)
    combined_w = sum(ws) / len(ws)
    bin_label = bin_z_5(combined_z)
    return combined_w, TABLES["diversity"][bin_label], {"bin": bin_label, "n_measures": len(zs)}


def _onedirectional_vote(fid: str, f: dict, call_types: list | None):
    """Л1/Л2: "нет" по raw==0 (равномерна, не тянет), иначе z-бин 3 (§5.3)."""
    raw = f.get("raw") or 0.0
    if raw <= 0:
        bin_label = "нет"
    else:
        z = f.get("z") or 0.0
        bin_label = "высокая" if z > 0.5 else "умеренная"
    w = feature_weight(fid, f["support_n"], call_types)
    return w, TABLES[fid][bin_label], {"bin": bin_label}


def _morphosyntax_vote(features: dict, call_types: list | None):
    """B5.3: М3/С3 — среднее z двух осей; 3 бина (↑ с возрастом)."""
    zs, sups = [], []
    for fid in ("prep_share", "subord_ratio"):
        f = features.get(fid)
        if f and f.get("z") is not None and f.get("support_n", 0) >= SUPPORT_FLOOR:
            zs.append(f["z"])
            sups.append(f["support_n"])
    if not zs:
        return None
    combined_z = sum(zs) / len(zs)
    bin_label = bin_z_3(combined_z)
    w = feature_weight("morphosyntax", max(sups), call_types)
    return w, TABLES["morphosyntax"][bin_label], {"bin": bin_label, "n_measures": len(zs)}


def _pool(votes: list[tuple[str, float, dict]]) -> dict:
    total_w = sum(w for _, w, _ in votes if w > 0)
    if total_w <= 0:
        return uniform_dist()
    pooled = {g: 0.0 for g in GROUP_CODES}
    for _, w, dist in votes:
        if w <= 0:
            continue
        for g in GROUP_CODES:
            pooled[g] += w * dist.get(g, 0.0)
    return {g: v / total_w for g, v in pooled.items()}


def score_contact(features: dict, call_types: list | None = None,
                  reference_year: int | None = None,
                  marker: dict | None = None) -> tuple[dict, dict, bool]:
    """→ (P(g) dict по GROUP_CODES, contributions dict feature_id->{weight,...},
    marker_conflict: bool).

    `reference_year` — год, к которому проецируется Т2 (реалии->год рождения->
    P(g)); должен совпадать с reference_now вызывающего пайплайна (иначе Т2
    молча взял бы сегодняшнюю дату — год рождения "поплыл" бы между прогонами
    с разным reference_now при идентичных данных).

    `marker` — валидный явный маркер СУЩЕСТВУЮЩЕЙ marker/relation-системы
    (`{"birth_low", "birth_high", "confidence"}` из contact_age_estimates),
    если есть. Входит в пул как "узкая сильная посылка" (vozrast.md §7.1,
    §5.2 п.6): при согласии со стилем усиливает и сужает итог, при конфликте —
    ПОБЕЖДАЕТ за счёт веса (стиль лишь слегка сдвигает интервал, не
    переопределяет). `marker_conflict` — True, если argmax(стиль-only) !=
    argmax(маркер); сигнал для Conflict-члена формулы доверия (§7.2), не для
    самого переопределения (оно уже происходит через вес в пуле выше).
    """
    call_types = call_types or []
    votes: list[tuple[str, float, dict]] = []
    contributions: dict = {}

    # B5.5: Prior всегда первым голосом
    votes.append(("prior", PRIOR_WEIGHT, PRIOR_DIST))
    contributions["prior"] = {"weight": PRIOR_WEIGHT}

    div = _diversity_vote(features, call_types)
    if div is not None:
        w, dist, meta = div
        votes.append(("diversity", w, dist))
        contributions["diversity"] = {"weight": w, **meta}

    if "ch6" in features:
        f = features["ch6"]
        if f.get("z") is not None and f.get("support_n", 0) >= SUPPORT_FLOOR:
            bin_label = bin_z_5(f["z"])
            w = feature_weight("ch6", f["support_n"], call_types)
            votes.append(("ch6", w, TABLES["ch6"][bin_label]))
            contributions["ch6"] = {"weight": w, "bin": bin_label}

    for fid in ("slang", "archaism"):
        f = features.get(fid)
        if f and f.get("support_n", 0) >= SUPPORT_FLOOR:
            w, dist, meta = _onedirectional_vote(fid, f, call_types)
            votes.append((fid, w, dist))
            contributions[fid] = {"weight": w, **meta}

    for fid in ("i_ratio", "vy_ratio"):
        f = features.get(fid)
        if f and f.get("z") is not None and f.get("support_n", 0) >= SUPPORT_FLOOR:
            bin_label = bin_z_3(f["z"])
            w = feature_weight(fid, f["support_n"], call_types)
            votes.append((fid, w, TABLES[fid][bin_label]))
            contributions[fid] = {"weight": w, "bin": bin_label}

    f = features.get("life_stage")
    if f and f.get("cluster") and f.get("support_n", 0) >= SUPPORT_FLOOR:
        dist = TABLES["life_stage"].get(f["cluster"])
        if dist:
            w = feature_weight("life_stage", f["support_n"], call_types)
            votes.append(("life_stage", w, dist))
            contributions["life_stage"] = {"weight": w, "cluster": f["cluster"]}

    # B5.1: Discourse (молодой/смешанный/старший по raw-доле, z не нужен)
    f = features.get("discourse")
    if f and f.get("raw") is not None and f.get("support_n", 0) >= SUPPORT_FLOOR:
        share = f["raw"]
        if share > 0.65:
            bin_label = "молодой"
        elif share < 0.35:
            bin_label = "старший"
        else:
            bin_label = "смешанный"
        w = feature_weight("discourse", f["support_n"], call_types)
        votes.append(("discourse", w, TABLES["discourse"][bin_label]))
        contributions["discourse"] = {"weight": w, "bin": bin_label}

    # B5.2: Kancelyarit (однонаправленный, как slang/archaism)
    f = features.get("kancelyarit")
    if f and f.get("support_n", 0) >= SUPPORT_FLOOR:
        w, dist, meta = _onedirectional_vote("kancelyarit", f, call_types)
        votes.append(("kancelyarit", w, dist))
        contributions["kancelyarit"] = {"weight": w, **meta}

    # B5.3: Morphosyntax (М3/С3 объединённый)
    morph = _morphosyntax_vote(features, call_types)
    if morph is not None:
        w, dist, meta = morph
        votes.append(("morphosyntax", w, dist))
        contributions["morphosyntax"] = {"weight": w, **meta}

    # B5.4: Tempo (3 бина по z, быстрый = z>0.5)
    f = features.get("tempo")
    if f and f.get("z") is not None and f.get("support_n", 0) >= SUPPORT_FLOOR:
        z = f["z"]
        if z > 0.5:
            bin_label = "быстрый"
        elif z < -0.5:
            bin_label = "медленный"
        else:
            bin_label = "средний"
        w = feature_weight("tempo", f["support_n"], call_types)
        votes.append(("tempo", w, TABLES["tempo"][bin_label]))
        contributions["tempo"] = {"weight": w, "bin": bin_label}

    f = features.get("realia")
    if f and f.get("year_range") and f.get("support_n", 0) >= SUPPORT_FLOOR:
        lo, hi = f["year_range"]
        dist = year_range_to_group_dist(lo, hi, reference_year)
        w = feature_weight("realia", f["support_n"], call_types)
        votes.append(("realia", w, dist))
        contributions["realia"] = {"weight": w, "year_range": f["year_range"]}

    marker_conflict = False
    if marker is not None:
        # конфликт меряем ПРОТИВ чисто-стилевого голоса (до добавления маркера) —
        # prior не мнение стиля: только prior в пуле => сравнивать не с чем.
        non_prior = [v for v in votes if v[0] != "prior"]
        style_only = _pool(non_prior) if non_prior else None
        marker_dist = year_range_to_group_dist(
            marker["birth_low"], marker["birth_high"], reference_year)
        if style_only is not None:
            marker_conflict = (max(style_only, key=style_only.get)
                               != max(marker_dist, key=marker_dist.get))
        mw = _MARKER_WEIGHT_COEF * (marker.get("confidence", 1) / 100.0)
        votes.append(("marker", mw, marker_dist))
        contributions["marker"] = {
            "weight": mw, "birth_range": (marker["birth_low"], marker["birth_high"])}

    return _pool(votes), contributions, marker_conflict
