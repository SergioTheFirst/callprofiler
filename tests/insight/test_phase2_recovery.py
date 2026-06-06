"""Phase 2: доказать, что текст-фичи улучшают восстановление архетипов.

Использует КАНОНИЧЕСКИЕ archetypes.fit_archetypes / adjusted_rand_index
(с юнит-тестами identical->1.0). НЕ локальные самописные метрики.
"""
from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight.feature_store import (
    build_contact_features, assemble_matrix, standardize, _META_FNS, _TEXT_FNS,
)
from callprofiler.insight.archetypes import fit_archetypes, adjusted_rand_index


def _recover(conn, ground_truth, fns):
    pc = build_contact_features(conn, "me", feature_fns=fns)
    cids, names, X, w = assemble_matrix(pc)
    Z = standardize(X, w)
    res = fit_archetypes(Z, k_range=range(2, 7), seed=0)
    truth = [ground_truth[c] for c in cids]
    return res["k"], adjusted_rand_index(res["labels"], truth)


def test_text_features_improve_recovery():
    """META-only сливает business+fading (k=3, ARI~0.71); META+TEXT разводит их (k=4, ARI=1.0)."""
    corpus = SyntheticCorpus(seed=0)
    conn = corpus.build(n_per=20)

    k_meta, ari_meta = _recover(conn, corpus.ground_truth, _META_FNS)
    k_full, ari_full = _recover(conn, corpus.ground_truth, _META_FNS + _TEXT_FNS)

    assert ari_full > ari_meta, f"text must improve: meta={ari_meta:.3f} full={ari_full:.3f}"
    assert ari_full >= 0.85, f"full recovery weak: {ari_full:.3f}"
    assert k_full >= k_meta  # текст добавляет различимость, не теряет
