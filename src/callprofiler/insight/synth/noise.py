"""Реалистичный ASR-шум для проверки устойчивости фич.

Модели ошибок: выпадение коротких частиц, транспозиция соседних букв,
гомофон-подмена. Детерминирован по seed.
"""
import random

# короткие слова-частицы, которые ASR часто глотает
_DROPPABLE = {"и", "а", "но", "же", "ли", "бы", "ну", "вот", "так", "уж", "то"}
# частые гомофоны/смешения в русском ASR
_HOMOPHONES = {
    "что": "што", "его": "ево", "сейчас": "щас", "тоже": "тож",
    "когда": "када", "сколько": "скока", "конечно": "конешно",
}


def _perturb_word(w, rng):
    if len(w) < 4:
        return w
    i = rng.randrange(1, len(w) - 1)
    chars = list(w)
    chars[i], chars[i + 1] = chars[i + 1], chars[i]  # transposition
    return "".join(chars)


def inject_asr_noise(text: str, rate: float = 0.2, seed: int = 0) -> str:
    if rate <= 0:
        return text
    rng = random.Random(seed)
    out = []
    for w in text.split():
        low = w.lower()
        if low in _DROPPABLE and rng.random() < rate:
            continue  # выпадение частицы
        if low in _HOMOPHONES and rng.random() < rate:
            out.append(_HOMOPHONES[low])
            continue
        if rng.random() < rate:
            out.append(_perturb_word(w, rng))
            continue
        out.append(w)
    return " ".join(out)
