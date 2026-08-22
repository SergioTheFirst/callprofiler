# -*- coding: utf-8 -*-
"""07_contradictions.py — E-6: таксономия LLM-«противоречий» (4 класса) по adjudication владельца.

Требует `graph-replay` на КОПИИ (verbatim-проверенные цитаты). `--request` печатает ≤20 строк;
`--answers FILE` (csv: fact_id,cls ∈ 1..4) считает долю класса 4. Правило — decision-rules.md §E-6.
Классы: 1 reminiscence (добавленная деталь) · 2 смена позиции по новой информации · 3 ASR/роль ·
4 противоречие в обязательстве или факте.
"""
from __future__ import annotations

import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import build_synth, emit, header, open_copy, parser  # noqa: E402


def main() -> None:
    p = parser("E-6 таксономия противоречий")
    p.add_argument("--request", action="store_true")
    p.add_argument("--answers")
    args = p.parse_args()
    if args.synth:
        conn = build_synth(args.seed)[0]
        conn.execute("UPDATE events SET event_type='contradiction', fact_id='f'||id, quote='я говорил другое' WHERE id % 7 = 0")
    else:
        conn = open_copy(args.db)
    u = args.user
    facts = conn.execute("SELECT id, fact_id, call_id, contact_id, quote, payload FROM events WHERE user_id=? "
                         "AND event_type='contradiction' AND fact_id IS NOT NULL AND quote IS NOT NULL", (u,)).fetchall()
    if args.request or not args.answers:
        rnd = random.Random(args.seed)
        pick = rnd.sample(facts, min(20, len(facts)))
        text = (header("E-6 — запрос владельцу", args) +
                "Класс: 1 = добавил деталь, не противоречие · 2 = сменил позицию после новой информации · "
                "3 = ошибка распознавания/перепутаны роли · 4 = реальное противоречие в обязательстве или факте\n\n"
                "| fact_id | call_id | цитата | что «противоречит» (payload) | класс |\n|---|---|---|---|---|\n" +
                "\n".join(f"| {r['fact_id']} | {r['call_id']} | {(r['quote'] or '')[:160]} | {(r['payload'] or '')[:120]} | |" for r in pick) + "\n")
        emit(text, args.out)
        if args.synth:
            assert pick; print("OK")
        return
    with open(args.answers, encoding="utf-8") as f:
        ans = [row for row in csv.DictReader(f)]
    share4 = sum(1 for a in ans if a.get("cls", "").strip() == "4") / max(len(ans), 1)
    emit(header("E-6 — результат", args) + f"- n={len(ans)}; доля класса 4 = {share4:.2f}\n"
         f"**Решение E-6: {'contradiction остаётся как E2-факт; R-29 исход A' if share4 >= 0.6 else 'R-29 исход B (удалить тип)'}**\n", args.out)


if __name__ == "__main__":
    main()
