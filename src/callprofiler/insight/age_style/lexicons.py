# -*- coding: utf-8 -*-
"""Загрузчик лексиконов age_style (данные — lexicons/*.txt, не код; Ф2 плана age.md)."""
from pathlib import Path

from ..features.base import normalize_lemma

_DIR = Path(__file__).resolve().parent / "lexicons"
_CACHE: dict[str, tuple[tuple[str, ...], ...]] = {}


def load_lexicon(name: str) -> tuple[tuple[str, ...], ...]:
    """Читает `<name>.txt`: TAB-разделённые строки, `#`-комментарии/пустые пропущены.

    Каждая строка → tuple колонов (первая — стем, ё→е+lower). Стем, начинающийся с `=`,
    означает точное совпадение токена (без startswith). Флаг `=` сохраняется в стеме
    для использования в _stem_hit (lexical_age.py).
    Кэшируется по имени (лексиконы неизменны в рантайме).
    """
    if name in _CACHE:
        return _CACHE[name]
    path = _DIR / f"{name}.txt"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = [c.strip() for c in line.split("\t")]
        stem = cols[0].lower()
        exact_prefix = ""
        if stem.startswith("="):
            exact_prefix = "="
            stem = stem[1:]
        cols[0] = exact_prefix + normalize_lemma(stem)
        rows.append(tuple(cols))
    result = tuple(rows)
    _CACHE[name] = result
    return result
