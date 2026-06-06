"""Траектория вовлечённости: тренд каденса + точки разлома. Тир IMMUNE."""
import numpy as np

from .base import Feature, Tier, parse_dt


def _cusum_changepoints(series):
    s = np.asarray(series, float)
    if len(s) < 4:
        return 0
    cum = np.cumsum(s - s.mean())
    d = np.diff(cum)
    signs = np.sign(d)
    signs = signs[signs != 0]
    if len(signs) < 2:
        return 0
    return int(np.sum(signs[1:] != signs[:-1]))


def compute_trajectory(calls, reference_now=None):
    dts = sorted(d for d in (parse_dt(c.get("call_datetime")) for c in calls) if d)
    n = len(dts)
    if n < 4:
        return {}
    t0 = dts[0]
    weeks = [(d - t0).days // 7 for d in dts]
    counts = np.zeros(weeks[-1] + 1)
    for w in weeks:
        counts[w] += 1
    x = np.arange(len(counts))
    slope = float(np.polyfit(x, counts, 1)[0]) if len(counts) >= 2 and x.std() > 0 else 0.0
    return {
        "cadence_slope": Feature(slope, n, Tier.IMMUNE),
        "changepoints": Feature(float(_cusum_changepoints(counts)), len(counts), Tier.IMMUNE),
    }
