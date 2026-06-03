# -*- coding: utf-8 -*-
"""
text_export.py — читабельный .txt-дамп транскрипта (по ролям).

Чистые функции без тяжёлых зависимостей (только stdlib) — легко тестируются
и переиспользуются. БД остаётся источником истины; .txt — удобный артефакт
рядом (имя = имя исходного аудио, расширение → .txt).
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from callprofiler.models import Segment

# Роли спикеров → метки в тексте. На Stage-1 (без диаризации) всё [?].
ROLE_TAGS = {"OWNER": "[me]", "OTHER": "[s2]", "UNKNOWN": "[?]"}


def format_transcript(segments: Iterable["Segment"]) -> str:
    """Собрать транскрипт в текст: одна строка на сегмент, ``<роль> текст``."""
    lines = [f"{ROLE_TAGS.get(s.speaker, '[?]')} {s.text}" for s in segments]
    return ("\n".join(lines) + "\n") if lines else ""


def write_transcript(
    text_dir: str,
    source_filename: str,
    segments: Iterable["Segment"],
) -> Path | None:
    """Записать .txt в ``text_dir`` под именем исходника.

    Возвращает путь записанного файла или None, если ``text_dir`` пуст.
    """
    if not text_dir:
        return None
    stem = Path(source_filename).stem if source_filename else "transcript"
    out_dir = Path(text_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.txt"
    out_path.write_text(format_transcript(segments), encoding="utf-8")
    return out_path
