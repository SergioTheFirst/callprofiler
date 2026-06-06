"""Feature primitives shared by all insight feature modules."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Tier(str, Enum):
    IMMUNE = "immune"        # metadata — ASR-неуязвимо
    ROBUST = "robust"        # агрегаты служебных слов
    AFFECTIVE = "affective"  # из LLM-анализа
    FRAGILE = "fragile"      # зависит от диаризации


@dataclass(frozen=True)
class Feature:
    value: float
    support_n: int
    tier: Tier


_FMTS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")


def parse_dt(s):
    """Парсит call_datetime (ISO/пробел/T/дата). None при пустом/мусоре."""
    if not s:
        return None
    s = s.strip().replace("T", " ")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in _FMTS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
