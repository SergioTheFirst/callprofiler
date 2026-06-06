import numpy as np
from callprofiler.insight.archetypes import (
    kmeans, silhouette, adjusted_rand_index, fit_archetypes,
)


def test_ari_identical_is_one():
    a = [0, 0, 1, 1, 2, 2]
    assert adjusted_rand_index(a, a) == 1.0


def test_ari_permuted_labels_is_one():
    a = [0, 0, 1, 1]
    b = [1, 1, 0, 0]  # та же разбивка, другие метки
    assert adjusted_rand_index(a, b) == 1.0


def test_kmeans_separates_two_blobs():
    rng = np.random.default_rng(0)
    blob = np.vstack([rng.normal(0, 0.1, (20, 2)), rng.normal(5, 0.1, (20, 2))])
    labels, centers = kmeans(blob, 2, seed=0)
    assert len(set(labels[:20])) == 1 and len(set(labels[20:])) == 1


def test_fit_picks_two_clusters_for_two_blobs():
    rng = np.random.default_rng(1)
    blob = np.vstack([rng.normal(0, 0.2, (25, 3)), rng.normal(8, 0.2, (25, 3))])
    res = fit_archetypes(blob, k_range=range(2, 6), seed=0)
    assert res["k"] == 2
    assert res["silhouette"] > 0.5
