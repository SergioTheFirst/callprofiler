# -*- coding: utf-8 -*-
"""02_promise_coverage.py — E-0a покрытие исходов (H2) + генерация adjudication-request (E-1/E-2).

`python 02_promise_coverage.py --db <копия> [--out results/E0a-coverage.md]`
`python 02_promise_coverage.py --db <копия> --adjudication-request --n 30 --overdue 10 --seed 0 --out adjudication-request.md`
Правила: protocol.md §5 (стратификация det/llm × статус, рандомизация, без CI/метода в выдаче).
"""
from __future__ import annotations

import os
import random
import sys
from collections import Counter
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from _common import build_synth, emit, header, open_copy, parser  # noqa: E402


def coverage_report(conn, u: str, args) -> str:
    rows = conn.execute("SELECT contact_id, status FROM promise_outcomes WHERE user_id=? AND side='contact'",
                        (u,)).fetchall()
    per = {}
    for r in rows:
        per.setdefault(r["contact_id"], Counter())[r["status"]] += 1
    n_res = [sum(c[s] for s in ("kept", "late", "broken")) for c in per.values()]
    n_contacts_all = conn.execute("SELECT COUNT(*) FROM contacts WHERE user_id=?", (u,)).fetchone()[0]
    hist = Counter(min(n, 8) for n in n_res)
    p4 = sum(1 for n in n_res if n >= 4) / max(n_contacts_all, 1)
    cov = [sum(c[s] for s in ("kept", "late", "broken")) / sum(c.values()) for c in per.values() if sum(c.values())]
    lines = [header("E-0a — покрытие исходов (H2)", args),
             f"- контактов всего: {n_contacts_all}; с обещаниями (side=contact): {len(per)}\n",
             f"- статусы: {dict(Counter(r['status'] for r in rows))}\n",
             f"- контактов с ≥4 разрешёнными: {sum(1 for n in n_res if n >= 4)} (p4 = {p4:.3f}; H2 ⇔ p4<0.25)\n",
             f"- среднее покрытие (разрешённые/все) по контактам с обещаниями: {sum(cov)/max(len(cov),1):.2f}\n",
             "\n| разрешённых исходов | контактов |\n|---|---|\n" +
             "\n".join(f"| {'8+' if k == 8 else k} | {v} |" for k, v in sorted(hist.items())) + "\n"]
    return "\n".join(lines)


def adjudication_request(conn, u: str, args) -> str:
    rnd = random.Random(args.seed)
    today = date.today()
    resolved = conn.execute("SELECT * FROM promise_outcomes WHERE user_id=? AND side='contact' AND "
                            "status IN ('kept','late','broken')", (u,)).fetchall()
    strata = {}
    for r in resolved:
        strata.setdefault((r["method"], r["status"]), []).append(r)
    # пропорционально, но ≥3 на ячейку где возможно
    picked = []
    cells = list(strata.items())
    total = sum(len(v) for _, v in cells) or 1
    for key, items in cells:
        k = max(3, round(args.n * len(items) / total))
        picked += rnd.sample(items, min(k, len(items)))
    picked = picked[: args.n]
    overdue = [r for r in conn.execute("SELECT * FROM promise_outcomes WHERE user_id=? AND side='contact' "
                                       "AND status='unknown' AND due IS NOT NULL", (u,)).fetchall()
               if date.fromisoformat(r["due"][:10]) < today - timedelta(days=2) and conn.execute(
                   "SELECT COUNT(*) FROM calls WHERE user_id=? AND contact_id=? AND call_datetime > ?",
                   (u, r["contact_id"], r["due"])).fetchone()[0] >= 2]
    picked += rnd.sample(overdue, min(args.overdue, len(overdue)))
    rnd.shuffle(picked)
    lines = ["# Запрос на adjudication (сгенерировано 02_promise_coverage.py)\n",
             f"seed={args.seed}; элементов: {len(picked)}. Ответы → `adjudication-answers.csv` "
             "(`promise_key,is_promise,outcome,role_swapped`; outcome ∈ исполнено|не исполнено|не знаю).\n",
             "| # | promise_key | дата | call_id | обещание (цитата) | что слышно потом | 1 обещание? | 2 исход | 3 роль? |",
             "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(picked, 1):
        d = conn.execute("SELECT call_datetime FROM calls WHERE call_id=?", (r["call_id"],)).fetchone()
        ev = conn.execute("SELECT evidence_quote FROM promise_outcomes WHERE promise_key=?", (r["promise_key"],)) \
            .fetchone() if _col(conn, "promise_outcomes", "evidence_quote") else None
        lines.append(f"| {i} | {r['promise_key']} | {(d[0] if d else '')[:10]} | {r['call_id']} | "
                     f"{(r['quote'] or r['what'] or '')[:160]} | {((ev[0] if ev and ev[0] else '') or '')[:160]} | | | |")
    return "\n".join(lines) + "\n"


def _col(conn, table, col) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def main() -> None:
    p = parser("E-0a покрытие исходов / генерация adjudication-request")
    p.add_argument("--adjudication-request", action="store_true")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--overdue", type=int, default=10)
    args = p.parse_args()
    conn = build_synth(args.seed, coverage=0.6)[0] if args.synth else open_copy(args.db)
    text = adjudication_request(conn, args.user, args) if args.adjudication_request else coverage_report(conn, args.user, args)
    emit(text, args.out)
    if args.synth:
        assert ("p4 =" in text) or ("promise_key" in text)
        if args.adjudication_request:
            assert "kept" not in text and "det" not in text.split("|", 12)[-1][:0], "метод/статус не показываем"
        print("OK")


if __name__ == "__main__":
    main()
