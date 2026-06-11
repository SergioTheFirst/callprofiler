"""Операции CLI insight: чистая логика, переиспользуется CLI и тестами.

Отделена от argparse — чтобы тестировать без подпроцесса.
"""
import numpy as np

from . import repository as repo
from .feature_store import build_contact_features, assemble_matrix, standardize
from .archetypes import fit_archetypes
from .labels import cluster_label, describe_dim
from .person_link import build_entity_contact_map

_MIN_CONTACTS = 4  # ниже — кластеризация бессмысленна
_DISTINCT_Z = 0.8   # порог |z| для «отличительной» оси
_MAX_DISTINCT = 5


def _confidence(total_calls):
    if total_calls >= 20:
        return "high"
    if total_calls >= 6:
        return "medium"
    return "low"


def _distinctive_dims(zrow, names):
    """Топ-оси контакта по |z| (≥ порога) с человеческими фразами."""
    order = sorted(range(len(names)), key=lambda j: abs(zrow[j]), reverse=True)
    out = []
    for j in order:
        z = float(zrow[j])
        if abs(z) < _DISTINCT_Z:
            break
        phrase = describe_dim(names[j], z, thr=_DISTINCT_Z)
        if phrase:
            out.append({"dim": names[j], "z": round(z, 2), "phrase": phrase})
        if len(out) >= _MAX_DISTINCT:
            break
    return out


def run_features_build(conn, user_id, reference_now=None):
    """Посчитать и записать по-контактные фичи. Идемпотентно (UPSERT)."""
    repo.apply_insight_schema(conn)
    per_contact = build_contact_features(conn, user_id, reference_now=reference_now)
    n = 0
    for cid, feats in per_contact.items():
        for name, feat in feats.items():
            conn.execute(
                "INSERT INTO contact_features(contact_id, user_id, feature_set, "
                "feature_name, value, support_n, tier) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(contact_id, feature_name) DO UPDATE SET "
                "value=excluded.value, support_n=excluded.support_n, "
                "tier=excluded.tier, computed_at=CURRENT_TIMESTAMP "
                "WHERE contact_features.user_id = excluded.user_id",  # user-scoped guard
                (cid, user_id, "metadata", name, feat.value, feat.support_n, feat.tier.value),
            )
            n += 1
    conn.commit()
    return n


def run_archetypes_fit(conn, user_id, version="arch-v1", reference_now=None):
    """Собрать вектор → z-score → кластеризовать → сохранить модель+назначения."""
    repo.apply_insight_schema(conn)
    per_contact = build_contact_features(conn, user_id, reference_now=reference_now)
    cids, names, X, w = assemble_matrix(per_contact)
    if len(cids) < _MIN_CONTACTS:
        link = build_entity_contact_map(conn, user_id)
        return {"k": 0, "silhouette": 0.0, "n_assigned": 0, "links": link["links"]}
    Z = standardize(X, w)
    res = fit_archetypes(Z, k_range=range(2, 8), seed=0)
    labels, Zp, centroids, k = res["labels"], res["projection"], res["centroids"], res["k"]

    # Имена кластеров из профиля в фич-пространстве (top-|mean z|)
    cluster_names = {}
    for c in range(k):
        mask = labels == c
        if not mask.any():
            cluster_names[c] = f"кластер {c}"
            continue
        prof = Z[mask].mean(axis=0)
        top = sorted(range(len(names)), key=lambda j: abs(prof[j]), reverse=True)[:3]
        cluster_names[c] = cluster_label([(names[j], float(prof[j])) for j in top])

    mid = repo.save_archetype_model(
        conn, user_id, version=version, k=k, silhouette=res["silhouette"],
        n_contacts=len(cids), feature_list=names,
        centroids=[c.tolist() for c in centroids],
        labels={str(c): cluster_names[c] for c in range(k)},
    )
    for i, cid in enumerate(cids):
        c = int(labels[i])
        dist = float(np.linalg.norm(Zp[i] - centroids[c]))
        membership = round(1.0 / (1.0 + dist), 3)
        tc = per_contact[cid].get("total_calls")
        conf = _confidence(tc.value if tc else 0)
        # PCA-2D координаты для карты архетипов (Фаза 7): первые две оси проекции.
        px = round(float(Zp[i][0]), 4)
        py = round(float(Zp[i][1]), 4) if Zp.shape[1] > 1 else 0.0
        repo.save_contact_archetype(
            conn, user_id, contact_id=cid, model_id=mid, cluster_idx=c,
            label=cluster_names[c], membership=membership,
            distinctive_dims=_distinctive_dims(Z[i], names), confidence=conf, evidence=[],
            pca_x=px, pca_y=py,
        )
    # Связка entity↔contact (Ф1 досье): перестраивается вместе с архетипами
    link = build_entity_contact_map(conn, user_id)
    return {"k": k, "silhouette": res["silhouette"], "n_assigned": len(cids),
            "links": link["links"]}
