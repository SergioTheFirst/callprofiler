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
    ("grandkids", re.compile(r"\bвну[кч](?!ово)\w*", re.IGNORECASE), 50, 85, 60),
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

# B3: Новые прямые маркеры (класс 3)
_RE_BORN_IN = re.compile(r"\bя\s+(?:родил(?:ся|ась)|рождён|рождена)\s+в\s+(\d{2,4})(?:-м)?\s*(?:году)?", re.IGNORECASE)
_RE_SINCE_YEAR = re.compile(r"\bя\s+(?:с\s+)?(\d{2})(?:-го)?\s+года\b", re.IGNORECASE)
_SLANG_NUMS = {"тридцатник": 30, "сорокет": 40, "сороковник": 40, "полтинник": 50, "полтос": 50}
_RE_AGE_SLANGNUM = re.compile(
    r"\bмне\s+(" + "|".join(re.escape(k) for k in _SLANG_NUMS) + r")", re.IGNORECASE)
_RE_AGE_APPROX = re.compile(
    r"\bмне\s+(?:уже\s+)?(?:под|за|к)\s+(тридцать|сорок|пятьдесят|шестьдесят|семьдесят)", re.IGNORECASE)

# B3: Год-якорные события (класс 2)
_RE_SCHOOL_FINISH_YEAR = re.compile(r"\bшколу\s+(?:за|о)конч\w+\s+в\s+(\d{2,4})", re.IGNORECASE)
_RE_UNI_ENTER_YEAR = re.compile(r"\bпоступ\w+\s+(?:в\s+\w+\s+)?в\s+(\d{4})", re.IGNORECASE)
_RE_UNI_FINISH_YEAR = re.compile(r"(?:за|о)конч\w+\s+(?:институт|универ\w*|вуз|академи\w+)\s+в\s+(\d{2,4})", re.IGNORECASE)
_RE_ARMY_YEAR = re.compile(r"(?:в\s+армию\s+(?:пошел|пошёл|призвали|забрали)|служил)\s+в\s+(\d{2,4})", re.IGNORECASE)

# "внуково" склоняется («Внукова», «Внуковом») — регэксп grandkids не всегда
# ловит суффикс; доп. гейт по контексту аэропорта/рейса.
_RE_GRANDKIDS_NOT = re.compile(r"внуково|аэропорт|рейс|прил[её]т|вылет|терминал", re.IGNORECASE)

# Третье лицо непосредственно перед маркером → реплика не о говорящем (Ф5: расширено)
_RE_THIRD_PERSON = re.compile(
    r"(?:мам[ае]?|пап[ае]?|сын\w*|доч(?:ь|к\w*)|муж[у]?|жен[ае]|брат[у]?|сестр[ае]|"
    r"бабушк[ае]|дедушк[ае]|он|она|ему|ей|им|реб[её]нк\w*|дет(?:и|ей|ям|ьми)|"
    r"учени\w*|классе\s+у|репетитор|внук\w*|внучк\w*|"
    r"у\s+(?:него|неё|нее|них|дочк|сына|детей|ребенка|реб[её]нка))\s*$",
    re.IGNORECASE,
)

