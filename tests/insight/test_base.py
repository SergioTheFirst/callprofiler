from datetime import datetime
from callprofiler.insight.features.base import Tier, Feature, parse_dt


def test_feature_holds_value_support_tier():
    f = Feature(0.5, 10, Tier.IMMUNE)
    assert f.value == 0.5 and f.support_n == 10 and f.tier == Tier.IMMUNE


def test_parse_dt_iso_space_and_t():
    assert parse_dt("2026-03-01 21:30:00") == datetime(2026, 3, 1, 21, 30, 0)
    assert parse_dt("2026-03-01T21:30:00") == datetime(2026, 3, 1, 21, 30, 0)


def test_parse_dt_none_and_garbage():
    assert parse_dt(None) is None
    assert parse_dt("") is None
    assert parse_dt("not a date") is None
