"""Сборка по-контактной матрицы фич, импутация, взвешивание, z-score."""
import sqlite3

import numpy as np

from .features.base import Tier
from .features.temporal import compute_temporal
from .features.reciprocity import compute_reciprocity
from .features.trajectory import compute_trajectory
from .features.linguistic import compute_linguistic
from .features.formality import compute_formality
from .features.pronouns import compute_pronouns

TIER_WEIGHTS = {
    Tier.IMMUNE: 1.0,
    Tier.ROBUST: 0.8,
    Tier.AFFECTIVE: 0.6,
    Tier.FRAGILE: 0.4,
}

_META_FNS = (compute_temporal, compute_reciprocity, compute_trajectory)
_IMMUNE_FNS = _META_FNS  # alias for backward compat
_TEXT_FNS = (compute_linguistic, compute_formality, compute_pronouns)


def assemble_matrix(per_contact_features, support_floor: int = 2):
    """per_contact_features: {contact_id: {name: Feature}} ->
       (contact_ids, names, X[NaN-missing], col_weights)."""
    cids = sorted(per_contact_features)
    names = sorted({nm for feats in per_contact_features.values() for nm in feats})
    name_idx = {nm: j for j, nm in enumerate(names)}
    X = np.full((len(cids), len(names)), np.nan)
    weights = np.ones(len(names))
    for i, cid in enumerate(cids):
        for nm, feat in per_contact_features[cid].items():
            j = name_idx[nm]
            if feat.support_n < support_floor:
                continue  # ниже порога — оставляем NaN (импутируется медианой)
            X[i, j] = feat.value
            weights[j] = TIER_WEIGHTS.get(feat.tier, 1.0)
    return cids, names, X, weights


def standardize(X, col_weights):
    """Импутация колоночной медианой → z-score → масштаб sqrt(weight)."""
    X = X.astype(float).copy()
    for j in range(X.shape[1]):
        col = X[:, j]
        mask = ~np.isnan(col)
        med = np.median(col[mask]) if mask.any() else 0.0
        col[~mask] = med
        mu, sd = col.mean(), col.std()
        col = (col - mu) / sd if sd > 0 else col - mu
        X[:, j] = col * np.sqrt(col_weights[j])
    return X


def build_contact_features(conn, user_id, feature_fns=None, reference_now=None):
    """Читает звонки и сегменты per contact, запускает фичи.

    Args:
        conn: sqlite3.Connection
        user_id: str
        feature_fns: tuple of feature functions, default = _META_FNS + _TEXT_FNS
        reference_now: для временных фич

    Returns:
        {contact_id: {name: Feature}}
    """
    if feature_fns is None:
        feature_fns = _META_FNS + _TEXT_FNS

    conn.row_factory = sqlite3.Row
    contact_ids = [r[0] for r in conn.execute(
        "SELECT contact_id FROM contacts WHERE user_id = ?", (user_id,)
    ).fetchall()]
    out = {}
    for cid in contact_ids:
        # Читаем звонки (для мета-фич)
        rows = conn.execute(
            "SELECT call_id, direction, call_datetime, duration_sec "
            "FROM calls WHERE user_id = ? AND contact_id = ? ORDER BY call_datetime",
            (user_id, cid),
        ).fetchall()
        calls = [dict(r) for r in rows]

        # Читаем сегменты транскрипта (для текст-фич)
        seg_rows = conn.execute(
            "SELECT t.speaker, t.text FROM transcripts t "
            "JOIN calls c ON c.call_id = t.call_id "
            "WHERE c.user_id = ? AND c.contact_id = ? "
            "ORDER BY t.call_id, t.start_ms",
            (user_id, cid),
        ).fetchall()
        segments = [dict(r) for r in seg_rows]

        feats = {}

        # Запускаем мета-фичи (используют calls)
        for fn in feature_fns:
            if fn in _META_FNS:
                feats.update(fn(calls, reference_now=reference_now))

        # Запускаем текст-фичи (используют segments)
        for fn in feature_fns:
            if fn in _TEXT_FNS:
                feats.update(fn(segments, reference_now=reference_now))

        if feats:
            out[cid] = feats
    return out
