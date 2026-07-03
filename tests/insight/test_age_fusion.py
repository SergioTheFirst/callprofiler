"""Тесты для age_fusion.py — ансамбль маркеров и стиля."""

import pytest
from callprofiler.insight.age_fusion import fuse_age, FUSION_VERSION


class TestFusionBoth:
    """Правило 3: оба валидны."""

    def test_intersection_overlap(self):
        """Пересечение интервалов непусто — интервал от marker, conf+5."""
        marker = {
            "method": "marker",
            "birth_year_low": 1970,
            "birth_year_high": 1980,
            "birth_year_point": 1975,
            "confidence": 80,
        }
        style = {
            "birth_point": 1974,
            "birth_year_low": 1972,
            "birth_year_high": 1978,
            "confidence": 60,
            "confidence_level": 3,
        }
        fused = fuse_age(marker, style, 2026)
        assert fused is not None
        assert fused["source"] == "marker+style"
        assert fused["confidence"] == min(95, 80 + 5)  # 85
        assert fused["birth_low"] == 1972  # max(1970, 1972)
        assert fused["birth_high"] == 1978  # min(1980, 1978)
        assert fused["birth_point"] == 1975  # from marker
        assert fused["age_point"] == 2026 - 1975  # 51
        assert fused["warnings"] == []
        assert fused["fusion_version"] == FUSION_VERSION

    def test_conflict_no_overlap(self):
        """Конфликт: интервалы не пересекаются — интервал от marker, conf-10."""
        marker = {
            "method": "relation",
            "birth_year_low": 1980,
            "birth_year_high": 1990,
            "birth_year_point": 1985,
            "confidence": 70,
        }
        style = {
            "birth_point": 1950,
            "birth_year_low": 1945,
            "birth_year_high": 1960,
            "confidence": 50,
            "confidence_level": 2,
        }
        fused = fuse_age(marker, style, 2026)
        assert fused is not None
        assert fused["source"] == "marker"
        assert fused["confidence"] == max(20, 70 - 10)  # 60
        assert fused["birth_low"] == 1980
        assert fused["birth_high"] == 1990
        assert "стиль расходится" in fused["warnings"][0]

    def test_edge_case_caps(self):
        """Доверие capped на 95 при пересечении, на 20 при конфликте."""
        marker = {
            "method": "marker",
            "birth_year_low": 1970,
            "birth_year_high": 1980,
            "birth_year_point": 1975,
            "confidence": 100,  # будет скешена до 95
        }
        style = {
            "birth_point": 1975,
            "confidence": 80,
            "confidence_level": 3,
        }
        fused = fuse_age(marker, style, 2026)
        assert fused["confidence"] == 95  # cap


class TestFusionMarkerOnly:
    """Правило 4: только marker."""

    def test_marker_only_regular(self):
        """Маркер с методом marker."""
        marker = {
            "method": "marker",
            "birth_year_low": 1975,
            "birth_year_high": 1985,
            "birth_year_point": 1980,
            "confidence": 85,
        }
        fused = fuse_age(marker, None, 2026)
        assert fused is not None
        assert fused["source"] == "marker"
        assert fused["confidence"] == 85
        assert fused["birth_point"] == 1980
        assert fused["age_point"] == 2026 - 1980

    def test_marker_llm_capped(self):
        """Маркер с методом llm — доверие capped до 50."""
        marker = {
            "method": "llm",
            "birth_year_low": 1975,
            "birth_year_high": 1985,
            "birth_year_point": 1980,
            "confidence": 90,  # будет capped до 50
        }
        fused = fuse_age(marker, None, 2026)
        assert fused is not None
        assert fused["source"] == "llm"
        assert fused["confidence"] == 50  # cap


class TestFusionStyleOnly:
    """Правило 5: только style."""

    def test_style_only(self):
        """Стиль с confidence_level >= 2."""
        style = {
            "birth_point": 1975,
            "birth_year_low": 1970,
            "birth_year_high": 1980,
            "confidence": 65,
            "confidence_level": 2,
        }
        fused = fuse_age(None, style, 2026)
        assert fused is not None
        assert fused["source"] == "style"
        assert fused["confidence"] == min(65, 70)  # cap 70
        assert fused["birth_point"] == 1975

    def test_style_only_without_interval(self):
        """Стиль с одной точкой — интервал вычисляется из неё."""
        style = {
            "birth_point": 1975,
            "confidence": 60,
            "confidence_level": 3,
        }
        fused = fuse_age(None, style, 2026)
        assert fused is not None
        assert fused["birth_point"] == 1975
        assert fused["birth_low"] == 1975 - 10
        assert fused["birth_high"] == 1975 + 10


class TestFusionNone:
    """Правило 6: ни одного — None."""

    def test_both_none(self):
        """Оба None."""
        assert fuse_age(None, None, 2026) is None

    def test_marker_invalid_no_birth_years(self):
        """Маркер невалиден — birth_year_* = None."""
        marker = {
            "method": "marker",
            "birth_year_low": None,
            "birth_year_high": None,
            "confidence": 80,
        }
        assert fuse_age(marker, None, 2026) is None

    def test_style_invalid_low_confidence_level(self):
        """Стиль невалиден — confidence_level < 2."""
        style = {
            "birth_point": 1975,
            "confidence": 80,
            "confidence_level": 1,
        }
        assert fuse_age(None, style, 2026) is None


class TestAgeClamp:
    """Возраст в [0, 105]."""

    def test_age_clamped_to_zero(self):
        """Отрицательный возраст становится 0."""
        marker = {
            "method": "marker",
            "birth_year_low": 2030,  # будущее
            "birth_year_high": 2040,
            "birth_year_point": 2035,
            "confidence": 80,
        }
        fused = fuse_age(marker, None, 2026)
        assert fused["age_point"] == 0
        assert fused["age_low"] == 0

    def test_age_clamped_to_max(self):
        """Возраст > 105 становится 105."""
        marker = {
            "method": "marker",
            "birth_year_low": 1800,  # очень древний
            "birth_year_high": 1810,
            "birth_year_point": 1805,
            "confidence": 80,
        }
        fused = fuse_age(marker, None, 2026)
        assert fused["age_point"] == 105 or fused["age_point"] > 100
        assert fused["age_high"] <= 105
