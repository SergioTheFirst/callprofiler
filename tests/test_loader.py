# -*- coding: utf-8 -*-
"""
test_loader.py — тесты для bulk_load функции.
"""

import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from callprofiler.bulk.loader import _parse_segments
from callprofiler.models import Segment


class TestParseSegments:
    """Тесты парсинга сегментов из текста."""

    def test_parse_simple_segments(self):
        """Простое разбиение на сегменты."""
        text = "[me]: Привет\n[s2]: Привет!"
        segments = _parse_segments(text)
        assert len(segments) == 2
        assert segments[0].text == "Привет"
        assert segments[0].speaker == "OWNER"
        assert segments[1].text == "Привет!"
        assert segments[1].speaker == "OTHER"

    def test_parse_with_multiple_lines(self):
        """Сегменты с многострочным текстом."""
        text = "[me]: Привет, как дела?\nОсновной текст\n[s2]: Хорошо!"
        segments = _parse_segments(text)
        assert len(segments) == 2
        assert "как дела?" in segments[0].text
        assert segments[0].speaker == "OWNER"

    def test_parse_case_insensitive(self):
        """Теги нечувствительны к регистру."""
        text = "[ME]: Текст1\n[S2]: Текст2"
        segments = _parse_segments(text)
        assert len(segments) == 2
        assert segments[0].speaker == "OWNER"
        assert segments[1].speaker == "OTHER"

    def test_parse_with_whitespace(self):
        """Убирать whitespace вокруг текста."""
        text = "  [me]:   Текст1  \n\n[s2]:  Текст2  "
        segments = _parse_segments(text)
        assert segments[0].text == "Текст1"
        assert segments[1].text == "Текст2"

    def test_parse_empty_text(self):
        """Пустой текст → пустой список."""
        assert _parse_segments("") == []
        assert _parse_segments(None) == []

    def test_parse_no_markers(self):
        """Текст без маркеров → пустой список."""
        assert _parse_segments("просто текст") == []

    def test_parse_timing(self):
        """Проверить что timing правильно назначается."""
        text = "[me]: Текст1\n[s2]: Текст2\n[me]: Текст3"
        segments = _parse_segments(text)
        assert segments[0].start_ms == 0
        assert segments[0].end_ms == 100
        assert segments[1].start_ms == 100
        assert segments[1].end_ms == 200
        assert segments[2].start_ms == 200
        assert segments[2].end_ms == 300


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
