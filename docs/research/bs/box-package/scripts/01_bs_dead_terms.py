# -*- coding: utf-8 -*-
"""01_bs_dead_terms.py — E-0a: проверка D1 (мёртвые члены BS) и E-10 (r(bs_index, CR)).

Запуск: `python 01_bs_dead_terms.py --db <копия> [--compare] [--out results/E0a.md]` | `--synth`.
Правило решения — decision-rules.md §E-0a. Читает только копию.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import (build_synth, contact_estimates, emit, fit_prior, header, load_outcomes,  # noqa: E402
                     open_copy, parser)


def main() -> None:
    p = parser("E-0a: мёртвые члены BS-index; E-10: сравнение с CR")
    p.add_argument("--compare", action="store_true", help="E-10: корреляция bs_index vs CR median")
    args = p.parse_args()
    conn = build_synth(args.seed)[0] if args.synth else open_copy(args.db)
    u = args.user
    lines = [header("E-0a — мёртвые члены BS-index (D1)", args)]
    rows = conn.execute("SELECT event_type, COUNT(*) n FROM events WHERE user_id=? AND entity_id IS NOT NULL "
                        "GROUP BY event_type ORDER BY n DESC", (u,)).fetchall()
    lines.append("## event_type среди событий с entity_id\n\n| event_type | n |\n|---|---|\n" +
                 "\n".join(f"| {r['event_type']} | {r['n']} |" for r in rows) + "\n")
    m = conn.execute("SELECT COUNT(*) n, MAX(bs_index) mx, SUM(bs_index=0) zeros, SUM(vagueness_count) v, "
                     "SUM(blame_shift_count) b, SUM(emotional_spikes) e, SUM(broken_promises) br "
                     "FROM entity_metrics WHERE user_id=?", (u,)).fetchone()
    lines.append(f"## entity_metrics\n\n- строк: {m['n']}; MAX(bs_index) = {m['mx']}; нулей: {m['zeros']}\n"
                 f"- Σ vagueness_count={m['v']} blame_shift_count={m['b']} emotional_spikes={m['e']} "
                 f"broken_promises={m['br']}\n")
    dead_types = {r["event_type"] for r in rows} & {"vagueness", "blame_shift", "emotion_spike", "broken_promise"}
    d1 = (m["mx"] or 0) <= 20 and not dead_types and all((m[k] or 0) == 0 for k in ("v", "b", "e", "br"))
    lines.append(f"**D1 подтверждён: {'ДА' if d1 else 'НЕТ — стоп, пересмотреть 40-data-surface §4'}**\n")
    if args.compare:
        per, _ = load_outcomes(conn, u)
        rates = [sum(y for y, *_ in r) / len(r) for r in per.values() if len(r) >= 5]
        a0, b0 = fit_prior(rates)
        est = contact_estimates(per, a0, b0)
        # связь contact → entity: через entity_contact_map, если есть; synth: entity_id == contact_id
        has_map = conn.execute("SELECT 1 FROM sqlite_master WHERE name='entity_contact_map'").fetchone()
        if has_map:
            link = {r["contact_id"]: r["entity_id"] for r in conn.execute(
                "SELECT contact_id, entity_id FROM entity_contact_map WHERE user_id=? ORDER BY confidence", (u,))}
        else:
            link = {cid: cid for cid in est}
        bs = {r["entity_id"]: r["bs_index"] for r in conn.execute(
            "SELECT entity_id, bs_index FROM entity_metrics WHERE user_id=?", (u,))}
        pairs = [(bs[link[c]], e["median"]) for c, e in est.items() if e["n_eff"] >= 3 and link.get(c) in bs]
        if len(pairs) >= 5:
            mx = sum(x for x, _ in pairs) / len(pairs); my = sum(y for _, y in pairs) / len(pairs)
            num = sum((x - mx) * (y - my) for x, y in pairs)
            den = math.sqrt(sum((x - mx) ** 2 for x, _ in pairs) * sum((y - my) ** 2 for _, y in pairs))
            r = num / den if den else float("nan")
            lines.append(f"## E-10 — r(bs_index, CR median) по {len(pairs)} контактам с n_eff≥3: **{r:.3f}**\n")
        else:
            lines.append("## E-10 — недостаточно контактов с n_eff≥3 для корреляции\n")
    emit("\n".join(lines), args.out)
    if args.synth:
        assert d1, "synth должен воспроизводить D1"
        print("OK")


if __name__ == "__main__":
    main()
