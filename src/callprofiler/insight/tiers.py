# -*- coding: utf-8 -*-
"""
tiers.py — F8: контакт живёт в тире core|active|warm|cold|archive по формуле
забывания Эббингауза. Касание (новый звонок) поднимает, тишина опускает.
Тир = приоритет ночных LLM-очередей, сортировка списков, сырьё для F5.
"""
from __future__ import annotations

import math
import sqlite3
from datetime import date

TAU_DAYS = 30.0

TIER_ORDER = ("core", "active", "warm", "cold", "archive")

# CASE-выражение для ORDER BY в SQL-потребителях (bulk/enricher.py и т.п.).
# Неизвестный/ещё не вычисленный тир (contact_tiers пуста или строки нет) —
# нейтральный приоритет 'active', НЕ худший: иначе до первого tiers-recompute
# все звонки без вычисленного тира ушли бы в конец очереди.
TIER_RANK_SQL_CASE = (
    "CASE ct.tier "
    "WHEN 'core' THEN 0 WHEN 'active' THEN 1 WHEN 'warm' THEN 2 "
    "WHEN 'cold' THEN 3 WHEN 'archive' THEN 4 ELSE 1 END"
)


def _percentile(data: list[float], p: int) -> float:
    """Линейная интерполяция — тот же алгоритм, что risk_calibration.py/BSCalibrator."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    rank = (p / 100.0) * (n - 1)
    lower_idx = int(rank)
    upper_idx = min(lower_idx + 1, n - 1)
    fraction = rank - lower_idx
    return sorted_data[lower_idx] + fraction * (sorted_data[upper_idx] - sorted_data[lower_idx])


def compute_score(call_count: int, days_since_last_call: float, total_talk_minutes: float) -> float:
    """Чистая функция — Эббингауз-затухание. call_count=0 -> 0.0 (архив по построению)."""
    if call_count <= 0:
        return 0.0
    strength = 1.0 + math.log1p(call_count)
    retention = math.exp(-days_since_last_call / (TAU_DAYS * strength))
    return retention * math.log1p(max(total_talk_minutes, 0.0))


def classify_tier(score: float, thresholds: dict[str, float]) -> str:
    """Перцентильные пороги (значения score, не ранги) — top 5%→core, до 25%→active,
    до 60%→warm, до 90%→cold, хвост→archive."""
    if score <= 0:
        return "archive"
    if score >= thresholds["p95"]:
        return "core"
    if score >= thresholds["p75"]:
        return "active"
    if score >= thresholds["p40"]:
        return "warm"
    if score >= thresholds["p10"]:
        return "cold"
    return "archive"


def apply_tiers_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS contact_tiers (
            user_id     TEXT NOT NULL,
            contact_id  INTEGER NOT NULL,
            tier        TEXT NOT NULL CHECK(tier IN ('core','active','warm','cold','archive')),
            score       REAL NOT NULL,
            prev_tier   TEXT,
            computed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, contact_id)
        )"""
    )
    conn.commit()


def _contact_aggregates(conn: sqlite3.Connection, user_id: str, today: date) -> list[dict]:
    """Один SELECT-агрегат по calls на контакт (LEFT JOIN — контакты без звонков
    тоже попадают, call_count=0 -> archive). call_type IS NULL исключает
    voicenote-заметки (F4) — это не отношение с контактом."""
    rows = conn.execute(
        """SELECT ct.contact_id AS contact_id,
                  COUNT(c.call_id) AS call_count,
                  MAX(COALESCE(c.call_datetime, c.created_at)) AS last_call,
                  COALESCE(SUM(c.duration_sec), 0) AS total_sec
             FROM contacts ct
             LEFT JOIN calls c
               ON c.contact_id = ct.contact_id AND c.user_id = ct.user_id
              AND c.status = 'done' AND c.call_type IS NULL
            WHERE ct.user_id = ?
            GROUP BY ct.contact_id""",
        (user_id,),
    ).fetchall()

    out = []
    for r in rows:
        call_count = int(r["call_count"] or 0)
        if call_count <= 0 or not r["last_call"]:
            days_since = float("inf")
        else:
            last_date = date.fromisoformat(str(r["last_call"])[:10])
            days_since = max(0, (today - last_date).days)
        out.append({
            "contact_id": r["contact_id"],
            "call_count": call_count,
            "days_since_last_call": days_since,
            "total_talk_minutes": (r["total_sec"] or 0) / 60.0,
        })
    return out


def recompute_tiers(conn: sqlite3.Connection, user_id: str, today: date | None = None) -> dict:
    """UPSERT contact_tiers для всех контактов юзера. Возвращает статистику +
    список переходов (prev_tier != tier), для F5/C3."""
    apply_tiers_schema(conn)
    today = today or date.today()

    aggregates = _contact_aggregates(conn, user_id, today)
    for a in aggregates:
        a["score"] = compute_score(a["call_count"], a["days_since_last_call"], a["total_talk_minutes"])

    nonzero_scores = [a["score"] for a in aggregates if a["score"] > 0]
    thresholds = {
        "p95": _percentile(nonzero_scores, 95),
        "p75": _percentile(nonzero_scores, 75),
        "p40": _percentile(nonzero_scores, 40),
        "p10": _percentile(nonzero_scores, 10),
    }

    old_tiers = {
        r["contact_id"]: r["tier"]
        for r in conn.execute(
            "SELECT contact_id, tier FROM contact_tiers WHERE user_id = ?", (user_id,)
        ).fetchall()
    }

    transitions = []
    counts = {t: 0 for t in TIER_ORDER}
    for a in aggregates:
        tier = classify_tier(a["score"], thresholds)
        counts[tier] += 1
        conn.execute(
            """INSERT INTO contact_tiers(user_id, contact_id, tier, score, prev_tier, computed_at)
               VALUES (?,?,?,?,NULL,CURRENT_TIMESTAMP)
               ON CONFLICT(user_id, contact_id) DO UPDATE SET
                   prev_tier = contact_tiers.tier,
                   tier = excluded.tier,
                   score = excluded.score,
                   computed_at = excluded.computed_at
               WHERE contact_tiers.user_id = excluded.user_id""",
            (user_id, a["contact_id"], tier, a["score"]),
        )
        old = old_tiers.get(a["contact_id"])
        if old is not None and old != tier:
            transitions.append({"contact_id": a["contact_id"], "from": old, "to": tier})
    conn.commit()

    return {"ok": True, "n_contacts": len(aggregates), "counts": counts, "transitions": transitions}


def get_tier(conn: sqlite3.Connection, user_id: str, contact_id: int) -> str | None:
    row = conn.execute(
        "SELECT tier FROM contact_tiers WHERE user_id = ? AND contact_id = ?",
        (user_id, contact_id),
    ).fetchone()
    return row["tier"] if row else None
