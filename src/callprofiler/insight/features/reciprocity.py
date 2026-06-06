"""Реципрокность/власть/частота. Тир IMMUNE."""
import statistics

from .base import Feature, Tier, parse_dt


def compute_reciprocity(calls, reference_now=None):
    n = len(calls)
    if n == 0:
        return {}
    out = {"total_calls": Feature(float(n), n, Tier.IMMUNE)}
    known = [c for c in calls if (c.get("direction") or "UNKNOWN").upper() in ("IN", "OUT")]
    if known:
        outc = sum(1 for c in known if c["direction"].upper() == "OUT")
        out["outgoing_ratio"] = Feature(outc / len(known), len(known), Tier.IMMUNE)
    durs = [c["duration_sec"] for c in calls if c.get("duration_sec")]
    if durs:
        out["mean_duration_sec"] = Feature(float(statistics.fmean(durs)), len(durs), Tier.IMMUNE)
    dts = sorted(d for d in (parse_dt(c.get("call_datetime")) for c in calls) if d)
    if len(dts) >= 2:
        weeks = max((dts[-1] - dts[0]).days / 7.0, 1e-9)
        out["calls_per_week"] = Feature(len(dts) / weeks, len(dts), Tier.IMMUNE)
    return out
