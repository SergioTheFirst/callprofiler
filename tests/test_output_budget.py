# -*- coding: utf-8 -*-
"""Unit tests for analyze/output_budget.py — dynamic output-token budget."""

from __future__ import annotations

import pytest

from callprofiler.analyze.output_budget import (
    OUTPUT_ABS_MAX,
    OUTPUT_FLOOR,
    output_budget,
)

# Comfortable window where the hardware ceiling never binds (n_ctx large,
# prompt small). Isolates the value-tier logic.
_N_CTX = 16384
_SMALL_PROMPT = 1500


@pytest.mark.unit
@pytest.mark.parametrize(
    "transcript_chars, expected_base",
    [
        (0, 700),       # empty / degenerate → lowest tier
        (799, 700),     # just below first boundary
        (800, 1500),    # boundary flips to normal tier
        (2999, 1500),   # top of normal tier
        (3000, 2600),   # boundary flips to substantive
        (7999, 2600),   # top of substantive
        (8000, 3600),   # long / high-value tail
        (50000, 3600),  # very long stays at long tier (policy, not length, caps)
    ],
)
def test_length_tiers(transcript_chars, expected_base):
    assert output_budget(transcript_chars, _SMALL_PROMPT, _N_CTX) == expected_base


@pytest.mark.unit
def test_priority_bump_applies_above_threshold():
    # Normal tier base 1500 → ×1.2 = 1800 for an important contact.
    assert output_budget(1500, _SMALL_PROMPT, _N_CTX, priority=70) == 1800
    assert output_budget(1500, _SMALL_PROMPT, _N_CTX, priority=99) == 1800


@pytest.mark.unit
def test_priority_below_threshold_no_bump():
    assert output_budget(1500, _SMALL_PROMPT, _N_CTX, priority=69) == 1500
    assert output_budget(1500, _SMALL_PROMPT, _N_CTX, priority=0) == 1500


@pytest.mark.unit
def test_hardware_ceiling_binds_when_prompt_large():
    # Long call wants 3600, but only ~900 tokens free under n_ctx → clamp down.
    n_ctx = 4096
    prompt = 2700  # 4096 - 2700 - 512(margin) = 884 free
    budget = output_budget(10000, prompt, n_ctx)
    assert budget == 4096 - 2700 - 512  # 884
    assert budget < 3600


@pytest.mark.unit
def test_policy_abs_max_caps_budget():
    # Long tier base 3600 sits under abs_max; the priority bump (×1.2 = 4320)
    # would exceed it, so abs_max=4096 is what binds. Confirms the policy ceiling
    # is the hard cap, not the tier value.
    budget = output_budget(50000, 1000, 65536, priority=80)
    assert budget == OUTPUT_ABS_MAX


@pytest.mark.unit
def test_custom_abs_max_throttles_for_timeboxed_runs():
    # Operator lowers abs_max to cap wall-clock on the 17k run.
    budget = output_budget(50000, 1500, _N_CTX, abs_max=2000)
    assert budget == 2000


@pytest.mark.unit
def test_never_below_floor_in_normal_conditions():
    budget = output_budget(10, _SMALL_PROMPT, _N_CTX)
    assert budget >= OUTPUT_FLOOR


@pytest.mark.unit
def test_degenerate_prompt_overflows_window_returns_safe_ceiling():
    # Prompt nearly fills the window — budget must not push past n_ctx.
    n_ctx = 2048
    prompt = 1800  # 2048 - 1800 - 512 = -264 → ceiling <= 0
    budget = output_budget(5000, prompt, n_ctx)
    assert budget == 0
    # And prompt + budget never exceeds n_ctx.
    assert prompt + budget <= n_ctx


@pytest.mark.unit
def test_budget_plus_prompt_never_exceeds_window_across_lengths():
    n_ctx = 8192
    prompt = 3000
    for chars in (100, 1000, 5000, 20000, 100000):
        budget = output_budget(chars, prompt, n_ctx)
        assert prompt + budget <= n_ctx, f"overflow at {chars} chars"
