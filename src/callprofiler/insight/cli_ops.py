"""Операции CLI insight: чистая логика, переиспользуется CLI и тестами.

Отделена от argparse — чтобы тестировать без подпроцесса.
"""
from . import repository as repo
from .feature_store import build_contact_features, assemble_matrix, standardize
from .archetypes import fit_archetypes

_MIN_CONTACTS = 4  # ниже — кластеризация бессмысленна


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
                "tier=excluded.tier, computed_at=CURRENT_TIMESTAMP",
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
        return {"k": 0, "silhouette": 0.0, "n_assigned": 0}
    Z = standardize(X, w)
    res = fit_archetypes(Z, k_range=range(2, 8), seed=0)
    mid = repo.save_archetype_model(
        conn, user_id, version=version, k=res["k"], silhouette=res["silhouette"],
        n_contacts=len(cids), feature_list=names,
        centroids=[c.tolist() for c in res["centroids"]],
        labels={str(i): f"cluster_{i}" for i in range(res["k"])},
    )
    for cid, lab in zip(cids, res["labels"]):
        repo.save_contact_archetype(
            conn, user_id, contact_id=cid, model_id=mid, cluster_idx=int(lab),
            label=f"cluster_{int(lab)}", membership=1.0,
            distinctive_dims=[], confidence="medium", evidence=[],
        )
    return {"k": res["k"], "silhouette": res["silhouette"], "n_assigned": len(cids)}
