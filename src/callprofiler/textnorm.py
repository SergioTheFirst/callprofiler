# -*- coding: utf-8 -*-
"""
textnorm.py — шум-доктрина: нормализованный quote-гейт (Fable §4.1).

ОДИН хелпер для всех verbatim-гейтов («quote — подстрока источника»): сырой
substring-чек режет валидные находки на каждой ASR-вариации пунктуации/регистра/ё.
Сырой quote при этом ВСЕГДА хранится и показывается как вернула модель
(дословность для владельца) — norm_quote только для проверки присутствия.
"""

from __future__ import annotations

import re

_RE_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_RE_SPACES = re.compile(r"\s+")


def norm_quote(s: str) -> str:
    """lower → ё→е → убрать пунктуацию → схлопнуть пробелы."""
    s = (s or "").lower().replace("ё", "е")
    s = _RE_PUNCT.sub("", s)
    return _RE_SPACES.sub(" ", s).strip()
