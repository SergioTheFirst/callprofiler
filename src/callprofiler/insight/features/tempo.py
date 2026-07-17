"""Tempo/rhythm features from transcript timestamps (B1, ozalupennieStrategic5.md).

Needs start_ms/end_ms/call_id on segments (feature_store.py SELECT widened for B1) —
older/degraded rows without timestamps simply omit these features (router tolerates
missing keys), никаких выдуманных значений.
"""
import statistics

from .base import Feature, Tier

_MIN_SEGMENT_MS = 500          # короче — шум ASR-нарезки, не реальная реплика
_MIN_GAP_MS = 0                # gap <= 0 -> перебивание/overlap, не пауза
_MAX_GAP_MS = 15000            # gap >= 15s -> разрыв записи, не пауза на обдумывание
_MIN_OTHER_SEGMENTS_FOR_ACCEL = 6


def _cps(segs: list[dict]) -> float | None:
    """Знаков/сек по сегментам с dur >= 500ms; None если считать не по чему."""
    chars, secs = 0, 0.0
    for s in segs:
        start, end = s.get("start_ms"), s.get("end_ms")
        if start is None or end is None:
            continue
        dur_ms = end - start
        if dur_ms < _MIN_SEGMENT_MS:
            continue
        chars += len(s.get("text") or "")
        secs += dur_ms / 1000.0
    return chars / secs if secs > 0 else None


def _reply_latencies(segments: list[dict]) -> list[float]:
    """gap = other.start_ms - owner.end_ms для соседних пар OWNER->OTHER одного call_id."""
    gaps = []
    for a, b in zip(segments, segments[1:]):
        if a.get("call_id") != b.get("call_id"):
            continue
        if a.get("speaker") != "OWNER" or b.get("speaker") != "OTHER":
            continue
        a_end, b_start = a.get("end_ms"), b.get("start_ms")
        if a_end is None or b_start is None:
            continue
        gap = b_start - a_end
        if _MIN_GAP_MS < gap < _MAX_GAP_MS:
            gaps.append(gap)
    return gaps


def _tempo_accel_ratios(segments: list[dict]) -> list[float]:
    """Per-call отношение cps(последняя треть OTHER-сегментов)/cps(первая треть)."""
    by_call: dict = {}
    for s in segments:
        if s.get("speaker") != "OTHER":
            continue
        by_call.setdefault(s.get("call_id"), []).append(s)

    ratios = []
    for segs in by_call.values():
        n = len(segs)
        if n < _MIN_OTHER_SEGMENTS_FOR_ACCEL:
            continue
        third = n // 3
        cps_first = _cps(segs[:third])
        cps_last = _cps(segs[-third:])
        if cps_first and cps_last and cps_first > 0:
            ratios.append(cps_last / cps_first)
    return ratios


def compute_tempo(segments: list[dict], reference_now=None) -> dict[str, Feature]:
    """Темп/ритм речи контакта из таймстампов сегментов.

    Args:
        segments: list[{"call_id","speaker","text","start_ms","end_ms"}], упорядочены
            по (call_id, start_ms) — контракт feature_store.build_contact_features.
        reference_now: не используется.

    Returns:
        {tempo_cps?, reply_latency_ms?, tempo_accel?: Feature} — только те, для
        которых нашлось сырьё (нет end_ms/пусто -> ключ не эмитится).
    """
    out: dict[str, Feature] = {}

    other_valid = [
        s for s in segments
        if s.get("speaker") == "OTHER" and s.get("start_ms") is not None
        and s.get("end_ms") is not None and (s["end_ms"] - s["start_ms"]) >= _MIN_SEGMENT_MS
    ]
    if other_valid:
        cps = _cps(other_valid)
        if cps is not None:
            out["tempo_cps"] = Feature(value=cps, support_n=len(other_valid), tier=Tier.ROBUST)

    gaps = _reply_latencies(segments)
    if gaps:
        out["reply_latency_ms"] = Feature(
            value=statistics.median(gaps), support_n=len(gaps), tier=Tier.ROBUST,
        )

    ratios = _tempo_accel_ratios(segments)
    if ratios:
        out["tempo_accel"] = Feature(
            value=statistics.median(ratios), support_n=len(ratios), tier=Tier.ROBUST,
        )

    return out
