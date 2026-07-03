"""Age Ensemble Fusion — единая итоговая оценка возраста из маркеров и стиля.

Правила: детерминированные, по убыванию точности (vozrast.md §4.6).
Без БД, без импортов dashboard — чистая функция.
"""

FUSION_VERSION = "fuse-v1"


def fuse_age(
    marker: dict | None,
    style: dict | None,
    reference_year: int,
) -> dict | None:
    """Объединить маркер-оценку и стиль-оценку в единую итоговую оценку возраста.

    Args:
        marker: строка contact_age_estimates как dict {method, birth_year_low/high/point, confidence, ...}
                либо None, если маркеров нет.
        style: строка contact_age_style как dict {birth_point, birth_low/high, confidence, confidence_level, ...}
               либо None, если стиля нет.
        reference_year: текущий год для расчёта возраста из birth_year.

    Returns:
        {'age_point', 'age_low', 'age_high', 'birth_point', 'birth_low', 'birth_high',
         'confidence', 'source', 'warnings', 'fusion_version'} | None.
        None если ни marker, ни style не валидны.
    """
    marker_valid = _is_marker_valid(marker)
    style_valid = _is_style_valid(style)

    # Правило 6: ни одного → None
    if not marker_valid and not style_valid:
        return None

    # Правило 3: оба валидны
    if marker_valid and style_valid:
        return _fuse_both(marker, style, reference_year)

    # Правило 4: только marker
    if marker_valid:
        return _fuse_marker_only(marker, reference_year)

    # Правило 5: только style
    if style_valid:
        return _fuse_style_only(style, reference_year)

    return None


def _is_marker_valid(marker: dict | None) -> bool:
    """Маркер валиден, если method in ('marker','relation','combined') и birth_year_low/high не NULL.
    LLM-строка (method='llm' с непустым birth_*) — тоже вход, но слабая (conf cap 50).
    """
    if marker is None:
        return False
    method = marker.get("method")
    if method not in ("marker", "relation", "combined", "llm"):
        return False
    birth_low = marker.get("birth_year_low")
    birth_high = marker.get("birth_year_high")
    return birth_low is not None and birth_high is not None


def _is_style_valid(style: dict | None) -> bool:
    """Стиль валиден, если birth_point не NULL и confidence_level >= 2."""
    if style is None:
        return False
    birth_point = style.get("birth_point")
    confidence_level = style.get("confidence_level")
    return birth_point is not None and (confidence_level or 0) >= 2


def _fuse_both(marker: dict, style: dict, reference_year: int) -> dict:
    """Оба валидны: пересечение или конфликт."""
    marker_low = marker["birth_year_low"]
    marker_high = marker["birth_year_high"]
    marker_point = marker.get("birth_year_point") or (marker_low + marker_high) // 2
    marker_conf = marker.get("confidence", 50)
    marker_method = marker.get("method")
    if marker_method == "llm":  # llm-строка — слабый вход (cap 50) и честная метка
        marker_conf = min(marker_conf, 50)

    style_point = style["birth_point"]
    style_low = style.get("birth_year_low")
    style_high = style.get("birth_year_high")
    style_conf = style.get("confidence", 50)

    # Вычислить интервал для стиля, если задана только точка
    if style_low is None or style_high is None:
        style_span = 20  # guess: ±10 лет от точки
        style_low = style_point - style_span // 2
        style_high = style_point + style_span // 2

    # Пересечение интервалов
    inter_low = max(marker_low, style_low)
    inter_high = min(marker_high, style_high)

    # Пересечение непусто (правило: стиль шумный, интервал от marker)
    if inter_low <= inter_high:
        confidence = min(95, marker_conf + 5)
        source = "llm+style" if marker_method == "llm" else "marker+style"
        warnings = []
    else:
        # Конфликт: интервал/точка от marker, confidence штраф
        confidence = max(20, marker_conf - 10)
        source = "llm" if marker_method == "llm" else "marker"
        warnings = ["стиль расходится с маркером"]
        inter_low = marker_low
        inter_high = marker_high

    # Точка: использовать маркер-точку (не средняя пересечения)
    point = marker_point

    return {
        "age_point": _clamp_age(reference_year - point, 0, 105),
        "age_low": _clamp_age(reference_year - inter_high, 0, 105),
        "age_high": _clamp_age(reference_year - inter_low, 0, 105),
        "birth_point": point,
        "birth_low": inter_low,
        "birth_high": inter_high,
        "confidence": confidence,
        "source": source,
        "warnings": warnings,
        "fusion_version": FUSION_VERSION,
    }


def _fuse_marker_only(marker: dict, reference_year: int) -> dict:
    """Правило 4: только marker."""
    birth_low = marker["birth_year_low"]
    birth_high = marker["birth_year_high"]
    birth_point = marker.get("birth_year_point") or (birth_low + birth_high) // 2
    confidence = marker.get("confidence", 50)
    method = marker.get("method")

    # LLM-метод — слабый, cap conf 50
    if method == "llm":
        source = "llm"
        confidence = min(confidence, 50)
    else:
        source = "marker"

    return {
        "age_point": _clamp_age(reference_year - birth_point, 0, 105),
        "age_low": _clamp_age(reference_year - birth_high, 0, 105),
        "age_high": _clamp_age(reference_year - birth_low, 0, 105),
        "birth_point": birth_point,
        "birth_low": birth_low,
        "birth_high": birth_high,
        "confidence": confidence,
        "source": source,
        "warnings": [],
        "fusion_version": FUSION_VERSION,
    }


def _fuse_style_only(style: dict, reference_year: int) -> dict:
    """Правило 5: только style. Уверенность cap 70 (стиль без факта не выше 70)."""
    birth_point = style["birth_point"]
    birth_low = style.get("birth_year_low")
    birth_high = style.get("birth_year_high")
    confidence = min(style.get("confidence", 50), 70)

    # Если интервал не задан, вычислить из точки
    if birth_low is None or birth_high is None:
        span = 20  # ±10 лет
        birth_low = birth_point - span // 2
        birth_high = birth_point + span // 2

    return {
        "age_point": _clamp_age(reference_year - birth_point, 0, 105),
        "age_low": _clamp_age(reference_year - birth_high, 0, 105),
        "age_high": _clamp_age(reference_year - birth_low, 0, 105),
        "birth_point": birth_point,
        "birth_low": birth_low,
        "birth_high": birth_high,
        "confidence": confidence,
        "source": "style",
        "warnings": [],
        "fusion_version": FUSION_VERSION,
    }


def _clamp_age(value: int, min_val: int, max_val: int) -> int:
    """Зажать возраст в [min_val, max_val]."""
    return max(min_val, min(value, max_val))
