# -*- coding: utf-8 -*-
"""Темп речи (слов/сек) — FRAGILE tier."""
from .base import Feature, Tier


def words_per_sec(seg_stats: list[tuple[int, int]]) -> Feature:
    """Темп речи из таймстампов сегментов.

    Входе: список (n_tokens, dur_ms) по OTHER-сегментам.
    Возвращает: слов/сек, support = количество валидных сегментов.
    """
    if not seg_stats:
        return Feature(0.0, 0, Tier.FRAGILE)

    total_tokens = 0
    total_dur_sec = 0
    valid_count = 0

    for n_tokens, dur_ms in seg_stats:
        if dur_ms is None or dur_ms <= 0 or dur_ms > 300_000:
            continue
        total_tokens += n_tokens
        total_dur_sec += dur_ms / 1000.0
        valid_count += 1

    if total_dur_sec == 0:
        return Feature(0.0, 0, Tier.FRAGILE)

    rate = total_tokens / total_dur_sec
    return Feature(rate, valid_count, Tier.FRAGILE)
