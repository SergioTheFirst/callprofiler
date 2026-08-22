"""Test R-13: compute_bs_v2 formula (§4.4).

Golden examples + deterministic random vectors.
"""

import random
import pytest
from callprofiler.insight.bs_index import compute_bs_v2, BS_FORMULA_VERSION_V2


class TestBSV2Formula:
    """BS-v2 formula from §4.4."""

    def test_v2_roc_observed_exact_examples(self):
        """Golden examples from §4.4: 62.8, 89.8, 0.0."""

        # B=.50, L_C=.80, L_P=.90 (no direct L_P input; used in L calc)
        # L = (3*1*.80 + 1*1*.90) / (3*1 + 1*1) = (2.4 + 0.9) / 4 = 3.3 / 4 = .825
        # z = 11*1 + 5*1 + 2*1 = 18
        # BS = round_half_up(100*(11*1*.50 + 5*1*.825 + 2*1*.90)/18, 1)
        #    = round_half_up(100*(5.5 + 4.125 + 1.8)/18, 1)
        #    = round_half_up(100*11.425/18, 1)
        #    = round_half_up(63.47222..., 1)

        # This says L directly is .80, not computed.

        result = compute_bs_v2(B=0.50, L_C=0.80, L_P=None, M=0.90)
        # With L_C=.80 and no L_P: aC=1, aP=0
        # L = (3*1*.80 + 0) / (3*1 + 0) = 2.4 / 3 = .80 ✓
        # z = 11 + 5 + 2 = 18
        # BS = round_half_up(100*(11*.50 + 5*.80 + 2*.90)/18, 1)
        #    = round_half_up(100*(5.5 + 4.0 + 1.8)/18, 1)
        #    = round_half_up(100*11.3/18, 1)
        #    = round_half_up(62.777..., 1)
        #    = 62.8 ✓

        assert abs(result.value - 62.8) < 0.01, f"Expected 62.8, got {result.value}"
        assert result.components["behavior"] == 0.50
        assert abs(result.components["language"] - 0.80) < 0.01
        assert result.components["model"] == 0.90
        assert result.no_evidence is False

    def test_v2_roc_observed_missing_behavior(self):
        """B missing, L=.9375, M=.80 → 89.8."""

        # B missing, so aB=0
        # L_C only: aC=1, aP=0 → L = .9375
        # z = 0 + 5 + 2 = 7
        # BS = round_half_up(100*(0 + 5*.9375 + 2*.80)/7, 1)
        #    = round_half_up(100*(4.6875 + 1.6)/7, 1)
        #    = round_half_up(100*6.2875/7, 1)
        #    = round_half_up(89.821..., 1)
        #    = 89.8 ✓

        result = compute_bs_v2(B=None, L_C=0.9375, L_P=None, M=0.80)
        assert abs(result.value - 89.8) < 0.01, f"Expected 89.8, got {result.value}"
        assert result.components["behavior"] is None
        assert abs(result.components["language"] - 0.9375) < 0.01
        assert result.components["model"] == 0.80
        assert result.no_evidence is False

    def test_v2_all_missing_no_evidence(self):
        """All missing → BS=0.0, no_evidence=True."""

        result = compute_bs_v2(B=None, L_C=None, L_P=None, M=None)
        assert result.value == 0.0
        assert result.no_evidence is True
        assert all(v is None for v in result.components.values())

    def test_v2_deterministic_random_vectors(self):
        """10,000 generated vectors: bounded in [0,100], deterministic."""

        random.seed(42)  # Fixed seed for reproducibility

        results = []
        for _ in range(10000):
            # Generate random 0/1 valid values
            B = random.random() if random.random() > 0.3 else None
            L_C = random.random() if random.random() > 0.3 else None
            L_P = random.random() if random.random() > 0.3 else None
            M = random.random() if random.random() > 0.3 else None

            result = compute_bs_v2(B=B, L_C=L_C, L_P=L_P, M=M)
            results.append((result.value, B, L_C, L_P, M))

            # Check bounds
            assert 0.0 <= result.value <= 100.0, (
                f"Value {result.value} out of bounds for B={B}, L_C={L_C}, "
                f"L_P={L_P}, M={M}"
            )

            # no_evidence only when all missing
            if B is None and L_C is None and L_P is None and M is None:
                assert result.no_evidence is True
            else:
                assert result.no_evidence is False

        # Verify determinism: re-run with same seed
        random.seed(42)
        for i, _ in enumerate(range(10000)):
            B = random.random() if random.random() > 0.3 else None
            L_C = random.random() if random.random() > 0.3 else None
            L_P = random.random() if random.random() > 0.3 else None
            M = random.random() if random.random() > 0.3 else None

            result = compute_bs_v2(B=B, L_C=L_C, L_P=L_P, M=M)
            expected_value, exp_B, exp_L_C, exp_L_P, exp_M = results[i]

            # Verify same inputs
            assert B == exp_B and L_C == exp_L_C and L_P == exp_L_P and M == exp_M
            # Verify same output
            assert abs(result.value - expected_value) < 1e-10, (
                f"Non-deterministic at iteration {i}: "
                f"got {result.value}, expected {expected_value}"
            )

    def test_v2_version_field(self):
        """Result includes correct version string."""
        result = compute_bs_v2(B=0.5, L_C=0.5, L_P=None, M=0.5)
        assert result.version == BS_FORMULA_VERSION_V2
        assert result.version == "v2_roc_observed_1"

    def test_v2_rounding_half_up(self):
        """Rounding uses ROUND_HALF_UP (not banker's)."""

        # Case: 62.75 rounds to 62.8 (half-up), not 62.7
        # BS = round_half_up(100*numerator/z, 1)
        # If numerator/z = 0.6275, then 100*0.6275 = 62.75 → 62.8

        # z=100, numerator=62.75 → no, z must be sum of availability.
        # Let's try: 11*aB*B + 5*aL*L + 2*aM*M = 62.75, z=100
        # This requires specific non-integer z, which isn't possible.
        # Instead test the rounding function directly.

        from callprofiler.insight.bs_index import round_half_up

        assert round_half_up(62.75, 1) == 62.8
        assert round_half_up(62.74, 1) == 62.7
        assert round_half_up(62.76, 1) == 62.8
        assert round_half_up(0.05, 1) == 0.1  # .05 rounds up
        assert round_half_up(0.15, 1) == 0.2
        assert round_half_up(0.25, 1) == 0.3  # .25 rounds up (not banker's .20)
