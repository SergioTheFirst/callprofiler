"""Темпоральная подпись контакта. Тир IMMUNE (метаданные)."""
import statistics

from .base import Feature, Tier, parse_dt


def compute_temporal(calls, reference_now=None):
    dts = sorted(d for d in (parse_dt(c.get("call_datetime")) for c in calls) if d)
    n = len(dts)
    if n == 0:
        return {}
    evening = sum(1 for d in dts if 18 <= d.hour <= 23)
    night = sum(1 for d in dts if 0 <= d.hour <= 5)
    business = sum(1 for d in dts if d.weekday() < 5 and 9 <= d.hour < 18)
    weekend = sum(1 for d in dts if d.weekday() >= 5)
    out = {
        "evening_ratio": Feature(evening / n, n, Tier.IMMUNE),
        "night_ratio": Feature(night / n, n, Tier.IMMUNE),
        "business_ratio": Feature(business / n, n, Tier.IMMUNE),
        "weekend_ratio": Feature(weekend / n, n, Tier.IMMUNE),
        "tenure_days": Feature(float((dts[-1] - dts[0]).days), n, Tier.IMMUNE),
    }
    if n >= 3:
        gaps = [(dts[i + 1] - dts[i]).total_seconds() / 3600.0 for i in range(n - 1)]
        mean = statistics.fmean(gaps)
        sd = statistics.pstdev(gaps)
        b = (sd - mean) / (sd + mean) if (sd + mean) > 0 else 0.0
        out["burstiness"] = Feature(b, len(gaps), Tier.IMMUNE)
    if reference_now is not None:
        out["recency_days"] = Feature(float((reference_now - dts[-1]).days), n, Tier.IMMUNE)
    return out
