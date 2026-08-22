# -*- coding: utf-8 -*-
"""04_cr_eval.py — E-1/E-1b (точность исходов, sensitivity), E-2 (цензура), E-3 (калибровка CI), E-9 (w_role).

`python 04_cr_eval.py --db <копия> --adjudicated adjudication-answers.csv [--role-mode] [--out results/E1-3.md]`
`python 04_cr_eval.py --db <копия> --source outcome_feedback` — стадия 2 (ярлыки из таблицы ✓/✗).
`python 04_cr_eval.py --synth` — smoke на synth с известным q и p_true (synth, не evidence).
Правила — decision-rules.md §E-1/§E-2/§E-3/§E-9.
"""
from __future__ import annotations

import csv
import hashlib
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from _common import (build_synth, cluster_bootstrap, contact_estimates, emit, fit_prior, header,  # noqa: E402
                     load_outcomes, open_copy, parser)

OUT_MAP = {"исполнено": 1, "не исполнено": 0, "kept": 1, "broken": 0, "1": 1, "0": 0}


def read_answers(path: str) -> dict:
    ans = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ans[row["promise_key"]] = dict(is_promise=row.get("is_promise", "да").strip().lower() in ("да", "yes", "1"),
                                           y=OUT_MAP.get(row.get("outcome", "").strip().lower()),
                                           role_swapped=row.get("role_swapped", "нет").strip().lower() in ("да", "yes", "1"))
    return ans


def synth_answers(conn, truth, seed: int, n: int = 200) -> dict:
    """Synth-оракул: «владелец» знает истинный исход (по p_true контакта воспроизводим через seed)."""
    rnd = random.Random(seed + 1)
    ans = {}
    for r in conn.execute("SELECT promise_key, contact_id, status FROM promise_outcomes ORDER BY promise_key"):
        ans[r["promise_key"]] = dict(is_promise=True, y=truth["y"][r["promise_key"]], role_swapped=False)
    return dict(rnd.sample(list(ans.items()), min(n, len(ans))))


def accuracy_block(conn, u, ans) -> tuple[str, dict]:
    rows = {r["promise_key"]: r for r in conn.execute(
        "SELECT promise_key, status, method, contact_id FROM promise_outcomes WHERE user_id=? AND side='contact'", (u,))}
    stats, lines = {}, ["## E-1 — точность исходов по методу\n"]
    fp_extract = sum(1 for k, a in ans.items() if not a["is_promise"]) / max(len(ans), 1)
    swapped = sum(1 for a in ans.values() if a["role_swapped"]) / max(len(ans), 1)
    for method in ("det", "llm"):
        items = [(rows[k], a) for k, a in ans.items() if k in rows and rows[k]["method"] == method
                 and rows[k]["status"] != "unknown" and a["y"] is not None and a["is_promise"]]
        if len(items) < 5:
            lines.append(f"- {method}: n={len(items)} < 5 — не оцениваем (q остаётся по умолчанию, UNCALIBRATED)\n")
            continue
        tp = sum(1 for r, a in items if r["status"] in ("kept", "late") and a["y"] == 1)
        tn = sum(1 for r, a in items if r["status"] == "broken" and a["y"] == 0)
        fn = sum(1 for r, a in items if r["status"] == "broken" and a["y"] == 1)
        fp = sum(1 for r, a in items if r["status"] in ("kept", "late") and a["y"] == 0)
        q = (tp + tn) / len(items); sens = tp / max(tp + fn, 1); spec = tn / max(tn + fp, 1)
        groups = {}
        for r, a in items:
            groups.setdefault(r["contact_id"], []).append((r, a))
        _, lo, hi = cluster_bootstrap(groups, lambda xs: sum(1 for r, a in xs if (r["status"] != "broken") == (a["y"] == 1)) / len(xs))
        stats[method] = dict(q=q, sens=sens, spec=spec, n=len(items))
        lines.append(f"- **{method}**: n={len(items)}, q={q:.2f} [80%: {lo:.2f}, {hi:.2f}], sens={sens:.2f}, spec={spec:.2f}, "
                     f"sens−(1−spec)={sens - (1 - spec):.2f}\n")
    lines.append(f"- FP извлечения («это не обещание»): {fp_extract:.2f} (R-9: > 0.3 → стоп стадии 2)\n"
                 f"- роль перепутана: {swapped:.2f} (≥0.05 → role_weight_mode=continuous)\n")
    q_det = stats.get("det", {}).get("q")
    if q_det is not None:
        rule = ("cr-v1, q_det := измеренное, calibrated=1" if q_det >= 0.75 else
                "cr-v1n (R-17) при sens−(1−spec)≥0.2, иначе cr-v1 с q измеренным" if q_det >= 0.6 else
                "w_label(det)=0.3; фразы только по E0+llm; R-19 отложить")
        lines.append(f"\n**Решение E-1 (det): {rule}**\n")
    return "\n".join(lines), stats


