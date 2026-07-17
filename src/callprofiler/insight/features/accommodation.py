"""Lexical accommodation asymmetry (B6, ozalupennieStrategic5.md).

Per-call content-word overlap between OWNER and OTHER: does the contact echo
the owner's word choices more than the owner echoes the contact's (or the
reverse)? Positive value = contact accommodates the owner.
"""
import statistics

from .base import Feature, Tier, normalize_lemma, tokenize

_MIN_TOKEN_LEN = 4
_MIN_SET_SIZE = 20

_STOPWORDS = frozenset({
    "который", "чтобы", "просто", "давай", "сейчас", "потом", "здесь", "очень",
    "можно", "нужно", "будет", "есть", "этот", "такой", "такая", "такое",
    "тогда", "когда", "ничего", "что-то", "вообще", "короче", "понял",
    "поняла", "привет", "пока", "алло", "ага", "угу", "значит", "кстати",
    "например", "конечно", "спасибо", "пожалуйста", "слушай", "смотри",
    "говорю", "говорит",
})


def _content_words(text: str) -> set[str]:
    tokens = (normalize_lemma(t) for t in tokenize(text))
    return {t for t in tokens if len(t) >= _MIN_TOKEN_LEN and t not in _STOPWORDS}


def compute_accommodation(segments: list[dict], reference_now=None) -> dict[str, Feature]:
    """Медиана (align_contact − align_owner) по звонкам с достаточной лексикой.

    Args:
        segments: list[{"call_id","speaker","text"}].
        reference_now: не используется.

    Звонки с |content(OWNER)|<20 или |content(OTHER)|<20 пропускаются.

    Returns:
        {accommodation: Feature} если нашёлся хотя бы один учтённый звонок,
        иначе {}.
    """
    by_call: dict = {}
    for s in segments:
        by_call.setdefault(s.get("call_id"), []).append(s)

    deltas = []
    for segs in by_call.values():
        owner_text = " ".join(s.get("text") or "" for s in segs if s.get("speaker") == "OWNER")
        other_text = " ".join(s.get("text") or "" for s in segs if s.get("speaker") == "OTHER")
        a = _content_words(owner_text)
        b = _content_words(other_text)
        if len(a) < _MIN_SET_SIZE or len(b) < _MIN_SET_SIZE:
            continue
        inter = len(a & b)
        align_contact = inter / len(b)
        align_owner = inter / len(a)
        deltas.append(align_contact - align_owner)

    if not deltas:
        return {}

    return {
        "accommodation": Feature(
            value=statistics.median(deltas),
            support_n=len(deltas),
            tier=Tier.AFFECTIVE,
        )
    }
