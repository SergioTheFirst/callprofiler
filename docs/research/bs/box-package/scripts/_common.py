# -*- coding: utf-8 -*-
"""_common.py — общие помощники box-package скриптов: гард «только копия», synth-БД, Beta-математика.

Ни одна функция здесь не пишет в БД, кроме synth-построения временного файла/`:memory:`.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import random
import sqlite3
import sys
from datetime import date, timedelta

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

LIVE_MARKERS = (os.path.join("calls", "data"),)
# описательные фразы (прошедшее время, «из известных») — hostile review OBJ-4/OBJ-6
PHRASES = [(0.8, "из известных обещаний выполнял почти все"), (0.6, "выполнял большинство"),
           (0.4, "выполнял около половины"), (0.2, "выполнял меньшинство"), (0.0, "почти не выполнял")]


def parser(desc: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=desc)
    p.add_argument("--db", help="путь к КОПИИ БД (C:\\calls\\research\\...)")
    p.add_argument("--synth", action="store_true", help="построить мини-synth БД и прогнать на ней")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--user", default="me")
    p.add_argument("--out", default=None, help="markdown-отчёт (по умолчанию stdout)")
    return p


def open_copy(path: str) -> sqlite3.Connection:
    norm = os.path.normpath(os.path.abspath(path)).lower()
    if any(m in norm for m in LIVE_MARKERS):
        raise SystemExit(f"ОТКАЗ: {path} выглядит как живая БД (C:\\calls\\data). Работаем только с копией.")
    if not os.path.exists(path):
        raise SystemExit(f"нет файла: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def db_fingerprint(path: str | None) -> str:
    if not path or not os.path.exists(path):
        return "synth"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
    return h.hexdigest()[:12]


def header(name: str, args, extra: str = "") -> str:
    return (f"# {name}\n\n- db: `{args.db or 'synth'}` sha256[:12]=`{db_fingerprint(args.db)}`\n"
            f"- seed: {args.seed} · user: {args.user} · формула: cr-v1 {extra}\n\n")


def emit(text: str, out: str | None) -> None:
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"записано: {out}")
    else:
        print(text)


# ---------------------------------------------------------------- Beta math (numpy-free, сетка)
GRID = 20001


def _beta_grid(a: float, b: float):
    ln_norm = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    xs = [min(max(i / (GRID - 1), 1e-9), 1 - 1e-9) for i in range(GRID)]
    ys = [math.exp(ln_norm + (a - 1) * math.log(x) + (b - 1) * math.log(1 - x)) for x in xs]
    return xs, ys


def beta_cdf_points(a: float, b: float):
    xs, ys = _beta_grid(a, b)
    cdf, acc = [0.0], 0.0
    for i in range(1, GRID):
        acc += 0.5 * (ys[i] + ys[i - 1]) * (xs[i] - xs[i - 1])
        cdf.append(acc)
    return xs, cdf


def beta_quantile(a: float, b: float, q: float) -> float:
    xs, cdf = beta_cdf_points(a, b)
    for x, c in zip(xs, cdf):
        if c >= q:
            return x
    return 1.0


def ci_window(a: float, b: float, half: float = 0.1) -> tuple[int, float]:
    m = beta_quantile(a, b, 0.5)
    lo = min(max(m - half, 0.0), 1.0 - 2 * half)
    xs, cdf = beta_cdf_points(a, b)
    def at(x):
        i = min(int(x * (GRID - 1)), GRID - 1)
        return cdf[i]
    mass = at(lo + 2 * half) - at(lo)
    return max(1, min(100, round(100 * mass))), m


def phrase(m: float) -> str:
    return next(p for cut, p in PHRASES if m >= cut)


def tier(n_eff: float, cuts=(2, 4, 8)) -> str:
    if n_eff <= 0:
        return "no_data"
    if n_eff < cuts[0]:
        return "insufficient"
    if n_eff < cuts[1]:
        return "limited"
    if n_eff < cuts[2]:
        return "moderate"
    return "substantial"


def fit_prior(rates: list[float]) -> tuple[float, float]:
    if len(rates) < 10:
        return 1.0, 1.0
    m = sum(rates) / len(rates)
    v = sum((r - m) ** 2 for r in rates) / (len(rates) - 1)
    if v <= 0 or m <= 0 or m >= 1:
        return 1.0, 1.0
    k = m * (1 - m) / v - 1
    if k <= 0:
        return 1.0, 1.0
    return m * k, (1 - m) * k


def posterior(outcomes: list[tuple[int, float]], a0: float, b0: float) -> tuple[float, float, float]:
    """outcomes: [(y, w)] → (alpha, beta, n_eff)."""
    a = a0 + sum(w * y for y, w in outcomes)
    b = b0 + sum(w * (1 - y) for y, w in outcomes)
    return a, b, sum(w for _, w in outcomes)


def cluster_bootstrap(groups: dict, stat, B: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """groups: key → список элементов; stat(list_of_elements) → float. Возвращает (точка, q10, q90)."""
    rnd = random.Random(seed)
    keys = list(groups)
    point = stat([e for k in keys for e in groups[k]])
    vals = []
    for _ in range(B):
        sample = [e for k in (rnd.choice(keys) for _ in keys) for e in groups[k]]
        try:
            vals.append(stat(sample))
        except ZeroDivisionError:
            continue
    vals.sort()
    if not vals:
        return point, float("nan"), float("nan")
    return point, vals[int(0.1 * len(vals))], vals[min(len(vals) - 1, int(0.9 * len(vals)))]


# ---------------------------------------------------------------- synth
def build_synth(seed: int = 0, n_contacts: int = 60, user_id: str = "me", mnar: float = 0.0,
                q_det: float = 1.0, coverage: float = 1.0, drift: float = 0.0) -> tuple[sqlite3.Connection, dict]:
    """Мини-БД с таблицами, которые читают скрипты (не полная schema.sql). Возвращает (conn, truth).
    truth: contact_id → p_true. Synth — механизм, не evidence."""
    rnd = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE users(user_id TEXT PRIMARY KEY);
    CREATE TABLE contacts(contact_id INTEGER PRIMARY KEY, user_id TEXT, display_name TEXT);
    CREATE TABLE calls(call_id INTEGER PRIMARY KEY, user_id TEXT, contact_id INTEGER, call_datetime TEXT,
                       duration_sec INTEGER, role_fragile INTEGER, status TEXT);
    CREATE TABLE transcripts(call_id INTEGER, speaker TEXT, text TEXT, start_ms INTEGER, end_ms INTEGER);
    CREATE TABLE events(id INTEGER PRIMARY KEY, user_id TEXT, contact_id INTEGER, call_id INTEGER,
                        event_type TEXT, who TEXT, payload TEXT, source_quote TEXT, confidence REAL,
                        status TEXT, entity_id INTEGER, fact_id TEXT, quote TEXT);
    CREATE TABLE entity_metrics(entity_id INTEGER PRIMARY KEY, user_id TEXT, total_calls INTEGER,
                        total_promises INTEGER, broken_promises INTEGER, contradictions INTEGER,
                        vagueness_count INTEGER, blame_shift_count INTEGER, emotional_spikes INTEGER,
                        bs_index REAL, bs_formula_version TEXT);
    CREATE TABLE promise_outcomes(user_id TEXT, promise_key TEXT PRIMARY KEY, contact_id INTEGER,
                        call_id INTEGER, side TEXT, what TEXT, due TEXT, status TEXT, days_late INTEGER,
                        quote TEXT, evidence_date TEXT, confidence REAL, method TEXT);
    CREATE TABLE outcome_feedback(user_id TEXT, promise_key TEXT, verdict TEXT, source TEXT,
                        created_at TEXT, PRIMARY KEY(user_id, promise_key));
    """)
    conn.execute("INSERT INTO users VALUES (?)", (user_id,))
    truth, call_id, pk = {"p": {}, "y": {}}, 1, 1
    t0 = date(2024, 1, 1)
    for cid in range(1, n_contacts + 1):
        p_true = rnd.betavariate(2, 1.5)
        truth["p"][cid] = p_true
        conn.execute("INSERT INTO contacts VALUES (?,?,?)", (cid, user_id, f"c{cid}"))
        n_prom = rnd.choice([0, 0, 1, 2, 3, 5, 8, 12, 20])
        unk_share = rnd.choice([0.0, 0.05, 0.1, 0.2, 0.35, 0.5])
        for j in range(max(n_prom, 1) + 3):
            d = t0 + timedelta(days=rnd.randint(0, 720))
            conn.execute("INSERT INTO calls VALUES (?,?,?,?,?,?,?)",
                         (call_id, user_id, cid, d.isoformat() + " 12:00:00", rnd.randint(60, 900),
                          int(unk_share > 0.3), "done"))
            for s in range(10):
                spk = "UNKNOWN" if rnd.random() < unk_share else rnd.choice(["OWNER", "OTHER"])
                conn.execute("INSERT INTO transcripts VALUES (?,?,?,?,?)",
                             (call_id, spk, f"реплика {s}", s * 1000, s * 1000 + 900))
            if j < n_prom:
                # дрейф: после середины периода доля меняется на drift
                p = min(max(p_true + (drift if d > t0 + timedelta(days=360) else 0.0), 0.01), 0.99)
                y = 1 if rnd.random() < p else 0
                truth["y"][f"k{pk:06d}"] = y
                label = y if rnd.random() < q_det else 1 - y
                status = ("kept" if label else "broken")
                if rnd.random() > coverage * (1 + (mnar if y == 0 else 0)):
                    status = "unknown"
                due = (d + timedelta(days=rnd.randint(3, 30))).isoformat()
                ev = (d + timedelta(days=rnd.randint(5, 100))).isoformat() if status != "unknown" else None
                conn.execute("INSERT INTO promise_outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (user_id, f"k{pk:06d}", cid, call_id, "contact", f"обещание {pk} точно сделаю",
                              due, status, 0, f"я точно сделаю {pk}", ev, 0.7, "det"))
                conn.execute("INSERT INTO events(user_id,contact_id,call_id,event_type,who,payload,"
                             "source_quote,confidence,status,entity_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (user_id, cid, call_id, "promise", "UNKNOWN", f"обещание {pk}", "q", 0.8,
                              "open", cid))
                pk += 1
            call_id += 1
        conn.execute("INSERT INTO entity_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, user_id, max(n_prom, 1), n_prom, 0, rnd.choice([0, 0, 1, 2]), 0, 0, 0,
                      0.0, "v1_linear"))
    conn.execute("UPDATE entity_metrics SET bs_index = 20.0*MIN(contradictions*1.0/MAX(total_calls,1),1)")
    conn.commit()
    return conn, truth