# Ф5: гарды для специфичных маркеров
_RE_PENSION_FUTURE = re.compile(
    r"выйд[уе]\w*|через\s+\S+\s*(?:лет|год)|до\s+пенси|накоп|будущ|доживу|когда\s+вы[йи]д",
    re.IGNORECASE,
)
_RE_EXAM_NOT_SELF = re.compile(
    r"доч|сын|реб[её]нк|дет[еиь]|учени|классе\s+у|репетитор",
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
        if name == "grandkids" and _RE_GRANDKIDS_NOT.search(
                text[max(0, m.start() - 30):m.end() + 30]):
            continue
        # Ф5 гарды: pension-future, exam-not-self
        if name == "pension" and _RE_PENSION_FUTURE.search(
                text[max(0, m.start() - 40):m.end() + 20]):
            continue
        if name == "school_exam" and _RE_EXAM_NOT_SELF.search(
                text[max(0, m.start() - 30):m.end() + 30]):
            continue
        out.append(AgeSignal(year - ahi, year - alo, conf, _quote(text, m), name, dt))

    # B3: Новые прямые маркеры (класс 3)
    for m in _RE_BORN_IN.finditer(text):
        if _third_person(text, m):
            continue
        by = int(m.group(1))
        if 1930 <= by <= 2015:
            out.append(AgeSignal(by, by, 92, _quote(text, m), "born_in", dt))

    # B3: since_year (с NN-го года) — без глагола занятости
    for m in _RE_SINCE_YEAR.finditer(text):
        if _third_person(text, m):
            continue
        y2 = int(m.group(1))
        by = (1900 + y2) if y2 >= 30 else (2000 + y2)
        if 1930 <= by <= 2015:
            ctx = text[m.end():min(m.end() + 20, len(text))]
            if re.search(r"работ|живу|начал|учусь|служу", ctx, re.IGNORECASE):
                continue
            conf = 92 if "рожден" in text[max(0, m.start() - 50):m.end()] else 78
            out.append(AgeSignal(by, by, conf, _quote(text, m), "since_year", dt))

    # B3: age_slangnum (тридцатник, сорокет и т.д.)
    for m in _RE_AGE_SLANGNUM.finditer(text):
        if _third_person(text, m):
            continue
        age = _SLANG_NUMS.get(m.group(1).lower(), None)
        if age:
            out.append(AgeSignal(year - age - 1, year - age, 80, _quote(text, m), "age_slangnum", dt))

    # B3: age_approx (под/за/к + число)
    for m in _RE_AGE_APPROX.finditer(text):
        if _third_person(text, m):
            continue
        tens = _TENS.get(m.group(1).lower(), None)
        if tens:
            prefix = text[max(0, m.start()):m.start() + 6].lower()
            if "под" in prefix:
                alo, ahi = tens - 3, tens - 1
            elif "за" in prefix:
                alo, ahi = tens + 1, tens + 9
            else:  # "к"
                alo, ahi = tens - 3, tens - 1
            out.append(AgeSignal(year - ahi, year - alo, 65, _quote(text, m), "age_approx", dt))

    # B3: Год-якорные события (класс 2)
    for rex, (alo, ahi), conf, name in [
        (_RE_SCHOOL_FINISH_YEAR, (16, 18), 80, "school_finish_year"),
        (_RE_UNI_ENTER_YEAR, (16, 19), 70, "uni_enter_year"),
        (_RE_UNI_FINISH_YEAR, (21, 24), 70, "uni_finish_year"),
        (_RE_ARMY_YEAR, (18, 20), 70, "army_year"),
    ]:
        for m in rex.finditer(text):
            if _third_person(text, m):
                continue
            yy = int(m.group(1))
            by = (1900 + yy) if yy >= 30 else (2000 + yy)
            if 1945 <= by <= int(str(year or 2026)):
                birth_lo, birth_hi = year - ahi, year - alo
                out.append(AgeSignal(birth_lo, birth_hi, conf, _quote(text, m), name, dt))

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


# B4: KIN-арифметика: информация о своих родных контакта => возраст контакта
_RE_KIN_NOT = re.compile(r"тво|ваш|у\s+тебя|у\s+вас", re.IGNORECASE)
# «мне» в зазоре => речь о себе, не о возрасте ребёнка («дочь родилась, мне 30 лет»)
_RE_KIN_CHILD_AGE = re.compile(
    r"(?:доч\w*|сын\w*)\s*(?:у\s+(?:меня|нас)\s*)?(?:(?!мне).){0,12}?\b(\d{1,2})\s*"
    r"(?:лет|год\w*)\b", re.IGNORECASE)
_RE_KIN_PARENT_AGE = re.compile(
    r"(?:мам\w*|пап\w*|отц\w*|матер\w*)\s*(?:(?!мне).){0,10}?\b(\d{2})\s*(?:лет|год\w*)",
    re.IGNORECASE)
# Этапы жизни ребёнка контакта -> возраст ребёнка -> возраст контакта (+20..+40)
_RE_KIN_WORD = re.compile(r"\b(?:доч\w*|сын\w*|реб[её]нк\w*|дет(?:и|ей|ям|ьми))\b", re.IGNORECASE)
_KIN_STAGES = [  # (имя, regex этапа, возраст ребёнка lo..hi, conf)
    ("kin_child_stage", re.compile(r"садик|детсад|ясл[ия]", re.IGNORECASE), 2, 7, 55),
    ("kin_child_stage", re.compile(r"\bЕГЭ\b|выпускн|11[-\s]?класс", re.IGNORECASE), 16, 18, 60),
    ("kin_child_stage", re.compile(r"школ\w*|урок\w*", re.IGNORECASE), 7, 17, 55),
    ("kin_child_stage", re.compile(r"универ\w*|сесси[юи]|поступ\w*|институт", re.IGNORECASE), 17, 23, 55),
]
_RE_GRANDKID_WORD = re.compile(r"\bвну[кч](?!ово)\w*", re.IGNORECASE)
_RE_GRANDKID_CTX = re.compile(r"садик|детсад|школ|выпускн|родил|поступ", re.IGNORECASE)


def extract_kin_signals(text: str, call_dt) -> list[AgeSignal]:
    """B4: KIN-арифметика — информация о своих родных контакта.

    Гард: перед kin-словом в −25 символах НЕТ 'тво|ваш|у тебя|у вас' (чужие родные).
    Возвращает сигналы класса 2 (method='marker', priority 2).
    """
    year = _year(call_dt)
    if year is None or not text:
        return []
    out = []
    dt = str(call_dt)

    # kin_child_age: доч/сын + возраст => контакт = возраст ребёнка + [20..40]
    for m in _RE_KIN_CHILD_AGE.finditer(text):
        ctx_before = text[max(0, m.start() - 25):m.start()]
        if _RE_KIN_NOT.search(ctx_before):
            continue
        child_age = int(m.group(1))
        if 1 <= child_age <= 45:
            birth_lo = year - child_age - 40
            birth_hi = year - child_age - 20
            out.append(AgeSignal(birth_lo, birth_hi, 60, _quote(text, m), "kin_child_age", dt, method="marker"))

    # kin_child_stage: kin-слово + этап ребёнка в окне +30 => возраст ребёнка -> контакта
    for m in _RE_KIN_WORD.finditer(text):
        ctx_before = text[max(0, m.start() - 25):m.start()]
        if _RE_KIN_NOT.search(ctx_before):
            continue
        window = text[m.start():m.end() + 30]
        for name, rex, clo, chi, conf in _KIN_STAGES:
            if rex.search(window):
                out.append(AgeSignal(year - chi - 40, year - clo - 20, conf,
                                     _quote(text, m), name, dt, method="marker"))
                break  # один этап на kin-упоминание (первый по специфичности)

    # kin_grandchild: внук/внучка в этап-контексте => контакт 50-85 (бабушка/дед)
    for m in _RE_GRANDKID_WORD.finditer(text):
        ctx_before = text[max(0, m.start() - 25):m.start()]
        if _RE_KIN_NOT.search(ctx_before):
            continue
        window = text[max(0, m.start() - 30):m.end() + 30]
        if _RE_GRANDKIDS_NOT.search(window) or not _RE_GRANDKID_CTX.search(window):
            continue
        out.append(AgeSignal(year - 85, year - 50, 60, _quote(text, m),
                             "kin_grandchild", dt, method="marker"))

    # kin_parent_age: мам/пап + возраст (50-99) => контакт = родитель − [18..40]
    for m in _RE_KIN_PARENT_AGE.finditer(text):
        ctx_before = text[max(0, m.start() - 25):m.start()]
        if _RE_KIN_NOT.search(ctx_before):
            continue
        parent_age = int(m.group(1))
        if 50 <= parent_age <= 99:
            birth_lo = year - parent_age + 18
            birth_hi = year - parent_age + 40
            out.append(AgeSignal(birth_lo, birth_hi, 55, _quote(text, m), "kin_parent_age", dt, method="marker"))

    return out
