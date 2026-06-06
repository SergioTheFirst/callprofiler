"""Phase 3: affective-фичи восстанавливают twin, отличимый ТОЛЬКО по аффекту.

`volatile_client` ≡ `business_transactional` по метаданным И тексту; различие только в
risk/profanity. Силуэт-авто-k СЛИВАЕТ такие почти-близнецы (k=4 при истинных 5) независимо
от affective — поэтому вклад affective измеряется при ИСТИННОМ k (изоляция от выбора k, как
измеряют маргинальный вклад признака в ML). Канонические archetypes.pca/kmeans/adjusted_rand_index
(ограничен [-1,1]).

Эмпирически (seed=0): text-only ARI@k5≈0.71 (twin не разделён) → +affective ARI@k5=1.0.
"""
from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight.synth.archetypes import AFFECTIVE_TEMPLATES
from callprofiler.insight.feature_store import (
    build_contact_features, assemble_matrix, standardize,
    _META_FNS, _TEXT_FNS, _AFFECTIVE_FNS,
)
from callprofiler.insight.archetypes import pca, kmeans, adjusted_rand_index

_TRUE_K = len(AFFECTIVE_TEMPLATES)  # = 5


def _ari_at_true_k(conn, ground_truth, fns):
    pc = build_contact_features(conn, "me", feature_fns=fns)
    cids, names, X, w = assemble_matrix(pc)
    Z = standardize(X, w)
    Zp = pca(Z, min(10, Z.shape[1]))
    labels, _ = kmeans(Zp, _TRUE_K, seed=0)
    truth = [ground_truth[c] for c in cids]
    return adjusted_rand_index(labels, truth)


def test_affective_recovers_twin_at_true_k():
    corpus = SyntheticCorpus(seed=0)
    conn = corpus.build(n_per=20, templates=AFFECTIVE_TEMPLATES)

    ari_text = _ari_at_true_k(conn, corpus.ground_truth, _META_FNS + _TEXT_FNS)
    ari_aff = _ari_at_true_k(conn, corpus.ground_truth, _META_FNS + _TEXT_FNS + _AFFECTIVE_FNS)

    assert ari_aff > ari_text, f"affective must add value: text={ari_text:.3f} aff={ari_aff:.3f}"
    assert ari_aff >= 0.85, f"affective twin-recovery weak: {ari_aff:.3f}"
    assert ari_aff <= 1.0, f"ARI must stay bounded <=1, got {ari_aff:.3f}"  # guard vs broken metric
