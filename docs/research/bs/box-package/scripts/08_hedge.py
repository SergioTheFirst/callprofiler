# -*- coding: utf-8 -*-
"""08_hedge.py — E-7: относительный рост хеджирования (z внутри контакта, окна 90 дн., сегменты после
прямого запроса владельца) vs исход обещаний следующего окна.

`python 08_hedge.py --db <копия> [--out results/E7.md]` | `--synth`. Правило — decision-rules.md §E-7.
Лексикон — расширенный (C-03 R2), только для эксперимента, не production.
"""
from __future__ import annotations

import math
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from _common import build_synth, cluster_bootstrap, emit, header, load_outcomes, open_copy, parser  # noqa: E402

HEDGE = {"наверное", "наверно", "возможно", "может", "кажется", "вроде", "типа", "посмотрим", "попробую",
         "постараюсь", "неуверен", "затрудняюсь", "как бы", "вроде бы", "в принципе", "скорее всего", "может быть"}
RE_REQUEST = re.compile(r"\b(прошу|попрошу|можешь|сможешь|мог бы|сделай|скинь|отправь|пришли|помоги|подскажи)\b", re.I)
TOK = re.compile(r"[а-яёa-z]+")


def hedge_rate(texts: list[str]) -> float | None:
    toks = [t for s in texts for t in TOK.findall(s.lower().replace("ё", "е"))]
    if len(toks) < 30:
        return None
    joined = " ".join(toks)
    hits = sum(joined.count(h) for h in HEDGE)
    return hits / len(toks)


def main() -> None:
    args = parser("E-7 хеджирование после прямого запроса").parse_args()
    conn = build_synth(args.seed)[0] if args.synth else open_copy(args.db)
    u = args.user
    per, _ = load_outcomes(conn, u)
    contacts = [c for c, rows in per.items() if len(rows) >= 6]
    effects, hard_share = {}, []
    for cid in contacts:
        calls = conn.execute("SELECT call_id, call_datetime FROM calls WHERE user_id=? AND contact_id=? ORDER BY call_datetime",
                             (u, cid)).fetchall()
        if len(calls) < 10:
            continue
        # хедж-доля OTHER-реплик, следующих за OWNER-репликой с запросом, по окнам 90 дн.
        windows = {}
        for c in calls:
            segs = conn.execute("SELECT speaker, text FROM transcripts WHERE call_id=? ORDER BY start_ms", (c["call_id"],)).fetchall()
            after = [segs[i + 1]["text"] for i in range(len(segs) - 1)
                     if segs[i]["speaker"] == "OWNER" and RE_REQUEST.search(segs[i]["text"] or "") and segs[i + 1]["speaker"] == "OTHER"]
            wk = date.fromisoformat(c["call_datetime"][:10]).toordinal() // 90
            windows.setdefault(wk, []).extend(after)
        rates = {wk: hedge_rate(t) for wk, t in windows.items()}
        rates = {wk: r for wk, r in rates.items() if r is not None}
        if len(rates) < 3:
            continue
        mu = sum(rates.values()) / len(rates); sd = math.sqrt(sum((r - mu) ** 2 for r in rates.values()) / len(rates)) or 1e-9
        z = {wk: (r - mu) / sd for wk, r in rates.items()}
        pairs = []
        for y, w, s, d, k in per[cid]:
            if not d:
                continue
            wk = (date.fromisoformat(d[:10]) - timedelta(days=90)).toordinal() // 90
            if wk in z:
                pairs.append((z[wk], y))
        if len(pairs) >= 4:
            # эффект: разность доли провалов при z>0.5 vs z<=0.5
            hi = [1 - y for zz, y in pairs if zz > 0.5]; lo = [1 - y for zz, y in pairs if zz <= 0.5]
            if hi and lo:
                effects[cid] = [sum(hi) / len(hi) - sum(lo) / len(lo)]
                hard_share.append(1 - sum(hi) / len(hi))  # «хедж↑ → исполнено»
    lines = [header("E-7 — хеджирование после прямого запроса", args), f"- контактов с оценкой: {len(effects)}\n"]
    if len(effects) < 10:
        lines.append("**Решение E-7: < 10 контактов → недостаточно данных, закрыт**\n")
    else:
        pt, lo, hi = cluster_bootstrap(effects, lambda xs: sum(xs) / len(xs))
        hs = sum(hard_share) / len(hard_share)
        lines.append(f"- средний эффект (провал | хедж↑ − провал | хедж↓) = {pt:+.3f} [80%: {lo:+.3f}, {hi:+.3f}]; "
                     f"доля «хедж↑ → исполнено» = {hs:.2f}\n"
                     f"**Решение E-7: {'кандидат в roadmap' if lo > 0 and hs < 0.3 else 'закрыт'}**\n")
    emit("\n".join(lines), args.out)
    if args.synth:
        print("OK")


if __name__ == "__main__":
    main()
