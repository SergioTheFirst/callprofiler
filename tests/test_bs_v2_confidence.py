"""Test R-14: compute_bs_confidence formula (§5.4).

Golden tables from spec: clean N=E, raw-n variants.
"""

import pytest
from callprofiler.insight.bs_index import (
    confidence_value,
    compute_bs_confidence,
    EvidenceCluster,
    CONFIDENCE_FORMULA_VERSION_V1,
)


def make_cluster(
    family: str,
    source_call_id: int,
    source_date: str,
    potential: float = 1.0,
    qualified: float = 1.0,
    P: float = 1.0,
    R: float = 1.0,
    V: float = 1.0,
    rejection_reason: str = None,
) -> EvidenceCluster:
    """Helper to construct a cluster."""
    return EvidenceCluster(
        family=family,
        source_call_id=source_call_id,
        source_date=source_date,
        potential=potential,
        qualified=qualified,
        P_validity=P,
        R_validity=R,
        V_validity=V,
        rejection_reason=rejection_reason,
        stable_ref=str(source_call_id),  # simplified for tests
    )


class TestBSConfidenceFormula:
    """Confidence formula c1_effective_evidence_1 from §5.4."""

    def test_c1_exact_curve_and_quality_gates(self):
        """§5.4 таблицы — дословно, на самой кривой (N, E, A, S).

        Точки таблицы — математические: часть из них физически недостижима
        (одна строка не может дать одновременно B и L), поэтому кривая
        проверяется прямо, а вывод A/S из кластеров — отдельными тестами ниже.
        """
        # S доступна только когда КАЖДАЯ половина несёт E>=2 (§5.3) — отсюда
        # столбец S таблицы: при равномерной чистой массе это mass/2 >= 2.
        def stability(mass: float) -> float:
            return 1.0 if mass / 2 >= 2 else 0.0

        # Clean N=E: C при A=0 и при A=1
        table = {0: (1, 1), 1: (9, 18), 3: (18, 34), 10: (52, 77), 100: (65, 97)}
        for n, (c_a0, c_a1) in table.items():
            S = stability(n)
            assert confidence_value(n, n, 0.0, S) == c_a0, f"n={n}, A=0"
            assert confidence_value(n, n, 1.0, S) == c_a1, f"n={n}, A=1"

        # raw-n таблица: B-only (вес 1), L-only (5/11), M-only (2/11)
        raw = {
            0: (1, 1, 1),
            1: (9, 5, 3),
            3: (18, 11, 6),
            10: (52, 41, 13),
            100: (65, 63, 58),
        }
        for n, (b_only, l_only, m_only) in raw.items():
            assert confidence_value(n, n, 0.0, stability(n)) == b_only, f"B-only n={n}"
            mass_l = n * 5 / 11
            assert (
                confidence_value(mass_l, mass_l, 0.0, stability(mass_l)) == l_only
            ), f"L-only n={n}"
            mass_m = n * 2 / 11
            assert (
                confidence_value(mass_m, mass_m, 0.0, stability(mass_m)) == m_only
            ), f"M-only n={n}"

    def test_c1_agreement_and_stability_are_derived_not_assumed(self):
        """A и S — вычисляются из кластеров (§5.3), а не подставляются константой.

        Именно здесь ловится подмена: с плоскими A=0/S=0 (как в первой
        реализации) значения ниже недостижимы.
        """
        as_of = "2026-08-22"

        def cluster(family, call_id, component, num, den, ref):
            c = make_cluster(family, call_id, as_of)
            c["component"] = component
            c["num"] = num
            c["den"] = den
            c["stable_ref"] = ref
            return c

        # B == L == 0.5 → A = 1
        agree = [
            cluster("behavior", 1, "B", 0.5, 1.0, "p1"),
            cluster("language", 1, "C", 0.5, 1.0, "1"),
        ]
        assert compute_bs_confidence(agree, as_of=as_of).agreement_score == 1.0

        # B=0.0, L=1.0 → A = 0 (полное расхождение)
        disagree = [
            cluster("behavior", 1, "B", 0.0, 1.0, "p1"),
            cluster("language", 1, "C", 1.0, 1.0, "1"),
        ]
        assert compute_bs_confidence(disagree, as_of=as_of).agreement_score == 0.0

        # Только behavior → L недоступна → A = 0 (недоказуемо, не «ноль по факту»)
        assert compute_bs_confidence(
            [cluster("behavior", 1, "B", 0.5, 1.0, "p1")], as_of=as_of
        ).agreement_score == 0.0

        # Устойчивость: 4 одинаковых behavior-кластера (E>=2 в каждой половине,
        # одинаковый BS_raw) → S = 1
        stable = [
            cluster("behavior", i, "B", 0.5, 1.0, f"p{i}") for i in range(1, 5)
        ]
        for c in stable:
            c["source_date"] = as_of
        res_stable = compute_bs_confidence(stable, as_of=as_of)
        assert res_stable.stability_score == 1.0

        # Ранние 0.0 vs поздние 1.0 → S = 0
        drifting = [
            cluster("behavior", i, "B", 0.0 if i <= 2 else 1.0, 1.0, f"p{i}")
            for i in range(1, 5)
        ]
        for i, c in enumerate(drifting):
            c["source_date"] = "2026-01-0%d" % (i + 1)
        assert compute_bs_confidence(drifting, as_of=as_of).stability_score == 0.0

        # Мало массы в половине (2 кластера) → S недоступна → 0
        assert compute_bs_confidence(
            [cluster("behavior", i, "B", 0.5, 1.0, f"p{i}") for i in (1, 2)],
            as_of=as_of,
        ).stability_score == 0.0

    def test_c1_all_missing_confidence_one(self):
        """All components missing → C=1 (minimal confidence)."""

        result = compute_bs_confidence([], as_of="2026-08-22")
        assert result.value == 1
        assert result.potential_mass == 0.0
        assert result.qualified_mass == 0.0

    def test_c1_first_call_no_future_outcome_ceiling(self):
        """First call without future outcome: max nonbehavior E=5/11, C≤5."""

        # From §5.4: "Первый звонок без будущего outcome: max nonbehavior E=5/11, A=S=0 → C≤5"

        # This means language only (no behavior), E limited to 5/11 per call.
        # N = 5/11 (language potential), E = 5/11 (qualified), Q=1
        # coverage = (5/11) / (5/11 + 3) = (5/11) / (38/11) = 5/38 ≈ 0.132
        # C = round_half_up(1 + 99*0.132*1*1/3, 0)
        #   = round_half_up(1 + 4.36, 0) = 5

        clusters = [make_cluster("language", 1, "2026-08-22", potential=5/11, qualified=5/11)]
        result = compute_bs_confidence(clusters, as_of="2026-08-22")
        # Should be <= 5
        assert result.value <= 5, f"First call L-only should give C≤5, got {result.value}"

    def test_c1_future_rows_excluded(self):
        """Rows with source_date > as_of are excluded."""

        as_of = "2026-08-22"
        future_date = "2026-09-22"

        clusters = [
            make_cluster("behavior", 1, as_of),
            make_cluster("behavior", 2, future_date),  # future
        ]

        # Only first cluster should be counted
        result = compute_bs_confidence(clusters, as_of=as_of)

        # With only N=1, E=1, result should be same as single-cluster
        clusters_single = [make_cluster("behavior", 1, as_of)]
        result_single = compute_bs_confidence(clusters_single, as_of=as_of)

        assert result.value == result_single.value

    def test_c1_undated_excluded_audit_counter(self):
        """Undated rows excluded, counted in audit details."""

        as_of = "2026-08-22"

        clusters = [
            make_cluster("behavior", 1, as_of),
            make_cluster("behavior", 2, None),  # undated
        ]

        result = compute_bs_confidence(clusters, as_of=as_of)

        # Only dated cluster counted
        clusters_dated = [make_cluster("behavior", 1, as_of)]
        result_dated = compute_bs_confidence(clusters_dated, as_of=as_of)

        assert result.value == result_dated.value
        assert result.details["undated_excluded"] == 1

    def test_c1_version_field(self):
        """Result includes correct version string."""
        clusters = [make_cluster("behavior", 1, "2026-08-22")]
        result = compute_bs_confidence(clusters, as_of="2026-08-22")
        assert result.version == CONFIDENCE_FORMULA_VERSION_V1
        assert result.version == "c1_effective_evidence_1"

    def test_c1_geomean_quality_scoring(self):
        """Quality score uses geometric mean q = (P*R*V)^(1/3)."""

        as_of = "2026-08-22"

        # Cluster with P=R=V=1 → q=1
        cluster_full = make_cluster("behavior", 1, as_of, P=1.0, R=1.0, V=1.0)

        # Cluster with P=R=V=0.5 → q=0.5^(1/3) ≈ 0.794
        cluster_partial = make_cluster("behavior", 2, as_of, P=0.5, R=0.5, V=0.5)

        result_full = compute_bs_confidence([cluster_full], as_of=as_of)
        result_partial = compute_bs_confidence([cluster_partial], as_of=as_of)

        # Partial quality should give lower confidence
        assert result_partial.value < result_full.value

    def test_c1_rejected_attempt_increases_n_not_e(self):
        """Rejected evidence (qualified=0) increases N but not E."""

        as_of = "2026-08-22"

        # One accepted cluster
        accepted = make_cluster("behavior", 1, as_of, qualified=1.0)

        # One rejected (potential=1, qualified=0)
        rejected = make_cluster("behavior", 2, as_of, potential=1.0, qualified=0.0, rejection_reason="quote_mismatch")

        result = compute_bs_confidence([accepted, rejected], as_of=as_of)

        # With only accepted
        result_accepted = compute_bs_confidence([accepted], as_of=as_of)

        # rejected cluster should increase N (coverage rises) but E stays same
        # So Q=E/N decreases, resulting in lower confidence
        assert result.potential_mass == 2.0
        assert result.qualified_mass == 1.0
        assert result.quality_score < 1.0
        assert result.value < result_accepted.value

    def test_c1_clamp_bounds(self):
        """Result clamped to [1, 100]."""

        as_of = "2026-08-22"

        # Many clusters → should reach high C (when A and S are computed)
        many_clusters = [make_cluster("behavior", i, as_of) for i in range(1000)]
        result_many = compute_bs_confidence(many_clusters, as_of=as_of)
        assert 1 <= result_many.value <= 100
        # With many behavior clusters, N and E are large; Q=1; A and S default to 0
        # C ≈ round_half_up(1 + 99*coverage*1*1/3, 0)
        # coverage ≈ 1000/(1000+3) ≈ 0.997
        # C ≈ round_half_up(1 + 32.89, 0) = 34
        assert 30 <= result_many.value <= 40  # realistic with A=0, S=0

        # No clusters → C=1
        result_none = compute_bs_confidence([], as_of=as_of)
        assert result_none.value == 1
