# -*- coding: utf-8 -*-
"""03_role_quality.py — E-0a: качество ролей (UNKNOWN-доля) по звонкам и среди звонков с обещаниями (H4).

`python 03_role_quality.py --db <копия> [--out results/E0a-roles.md]` | `--synth`.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from _common import build_synth, emit, header, open_copy, parser  # noqa: E402


def main() -> None:
    args = parser("E-0a: UNKNOWN-доля и role_fragile").parse_args()
    conn = build_synth(args.seed)[0] if args.synth else open_copy(args.db)
    u = args.user
    unk = {r["call_id"]: r["u"] for r in conn.execute(
        "SELECT t.call_id, SUM(t.speaker='UNKNOWN')*1.0/COUNT(*) u FROM transcripts t JOIN calls c ON c.call_id=t.call_id "
        "WHERE c.user_id=? GROUP BY t.call_id", (u,))}
    prom_calls = {r[0] for r in conn.execute(
        "SELECT DISTINCT call_id FROM promise_outcomes WHERE user_id=? AND side='contact'", (u,))}
    def buckets(vals):
        c = Counter()
        for v in vals:
            c["0" if v == 0 else "≤0.1" if v <= 0.1 else "≤0.3" if v <= 0.3 else "≤0.5" if v <= 0.5 else ">0.5"] += 1
        return c
    all_v = list(unk.values()); pv = [unk[c] for c in prom_calls if c in unk]
    fragile = conn.execute("SELECT SUM(COALESCE(role_fragile,0)), COUNT(*) FROM calls WHERE user_id=?", (u,)).fetchone()
    mean_p = sum(pv) / max(len(pv), 1)
    lines = [header("E-0a — качество ролей (H4)", args),
             f"- звонков с транскриптом: {len(all_v)}; role_fragile: {fragile[0] or 0}/{fragile[1]}\n",
             f"- UNKNOWN-доля по всем звонкам: {dict(buckets(all_v))}\n",
             f"- звонков с обещаниями контакта: {len(pv)}; UNKNOWN-доля: {dict(buckets(pv))}; "
             f"средняя = {mean_p:.3f} (E-9 пропускается, если > 0.3)\n",
             f"**Решение E-0a: role_weight_mode = {'continuous (фиксировано)' if mean_p > 0.3 else 'по E-9'}**\n"]
    emit("\n".join(lines), args.out)
    if args.synth:
        assert len(all_v) > 0
        print("OK")


if __name__ == "__main__":
    main()
