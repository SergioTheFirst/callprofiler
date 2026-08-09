# -*- coding: utf-8 -*-
"""test_text_export.py — .txt-дамп транскрипта по ролям (T-08: атомарно, tenant-safe)."""
from callprofiler.models import Segment
from callprofiler.transcribe.text_export import (
    find_transcript,
    format_transcript,
    write_transcript,
)


def test_format_roles():
    segs = [
        Segment(0, 1000, "привет", "UNKNOWN"),
        Segment(1000, 2000, "да", "OWNER"),
        Segment(2000, 3000, "нет", "OTHER"),
    ]
    assert format_transcript(segs) == "[?] привет\n[me] да\n[s2] нет\n"


def test_format_empty():
    assert format_transcript([]) == ""


def test_write_transcript_path_includes_user_and_call_id(tmp_path):
    segs = [Segment(0, 1000, "строка", "UNKNOWN")]
    p = write_transcript(str(tmp_path), "me", 42, "Ivan_2026-06-03_in.mp3", segs)
    assert p is not None
    assert p.name == "42__Ivan_2026-06-03_in.txt"
    assert p.parent.name == "me"
    assert p.read_text(encoding="utf-8") == "[?] строка\n"


def test_write_transcript_disabled_when_no_dir():
    assert write_transcript("", "me", 1, "x.mp3", []) is None


def test_two_users_same_source_filename_do_not_collide(tmp_path):
    segs_a = [Segment(0, 1000, "от alice", "UNKNOWN")]
    segs_b = [Segment(0, 1000, "от bob", "UNKNOWN")]
    pa = write_transcript(str(tmp_path), "alice", 1, "audio.mp3", segs_a)
    pb = write_transcript(str(tmp_path), "bob", 1, "audio.mp3", segs_b)
    assert pa != pb
    assert pa.read_text(encoding="utf-8") == "[?] от alice\n"
    assert pb.read_text(encoding="utf-8") == "[?] от bob\n"


def test_same_user_two_calls_same_source_filename_do_not_collide(tmp_path):
    segs_1 = [Segment(0, 1000, "первый", "UNKNOWN")]
    segs_2 = [Segment(0, 1000, "второй", "UNKNOWN")]
    p1 = write_transcript(str(tmp_path), "me", 1, "audio.mp3", segs_1)
    p2 = write_transcript(str(tmp_path), "me", 2, "audio.mp3", segs_2)
    assert p1 != p2
    assert p1.read_text(encoding="utf-8") == "[?] первый\n"
    assert p2.read_text(encoding="utf-8") == "[?] второй\n"


def test_write_transcript_idempotent_rerun(tmp_path):
    segs = [Segment(0, 1000, "строка", "UNKNOWN")]
    p1 = write_transcript(str(tmp_path), "me", 1, "audio.mp3", segs)
    p2 = write_transcript(str(tmp_path), "me", 1, "audio.mp3", segs)
    assert p1 == p2
    assert p1.read_text(encoding="utf-8") == "[?] строка\n"


def test_find_transcript_locates_new_path(tmp_path):
    segs = [Segment(0, 1000, "строка", "UNKNOWN")]
    write_transcript(str(tmp_path), "me", 7, "audio.mp3", segs)
    found = find_transcript(str(tmp_path), "me", 7, "audio.mp3")
    assert found is not None
    assert found.read_text(encoding="utf-8") == "[?] строка\n"


def test_find_transcript_falls_back_to_legacy_flat_path(tmp_path):
    # Симуляция файла, написанного ДО T-08 (плоский путь, без user/call_id).
    legacy = tmp_path / "audio.txt"
    legacy.write_text("[?] старый формат\n", encoding="utf-8")
    found = find_transcript(str(tmp_path), "me", 99, "audio.mp3")
    assert found == legacy
    assert found.read_text(encoding="utf-8") == "[?] старый формат\n"


def test_find_transcript_none_when_neither_path_exists(tmp_path):
    assert find_transcript(str(tmp_path), "me", 1, "audio.mp3") is None


def test_find_transcript_disabled_when_no_dir():
    assert find_transcript("", "me", 1, "x.mp3") is None
