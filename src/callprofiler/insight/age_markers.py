# -*- coding: utf-8 -*-
"""Детерминированные возрастные маркеры в репликах (Ф0/Ф1 плана age-estimation).

Чистые функции без БД/LLM. Каждый сигнал — интервал ГОДА РОЖДЕНИЯ: возраст
индексируется к дате звонка уже при извлечении, поэтому записанная оценка не
устаревает с приходом новых звонков (возраст «сейчас» = reference_year − birth).
Precision-first: сомнительный контекст (третье лицо, «мне 45 минут») → нет сигнала.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_QUOTE_MAX = 120
_QUOTE_PAD = 40  # контекст вокруг матча в цитате


@dataclass(frozen=True)
class AgeSignal:
    """Один возрастной сигнал: интервал года рождения + уверенность + evidence."""
    birth_low: int
    birth_high: int
    confidence: int
    quote: str
    signal: str
    dt: str
    method: str = "marker"  # 'marker' | 'relation' | 'llm'


# ── Прямые маркеры (контакт о себе) ─────────────────────────────────────────

_RE_DIRECT_DIGIT = re.compile(
    r"\bмне\s+(?:уже\s+|ещё\s+|еще\s+|только\s+)?(\d{1,2})\s*(?:лет|год(?:а|ов)?)\b",
    re.IGNORECASE,
)
_RE_TOLD_DIGIT = re.compile(
    r"\bмне\s+(?:вчера\s+|недавно\s+|вот\s+)?(?:исполнилось|исполнился|исполнится|стукнуло)\s+"
    r"(\d{1,2})\b",
    re.IGNORECASE,
)

_TENS = {"двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
         "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90}
_UNITS = {"один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5,
          "шесть": 6, "семь": 7, "восемь": 8, "девять": 9}
_RE_DIRECT_WORDS = re.compile(
    r"\bмне\s+(?:уже\s+|ещё\s+|еще\s+|только\s+)?(" + "|".join(_TENS) + r")"
    r"(?:\s+(" + "|".join(_UNITS) + r"))?\s*(?:лет|год(?:а|ов)?)\b",
    re.IGNORECASE,
)

_RE_BIRTH_YEAR = re.compile(r"\b(19[3-9]\d|200\d)\s*год[ау]?\s*рожден", re.IGNORECASE)

_RE_JUBILEE = re.compile(r"\b(\d{2})[-\s]?лети[ея]\b", re.IGNORECASE)
# Юбилей засчитываем только при явном «своём» контексте; чужие юбилеи — мимо
_RE_JUBILEE_SELF = re.compile(r"у\s+меня|мо[йёяе]\b|сво[йёяе]\b", re.IGNORECASE)
_RE_JUBILEE_NOT_PERSON = re.compile(
    r"свадьб|компани|завод|фирм|школ|город|организаци", re.IGNORECASE
)

# Этапные маркеры: (имя, regex, age_low, age_high, confidence) — диапазоны плана
_STAGES = [
    ("pension", re.compile(r"\bна\s+пенси[ию]\b|\bпенсионер", re.IGNORECASE), 60, 80, 65),
    ("grandkids", re.compile(r"\bвну[кч]\w*", re.IGNORECASE), 50, 85, 60),
    ("army_done", re.compile(
        r"\bпосле\s+армии|\bиз\s+армии\s+(?:пришёл|пришел|вернулся)|\bдембельну|\bдембеля\b",
        re.IGNORECASE), 20, 30, 60),
    ("student", re.compile(
        r"\bсесси[юи]\s+сда|\bв\s+универе|\bв\s+общаге|\bна\s+\w+\s+курсе\b",
        re.IGNORECASE), 17, 25, 65),
    ("school_exam", re.compile(r"\bЕГЭ\b", re.IGNORECASE), 16, 18, 70),
    ("school_finish", re.compile(
        r"\bшколу\s+заканчива|\bвыпускной\s+класс|\b11[-\s]?класс", re.IGNORECASE), 15, 18, 70),
]

# Третье лицо непосредственно перед маркером → реплика не о говорящем
_RE_THIRD_PERSON = re.compile(
    r"(?:мам[ае]?|пап[ае]?|сын[уа]?|доч(?:ь|ке|ка)|муж[у]?|жен[ае]|брат[у]?|сестр[ае]|"
    r"бабушк[ае]|дедушк[ае]|он|она|ему|ей|им|у\s+(?:него|неё|нее|них))\s*$",
    re.IGNORECASE,
)


def _year(call_dt) -> int | None:
    m = re.match(r"(\d{4})", str(call_dt or ""))
    if not m:
        return None
    y = int(m.group(1))
    return y if 1900 < y < 2100 else None


def _quote(text: str, m: re.Match) -> str:
    lo = max(0, m.start() - _QUOTE_PAD)
    hi = min(len(text), m.end() + _QUOTE_PAD)
    return " ".join(text[lo:hi].split())[:_QUOTE_MAX]


def _third_person(text: str, m: re.Match) -> bool:
    return bool(_RE_THIRD_PERSON.search(text[max(0, m.start() - 18):m.start()]))


def extract_marker_signals(text: str, call_dt) -> list[AgeSignal]:
    """Прямые + этапные маркеры из ОДНОЙ реплики контакта (speaker=OTHER)."""
    year = _year(call_dt)
    if year is None or not text:
        return []
    out: list[AgeSignal] = []
    dt = str(call_dt)

    for rex, conf in ((_RE_DIRECT_DIGIT, 90), (_RE_TOLD_DIGIT, 90), (_RE_DIRECT_WORDS, 88)):
        for m in rex.finditer(text):
            if _third_person(text, m):
                continue
            if rex is _RE_DIRECT_WORDS:
                age = _TENS[m.group(1).lower()] + _UNITS.get((m.group(2) or "").lower(), 0)
            else:
                age = int(m.group(1))
            if not 5 <= age <= 99:
                continue
            # ±1 год: день рождения в году звонка мог пройти или нет
            out.append(AgeSignal(year - age - 1, year - age, conf,
                                 _quote(text, m), "direct_age", dt))

    for m in _RE_BIRTH_YEAR.finditer(text):
        if _third_person(text, m):
            continue
        by = int(m.group(1))
        out.append(AgeSignal(by, by, 92, _quote(text, m), "birth_year", dt))

    for m in _RE_JUBILEE.finditer(text):
        ctx = text[max(0, m.start() - 30):m.end() + 30]
        if (_third_person(text, m) or not _RE_JUBILEE_SELF.search(ctx)
                or _RE_JUBILEE_NOT_PERSON.search(ctx)):
            continue
        age = int(m.group(1))
        if not 20 <= age <= 95:
            continue
        out.append(AgeSignal(year - age - 1, year - age, 78,
                             _quote(text, m), "jubilee", dt))

    for name, rex, alo, ahi, conf in _STAGES:
        m = rex.search(text)
        if not m or _third_person(text, m):
            continue
        out.append(AgeSignal(year - ahi, year - alo, conf, _quote(text, m), name, dt))

    return out


# ── Ф1: реляционные якоря (направление зависит от того, КТО говорит) ────────
# Смещение = возраст контакта − возраст владельца (лет): parent = +20..+35 и т.д.

_REL_OWNER_SAYS = [  # владелец обращается К КОНТАКТУ
    ("rel_parent", re.compile(r"\bмам\b|\bпап\b|\bмамул|\bпапул|\bмамочк|\bпапочк",
                              re.IGNORECASE), 20, 35, 70),
    ("rel_grandparent", re.compile(r"\bбабул|\bдедул|\bбабушк\b|\bдедушк",
                                   re.IGNORECASE), 40, 60, 65),
    ("rel_child", re.compile(r"\bсынок\b|\bсынул|\bдоч(?:а|еньк|урк)",
                             re.IGNORECASE), -35, -18, 65),
]
_REL_CONTACT_SAYS = [  # контакт обращается К ВЛАДЕЛЬЦУ (Сергей — мужчина)
    ("rel_is_parent", re.compile(r"\bсынок\b|\bсынул", re.IGNORECASE), 20, 35, 60),
    ("rel_is_child", re.compile(r"\bпап\b|\bпапул|\bбать\b|\bбатя\b",
                                re.IGNORECASE), -35, -18, 60),
]
_REL_SYMMETRIC = [  # любая сторона
    ("rel_classmate", re.compile(r"\bодноклассни|\bоднокурсни", re.IGNORECASE), -2, 2, 85),
    ("rel_army_mate", re.compile(r"служили\s+вместе|вместе\s+служили", re.IGNORECASE),
     -3, 3, 75),
]


def extract_relation_signals(owner_lines, contact_lines,
                             owner_birth_year: int) -> list[AgeSignal]:
    """Якоря «возраст контакта относительно владельца».

    owner_lines/contact_lines: [(text, call_dt)]. Якоря привязаны к году
    рождения владельца, а не к дате звонка → дата нужна только для evidence.
    owner_birth_year=0 → якоря выключены (план Ф1).
    """
    if not owner_birth_year:
        return []
    out: list[AgeSignal] = []

    def _scan(lines, table):
        for text, dt in lines:
            for name, rex, lo, hi, conf in table:
                m = rex.search(text or "")
                if m:
                    out.append(AgeSignal(owner_birth_year - hi, owner_birth_year - lo,
                                         conf, _quote(text, m), name, str(dt or ""),
                                         method="relation"))

    _scan(owner_lines, _REL_OWNER_SAYS)
    _scan(contact_lines, _REL_CONTACT_SAYS)
    _scan(list(owner_lines) + list(contact_lines), _REL_SYMMETRIC)
    return out
