# -*- coding: utf-8 -*-
"""
text_export.py — читабельный .txt-дамп транскрипта (по ролям).

Чистые функции без тяжёлых зависимостей (только stdlib) — легко тестируются
и переиспользуются. БД остаётся источником истины; .txt — удобный артефакт
рядом (имя = имя исходного аудио, расширение → .txt).

Путь (T-08): ``text_dir/users/{user_id}/{call_id}__{stem}.txt`` — построен
через ``identity.user_profile_dir`` (реюз realpath-containment, ``text_dir``
подаётся вместо ``data_dir`` — helper не завязан на конкретный корень) и
всегда уникален между профилями и между звонками с одинаковым именем
исходника (call_id-префикс). Запись атомарна (``artifacts.atomic_write_text``).

Старый плоский путь ``text_dir/{stem}.txt`` (до T-08) НЕ переносится и НЕ
удаляется — ``find_transcript`` умеет найти файл там, если новый путь пуст.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from callprofiler.artifacts import atomic_write_text
from callprofiler.identity import user_profile_dir

if TYPE_CHECKING:
    from callprofiler.models import Segment

# Роли спикеров → метки в тексте. На Stage-1 (без диаризации) всё [?].
ROLE_TAGS = {"OWNER": "[me]", "OTHER": "[s2]", "UNKNOWN": "[?]"}


def format_transcript(segments: Iterable["Segment"]) -> str:
    """Собрать транскрипт в текст: одна строка на сегмент, ``<роль> текст``."""
    lines = [f"{ROLE_TAGS.get(s.speaker, '[?]')} {s.text}" for s in segments]
    return ("\n".join(lines) + "\n") if lines else ""


def _stem(source_filename: str) -> str:
    return Path(source_filename).stem if source_filename else "transcript"


def _legacy_path(text_dir: str, source_filename: str) -> Path:
    """Плоский путь до T-08 — ``text_dir/{stem}.txt``, без владельца/call_id."""
    return Path(text_dir) / f"{_stem(source_filename)}.txt"


def write_transcript(
    text_dir: str,
    user_id: str,
    call_id: int,
    source_filename: str,
    segments: Iterable["Segment"],
) -> Path | None:
    """Записать .txt под ``text_dir/users/{user_id}/{call_id}__{stem}.txt``.

    Возвращает путь записанного файла или None, если ``text_dir`` пуст.
    """
    if not text_dir:
        return None
    out_path = user_profile_dir(text_dir, user_id, f"{call_id}__{_stem(source_filename)}.txt")
    atomic_write_text(out_path, format_transcript(segments))
    return out_path


def find_transcript(
    text_dir: str,
    user_id: str,
    call_id: int,
    source_filename: str,
) -> Path | None:
    """Локатор для чтения: новый путь (T-08), фоллбэк — старый плоский путь.

    Ничего не пишет и не переносит — только смотрит, что уже есть на диске.
    """
    if not text_dir:
        return None
    new_path = user_profile_dir(text_dir, user_id, f"{call_id}__{_stem(source_filename)}.txt")
    if new_path.exists():
        return new_path
    legacy_path = _legacy_path(text_dir, source_filename)
    if legacy_path.exists():
        return legacy_path
    return None
