# -*- coding: utf-8 -*-
"""
graph/calibration.py — BS-index calibration and thresholding.

Computes user-specific percentile-based thresholds for BS-index labels.
Enables data-driven risk categorization (reliable/noisy/risky/unreliable/critical).
"""

from __future__ import annotations

import logging
import statistics
from typing import Literal

from callprofiler.graph.repository import GraphRepository

log = logging.getLogger(__name__)


class BSCalibrator:
    """Compute and apply BS-index thresholds per user."""

    LABEL_MAP = {
        "reliable": "🟢",
        "noisy": "🟡",
        "risky": "🔴",
        "unreliable": "🔴",
        "critical": "⚫",
        "uncalibrated": "⚪",
    }

    def __init__(self, grepo: GraphRepository) -> None:
        self._grepo = grepo

    def analyze(self, user_id: str, min_calls: int = 3, min_promises: int = 1) -> dict:
        """
        Analyze BS-index distribution for user_id and compute percentile thresholds.

        Filters entities with total_calls >= min_calls and total_promises >= min_promises.
        Ignores archived entities and the owner entity.

        Returns dict with:
            - ok: bool (True if >= 3 entities analyzed)
            - entity_count: int
            - thresholds: dict with reliable_max, noisy_max, risky_max, unreliable_max
            - percentiles: dict with p25, p50, p75, p90
            - std_dev: float
        """
        scores = self._grepo.get_bs_scores_filtered(user_id, min_calls, min_promises)

        if len(scores) < 3:
            log.warning("[calibrator] analyze(%s): < 3 entities, cannot calibrate", user_id)
            return {
                "ok": False,
                "entity_count": len(scores),
                "thresholds": None,
                "percentiles": None,
                "std_dev": None,
            }

        # Compute percentiles
        p25 = self._percentile(scores, 25)
        p50 = self._percentile(scores, 50)
        p75 = self._percentile(scores, 75)
        p90 = self._percentile(scores, 90)

        # Compute standard deviation
        try:
            std_dev = statistics.stdev(scores)
        except (ValueError, statistics.StatisticsError):
            std_dev = 0.0

        # Define thresholds
        thresholds = {
            "reliable_max": p25,
            "noisy_max": p50,
            "risky_max": p75,
            "unreliable_max": p90,
        }

        log.info(
            "[calibrator] analyze(%s): entity_count=%d, p25=%.1f, p50=%.1f, "
            "p75=%.1f, p90=%.1f, std_dev=%.2f",
            user_id, len(scores), p25, p50, p75, p90, std_dev,
        )

        # Save thresholds to DB
        try:
            self._grepo.save_bs_thresholds(user_id, thresholds, len(scores), std_dev)
        except Exception as e:
            log.warning("[calibrator] failed to save thresholds for %s: %s", user_id, e)

        return {
            "ok": True,
            "entity_count": len(scores),
            "thresholds": thresholds,
            "percentiles": {"p25": p25, "p50": p50, "p75": p75, "p90": p90},
            "std_dev": std_dev,
        }

    def get_label(
        self, bs_index: float, user_id: str, use_fallback: bool = True
    ) -> tuple[str, str]:
        """
        Get risk label and emoji for bs_index using user's thresholds.

        Args:
            bs_index: BS-index value (0-100)
            user_id: User ID to fetch thresholds for
            use_fallback: If True, use emoji-only fallback if thresholds not found

        Returns:
            (label, emoji) tuple, e.g. ("reliable", "🟢")
        """
        thresholds = self._grepo.get_latest_bs_thresholds(user_id)

        if thresholds is None:
            label = "uncalibrated"
            emoji = self.LABEL_MAP[label]
            log.debug("[calibrator] get_label(%s, %s): no thresholds, using fallback",
                      bs_index, user_id)
            return (label, emoji)

        # Determine label based on thresholds
        if bs_index <= thresholds.get("reliable_max", 25):
            label = "reliable"
        elif bs_index <= thresholds.get("noisy_max", 50):
            label = "noisy"
        elif bs_index <= thresholds.get("risky_max", 75):
            label = "risky"
        elif bs_index <= thresholds.get("unreliable_max", 90):
            label = "unreliable"
        else:
            label = "critical"

        emoji = self.LABEL_MAP[label]
        return (label, emoji)

    @staticmethod
    def _percentile(data: list[float], p: int) -> float:
        """Compute p-th percentile using linear interpolation."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        n = len(sorted_data)
        rank = (p / 100.0) * (n - 1)
        lower_idx = int(rank)
        upper_idx = min(lower_idx + 1, n - 1)
        lower_val = sorted_data[lower_idx]
        upper_val = sorted_data[upper_idx]
        fraction = rank - lower_idx
        return lower_val + fraction * (upper_val - lower_val)
