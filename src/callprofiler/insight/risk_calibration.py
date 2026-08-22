# -*- coding: utf-8 -*-
"""
risk_calibration.py — A4 (ozalupennieStrategic5.md §A4): перцентильные пороги
risk_score, отдельно от BS-index.

Bug fixed: `card_generator._risk_emoji_with_calibration` применял
`graph.calibration.BSCalibrator` (калиброван на entity_metrics.bs_index,
graph-health garant) к contact_summaries.global_risk — другая метрика,
другое распределение. `bs_thresholds` НЕ трогается (graph-health от неё
зависит) — risk получает СВОЮ таблицу `risk_thresholds`.
"""

from __future__ import annotations

import sqlite3

_MIN_ANALYSES = 50


def apply_risk_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — CREATE TABLE IF NOT EXISTS."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS risk_thresholds (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT NOT NULL,
            green_max      REAL NOT NULL,
            yellow_max     REAL NOT NULL,
            analysis_count INTEGER DEFAULT 0,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_risk_thresholds_user ON risk_thresholds(user_id, created_at)"
    )
    conn.commit()


def _percentile(data: list[float], p: int) -> float:
    """Линейная интерполяция — тот же алгоритм, что graph/calibration.py::BSCalibrator."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    rank = (p / 100.0) * (n - 1)
    lower_idx = int(rank)
    upper_idx = min(lower_idx + 1, n - 1)
    fraction = rank - lower_idx
    return sorted_data[lower_idx] + fraction * (sorted_data[upper_idx] - sorted_data[lower_idx])


def calibrate_risk(conn: sqlite3.Connection, user_id: str, min_analyses: int = _MIN_ANALYSES) -> dict:
    """Собрать risk_score юзера, посчитать p50/p85, сохранить строку в risk_thresholds.

    Исключает `feedback='inaccurate'` (юзер пометил анализ неверным, A5) и
    `risk_score=0` (заглушка коротких звонков — pipeline.md, не сигнал риска).
    < min_analyses значений → {"ok": False, "reason": "too_few"}, ничего не пишет.
    """
    apply_risk_schema(conn)
    rows = conn.execute(
        """SELECT a.risk_score FROM analyses a
             JOIN calls c ON c.call_id = a.call_id
            WHERE c.user_id = ? AND COALESCE(a.feedback, '') != 'inaccurate'
              AND a.risk_score > 0""",
        (user_id,),
    ).fetchall()
    scores = [float(r["risk_score"]) for r in rows]

    if len(scores) < min_analyses:
        return {"ok": False, "reason": "too_few", "count": len(scores)}

    green_max = _percentile(scores, 50)
    yellow_max = _percentile(scores, 85)

    conn.execute(
        """INSERT INTO risk_thresholds(user_id, green_max, yellow_max, analysis_count)
           VALUES (?,?,?,?)""",
        (user_id, green_max, yellow_max, len(scores)),
    )
    conn.commit()
    return {"ok": True, "count": len(scores), "green_max": green_max, "yellow_max": yellow_max}


def get_latest_risk_thresholds(conn: sqlite3.Connection, user_id: str) -> dict | None:
    """None если таблицы ещё нет (не откалибровано ни разу) или нет строки юзера."""
    try:
        row = conn.execute(
            "SELECT * FROM risk_thresholds WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(row) if row else None


RISK_POLICY_VERSION = "risk-v1"
FALLBACK_GREEN_MAX = 30
FALLBACK_YELLOW_MAX = 70


def risk_band(score: float | None, thresholds: dict | None = None) -> str:
    """Classify risk score into band: 'low' | 'mid' | 'high' | 'none'.

    Args:
        score: Risk score (0-100) or None
        thresholds: dict with 'green_max' and 'yellow_max' from get_latest_risk_thresholds,
                   or None to use fallback (30/70)

    Returns:
        'low' (<green_max), 'mid' (>=green_max and <yellow_max), 'high' (>=yellow_max), or 'none' (score is None)
    """
    if score is None:
        return "none"

    if thresholds is None:
        green_max = FALLBACK_GREEN_MAX
        yellow_max = FALLBACK_YELLOW_MAX
    else:
        green_max = thresholds.get("green_max", FALLBACK_GREEN_MAX)
        yellow_max = thresholds.get("yellow_max", FALLBACK_YELLOW_MAX)

    # Контракт прежнего risk_emoji (tests/insight/test_risk_calibration.py): 🟢 <green_max, 🟡 ≥green_max, 🔴 ≥yellow_max
    if score < green_max:
        return "low"
    if score < yellow_max:
        return "mid"
    return "high"


def risk_emoji(risk: float, thresholds: dict | None) -> str:
    """🟢/🟡/🔴. thresholds=None → дефолт 30/70 (прежнее поведение)."""
    band = risk_band(risk, thresholds)
    if band == "low":
        return "🟢"
    if band == "mid":
        return "🟡"
    if band == "high":
        return "🔴"
    return "⚪"  # none
