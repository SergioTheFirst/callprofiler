"""Dormancy alerts for valuable ties (C3, ozalupennieStrategic5.md).

Value gate: contact had >=1 calendar year with >=26 calls, OR total call
duration sits in this user's top quartile. Dormancy gate: days since last
call exceeds the contact's OWN rhythm (3x median gap), not a global cutoff.
"""
from __future__ import annotations

import statistics
from datetime import date

from .features.base import parse_dt
from .tiers import _percentile

MIN_YEARLY_CALLS = 26
DORMANCY_FLOOR_DAYS = 60
DORMANCY_GAP_MULTIPLIER = 3


def _to_date(raw):
    dt = parse_dt(raw)
    return dt.date() if dt else None


def dormant_valuable(conn, user_id: str, today: date | None = None, top: int = 5) -> list[dict]:
    """До `top` контактов: раньше ценные, сейчас затихшие по СВОЕМУ ритму.

    Returns:
        [{contact_id, name, last_date, why}], отсортировано по (объём звонков
        убыв., days_since_last убыв.).
    """
    today = today or date.today()
    rows = conn.execute(
        """SELECT c.contact_id, c.call_datetime, c.duration_sec,
                  COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164, '?') AS name
             FROM calls c JOIN contacts ct ON ct.contact_id = c.contact_id
            WHERE c.user_id = ? AND c.call_datetime IS NOT NULL
              AND c.status = 'done' AND c.call_type IS NULL
            ORDER BY c.contact_id, c.call_datetime""",
        (user_id,),
    ).fetchall()

    by_contact: dict[int, dict] = {}
    for r in rows:
        d = _to_date(r["call_datetime"])
        if d is None:
            continue
        entry = by_contact.setdefault(r["contact_id"], {"name": r["name"], "dates": [], "duration": 0.0})
        entry["dates"].append(d)
        entry["duration"] += r["duration_sec"] or 0

    if not by_contact:
        return []

    duration_p75 = _percentile([e["duration"] for e in by_contact.values()], 75)

    candidates = []
    for cid, e in by_contact.items():
        dates = sorted(e["dates"])
        if len(dates) < 2:
            continue

        year_counts: dict[int, int] = {}
        for d in dates:
            year_counts[d.year] = year_counts.get(d.year, 0) + 1
        has_weekly_year = max(year_counts.values()) >= MIN_YEARLY_CALLS
        is_top_duration = duration_p75 > 0 and e["duration"] >= duration_p75
        if not (has_weekly_year or is_top_duration):
            continue

        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        median_gap = statistics.median(gaps) if gaps else 0.0
        days_since_last = (today - dates[-1]).days
        threshold = max(DORMANCY_FLOOR_DAYS, DORMANCY_GAP_MULTIPLIER * median_gap)
        if days_since_last <= threshold:
            continue

        why = ("раньше вы говорили почти каждую неделю" if has_weekly_year
               else "один из самых длинных собеседников")
        candidates.append({
            "contact_id": cid, "name": e["name"], "last_date": dates[-1].isoformat(),
            "why": why, "_call_count": len(dates), "_days_since": days_since_last,
        })

    candidates.sort(key=lambda c: (-c["_call_count"], -c["_days_since"]))
    for c in candidates:
        del c["_call_count"]
        del c["_days_since"]
    return candidates[:top]