def load_outcomes(conn, user_id: str, q_det: float = 0.7, q_llm: float = 0.6, half_life=None,
                  role_mode: str = "continuous", ref_date: date | None = None):
    """→ {contact_id: [(y, w, status, evidence_date, promise_key)]}, unknown-счётчики отдельно."""
    ref_date = ref_date or date.today()
    unk = {r["call_id"]: r["u"] for r in conn.execute(
        "SELECT call_id, SUM(speaker='UNKNOWN')*1.0/COUNT(*) AS u FROM transcripts GROUP BY call_id")}
    fb = {r["promise_key"]: r["verdict"] for r in conn.execute(
        "SELECT promise_key, verdict FROM outcome_feedback WHERE user_id=?", (user_id,))} \
        if _has(conn, "outcome_feedback") else {}
    per, unknown = {}, {}
    for r in conn.execute("SELECT * FROM promise_outcomes WHERE user_id=? AND side='contact'", (user_id,)):
        cid = r["contact_id"]
        status, w_label = r["status"], (q_det if r["method"] == "det" else q_llm)
        if r["promise_key"] in fb:
            status, w_label = {"kept": "kept", "broken": "broken", "unknown": "unknown"}[fb[r["promise_key"]]], 1.0
        if status == "unknown":
            unknown.setdefault(cid, []).append(r)
            continue
        y = 1 if status in ("kept", "late") else 0
        w_role = 1.0 - unk.get(r["call_id"], 0.0) if role_mode == "continuous" else 1.0
        w_time = 1.0
        if half_life and r["evidence_date"]:
            age = (ref_date - date.fromisoformat(r["evidence_date"][:10])).days
            w_time = 0.5 ** (max(age, 0) / half_life)
        per.setdefault(cid, []).append((y, w_label * w_role * w_time, status, r["evidence_date"], r["promise_key"]))
    return per, unknown


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def contact_estimates(per: dict, a0: float, b0: float) -> dict:
    out = {}
    for cid, rows in per.items():
        a, b, n_eff = posterior([(y, w) for y, w, *_ in rows], a0, b0)
        ci, m = ci_window(a, b)
        out[cid] = dict(alpha=a, beta=b, n_eff=n_eff, ci=ci, median=m, phrase=phrase(m), tier=tier(n_eff),
                        mean=a / (a + b))
    return out
