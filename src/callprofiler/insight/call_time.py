# -*- coding: utf-8 -*-
"""
call_time.py — «лучшее время звонка» контакту (A6, oz5 §A6 п.1, IMMUNE-сигнал).

Чистая функция над списком звонков (call_datetime, duration_sec). Бакеты:
будни-день(9-18) / будни-вечер(18-23) / выходные(любой час 7-23 и 23-7 —
ночь побеждает) / ночь(23-7, любой день). Звонки за последние 180 дней
весят вдвое. Топ-бакет отдаётся только при доле >=0.45 И поддержке >=8
звонков — иначе None (инвариант 6: лучше промолчать, чем угадать).
"""

from __future__ import annotations

from datetime import datetime, timedelta

RECENT_WINDOW_DAYS = 180
RECENT_WEIGHT = 2.0
DEFAULT_WEIGHT = 1.0
TOP_SHARE_MIN = 0.45
SUPPORT_MIN = 8

BUCKET_PHRASES = {
    "weekday_day": "будни днём",
    "weekday_evening": "будни вечером",
    "weekend": "на выходных",
    "night": "ночью",
}


def _parse_dt(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)[:19])
    except ValueError:
        return None


def _bucket(dt: datetime) -> str:
    if dt.hour >= 23 or dt.hour < 7:
        return "night"
    if dt.weekday() >= 5:
        return "weekend"
    if dt.hour >= 18:
        return "weekday_evening"
    return "weekday_day"


def best_call_time(calls: list[dict]) -> str | None:
    """calls: [{call_datetime, duration_sec}, ...] -> фраза или None (мало данных)."""
    cutoff = datetime.now() - timedelta(days=RECENT_WINDOW_DAYS)
    weight_by_bucket: dict[str, float] = {}
    support_by_bucket: dict[str, int] = {}
    total_weight = 0.0

    for call in calls:
        dt = _parse_dt(call.get("call_datetime"))
        if dt is None:
            continue
        bucket = _bucket(dt)
        weight = RECENT_WEIGHT if dt >= cutoff else DEFAULT_WEIGHT
        weight_by_bucket[bucket] = weight_by_bucket.get(bucket, 0.0) + weight
        support_by_bucket[bucket] = support_by_bucket.get(bucket, 0) + 1
        total_weight += weight

    if total_weight <= 0:
        return None

    top_bucket = max(weight_by_bucket, key=weight_by_bucket.get)
    share = weight_by_bucket[top_bucket] / total_weight
    support = support_by_bucket[top_bucket]

    if share >= TOP_SHARE_MIN and support >= SUPPORT_MIN:
        return BUCKET_PHRASES[top_bucket]
    return None
