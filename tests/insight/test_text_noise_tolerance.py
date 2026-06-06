"""Phase 2: устойчивость текст-фич к ASR-шуму.

Главное утверждение — АГРЕГАТНОЕ восстановление архетипов переживает шум (ARI),
и РАЗДЕЛИМОСТЬ когорт сохраняется (порядок hedge: fading > business), даже если
абсолютные значения отдельных фич плывут. Канонический adjusted_rand_index.
"""
from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight.feature_store import (
    build_contact_features, assemble_matrix, standardize, _META_FNS, _TEXT_FNS,
)
from callprofiler.insight.archetypes import fit_archetypes, adjusted_rand_index


def _mean_hedge(ground_truth, pc, archetype):
    vals = [pc[c]["hedge_ratio"].value
            for c, name in ground_truth.items()
            if name == archetype and c in pc and "hedge_ratio" in pc[c]]
    return sum(vals) / len(vals) if vals else 0.0


def test_aggregate_recovery_survives_noise():
    noisy = SyntheticCorpus(seed=0)
    conn = noisy.build(n_per=20, noise_rate=0.3)
    pc = build_contact_features(conn, "me", feature_fns=_META_FNS + _TEXT_FNS)
    cids, names, X, w = assemble_matrix(pc)
    Z = standardize(X, w)
    res = fit_archetypes(Z, k_range=range(2, 7), seed=0)
    truth = [noisy.ground_truth[c] for c in cids]
    ari_noisy = adjusted_rand_index(res["labels"], truth)
    assert ari_noisy >= 0.6, f"recovery collapsed under noise: {ari_noisy:.3f}"


def test_cohort_separation_preserved_under_noise():
    """Отдельная фича плывёт под шумом, но РАЗДЕЛИМОСТЬ когорт держится."""
    noisy = SyntheticCorpus(seed=0)
    conn = noisy.build(n_per=20, noise_rate=0.3)
    pc = build_contact_features(conn, "me", feature_fns=_TEXT_FNS)
    fading = _mean_hedge(noisy.ground_truth, pc, "fading_tie")        # регистр hedge=0.70
    business = _mean_hedge(noisy.ground_truth, pc, "business_transactional")  # hedge=0.10
    assert fading > business, f"hedge ordering lost under noise: fading={fading:.3f} business={business:.3f}"