def sensitivity_block(conn, u, q_det: float) -> str:
    (a0, b0), per = _per(conn, u, q_det)
    base = contact_estimates(per, a0, b0)
    changed = 0; shown = 0
    for dq in (-0.05, 0.05):
        (a1, b1), per1 = _per(conn, u, max(0.05, min(0.99, q_det + dq)))
        est = contact_estimates(per1, a1, b1)
        for cid, e in base.items():
            if e["ci"] >= 50:
                shown += 1
                if est[cid]["phrase"] != e["phrase"]:
                    changed += 1
    share = changed / max(shown, 1)
    return (f"## E-1b — чувствительность к q_det ±0.05\n\n- контактов с фразой: {shown // 2 if shown else 0}; "
            f"меняют фразу: {share:.2f} ({'> 0.2 → tier_cuts на шаг вверх' if share > 0.2 else 'ок'})\n")


def _per(conn, u, q_det, role_mode="continuous"):
    per, _ = load_outcomes(conn, u, q_det=q_det, role_mode=role_mode)
    rates = [sum(y for y, *_ in r) / len(r) for r in per.values() if len(r) >= 5]
    a0, b0 = fit_prior(rates)
    return (a0, b0), per


def censoring_block(conn, u, ans) -> str:
    rows = {r["promise_key"]: r["status"] for r in conn.execute(
        "SELECT promise_key, status FROM promise_outcomes WHERE user_id=? AND side='contact'", (u,))}
    unk = [a["y"] for k, a in ans.items() if rows.get(k) == "unknown" and a["y"] is not None and a["is_promise"]]
    res = [a["y"] for k, a in ans.items() if rows.get(k) in ("kept", "late", "broken") and a["y"] is not None and a["is_promise"]]
    if len(unk) < 8:
        return f"## E-2 — цензура\n\n- adjudicated overdue-unknown: {len(unk)} < 8 → решение отложено, cap покрытия остаётся\n"
    pb = 1 - sum(unk) / len(unk); pr = 1 - sum(res) / max(len(res), 1)
    d = abs(pb - pr)
    return (f"## E-2 — цензура\n\n- π_b (провал | unknown overdue) = {pb:.2f} (n={len(unk)}); π_r = {pr:.2f} (n={len(res)}); |Δ| = {d:.2f}\n"
            f"**Решение: {'MAR → coverage_cap=0' if d <= 0.10 else f'cr-v1c, pi_unknown_broken={pb:.2f}, cap остаётся'}**\n")


