# -*- coding: utf-8 -*-
"""Оркестратор стилометрической оценки возраста (Ф4 плана age.md).

Вход: реплики контакта (speaker='OTHER', §2.7) по ВСЕМ звонкам, агрегат-уровень
(MVP, Жёсткое решение #2). Поток: сырые признаки (Фаза 2) -> z внутри
популяции пользователя (`feature_store`, Жёсткое решение #3) -> биннинг+таблицы
(Фаза 3) -> год рождения (accumulate) -> доверие (confidence) -> UPSERT
contact_age_style. НЕ пишет и НЕ вызывает `_aggregate`/aggregation
существующей marker/relation/LLM-системы (Жёсткое решение #1) — стиль живёт
в своей таблице. READ-ONLY заимствование: `_get_marker` читает (не пишет)
`contact_age_estimates.method/birth_year_*` как валидный явный маркер для
пула §7.1 и для Conflict-члена доверия §7.2 (vozrast.md §5.2 п.6).
"""
from __future__ import annotations

import logging
from datetime import date

from .. import repository as repo_mod
from .accumulate import to_birth_year
from .confidence import agreement_from_dist, confidence
from .rules import edge_bonus, gate_enough_data, sanity_bimodal
from .scorer import score_contact
from .tables import RULES_VERSION, TABLE_VERSION
from ..feature_store import assemble_matrix, standardize
from ..features import diversity_age, lexical_age, morphosyntax_age, readability_age
from ..features.base import tokenize
from ..features.formality import compute_formality

log = logging.getLogger(__name__)

_SCALAR_FEATURE_FNS = {
    "ch6": readability_age.mean_syllables_per_word,
    "mattr": diversity_age.mattr,
    "mtld": diversity_age.mtld,
    "yule_k": diversity_age.yule_k,
    "slang": lexical_age.slang_density,
    "archaism": lexical_age.archaism_density,
    "i_ratio": morphosyntax_age.pronoun_i_ratio,
}
_Z_SCALAR_IDS = ("ch6", "mattr", "mtld", "yule_k", "i_ratio", "vy_ratio")
_RAW_Z_IDS = ("slang", "archaism")


def _anchor_year(call_rows) -> int | None:
    """Средний год звонков контакта — якорь конвертации возраст->год рождения
    (vozrast.md §2.2: "конвертируется в год рождения по дате звонка"). НЕ дата
    запуска пересчёта: иначе один и тот же стиль давал бы разный год рождения
    в зависимости от того, когда именно был вызван run_style_estimate."""
    years = [int(str(r[0])[:4]) for r in call_rows if r[0] and str(r[0])[:4].isdigit()]
    return round(sum(years) / len(years)) if years else None


def _gather_contact(conn, user_id, contact_id):
    """Реплики speaker='OTHER' (§2.7, не UNKNOWN) + число звонков + темы + якорь-год."""
    rows = conn.execute(
        "SELECT t.speaker, t.text FROM transcripts t "
        "JOIN calls c ON c.call_id = t.call_id "
        "WHERE c.user_id = ? AND c.contact_id = ? "
        "ORDER BY t.call_id, t.start_ms",
        (user_id, contact_id),
    ).fetchall()
    other_segments = [{"speaker": "OTHER", "text": r[1]} for r in rows if r[0] == "OTHER"]
    tokens = []
    for seg in other_segments:
        tokens.extend(tokenize(seg["text"] or ""))
    call_rows = conn.execute(
        "SELECT call_datetime FROM calls WHERE user_id = ? AND contact_id = ?",
        (user_id, contact_id),
    ).fetchall()
    ct_rows = conn.execute(
        "SELECT a.call_type FROM analyses a JOIN calls c ON c.call_id = a.call_id "
        "WHERE c.user_id = ? AND c.contact_id = ? AND a.call_type IS NOT NULL",
        (user_id, contact_id),
    ).fetchall()
    return tokens, other_segments, len(call_rows), [r[0] for r in ct_rows], _anchor_year(call_rows)


def _raw_features(tokens, other_segments):
    feats = {name: fn(tokens) for name, fn in _SCALAR_FEATURE_FNS.items()}
    feats.update(compute_formality(other_segments))  # {"vy_ratio": Feature} либо {}
    return feats


def _get_marker(conn, user_id, contact_id) -> dict | None:
    """Валидный явный маркер СУЩЕСТВУЮЩЕЙ marker/relation-системы (не 'llm' —
    та же по духу слабая лексическая догадка, что и весь этот модуль; считать
    её "явным маркером" было бы циклической самопроверкой)."""
    row = conn.execute(
        "SELECT method, birth_year_low, birth_year_high, confidence "
        "FROM contact_age_estimates WHERE user_id = ? AND contact_id = ?",
        (user_id, contact_id),
    ).fetchone()
    if not row or row[0] not in ("marker", "relation", "combined"):
        return None
    if row[1] is None or row[2] is None:
        return None
    return {"birth_low": row[1], "birth_high": row[2], "confidence": row[3] or 1}


