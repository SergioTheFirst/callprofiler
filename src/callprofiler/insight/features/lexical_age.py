# -*- coding: utf-8 -*-
"""Лексические возрастные признаки — Л1/Л2/Т1/Т2 (vozrast.md §3.1/§3.8, Ф2 плана age.md).

Матч по лексиконам через token.startswith(стем) — без pymorphy2 (Жёсткое
решение #4: numpy+regex only). Т1/Т2 несут кластер/год, не скаляр — Feature
не подходит, возвращаются отдельные структуры (dict/tuple).
"""
from collections import Counter

from ..age_style.lexicons import load_lexicon
from .base import Feature, Tier, normalize_lemma

_PER_MILLE = 1000


def _stem_hit(token: str, stem: str) -> bool:
    """Проверка совпадения токена со стемом.

    Если стем начинается с `=`, делает точное сравнение; иначе startswith.
    """
    if stem.startswith("="):
        return token == stem[1:]
    return token.startswith(stem)


def lexicon_hits(tokens_norm: list[str], stems: tuple[str, ...]) -> int:
    """Универсальный счётчик хитов для uni/bigrams в лексиконе.

    Для каждого стема:
    - если в нём нет пробела (юниграмма): матчить _stem_hit(token, stem)
    - если в нём пробел (биграмма): матчить пару соседних токенов точным сравнением

    Args:
        tokens_norm: список нормализованных токенов
        stems: кортеж стемов (некоторые могут содержать пробел)

    Returns:
        количество найденных хитов (юниграмм + биграмм)
    """
    if not tokens_norm:
        return 0

    hits = 0
    used_indices = set()  # track indices used in bigram matches to avoid re-use

    for i, t in enumerate(tokens_norm):
        if i in used_indices:
            continue
        for stem in stems:
            if ' ' not in stem:
                # юниграмма
                if _stem_hit(t, stem):
                    hits += 1
                    break
            else:
                # биграмма: две части разделены пробелом
                parts = stem.split(' ', 1)
                if len(parts) == 2:
                    part1, part2 = parts
                    # убираем префикс = если есть
                    p1_exact = part1.startswith('=')
                    p1_stem = part1[1:] if p1_exact else part1
                    p2_exact = part2.startswith('=')
                    p2_stem = part2[1:] if p2_exact else part2

                    # ищем соседнюю пару
                    if i + 1 < len(tokens_norm):
                        t_next = tokens_norm[i + 1]
                        # обе части матчатся точно (независимо от =)
                        if t == p1_stem and t_next == p2_stem:
                            hits += 1
                            used_indices.add(i)
                            used_indices.add(i + 1)
                            break

    return hits


def _distinct_stems(tokens_norm: list[str], stems: tuple[str, ...]) -> int:
    """Счётчик РАЗНЫХ стемов, которые нашлись в текстё.

    Нужен для гейта ≥2 разных стемов в life_stage/realia.
    """
    if not tokens_norm:
        return 0

    found_stems = set()

    for i, t in enumerate(tokens_norm):
        for stem in stems:
            if ' ' not in stem:
                # юниграмма
                if _stem_hit(t, stem):
                    found_stems.add(stem)
                    break
            else:
                # биграмма
                parts = stem.split(' ', 1)
                if len(parts) == 2 and i + 1 < len(tokens_norm):
                    part1, part2 = parts
                    p1_exact = part1.startswith('=')
                    p1_stem = part1[1:] if p1_exact else part1
                    p2_exact = part2.startswith('=')
                    p2_stem = part2[1:] if p2_exact else part2

                    t_next = tokens_norm[i + 1]
                    if t == p1_stem and t_next == p2_stem:
                        found_stems.add(stem)
                        break

    return len(found_stems)


def _density(tokens: list[str], stems: tuple) -> Feature:
    """Плотность лексических признаков (юни/бигарммы).

    Возвращает Feature с support_n = количество хитов (не длина нормализованного текста).
    Это изменение с B2: для слэнга/архаизмов гейт теперь на хиты, не на корпус.
    """
    if not tokens:
        return Feature(0.0, 0, Tier.IMMUNE)
    norm = [normalize_lemma(t) for t in tokens]
    hits = lexicon_hits(norm, stems)
    if hits == 0:
        return Feature(0.0, 0, Tier.IMMUNE)
    # Плотность на 1000 слов, но support_n теперь = количество хитов
    return Feature(hits * _PER_MILLE / len(norm), hits, Tier.IMMUNE)


def slang_density(tokens: list[str]) -> Feature:
    """Л1: молодёжный/интернет-сленг на 1000 слов. ↓ с возрастом, однонаправленный."""
    stems = tuple(row[0] for row in load_lexicon("slang"))
    return _density(tokens, stems)


