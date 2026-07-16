# -*- coding: utf-8 -*-
"""
mirror.py — A3: «Зеркало» владельца (self-dossier: обещания/риск-тренд/
концентрация общения/регистр речи). Read-only агрегаты поверх уже
имеющихся данных (A1 леджер, analyses, calls, transcripts) — ничего
нового не извлекается.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import numpy as np

from callprofiler.deliver.digest import open_items, overdue_items
from callprofiler.insight.features.formality import compute_formality

RISK_TREND_SLOPE_THRESHOLD = 1.0
RISK_TREND_WINDOW_DAYS = 365
DEPENDENCY_TOP_N = 3
DEPENDENCY_SHARE_THRESHOLD = 0.6
DEPENDENCY_WINDOW_DAYS = 180
REGISTER_MIN_OWNER_TOKENS = 40
REGISTER_TOP_N = 3


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except ValueError:
        return None


def _promises_block(conn, user_id: str, today: str | None = None) -> dict:
    overdue = [i for i in overdue_items(conn, user_id, today) if i["side"] == "owner"]
    upcoming = [i for i in open_items(conn, user_id, today) if i["side"] == "owner"]
    open_n = len(overdue) + len(upcoming)
    overdue_n = len(overdue)
    if open_n == 0:
        phrase = "за вами долгов нет"
    else:
        phrase = f"открытых обязательств: {open_n}"
        if overdue_n:
            phrase += f" (из них просрочено: {overdue_n})"
    return {"open_n": open_n, "overdue_n": overdue_n, "phrase": phrase}


def _risk_trend_block(conn, user_id: str, today: str | None = None) -> dict:
    ref = _parse_date(today) or date.today()
    start = ref - timedelta(days=RISK_TREND_WINDOW_DAYS)
    rows = conn.execute(
        """SELECT strftime('%Y-%m', c.call_datetime) AS ym, AVG(a.risk_score) AS avg_risk
             FROM analyses a JOIN calls c ON c.call_id = a.call_id
            WHERE c.user_id = ? AND c.call_datetime >= ? AND a.risk_score IS NOT NULL
            GROUP BY ym ORDER BY ym""",
        (user_id, start.isoformat()),
    ).fetchall()
    months = [r["ym"] for r in rows]
    values = [r["avg_risk"] for r in rows]

    if len(values) < 2:
        return {"months": months, "values": values, "slope": None, "phrase": "недостаточно данных"}

    slope = float(np.polyfit(np.arange(len(values)), values, 1)[0])
    if slope > RISK_TREND_SLOPE_THRESHOLD:
        phrase = "фон ваших разговоров становится напряжённее"
    elif slope < -RISK_TREND_SLOPE_THRESHOLD:
        phrase = "фон ваших разговоров становится спокойнее"
    else:
        phrase = "ровный"
    return {"months": months, "values": values, "slope": round(slope, 3), "phrase": phrase}


def _dependency_block(conn, user_id: str, today: str | None = None) -> dict:
    ref = _parse_date(today) or date.today()
    start = ref - timedelta(days=DEPENDENCY_WINDOW_DAYS)
    rows = conn.execute(
        """SELECT c.contact_id AS contact_id,
                  COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164, '?') AS name,
                  SUM(c.duration_sec) AS total_sec
             FROM calls c
             LEFT JOIN contacts ct ON ct.contact_id = c.contact_id AND ct.user_id = c.user_id
            WHERE c.user_id = ? AND c.call_datetime >= ? AND c.duration_sec IS NOT NULL
              AND c.contact_id IS NOT NULL
            GROUP BY c.contact_id
            ORDER BY total_sec DESC""",
        (user_id, start.isoformat()),
    ).fetchall()

    total = sum(r["total_sec"] for r in rows) if rows else 0
    if not rows or not total:
        return {"share": None, "top": [], "phrase": "недостаточно данных"}

    top = rows[:DEPENDENCY_TOP_N]
    share = sum(r["total_sec"] for r in top) / total
    names = [r["name"] for r in top]

    if share > DEPENDENCY_SHARE_THRESHOLD:
        phrase = f"общение сконцентрировано на {len(top)} людях: " + ", ".join(names)
    else:
        phrase = "общение распределено без явной концентрации"
    return {"share": round(share, 3), "top": names, "phrase": phrase}


def _register_block(conn, user_id: str) -> dict:
    contact_ids = [r[0] for r in conn.execute(
        "SELECT contact_id FROM contacts WHERE user_id = ?", (user_id,)
    ).fetchall()]

    scored = []
    for cid in contact_ids:
        seg_rows = conn.execute(
            """SELECT t.speaker, t.text FROM transcripts t
                 JOIN calls c ON c.call_id = t.call_id
                WHERE c.user_id = ? AND c.contact_id = ?
                ORDER BY t.call_id, t.start_ms""",
            (user_id, cid),
        ).fetchall()
        segments = [dict(r) for r in seg_rows]
        feats = compute_formality(segments, side="OWNER")
        f = feats.get("vy_ratio")
        if f is None or f.support_n < REGISTER_MIN_OWNER_TOKENS:
            continue
        name_row = conn.execute(
            "SELECT COALESCE(display_name, guessed_name, phone_e164, '?') AS name "
            "FROM contacts WHERE contact_id = ?",
            (cid,),
        ).fetchone()
        scored.append({"contact_id": cid, "name": name_row["name"],
                       "vy_ratio": f.value, "support_n": f.support_n})

    if not scored:
        return {"formal_top": [], "informal_top": [], "phrase": "недостаточно данных"}

    by_formal_desc = sorted(scored, key=lambda s: s["vy_ratio"], reverse=True)
    formal_top = [s["name"] for s in by_formal_desc[:REGISTER_TOP_N]]
    informal_top = [s["name"] for s in list(reversed(by_formal_desc))[:REGISTER_TOP_N]]
    phrase = ("подчёркнуто на «вы» с: " + ", ".join(formal_top) +
              "; свободнее всего с: " + ", ".join(informal_top))
    return {"formal_top": formal_top, "informal_top": informal_top, "phrase": phrase}


def build_mirror(conn, user_id: str, today: str | None = None) -> dict:
    """Собрать досье владельца — 4 блока, каждый с числами-основаниями + фразой."""
    return {
        "promises": _promises_block(conn, user_id, today),
        "risk_trend": _risk_trend_block(conn, user_id, today),
        "dependency": _dependency_block(conn, user_id, today),
        "register": _register_block(conn, user_id),
    }


def save_mirror(conn, user_id: str, payload: dict) -> None:
    """UPSERT owner_mirror. PK = user_id (единственная строка на юзера)."""
    conn.execute(
        "INSERT INTO owner_mirror(user_id, payload, computed_at) VALUES (?,?,CURRENT_TIMESTAMP) "
        "ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload, "
        "computed_at = CURRENT_TIMESTAMP",
        (user_id, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