def run_style_estimate(conn, user_id: str, *, reference_now=None,
                       stale_only: bool = False) -> dict:
    """Оценить стилометрический возраст контактов пользователя. Идемпотентно (UPSERT)."""
    repo_mod.apply_insight_schema(conn)
    ref_year = getattr(reference_now, "year", None)
    if ref_year is None:
        ref_year = int(reference_now) if reference_now else date.today().year

    contact_ids = [r[0] for r in conn.execute(
        "SELECT contact_id FROM contacts WHERE user_id = ?", (user_id,)
    ).fetchall()]
    computed = {r[0]: r[1] for r in conn.execute(
        "SELECT contact_id, computed_at FROM contact_age_style WHERE user_id = ?",
        (user_id,)).fetchall()}
    last_call = {r[0]: r[1] for r in conn.execute(
        "SELECT contact_id, MAX(COALESCE(call_datetime, created_at, '')) FROM calls "
        "WHERE user_id = ? AND contact_id IS NOT NULL GROUP BY contact_id",
        (user_id,)).fetchall()}

    stats = {"contacts": 0, "estimated": 0, "skipped_fresh": 0, "skipped_no_data": 0}

    target_ids = []
    for cid in contact_ids:
        if stale_only and cid in computed:
            last_norm = str(last_call.get(cid, "") or "").replace("T", " ")
            comp_norm = str(computed[cid] or "").replace("T", " ")
            if last_norm and last_norm <= comp_norm:
                stats["skipped_fresh"] += 1
                continue
        target_ids.append(cid)

    per_contact_matrix, per_contact_extra = {}, {}
    for cid in target_ids:
        try:
            tokens, other_segments, n_conv, call_types, anchor = _gather_contact(
                conn, user_id, cid)
        except Exception as exc:  # noqa: BLE001 — pipeline.md: non-fatal, continue
            log.warning("age-style: сбор данных contact=%s: %s", cid, exc)
            continue
        total_tokens = len(tokens)
        if n_conv == 0 or total_tokens == 0:
            stats["skipped_no_data"] += 1
            continue
        per_contact_matrix[cid] = _raw_features(tokens, other_segments)
        per_contact_extra[cid] = {
            "n_conversations": n_conv, "total_tokens": total_tokens,
            "call_types": call_types, "anchor_year": anchor or ref_year,
            "life_stage": lexical_age.life_stage_profile(tokens),
            "realia": lexical_age.realia_birth_year(tokens),
        }

    if not per_contact_matrix:
        return stats

    cids, names, x, w = assemble_matrix(per_contact_matrix)
    z = standardize(x, w)
    name_idx = {nm: j for j, nm in enumerate(names)}

    for i, cid in enumerate(cids):
        try:
            stats["contacts"] += 1
            _score_and_save(conn, user_id, cid, per_contact_matrix[cid],
                            per_contact_extra[cid], z[i], name_idx)
            stats["estimated"] += 1
        except Exception as exc:  # noqa: BLE001 — pipeline.md: non-fatal, continue
            log.warning("age-style: contact=%s: %s", cid, exc)

    return stats


def _score_and_save(conn, user_id, cid, raw, extra, z_row, name_idx):
    anchor_year = extra["anchor_year"]
    features = {}
    for fid in _Z_SCALAR_IDS:
        f = raw.get(fid)
        if f is not None and f.support_n > 0 and fid in name_idx:
            features[fid] = {"z": float(z_row[name_idx[fid]]), "support_n": f.support_n}
    for fid in _RAW_Z_IDS:
        f = raw.get(fid)
        if f is not None:
            zval = float(z_row[name_idx[fid]]) if fid in name_idx and f.support_n > 0 else None
            features[fid] = {"raw": f.value, "z": zval, "support_n": f.support_n}
    ls = extra["life_stage"]
    features["life_stage"] = {"cluster": ls.get("cluster"),
                              "support_n": ls["density"].support_n}
    if extra["realia"] is not None:
        features["realia"] = {"year_range": extra["realia"], "support_n": extra["total_tokens"]}

    marker = _get_marker(conn, user_id, cid)
    p_group, contributions, marker_conflict = score_contact(
        features, extra["call_types"], anchor_year, marker=marker)
    agreement = agreement_from_dist(p_group)
    bimodal = sanity_bimodal(p_group)
    conf, level = confidence(
        extra["n_conversations"], extra["total_tokens"], agreement,
        marker_strength=(marker["confidence"] / 100.0) if marker else 0.0,
        conflict=1.0 if (bimodal or marker_conflict) else 0.0,
    )
    if not bimodal:
        conf = max(1, min(100, int(round(conf + edge_bonus(ls.get("cluster"))))))
    enough = gate_enough_data(extra["n_conversations"], extra["total_tokens"])
    if not enough:
        # §7.1: "данных мало" -> широкий приор, БЕЗ точки (не ложная точность).
        level = 1
        birth_low = birth_high = birth_point = None
    else:
        birth_low, birth_high, birth_point = to_birth_year(p_group, anchor_year)
        # §7.4: ширина интервала = масса незнания (1 - confidence/100).
        # ponytail: линейный widen-коэффициент — стартовая калибровка (§15).
        widen = max(1.0, (100 - conf) / 40.0)
        half = max(1, (birth_high - birth_low) / 2.0 * widen)
        birth_low = int(round(birth_point - half))
        birth_high = int(round(birth_point + half))

    warnings = []
    if not enough:
        warnings.append("мало данных")
    if bimodal:
        warnings.append("конфликтующие сигналы")
    if marker_conflict:
        warnings.append("расходится с явным маркером")

    top = sorted(
        ((k, round(v.get("weight", 0.0), 3)) for k, v in contributions.items()),
        key=lambda kv: -kv[1],
    )[:5]

    repo_mod.save_contact_age_style(
        conn, user_id, contact_id=cid, group_code=max(p_group, key=p_group.get),
        group_dist={g: round(v, 4) for g, v in p_group.items()},
        birth_low=birth_low, birth_high=birth_high, birth_point=birth_point,
        confidence=conf, confidence_level=level,
        n_conversations=extra["n_conversations"], total_tokens=extra["total_tokens"],
        top=top, warnings=warnings, table_version=f"{TABLE_VERSION}+{RULES_VERSION}",
    )
