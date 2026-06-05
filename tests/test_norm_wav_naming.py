# -*- coding: utf-8 -*-
"""Именование normalized .wav по источнику + back-compat парсинга в cleanup.

Регресс: wav называется ``{call_id}__{источник}.wav`` (call_id префиксом для
уникальности и парсинга), чтобы при крахе массового прогона уже нормализованный
файл узнавался и не пере-нормализовался. ``watcher.cleanup_normalized`` парсит
call_id из имени и должен понимать и новое, и старое ``{call_id}.wav``.
"""
from pathlib import Path

from callprofiler.pipeline.orchestrator import _safe_stem, norm_wav_path


def test_name_includes_source_stem():
    p = norm_wav_path(Path("/n"), 18343, "REC 2021-03/Вася(IN).mp3")
    assert p.name.startswith("18343__")
    assert p.suffix == ".wav"
    # парсинг call_id обратно (как в cleanup_normalized)
    assert int(p.stem.split("__", 1)[0]) == 18343


def test_name_falls_back_to_call_id_when_no_source():
    assert norm_wav_path(Path("/n"), 7, None).name == "7.wav"
    assert norm_wav_path(Path("/n"), 7, "").name == "7.wav"


def test_legacy_plain_name_still_parses():
    # старое имя без "__" → split возвращает весь stem → int работает
    assert int(Path("7.wav").stem.split("__", 1)[0]) == 7


def test_safe_stem_strips_unsafe_chars_and_limits_length():
    s = _safe_stem("a/b:c*?<>|.mp3")
    assert "/" not in s and ":" not in s and "*" not in s
    assert len(_safe_stem("x" * 200)) <= 60
