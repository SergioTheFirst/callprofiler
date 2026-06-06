from callprofiler.insight.labels import describe_dim, cluster_label


def test_describe_dim_high_low_none():
    assert describe_dim("mean_risk", 2.0) == "высокий риск-фон"
    assert describe_dim("mean_risk", -2.0) == "спокойный фон"
    assert describe_dim("cadence_slope", -1.5) == "отношения остывают"
    assert describe_dim("mean_risk", 0.2) is None          # ниже порога
    assert describe_dim("night_ratio", -2.0) is None       # low_phrase пустой
    assert describe_dim("unknown_feature", 5.0) is None     # нет в словаре


def test_cluster_label_uses_top_phrases_and_deterministic():
    dims = [("evening_ratio", 1.5), ("mean_risk", 1.2)]
    lab = cluster_label(dims)
    assert "вечер" in lab.lower()
    assert " · " in lab
    assert cluster_label(dims) == cluster_label(dims)


def test_cluster_label_fallback_when_no_strong_dim():
    assert cluster_label([("mean_risk", 0.1)]) == "смешанный профиль"
