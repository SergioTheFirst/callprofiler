from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight.feature_store import build_contact_features, assemble_matrix, standardize
from callprofiler.insight.archetypes import fit_archetypes, adjusted_rand_index


def _recover(seed, n_per):
    corpus = SyntheticCorpus(seed=seed)
    conn = corpus.build(n_per=n_per)
    per_contact = build_contact_features(conn, "me")
    cids, names, X, w = assemble_matrix(per_contact)
    Z = standardize(X, w)
    res = fit_archetypes(Z, k_range=range(2, 7), seed=0)
    truth = [corpus.ground_truth[c] for c in cids]
    return adjusted_rand_index(res["labels"], truth)


def test_recovers_planted_archetypes_clean():
    assert _recover(seed=0, n_per=20) >= 0.6


def test_recovers_under_small_sample():
    assert _recover(seed=3, n_per=12) >= 0.4
