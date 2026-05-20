# -*- coding: utf-8 -*-
"""
graph/entity_normalizer.py — deterministic entity key normalization.

Replaces LLM-generated normalized_key with a stable Python implementation.
RU → EN transliteration, case folding, punctuation stripping, canonical order.

Canonical key = entity_type + "_" + normalized_canonical_name
"""

from __future__ import annotations

import re
import unicodedata

# Таблица транслитерации кириллица → латиница
_RU_TRANSLIT: dict[str, str] = {
    "А": "A",
    "Б": "B",
    "В": "V",
    "Г": "G",
    "Д": "D",
    "Е": "E",
    "Ё": "E",
    "Ж": "ZH",
    "З": "Z",
    "И": "I",
    "Й": "Y",
    "К": "K",
    "Л": "L",
    "М": "M",
    "Н": "N",
    "О": "O",
    "П": "P",
    "Р": "R",
    "С": "S",
    "Т": "T",
    "У": "U",
    "Ф": "F",
    "Х": "KH",
    "Ц": "TS",
    "Ч": "CH",
    "Ш": "SH",
    "Щ": "SHCH",
    "Ъ": "",
    "Ы": "Y",
    "Ь": "",
    "Э": "E",
    "Ю": "YU",
    "Я": "YA",
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def _transliterate(text: str) -> str:
    """Транслитерировать кириллицу в латиницу (char-by-char)."""
    return "".join(_RU_TRANSLIT.get(ch, ch) for ch in text)


def normalize_entity_key(canonical_name: str, entity_type: str) -> str:
    """Compute a deterministic, stable entity key.

    Returns something like:  person_ivan_petrov  or  company_ooo_romashka
    """
    canonical_name = canonical_name.strip()
    if not canonical_name:
        return f"{entity_type.lower()}_unknown"

    # Transliterate Cyrillic → Latin
    latin = _transliterate(canonical_name)

    # Normalize Unicode (decompose accents, etc.)
    latin = unicodedata.normalize("NFKD", latin)

    # Lowercase, strip punctuation and diacritics
    latin = latin.lower()
    latin = "".join(ch for ch in latin if ch.isalnum() or ch in (" ", "_", "-"))
    latin = re.sub(r"[\s\-]+", "_", latin)
    latin = re.sub(r"_+", "_", latin).strip("_")

    return f"{entity_type.lower()}_{latin}"


def normalize_canonical_name(name: str) -> str:
    """Return a normalized display form (title case, collapsed whitespace)."""
    if not name or not name.strip():
        return ""
    name = " ".join(name.split())
    return name.strip()
