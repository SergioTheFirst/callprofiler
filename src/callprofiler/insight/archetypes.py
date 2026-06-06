"""Кластеризация архетипов на чистом numpy: PCA, k-means, silhouette, ARI."""
from math import comb

import numpy as np


def pca(X, k):
    Xc = X - X.mean(0)
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    k = min(k, Vt.shape[0])
    return Xc @ Vt[:k].T


def _kpp_init(X, k, rng):
    n = len(X)
    centers = [X[rng.integers(n)]]
    for _ in range(1, k):
        d2 = np.min([((X - c) ** 2).sum(1) for c in centers], axis=0)
        probs = d2 / d2.sum() if d2.sum() > 0 else np.full(n, 1 / n)
        centers.append(X[rng.choice(n, p=probs)])
    return np.array(centers)


def kmeans(X, k, seed=0, n_init=10, max_iter=100):
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(n_init):
        centers = _kpp_init(X, k, rng)
        labels = np.zeros(len(X), int)
        for _ in range(max_iter):
            d = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(2)
            new_labels = d.argmin(1)
            new_centers = np.array([
                X[new_labels == c].mean(0) if (new_labels == c).any() else centers[c]
                for c in range(k)
            ])
            if np.array_equal(new_labels, labels) and np.allclose(new_centers, centers):
                labels, centers = new_labels, new_centers
                break
            labels, centers = new_labels, new_centers
        inertia = ((X - centers[labels]) ** 2).sum()
        if best is None or inertia < best[0]:
            best = (inertia, labels, centers)
    return best[1], best[2]


def silhouette(X, labels):
    uniq = np.unique(labels)
    if len(uniq) < 2:
        return -1.0
    D = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(2))
    sil = np.zeros(len(X))
    for i in range(len(X)):
        same = labels == labels[i]
        same[i] = False
        a = D[i, same].mean() if same.any() else 0.0
        b = min(D[i, labels == c].mean() for c in uniq if c != labels[i])
        sil[i] = 0.0 if max(a, b) == 0 else (b - a) / max(a, b)
    return float(sil.mean())


def adjusted_rand_index(a, b):
    a, b = np.asarray(a), np.asarray(b)
    ca = {v: i for i, v in enumerate(np.unique(a))}
    cb = {v: i for i, v in enumerate(np.unique(b))}
    cont = np.zeros((len(ca), len(cb)), int)
    for x, y in zip(a, b):
        cont[ca[x], cb[y]] += 1
    sum_c = sum(comb(int(v), 2) for v in cont.flatten())
    a_c = sum(comb(int(v), 2) for v in cont.sum(1))
    b_c = sum(comb(int(v), 2) for v in cont.sum(0))
    tot = comb(len(a), 2)
    exp = a_c * b_c / tot if tot else 0.0
    maxi = (a_c + b_c) / 2
    return float((sum_c - exp) / (maxi - exp)) if (maxi - exp) != 0 else 1.0


def fit_archetypes(X, k_range=range(2, 8), seed=0, pca_dim=10):
    Xp = pca(X, min(pca_dim, X.shape[1]))
    best = None
    for k in k_range:
        if k >= len(X):
            continue
        labels, centers = kmeans(Xp, k, seed=seed)
        s = silhouette(Xp, labels)
        if best is None or s > best["silhouette"]:
            best = {"silhouette": s, "k": k, "labels": labels,
                    "centroids": centers, "projection": Xp}
    return best
