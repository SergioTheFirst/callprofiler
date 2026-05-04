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

_RU_TO_EN = str.maketrans(
    "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "ABVGDEEZHZIJKLMNOPRSTUFHTSCHSHSCH_Y_EYUYAabvgdeezhzijklmnoprstufhtschshsch_y_eyuya",
)

_TS_MAP = {"ТС": "TS", "Тс": "Ts", "тс": "ts", "Ц": "C", "ц": "c"}


def normalize_entity_key(canonical_name: str, entity_type: str) -> str:
    """Compute a deterministic, stable entity key.

    Returns something like:  person_ivan_petrov  or  company_ooo_romashka
    """
    canonical_name = canonical_name.strip()
    if not canonical_name:
        return f"{entity_type.lower()}_unknown"

    # Transliterate Cyrillic → Latin
    latin = canonical_name.translate(_RU_TO_EN)

    # Apply TS→C normalisation for common Russian consonant clusters
    for ru_pair, en_pair in _TS_MAP.items():
        latin = latin.replace(ru_pair, en_pair)

    # Normalize Unicode (decompose accents, etc.)
    latin = unicodedata.normalize("NFKD", latin)

    # Lowercase, strip punctuation and diacritics
    latin = latin.lower()
    latin = "".join(ch for ch in latin if ch.isalnum() or ch == "_")
    latin = re.sub(r"_+", "_", latin).strip("_")

    return f"{entity_type.lower()}_{latin}"


def normalize_canonical_name(name: str) -> str:
    """Return a normalized display form (title case, collapsed whitespace)."""
    if not name or not name.strip():
        return ""
    name = " ".join(name.split())
    return name.strip()