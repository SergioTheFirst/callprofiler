# -*- coding: utf-8 -*-
"""05_temporal_holdout.py — E-8 (затухание h) и E-4 (предсказательная ценность CR) на temporal holdout.

`python 05_temporal_holdout.py --db <копия> [--q-det 0.7] [--out results/E8-E4.md]` | `--synth`.
Holdout: T0 = max(evidence_date) − 180 дн.; обучение — исходы < T0, тест — исходы ≥ T0 (protocol.md §2).
Правила — decision-rules.md §E-8/§E-4.
"""
from __future__ import annotations

import math
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from _common import build_synth, cluster_bootstrap, emit, fit_prior, header, load_outcomes, open_copy, parser  # noqa: E402


def split(conn, u, q_det, half_life):
    per, _ = load_outcomes(conn, u, q_det=q_det, half_life=half_life, ref_date=None)
    dates = [date.fromisoformat(d[:10]) for rows in per.values() for *_, d, _k in rows if d]
    if not dates:
        return None, None, None
    t0 = max(dates) - timedelta(days=180)
    train = {c: [r for r in rows if r[3] and date.fromisoformat(r[3][:10]) < t0] for c, rows in per.items()}
    test = {c: [r for r in rows if r[3] and date.fromisoformat(r[3][:10]) >= t0] for c, rows in per.items()}
    # w_time в train считаем относительно t0, не today
    if half_life:
        train = {c: [(y, w * 0.5 ** (max((t0 - date.fromisoformat(d[:10])).days, 0) / half_life) / max(w, 1e-9) * w, s, d, k)
                     for y, w, s, d, k in rows] for c, rows in train.items()}
    return t0, train, test


def logloss_items(train, test, a0, b0, base_rate):
    items = {}
    for c, rows in test.items():
        if not rows:
            continue
        tr = train.get(c, [])
        a = a0 + sum(w * y for y, w, *_ in tr); b = b0 + sum(w * (1 - y) for y, w, *_ in tr)
        p = a / (a + b)
        for y, *_ in rows:
            items.setdefault(c, []).append((y, p, base_rate))
    return items


def ll(xs, which):
    eps = 1e-6
    return -sum(y * math.log(max(p if which == "cr" else b, eps)) + (1 - y) * math.log(max(1 - (p if which == "cr" else b), eps))
                for y, p, b in xs) / len(xs)


def auc(xs):
    pos = [p for y, p, _ in xs if y == 1]; neg = [p for y, p, _ in xs if y == 0]
    if not pos or not neg:
        return float("nan")
    return sum((1 if a > b else 0.5 if a == b else 0) for a in pos for b in neg) / (len(pos) * len(neg))


def main() -> None:
    p = parser("E-8/E-4 temporal holdout")
    p.add_argument("--q-det", type=float, default=0.7)
    args = p.parse_args()
    conn = build_synth(args.seed, drift=-0.25)[0] if args.synth else open_copy(args.db)
    u = args.user
    lines = [header("E-8/E-4 — temporal holdout", args)]
    results = {}
    for h in (None, 365, 180):
        t0, train, test = split(conn, u, args.q_det, h)
        if train is None:
            emit("нет исходов с датами", args.out); return
        rates = [sum(y for y, *_ in r) / len(r) for r in train.values() if len(r) >= 5]
        a0, b0 = fit_prior(rates)
        all_train = [y for r in train.values() for y, *_ in r]
        base = sum(all_train) / max(len(all_train), 1)
        items = logloss_items(train, test, a0, b0, base)
        if not items:
            lines.append("- тестовых исходов нет\n"); break
        pt, lo, hi = cluster_bootstrap(items, lambda xs: ll(xs, "cr"))
        results[h] = (pt, lo, hi, items, base, a0, b0, t0)
        lines.append(f"- h={'∞' if h is None else h}: log-loss CR = {pt:.4f} [80%: {lo:.4f}, {hi:.4f}] "
                     f"(T0={t0}, приор Beta({a0:.2f},{b0:.2f}), тест-исходов={sum(len(v) for v in items.values())})\n")
    if None in results:
        inf_items = results[None][3]
        for h in (365, 180):
            if h not in results:
                continue
            merged = {c: [(a, b) for a, b in zip(results[h][3].get(c, []), inf_items.get(c, []))] for c in inf_items if c in results[h][3]}
            pt, lo, hi = cluster_bootstrap(merged, lambda xs: ll([a for a, _ in xs], "cr") - ll([b for _, b in xs], "cr"))
            lines.append(f"- Δlog-loss(h={h}) − (∞) = {pt:+.4f} [80%: {lo:+.4f}, {hi:+.4f}] → "
                         f"{'h=' + str(h) + ' (CI < 0 целиком; Holm на 2 сравнения — проверить вручную)' if hi < 0 else 'оставить ∞'}\n")
        # E-4: lift над базовой долей
        pt, lo, hi = cluster_bootstrap(inf_items, lambda xs: ll(xs, "base") - ll(xs, "cr"))
        a = auc([it for v in inf_items.values() for it in v])
        lines.append(f"\n## E-4\n\n- lift log-loss (base − CR) = {pt:+.4f} [80%: {lo:+.4f}, {hi:+.4f}]; AUC = {a:.3f}\n"
                     f"**Решение E-4: phrase_mode = {'predictive' if lo > 0 else 'descriptive'}**\n")
    emit("\n".join(lines), args.out)
    if args.synth:
        assert None in results
        print("OK")


if __name__ == "__main__":
    main()
