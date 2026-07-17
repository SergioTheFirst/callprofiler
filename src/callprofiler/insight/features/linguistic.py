"""Linguistic features: hedging, directives, questions, lexical diversity."""
import re

from .base import Feature, Tier, tokenize, count_markers

# Маркеры (lowercase)
HEDGE = {
    "наверное", "наверно", "возможно", "может", "кажется", "вроде", "типа",
    "посмотрим", "попробую", "постараюсь", "неуверен", "затрудняюсь"
}

DIRECTIVE = {
    "сделай", "сделайте", "нужно", "надо", "должен", "должны", "давай", "давайте",
    "пришли", "пришлите", "отправь", "отправьте", "перезвони", "перезвоните",
    "бери", "держи", "срочно", "обязательно"
}


def compute_linguistic(segments: list[dict], reference_now=None) -> dict[str, Feature]:
    """Считает лингвистические фичи по речи контакта (не OWNER).

    Args:
        segments: list[{"speaker": str, "text": str}]
        reference_now: не используется

    Returns:
        {name: Feature} с hedge_ratio, directive_ratio, question_ratio, lexical_ttr, mean_turn_words.
        Пустой вход или 0 слов → {}.
    """
    # Фильтруем речь контакта: speaker != "OWNER"; если нет — fallback на все
    contact_segments = [s for s in segments if s.get("speaker") != "OWNER"]
    if not contact_segments:
        contact_segments = segments

    if not contact_segments:
        return {}

    all_words = []
    all_texts = []
    question_count = 0
    total_segments = len(contact_segments)

    for seg in contact_segments:
        text = seg.get("text", "")
        words = tokenize(text)
        all_words.extend(words)
        all_texts.append(text)
        if "?" in text:
            question_count += 1

    if not all_words:
        return {}

    total_words = len(all_words)
    hedge_count = count_markers(all_words, HEDGE)
    directive_count = count_markers(all_words, DIRECTIVE)
    unique_words = len(set(all_words))

    result = {}

    # hedge_ratio
    result["hedge_ratio"] = Feature(
        value=hedge_count / total_words if total_words > 0 else 0.0,
        support_n=total_words,
        tier=Tier.ROBUST
    )

    # directive_ratio
    result["directive_ratio"] = Feature(
        value=directive_count / total_words if total_words > 0 else 0.0,
        support_n=total_words,
        tier=Tier.ROBUST
    )

    # question_ratio (по сегментам)
    result["question_ratio"] = Feature(
        value=question_count / total_segments if total_segments > 0 else 0.0,
        support_n=total_segments,
        tier=Tier.ROBUST
    )

    # lexical_ttr (тип-токен рацио)
    result["lexical_ttr"] = Feature(
        value=unique_words / total_words if total_words > 0 else 0.0,
        support_n=total_words,
        tier=Tier.ROBUST
    )

    # mean_turn_words (среднее слов в реплике контакта)
    result["mean_turn_words"] = Feature(
        value=total_words / total_segments if total_segments > 0 else 0.0,
        support_n=total_segments,
        tier=Tier.ROBUST
    )

    return result


_RE_REQUEST = re.compile(
    r"\b(прошу|попрошу|можешь|сможешь|мог бы|могла бы|сделай|скинь|отправь|"
    r"пришли|привези|принеси|помоги|выручи|одолжи|займи|подскажи|посмотри|"
    r"узнай|напомни)\b",
    re.I,
)


def compute_request_balance(segments: list[dict], reference_now=None) -> dict[str, Feature]:
    """B5: кто чаще просит — OTHER минус OWNER, нормировано на сумму хитов.

    UNKNOWN-сегменты пропускаются целиком (не в ту, не в другую корзину) —
    в отличие от остальных фич модуля тут нужны ОБЕ стороны раздельно, единый
    fallback-на-всё не подходит.

    Returns:
        {request_balance: Feature} если req_other+req_owner >= 3, иначе {}.
    """
    req_other = 0
    req_owner = 0
    for seg in segments:
        speaker = seg.get("speaker")
        if speaker not in ("OWNER", "OTHER"):
            continue
        hits = len(_RE_REQUEST.findall((seg.get("text") or "").lower()))
        if speaker == "OTHER":
            req_other += hits
        else:
            req_owner += hits

    total = req_other + req_owner
    if total < 3:
        return {}

    return {
        "request_balance": Feature(
            value=(req_other - req_owner) / total,
            support_n=total,
            tier=Tier.ROBUST,
        )
    }