def archaism_density(tokens: list[str]) -> Feature:
    """Л2: архаизмы/советизмы на 1000 слов. ↑ с возрастом, однонаправленный."""
    stems = tuple(row[0] for row in load_lexicon("archaisms"))
    return _density(tokens, stems)


def kancelyarit_density(tokens: list[str]) -> Feature:
    """Л6: канцелярит/официоз на 1000 слов. ↑ с возрастом, однонаправленный."""
    stems = tuple(row[0] for row in load_lexicon("kancelyarit"))
    return _density(tokens, stems)


def life_stage_profile(tokens: list[str]) -> dict:
    """Т1: доминирующий кластер жизненного этапа (ключ строки Т-Л6) + плотность.

    Гейт: доминирующий кластер засчитывается только если в нём ≥2 попаданий И
    ≥2 РАЗНЫХ стемов (родитель, один раз сказавший «школа», отсекается).

    Returns:
        {"cluster": str|None, "density": Feature}
    """
    rows = load_lexicon("life_stage")
    norm = [normalize_lemma(t) for t in tokens]
    counts: Counter = Counter()
    cluster_stems: dict[str, set[str]] = {}  # track distinct stems per cluster

    for i, t in enumerate(norm):
        for stem, cluster in rows:
            matched = False
            if ' ' not in stem:
                # юниграмма
                if _stem_hit(t, stem):
                    matched = True
            else:
                # биграмма
                parts = stem.split(' ', 1)
                if len(parts) == 2 and i + 1 < len(norm):
                    part1, part2 = parts
                    p1_exact = part1.startswith('=')
                    p1_stem = part1[1:] if p1_exact else part1
                    p2_exact = part2.startswith('=')
                    p2_stem = part2[1:] if p2_exact else part2

                    t_next = norm[i + 1]
                    if t == p1_stem and t_next == p2_stem:
                        matched = True

            if matched:
                counts[cluster] += 1
                if cluster not in cluster_stems:
                    cluster_stems[cluster] = set()
                cluster_stems[cluster].add(stem)
                break

    if not counts or not norm:
        return {"cluster": None, "density": Feature(0.0, 0, Tier.IMMUNE)}

    cluster, hits = counts.most_common(1)[0]
    distinct_stems = len(cluster_stems.get(cluster, set()))

    # Гейт: ≥2 попаданий И ≥2 разных стемов
    if hits < 2 or distinct_stems < 2:
        return {"cluster": None, "density": Feature(0.0, 0, Tier.IMMUNE)}

    return {"cluster": cluster, "density": Feature(hits / len(norm), hits, Tier.IMMUNE)}


def realia_birth_year(tokens: list[str]) -> tuple[int, int] | None:
    """Т2: доминирующая поколенческая реалия → (birth_low, birth_high), либо None.

    Засчитывается только при ≥2 попаданиях И ≥2 разных стемах доминирующей эпохи.
    """
    rows = load_lexicon("realia_by_epoch")
    norm = [normalize_lemma(t) for t in tokens]
    counts: Counter = Counter()
    year_stems: dict[tuple[int, int], set[str]] = {}  # track distinct stems per year range

    for i, t in enumerate(norm):
        for stem, lo, hi in rows:
            matched = False
            year_range = (int(lo), int(hi))

            if ' ' not in stem:
                # юниграмма
                if _stem_hit(t, stem):
                    matched = True
            else:
                # биграмма
                parts = stem.split(' ', 1)
                if len(parts) == 2 and i + 1 < len(norm):
                    part1, part2 = parts
                    p1_exact = part1.startswith('=')
                    p1_stem = part1[1:] if p1_exact else part1
                    p2_exact = part2.startswith('=')
                    p2_stem = part2[1:] if p2_exact else part2

                    t_next = norm[i + 1]
                    if t == p1_stem and t_next == p2_stem:
                        matched = True

            if matched:
                counts[year_range] += 1
                if year_range not in year_stems:
                    year_stems[year_range] = set()
                year_stems[year_range].add(stem)
                break

    if not counts:
        return None

    year_range, hits = counts.most_common(1)[0]
    if hits >= 2:  # доминирующая эпоха подтверждена повтором
        return year_range

    # Одиночные хиты РАЗНЫХ стемов: согласие эпох = пересечение интервалов
    # («дискотека» 1945-80 + «пейджер» 1960-82 -> 1960-80). Дизъюнктные -> None.
    total_hits = sum(counts.values())
    distinct = set()
    for stems in year_stems.values():
        distinct |= stems
    if total_hits < 2 or len(distinct) < 2:
        return None
    lo = max(r[0] for r in counts)
    hi = min(r[1] for r in counts)
    return (lo, hi) if lo <= hi else None
