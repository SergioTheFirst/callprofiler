# -*- coding: utf-8 -*-
"""
analyze/transcript_format.py — единый role-tagged формат стенограммы (R-05).

До этого было три несовместимых формата: ``pipeline/orchestrator._format_transcript``
(``[MM:SS] SPEAKER: текст``), ``bulk/enricher._format_transcript``
(``[Я]/[Собеседник]``) и bare-склейка в ``graph/builder`` (вообще без ролей).
``FactValidator._detect_speaker_context`` ищет маркеры ``[me]``/``[s2]`` —
поэтому в боевом пути speaker у КАЖДОГО факта выходил ``unknown``, а
grounding-контракт §3.2 (кто именно сказал цитату) не работал нигде, кроме
replay. Один формат — одна проверяемая привязка роли.

Формат: одна строка на сегмент, в порядке ``start_ms``:
``[me] текст`` (OWNER) · ``[s2] текст`` (OTHER) · ``[?] текст`` (UNKNOWN/прочее).
"""

from __future__ import annotations

from typing import Any, Iterable

_MARKERS = {"OWNER": "[me]", "OTHER": "[s2]"}


def _field(seg: Any, name: str, default: Any = None) -> Any:
    """Сегмент бывает dict (repo.get_transcript) и dataclass Segment — оба пути общие."""
    if isinstance(seg, dict):
        return seg.get(name, default)
    try:
        return seg[name]  # sqlite3.Row
    except (TypeError, IndexError, KeyError):
        return getattr(seg, name, default)


def format_role_tagged(segments: Iterable[Any]) -> str:
    """Собрать role-tagged стенограмму из сегментов (dict | Segment | sqlite3.Row)."""
    items = []
    for seg in segments or []:
        text = (_field(seg, "text", "") or "").strip()
        if not text:
            continue
        start = _field(seg, "start_ms", 0) or 0
        try:
            start = int(start)
        except (TypeError, ValueError):
            start = 0
        speaker = str(_field(seg, "speaker", "") or "").upper()
        items.append((start, len(items), _MARKERS.get(speaker, "[?]"), text))
    items.sort(key=lambda t: (t[0], t[1]))
    return "\n".join(f"{marker} {text}" for _, _, marker, text in items)


def load_role_tagged(conn, call_id: int) -> str | None:
    """Прочитать сегменты звонка и вернуть role-tagged текст (``None``, если их нет)."""
    rows = conn.execute(
        "SELECT text, speaker, start_ms FROM transcripts WHERE call_id = ? ORDER BY start_ms",
        (call_id,),
    ).fetchall()
    if not rows:
        return None
    return format_role_tagged(rows) or None
