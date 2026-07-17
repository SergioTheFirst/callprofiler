"""Style drift over years — FRAGILE, gated (B8, ozalupennieStrategic5.md).

Live per-contact computation (dashboard reads, never writes) — cheap for one
contact, reuses existing age_style feature functions instead of a new pass.
"""
import numpy as np

from ..features.base import tokenize
from ..features.formality import compute_formality
from ..features.lexical_age import slang_density
from ..features.readability_age import mean_syllables_per_word

_UNKNOWN_SHARE_GATE = 0.4
_TREND_RATIO_GATE = 0.25
_MAX_PHRASES = 2
_SUFFIX = " (осторожная оценка по стилю)"

_PHRASES = {
    "slang": {"down": "сленга в речи становится меньше",
              "up": "сленга в речи становится больше"},
    "syllables": {"up": "речь становится тяжелее и формальнее",
                  "down": "речь становится легче и проще"},
    "vy": {"up": "переходит на более официальное «вы»",
           "down": "переходит на более неформальное «ты»"},
}


def _trend(values: list[float]) -> tuple[float, float]:
    """(|Δ за период| / диапазон значений, знак Δ) — (0, 0) при нулевом диапазоне."""
    value_range = max(values) - min(values)
    if value_range <= 0:
        return 0.0, 0.0
    x = list(range(len(values)))
    slope, _ = np.polyfit(x, values, 1)
    delta = slope * (len(values) - 1)
    return abs(delta) / value_range, delta


def style_drift(conn, user_id: str, contact_id: int,
                 min_tokens_per_year: int = 500, min_years: int = 3) -> list[str]:
    """До 2 фраз о дрейфе стиля речи контакта по годам (slang/слоги/вы-ты).

    Гейт FRAGILE: доля UNKNOWN-сегментов контакта >40% -> []. Мало
    качественных лет (<min_years с >=min_tokens_per_year токенов OTHER
    каждый) -> []. Каждая фраза — display-only оценка, не факт.
    """
    rows = conn.execute(
        """SELECT strftime('%Y', c.call_datetime) AS year, t.speaker, t.text
             FROM transcripts t JOIN calls c ON c.call_id = t.call_id
            WHERE c.user_id = ? AND c.contact_id = ? AND c.call_datetime IS NOT NULL""",
        (user_id, contact_id),
    ).fetchall()
    if not rows:
        return []

    unknown_share = sum(1 for r in rows if r["speaker"] == "UNKNOWN") / len(rows)
    if unknown_share > _UNKNOWN_SHARE_GATE:
        return []

    by_year: dict[str, list[dict]] = {}
    for r in rows:
        if r["speaker"] != "OTHER" or not r["year"]:
            continue
        by_year.setdefault(r["year"], []).append({"speaker": "OTHER", "text": r["text"]})

    years = sorted(
        y for y, segs in by_year.items()
        if sum(len(tokenize(s["text"])) for s in segs) >= min_tokens_per_year
    )
    if len(years) < min_years:
        return []

    slang_vals, syll_vals, vy_vals = [], [], []
    for y in years:
        segs = by_year[y]
        tokens = [tok for s in segs for tok in tokenize(s["text"])]
        slang_vals.append(slang_density(tokens).value)
        syll_vals.append(mean_syllables_per_word(tokens).value)
        vy_feat = compute_formality(segs).get("vy_ratio")
        vy_vals.append(vy_feat.value if vy_feat else 0.0)

    candidates = []
    for name, values in (("slang", slang_vals), ("syllables", syll_vals), ("vy", vy_vals)):
        ratio, delta = _trend(values)
        if ratio >= _TREND_RATIO_GATE:
            direction = "up" if delta > 0 else "down"
            candidates.append((ratio, _PHRASES[name][direction] + _SUFFIX))

    candidates.sort(key=lambda c: c[0], reverse=True)
    return [phrase for _, phrase in candidates[:_MAX_PHRASES]]
