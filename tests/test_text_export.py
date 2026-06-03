# -*- coding: utf-8 -*-
"""test_text_export.py — .txt-дамп транскрипта по ролям."""
from callprofiler.models import Segment
from callprofiler.transcribe.text_export import format_transcript, write_transcript


def test_format_roles():
    segs = [
        Segment(0, 1000, "привет", "UNKNOWN"),
        Segment(1000, 2000, "да", "OWNER"),
        Segment(2000, 3000, "нет", "OTHER"),
    ]
    assert format_transcript(segs) == "[?] привет\n[me] да\n[s2] нет\n"


def test_format_empty():
    assert format_transcript([]) == ""


def test_write_transcript_uses_source_stem(tmp_path):
    segs = [Segment(0, 1000, "строка", "UNKNOWN")]
    p = write_transcript(str(tmp_path), "Ivan_2026-06-03_in.mp3", segs)
    assert p is not None
    assert p.name == "Ivan_2026-06-03_in.txt"
    assert p.read_text(encoding="utf-8") == "[?] строка\n"


def test_write_transcript_disabled_when_no_dir():
    assert write_transcript("", "x.mp3", []) is None