def calibration_block(conn, u, ans, q_det: float, role_mode: str = "continuous", label: str = "E-3") -> tuple[str, float]:
    (a0, b0), per = _per(conn, u, q_det, role_mode)
    est = contact_estimates(per, a0, b0)
    rows = {r["promise_key"]: r["contact_id"] for r in conn.execute(
        "SELECT promise_key, contact_id FROM promise_outcomes WHERE user_id=? AND side='contact'", (u,))}
    adj = {}
    for k, a in ans.items():
        if a["y"] is not None and a["is_promise"] and k in rows:
            adj.setdefault(rows[k], []).append(a["y"])
    items = [(est[c]["ci"] / 100, 1 if abs(sum(ys) / len(ys) - est[c]["median"]) <= 0.1 else 0, c)
             for c, ys in adj.items() if len(ys) >= 3 and c in est]
    if len(items) < 8:
        return f"## {label} — калибровка\n\n- контактов с ≥3 adjudicated: {len(items)} < 8 — диаграмма не строится\n", float("nan")
    def ece(xs):
        xs = sorted(xs); nb = max(1, len(xs) // 8); bins = [xs[i::nb] for i in range(nb)] if nb > 1 else [xs]
        return sum(abs(sum(c for c, *_ in b) / len(b) - sum(h for _, h, *_ in b) / len(b)) * len(b) for b in bins) / len(xs)
    groups = {c: [it] for *_, c in items for it in [next(i for i in items if i[2] == c)]}
    point, lo, hi = cluster_bootstrap(groups, ece)
    brier = sum((c - h) ** 2 for c, h, _ in items) / len(items)
    over = sum(c for c, *_ in items) / len(items) - sum(h for _, h, _ in items) / len(items)
    xs = sorted(items); nb = max(1, len(xs) // 8)
    diag = "\n".join(f"| {sum(c for c,*_ in b)/len(b):.2f} | {sum(h for _,h,_ in b)/len(b):.2f} | {len(b)} |"
                     for b in ([xs[i::nb] for i in range(nb)] if nb > 1 else [xs]))
    return (f"## {label} — калибровка CI (контактов: {len(items)})\n\n| mean CI | доля попаданий ±0.1 | n |\n|---|---|---|\n{diag}\n\n"
            f"- ECE_adapt = {point:.3f} [80%: {lo:.3f}, {hi:.3f}]; Brier = {brier:.3f}; "
            f"направление: {'overconfidence' if over > 0 else 'underconfidence'} ({over:+.3f})\n"
            f"- стадия 1: число CI НЕ включается; {'tier_cuts на шаг вверх' if hi > 0.25 and over > 0 else 'без изменений'}\n"
            f"- стадия 2 (≥150 исходов/≥30 контактов): {'numeric_ci_enabled=1' if point <= 0.15 and hi <= 0.20 else 'temperature / число выключено'}\n",
            brier)


def main() -> None:
    p = parser("E-1/E-1b/E-2/E-3/E-9")
    p.add_argument("--adjudicated", help="adjudication-answers.csv")
    p.add_argument("--source", choices=["csv", "outcome_feedback"], default="csv")
    p.add_argument("--role-mode", action="store_true", help="E-9: сравнить continuous vs off")
    args = p.parse_args()
    if args.synth:
        conn, truth = build_synth(args.seed, q_det=0.8, coverage=0.7, mnar=0.3)
        ans = synth_answers(conn, truth, args.seed)
    else:
        conn = open_copy(args.db)
        if args.source == "outcome_feedback":
            ans = {r["promise_key"]: dict(is_promise=True, y={"kept": 1, "broken": 0}.get(r["verdict"]), role_swapped=False)
                   for r in conn.execute("SELECT promise_key, verdict FROM outcome_feedback WHERE user_id=?", (args.user,))}
        else:
            ans = read_answers(args.adjudicated)
    u = args.user
    acc, stats = accuracy_block(conn, u, ans)
    q_det = stats.get("det", {}).get("q", 0.7)
    parts = [header("E-1/E-2/E-3 — CR/CI оценка", args, f"q_det={q_det:.2f}"), acc, sensitivity_block(conn, u, q_det),
             censoring_block(conn, u, ans)]
    cal, brier_c = calibration_block(conn, u, ans, q_det)
    parts.append(cal)
    if args.role_mode:
        cal_off, brier_o = calibration_block(conn, u, ans, q_det, role_mode="off", label="E-9 (role off)")
        parts.append(cal_off)
        if brier_c == brier_c and brier_o == brier_o:
            parts.append(f"**Решение E-9: {'off (разница Brier < 0.005)' if abs(brier_c - brier_o) < 0.005 else ('continuous' if brier_c < brier_o else 'off')}**\n")
    emit("\n".join(parts), args.out)
    if args.synth:
        q = stats["det"]["q"]
        assert abs(q - 0.8) <= 0.08, f"synth q_det восстановлен неверно: {q}"
        print("OK")


if __name__ == "__main__":
    main()
