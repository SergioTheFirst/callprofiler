"""Emotional palette lexicon features (B4, ozalupennieStrategic5.md).

Lexicon files live under ``age_style/lexicons/`` (not ``features/lexicons/`` as
the spec text names) — reuses ``age_style.lexicons.load_lexicon`` unmodified
rather than adding a second lexicon directory/loader for one feature.
"""
from ..age_style.lexicons import load_lexicon
from .base import Feature, Tier, normalize_lemma, tokenize
from .lexical_age import lexicon_hits

_AXES = ("emo_anger", "emo_anxiety", "emo_joy", "emo_contempt")
_PER_MILLE = 1000


def compute_emotion_palette(segments: list[dict], reference_now=None) -> dict[str, Feature]:
    """Плотность 4 эмоциональных лексиконов на 1000 токенов речи контакта.

    Args:
        segments: list[{"speaker": str, "text": str}]
        reference_now: не используется (сигнатура унифицирована с другими фичами).

    Returns:
        {emo_anger|emo_anxiety|emo_joy|emo_contempt: Feature} если есть речь
        контакта, иначе {}. Оси без хитов возвращаются с value=0.0 (не
        опускаются) — стабильный набор ключей для dashboard/labels.
    """
    contact_segments = [s for s in segments if s.get("speaker") != "OWNER"]
    if not contact_segments:
        contact_segments = segments
    if not contact_segments:
        return {}

    tokens = []
    for seg in contact_segments:
        tokens.extend(tokenize(seg.get("text") or ""))
    if not tokens:
        return {}
    norm = [normalize_lemma(t) for t in tokens]
    total = len(norm)

    out = {}
    for axis in _AXES:
        stems = tuple(row[0] for row in load_lexicon(axis))
        hits = lexicon_hits(norm, stems)
        out[axis] = Feature(hits * _PER_MILLE / total, hits, Tier.AFFECTIVE)
    return out
