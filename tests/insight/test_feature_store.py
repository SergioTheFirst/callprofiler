import numpy as np
from callprofiler.insight.features.base import Feature, Tier
from callprofiler.insight.feature_store import assemble_matrix, standardize


def test_assemble_aligns_names_and_imputes_missing():
    per_contact = {
        1: {"a": Feature(1.0, 5, Tier.IMMUNE), "b": Feature(2.0, 5, Tier.IMMUNE)},
        2: {"a": Feature(3.0, 5, Tier.IMMUNE)},  # b отсутствует
    }
    cids, names, X, weights = assemble_matrix(per_contact)
    assert cids == [1, 2]
    assert names == ["a", "b"]
    assert np.isnan(X[1, 1])  # b у контакта 2 пропущен


def test_standardize_imputes_and_zscores():
    X = np.array([[1.0, np.nan], [3.0, 4.0], [5.0, 6.0]])
    weights = np.array([1.0, 1.0])
    Z = standardize(X, weights)
    assert not np.isnan(Z).any()
    assert abs(Z[:, 0].mean()) < 1e-9  # колонка центрирована


def test_low_support_blanked():
    per_contact = {
        1: {"a": Feature(1.0, 1, Tier.IMMUNE)},  # support_n=1 < floor
        2: {"a": Feature(3.0, 9, Tier.IMMUNE)},
    }
    cids, names, X, weights = assemble_matrix(per_contact, support_floor=2)
    assert np.isnan(X[0, 0])  # выбракован по support
