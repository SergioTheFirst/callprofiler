"""Pure BS-v2 formulas (§4, §5 from 100bsindex.md).

No DB, no clock, no config — mathematical functions only.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from typing import Optional, Sequence, TypedDict


# Version constants (match db/migrations.py M12 contract)
BS_FORMULA_VERSION_V2 = "v2_roc_observed_1"
CONFIDENCE_FORMULA_VERSION_V1 = "c1_effective_evidence_1"

# Weights (§4.4): (11,5,2)/18
W_B = Fraction(11, 18)
W_L = Fraction(5, 18)
W_M = Fraction(2, 18)

# Confidence anchors (§5.1-5.2)
K_DEFAULT = 3  # denominator constant for coverage = N/(N+K)


@dataclass
class BSResult:
    """Result of compute_bs_v2."""

    value: float  # 0.0-100.0
    components: dict  # {"behavior": float|None, "contradiction": float|None, ...}
    version: str = BS_FORMULA_VERSION_V2
    no_evidence: bool = False  # all components missing


@dataclass
class ConfidenceResult:
    """Result of compute_bs_confidence."""

    value: int  # 1-100
    potential_mass: float
    qualified_mass: float
    quality_score: float  # Q = E/N
    agreement_score: float  # A = 1-abs(B-L)
    stability_score: float  # S from chronological split
    version: str = CONFIDENCE_FORMULA_VERSION_V1
    details: dict = field(default_factory=dict)  # audit info


def round_half_up(value: float, decimals: int) -> float:
    """Round using ROUND_HALF_UP (banker's rounding forbidden).

    Args:
        value: number to round
        decimals: decimal places (1 = 0.1, 0 = integer)

    Returns:
        Rounded float.
    """
    if decimals < 0:
        raise ValueError("decimals must be >= 0")

    multiplier = 10 ** decimals
    d = Decimal(str(value * multiplier))
    rounded = d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(rounded) / multiplier


def compute_bs_v2(
    B: Optional[float],
    L_C: Optional[float],
    L_P: Optional[float],
    M: Optional[float],
) -> BSResult:
    """Compute BS-v2 index from behavior, language, model scores.

    §4.1-4.4 dword-for-word.

    Args:
        B: behavior_score (0.0-1.0 or None if missing)
        L_C: contradiction language component (0.0-1.0 or None)
        L_P: promise_vague language component (0.0-1.0 or None)
        M: model_score (0.0-1.0 or None)

    Returns:
        BSResult with value 0-100, components dict, no_evidence flag.
    """
    components = {
        "behavior": B,
        "contradiction": L_C,
        "promise_vague": L_P,
        "language": None,
        "model": M,
    }

    # Compute L from C and P (§4.2)
    # L = (3*aC*C + 1*aP*P) / (3*aC + 1*aP)
    aC = 1 if L_C is not None else 0
    aP = 1 if L_P is not None else 0

    if aC > 0 or aP > 0:
        numerator = 3 * aC * (L_C or 0) + 1 * aP * (L_P or 0)
        denominator = 3 * aC + 1 * aP
        L = numerator / denominator
        components["language"] = L
    else:
        L = None

    # Availability flags
    aB = 1 if B is not None else 0
    aL = 1 if L is not None else 0
    aM = 1 if M is not None else 0

    # Aggregation (§4.4)
    # z = 11*aB + 5*aL + 2*aM
    z = 11 * aB + 5 * aL + 2 * aM

    if z == 0:
        # All missing
        return BSResult(value=0.0, components=components, no_evidence=True)

    # BS = round_half_up(100*(11*aB*B + 5*aL*L + 2*aM*M)/z, 1)
    numerator = (
        11 * aB * (B or 0) + 5 * aL * (L or 0) + 2 * aM * (M or 0)
    )
    bs_raw = 100.0 * numerator / z
    bs_value = round_half_up(bs_raw, 1)

    return BSResult(value=bs_value, components=components, no_evidence=False)


# Cluster TypedDict for compute_bs_confidence §5.1
class EvidenceCluster(TypedDict, total=False):
    """One evidence cluster (behavior/language/model component)."""

    family: str  # "behavior" | "language" | "model"
    source_call_id: int
    source_date: str  # ISO-8601 UTC
    potential: float  # P_i (0 or 1)
    qualified: float  # qualified P_i
    P_validity: float  # P_i (0/1)
    R_validity: float  # R_i (0/1)
    V_validity: float  # V_i (0/1)
    rejection_reason: Optional[str]  # None if qualified
    stable_ref: str  # promise_key (str) or call_id (int→str)
    # Вклад кластера в компонент BS (§4): нужен для A (согласие B vs L) и S
    # (устойчивость по половинам). Заполняет сборщик входов (R-16); без них
    # A и S равны 0 — недоказуемы, а не «нулевые по факту».
    component: Optional[str]  # "B" | "C" | "P" | "M" | None
    num: float  # взвешенный числитель вклада
    den: float  # взвешенный знаменатель вклада


def compute_bs_confidence(
    clusters: Sequence[EvidenceCluster],
    as_of: str,  # ISO-8601 date, e.g. "2026-08-22"
    k: int = K_DEFAULT,
) -> ConfidenceResult:
    """Compute confidence (c1_effective_evidence_1) from typed clusters.

    §5.1-5.4 dword-for-word.

    Args:
        clusters: list of EvidenceCluster, pre-filtered to source_date <= as_of
        as_of: reference date (YYYY-MM-DD) for recency decay r(age_days)
        k: denominator constant (default 3, per §5.2)

    Returns:
        ConfidenceResult with value 1-100, mass/quality/agreement/stability.
    """
    # Filter out future rows (safety check; caller should pre-filter)
    # Also filter out undated (None source_date) — they're counted separately
    clusters_filtered = [c for c in clusters if c["source_date"] and c["source_date"] <= as_of]

    # Separate behavior from language/model for aggregation
    behavior_clusters = [c for c in clusters_filtered if c["family"] == "behavior"]
    call_clusters = [c for c in clusters_filtered if c["family"] in ("language", "model")]

    # Compute potential and qualified mass (§5.1-5.2)
    # N_call = max(r*p_L, r*p_M) per call
    # E_call = max(r*qualified_L*q_L, r*qualified_M*q_M) per call
    # N = sum_behavior + sum_call_clusters
    # E = sum_behavior + sum_call_clusters

    N = 0.0
    E = 0.0
    undated_excluded = 0

    # Count undated rows in all clusters (before filtering)
    for c in clusters:
        if not c["source_date"]:
            undated_excluded += 1

    # Behavior clusters
    for c in behavior_clusters:
        r = recency_decay(c["source_date"], as_of)
        q_i = (c["P_validity"] * c["R_validity"] * c["V_validity"]) ** (1 / 3)

        N += r * c["potential"]
        E += r * c["qualified"] * q_i

    # Call-level clusters: max of L and M for each call
    call_levels = {}
    for c in call_clusters:
        cid = c["source_call_id"]
        if cid not in call_levels:
            call_levels[cid] = {"L": None, "M": None, "date": c["source_date"]}

        family = c["family"]
        if family == "language":
            call_levels[cid]["L"] = c
        elif family == "model":
            call_levels[cid]["M"] = c

    for cid, data in call_levels.items():
        r = recency_decay(data["date"], as_of)
        p_L = data["L"]["potential"] if data["L"] else 0.0
        p_M = data["M"]["potential"] if data["M"] else 0.0
        N_call = max(r * p_L, r * p_M)
        N += N_call

        # qualified * q
        q_L = 0.0
        if data["L"]:
            q_L = (
                data["L"]["P_validity"]
                * data["L"]["R_validity"]
                * data["L"]["V_validity"]
            ) ** (1 / 3)
        q_M = 0.0
        if data["M"]:
            q_M = (
                data["M"]["P_validity"]
                * data["M"]["R_validity"]
                * data["M"]["V_validity"]
            ) ** (1 / 3)

        qualified_L = data["L"]["qualified"] if data["L"] else 0.0
        qualified_M = data["M"]["qualified"] if data["M"] else 0.0

        E_call = max(r * qualified_L * q_L, r * qualified_M * q_M)
        E += E_call

    # Quality (§5.2)
    Q = E / N if N > 0 else 0.0

    # Coverage (§5.2)
    coverage = N / (N + k)

    # Agreement (§5.3): A = 1-|B-L|, доступно только когда доступны ОБА.
    # Значения компонентов приходят вместе с кластерами (`component`/`num`/`den`):
    # каждый кластер несёт свой взвешенный вклад в числитель/знаменатель своего
    # компонента (§4.1-4.3 — все компоненты суть отношения взвешенных сумм),
    # поэтому одна и та же функция считает и полный набор, и половины для S.
    B_all, C_all, P_all, M_all = _components_from_clusters(clusters_filtered, as_of)
    L_all = _language_component(C_all, P_all)
    A = 1.0 - abs(B_all - L_all) if (B_all is not None and L_all is not None) else 0.0

    # Stability (§5.3): хронологический сплит по ключу
    # (source_date, family_rank, stable_ref); нечётное n → лишний кластер в
    # ПОЗДНЮЮ половину; S доступна только при E>=2 в каждой половине.
    S = 0.0
    sorted_clusters = sorted(
        clusters_filtered,
        key=lambda c: (
            c["source_date"],
            0 if c["family"] == "behavior" else 1,
            str(c["stable_ref"]),
        ),
    )
    if sorted_clusters:
        mid = len(sorted_clusters) // 2  # нечётное n → поздняя половина длиннее
        early, late = sorted_clusters[:mid], sorted_clusters[mid:]
        E_early = _qualified_mass(early, as_of)
        E_late = _qualified_mass(late, as_of)
        if E_early >= 2 and E_late >= 2:
            bs_early = _bs_raw_unit(early, as_of)
            bs_late = _bs_raw_unit(late, as_of)
            if bs_early is not None and bs_late is not None:
                S = max(0.0, 1.0 - abs(bs_early - bs_late))

    # Final confidence (§5.4)
    C = confidence_value(N, E, A, S, k)

    return ConfidenceResult(
        value=C,
        potential_mass=N,
        qualified_mass=E,
        quality_score=Q,
        agreement_score=A,
        stability_score=S,
        details={
            "undated_excluded": undated_excluded,
            "coverage": coverage,
            "k": k,
        },
    )



def confidence_value(N: float, E: float, A: float, S: float, k: int = K_DEFAULT) -> int:
    """C = clamp(round_half_up(1 + 99*coverage*Q*(1+A+S)/3), 1, 100) — §5.4.

    Вынесено отдельной чистой функцией: таблицы §5.4 — это кривая по массам
    (N, E) и флагам (A, S), и проверять её надо прямо, а не подбирать кластеры,
    часть точек которых физически недостижима (см. §5.4 «stable one-line …»).
    """
    coverage = N / (N + k) if (N + k) > 0 else 0.0
    Q = E / N if N > 0 else 0.0
    value = round_half_up(1.0 + 99.0 * coverage * Q * (1.0 + A + S) / 3.0, 0)
    return max(1, min(100, int(value)))


def recency_decay(source_date: str, as_of: str) -> float:
    """Compute recency decay r(age_days) = 2^(-age_days/180).

    Args:
        source_date: ISO-8601 date of evidence (YYYY-MM-DD)
        as_of: reference date (YYYY-MM-DD)

    Returns:
        Decay factor 0.0-1.0.
    """
    from datetime import datetime

    try:
        d_source = datetime.fromisoformat(source_date).date()
        d_as_of = datetime.fromisoformat(as_of).date()
    except (ValueError, TypeError):
        return 1.0  # fallback: no decay if dates invalid

    age_days = (d_as_of - d_source).days
    if age_days < 0:
        # Future date; shouldn't happen (should be pre-filtered)
        return 1.0
    if age_days == 0:
        return 1.0

    # r(age) = 2^(-age/180)
    decay = 2.0 ** (-age_days / 180.0)
    return max(0.0, decay)


# ── компонентная арифметика для A и S (§5.3) ────────────────────────────────
# Кластер может нести свой вклад в компонент BS: component ∈ {"B","C","P","M"},
# num/den — уже взвешенные (r*g*y и r*g для B, r*c и r*oC для C, и т.д.).
# Без этих полей A и S равны 0 — не «предположительно нулевые», а недоступные:
# согласие и устойчивость невозможно доказать, если основания не переданы.

def _ratio(num: float, den: float) -> Optional[float]:
    return (num / den) if den > 0 else None


def _components_from_clusters(
    clusters: Sequence[EvidenceCluster], as_of: str
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """(B, C, P, M) как отношения взвешенных сумм вкладов кластеров."""
    acc = {key: [0.0, 0.0] for key in ("B", "C", "P", "M")}
    for c in clusters:
        component = c.get("component")
        if component not in acc:
            continue
        acc[component][0] += float(c.get("num", 0.0))
        acc[component][1] += float(c.get("den", 0.0))
    return (
        _ratio(*acc["B"]),
        _ratio(*acc["C"]),
        _ratio(*acc["P"]),
        _ratio(*acc["M"]),
    )


def _language_component(C: Optional[float], P: Optional[float]) -> Optional[float]:
    """L = (3*aC*C + 1*aP*P) / (3*aC + 1*aP) — §4.2, одна формула на все вызовы."""
    aC, aP = (1 if C is not None else 0), (1 if P is not None else 0)
    if not (aC or aP):
        return None
    return (3 * aC * (C or 0.0) + aP * (P or 0.0)) / (3 * aC + aP)


def _qualified_mass(clusters: Sequence[EvidenceCluster], as_of: str) -> float:
    """E половины — та же геосредняя q, что и в основном расчёте."""
    total = 0.0
    for c in clusters:
        if not c["source_date"]:
            continue
        r = recency_decay(c["source_date"], as_of)
        q = (c["P_validity"] * c["R_validity"] * c["V_validity"]) ** (1 / 3)
        total += r * c["qualified"] * q
    return total


def _bs_raw_unit(clusters: Sequence[EvidenceCluster], as_of: str) -> Optional[float]:
    """Неокруглённый BS половины в шкале 0..1 (для S; §5.3 «unrounded BS_raw»)."""
    B, C, P, M = _components_from_clusters(clusters, as_of)
    L = _language_component(C, P)
    aB, aL, aM = (1 if B is not None else 0), (1 if L is not None else 0), (1 if M is not None else 0)
    z = 11 * aB + 5 * aL + 2 * aM
    if z == 0:
        return None
    return (11 * aB * (B or 0.0) + 5 * aL * (L or 0.0) + 2 * aM * (M or 0.0)) / z
