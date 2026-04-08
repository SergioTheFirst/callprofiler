# -*- coding: utf-8 -*-
"""
filename_parser.py — парсинг имён аудиофайлов в CallMetadata (5 форматов).

Поддерживаемые форматы:
  1. Номер с дефисами + дубль в скобках:
     007496451-07-97(0074964510797)_20240925154220
  2. 8(код)номер + дубль в скобках:
     8(495)197-87-11(84951978711)_20240502164535
  3. 8 без скобок вокруг кода:
     8496451-07-97(84964510797)_20240502170140
  4. Имя контакта + номер в скобках:
     Алштейндлештейн онвел(0079252475209)_20230925135064
     Вызов@Ира дледлир(007925291-85-95)_20170828123145
  5. Только имя + дата (старые записи):
     Варлакаув Хрюн 2009_09_03 21_05_57
     (телефон отсутствует)

Сервисные номера (короткие, 3-4 цифры):
  900(900)_20231009112764
  0500(0500)_20240205175213
  112(Эвдлиренный нукаер)_20231207134410
"""

import re
from datetime import datetime
from pathlib import Path

from callprofiler.models import CallMetadata

# ───────────────────────────────────────────────────────────────
# Нормализация телефонного номера
# ───────────────────────────────────────────────────────────────

_DIGITS_ONLY = re.compile(r"\D")


def normalize_phone(raw: str) -> str | None:
    """
    Привести номер к E.164 или оставить как короткий сервисный.

    Правила:
    - Убрать дефисы, скобки, пробелы
    - 007... → +7... (международный формат)
    - 8 + 11 цифр → +7... (русский 8)
    - 00 + не 007 → +... (международный)
    - 3-4 цифры → оставить как есть (короткий номер)
    - Иначе → None
    """
    if not raw or not isinstance(raw, str):
        return None

    # Убрать все нецифровые символы
    digits = _DIGITS_ONLY.sub("", raw.strip())

    if not digits:
        return None

    # Короткие сервисные номера (3-4 цифры)
    if 3 <= len(digits) <= 4:
        return digits

    # 007... → +7...
    if digits.startswith("007") and len(digits) >= 11:
        return "+" + digits[2:]

    # 8 + 11 цифр → +7...
    if digits.startswith("8") and len(digits) == 11:
        return "+7" + digits[1:]

    # 00... (не 007) → +...
    if digits.startswith("00") and not digits.startswith("007"):
        return "+" + digits[2:]

    # +7... или 7... + 11 цифр
    if digits.startswith("7") and len(digits) == 11:
        return "+" + digits

    # +79... (12 цифр)
    if digits.startswith("79") and len(digits) == 12:
        return "+" + digits

    return None


# ───────────────────────────────────────────────────────────────
# Regex для форматов
# ───────────────────────────────────────────────────────────────

# Формат 1: {номер_с_дефисами}({номер_чистый})_{YYYYMMDDHHMMSS}
# Примеры: 007496451-07-97(0074964510797)_20240925154220
_FMT1_RE = re.compile(
    r"""^([\d\-]{10,})     # номер с дефисами
        \((\d{10,})\)      # дубль в скобках (чистый номер)
        _(\d{14})$""",
    re.VERBOSE
)

# Формат 2: 8({код}){номер}({номер_чистый})_{YYYYMMDDHHMMSS}
# Примеры: 8(495)197-87-11(84951978711)_20240502164535
_FMT2_RE = re.compile(
    r"""^8\((\d{3})\)([\d\-]{6,})  # 8(код)номер
        \((\d{10,})\)               # дубль в скобках
        _(\d{14})$""",
    re.VERBOSE
)

# Формат 3: 8{код}{номер}({номер_чистый})_{YYYYMMDDHHMMSS}
# Примеры: 8496451-07-97(84964510797)_20240502170140
_FMT3_RE = re.compile(
    r"""^8([\d\-]{9,})     # 8 + остаток номера
        \((\d{10,})\)      # дубль в скобках
        _(\d{14})$""",
    re.VERBOSE
)

# Формат 4a: {имя}({номер})_{YYYYMMDDHHMMSS}
# Примеры: Алштейндлештейн онвел(0079252475209)_20230925135064
#          Вызов@Ира дледлир(007925291-85-95)_20170828123145
#          Вызов@удлиаиув Билайн(0511)_20170828145731
_FMT4_RE = re.compile(
    r"""^(?:Вызов@)?         # опциональный префикс
        (.+?)                # имя (non-greedy)
        \(([^)]+)\)          # номер в скобках (может быть 007..., 8..., или короткий)
        _(\d{14})$""",
    re.VERBOSE
)

# Формат 5: {имя} {YYYY_MM_DD} {HH_MM_SS}
# Примеры: Варлакаув Хрюн 2009_09_03 21_05_57
#          Вив 2009_08_17 12_15_49
_FMT5_RE = re.compile(
    r"""^(.+?)                      # имя
        \s+                          # пробел
        (\d{4})_(\d{2})_(\d{2})      # YYYY_MM_DD
        \s+                          # пробел
        (\d{2})_(\d{2})_(\d{2})$""", # HH_MM_SS
    re.VERBOSE
)


# ───────────────────────────────────────────────────────────────
# Парсеры для каждого формата
# ───────────────────────────────────────────────────────────────

def _parse_fmt1(stem: str) -> CallMetadata | None:
    """Формат 1: {номер_с_дефисами}({номер_чистый})_{YYYYMMDDHHMMSS}"""
    m = _FMT1_RE.match(stem)
    if not m:
        return None

    _, phone_raw, dt_s = m.groups()

    try:
        dt = datetime.strptime(dt_s, "%Y%m%d%H%M%S")
    except ValueError:
        dt = None

    phone = normalize_phone(phone_raw)

    return CallMetadata(
        phone=phone,
        call_datetime=dt,
        direction="UNKNOWN",
        contact_name=None,
        raw_filename=stem,
    )


def _parse_fmt2(stem: str) -> CallMetadata | None:
    """Формат 2: 8({код}){номер}({номер_чистый})_{YYYYMMDDHHMMSS}"""
    m = _FMT2_RE.match(stem)
    if not m:
        return None

    code, _, phone_raw, dt_s = m.groups()

    try:
        dt = datetime.strptime(dt_s, "%Y%m%d%H%M%S")
    except ValueError:
        dt = None

    phone = normalize_phone(phone_raw)

    return CallMetadata(
        phone=phone,
        call_datetime=dt,
        direction="UNKNOWN",
        contact_name=None,
        raw_filename=stem,
    )


def _parse_fmt3(stem: str) -> CallMetadata | None:
    """Формат 3: 8{код}{номер}({номер_чистый})_{YYYYMMDDHHMMSS}"""
    m = _FMT3_RE.match(stem)
    if not m:
        return None

    _, phone_raw, dt_s = m.groups()

    try:
        dt = datetime.strptime(dt_s, "%Y%m%d%H%M%S")
    except ValueError:
        dt = None

    phone = normalize_phone(phone_raw)

    return CallMetadata(
        phone=phone,
        call_datetime=dt,
        direction="UNKNOWN",
        contact_name=None,
        raw_filename=stem,
    )


def _parse_fmt4(stem: str) -> CallMetadata | None:
    """Формат 4: {имя}({номер})_{YYYYMMDDHHMMSS}"""
    m = _FMT4_RE.match(stem)
    if not m:
        return None

    name_raw, phone_raw, dt_s = m.groups()

    try:
        dt = datetime.strptime(dt_s, "%Y%m%d%H%M%S")
    except ValueError:
        dt = None

    contact_name = name_raw.strip() if name_raw else None
    phone = normalize_phone(phone_raw)

    return CallMetadata(
        phone=phone,
        call_datetime=dt,
        direction="UNKNOWN",
        contact_name=contact_name,
        raw_filename=stem,
    )


def _parse_fmt5(stem: str) -> CallMetadata | None:
    """Формат 5: {имя} {YYYY_MM_DD} {HH_MM_SS}"""
    m = _FMT5_RE.match(stem)
    if not m:
        return None

    name_raw, yyyy, mm, dd, hh, mi, ss = m.groups()

    try:
        dt = datetime(int(yyyy), int(mm), int(dd), int(hh), int(mi), int(ss))
    except ValueError:
        dt = None

    contact_name = name_raw.strip() if name_raw else None

    return CallMetadata(
        phone=None,  # Формат 5: телефон отсутствует
        call_datetime=dt,
        direction="UNKNOWN",
        contact_name=contact_name,
        raw_filename=stem,
    )


# ───────────────────────────────────────────────────────────────
# Публичный API
# ───────────────────────────────────────────────────────────────

def parse_filename(filename: str) -> CallMetadata:
    """
    Распарсить имя файла и вернуть CallMetadata.
    Поддерживает 5 форматов (см. модуль docstring).
    При неизвестном формате: phone=None, direction='UNKNOWN'.

    Работает с Unix и Windows путями.
    """
    # Извлечь имя файла из пути
    last_sep = max(filename.rfind("/"), filename.rfind("\\"))
    if last_sep >= 0:
        filename_only = filename[last_sep + 1:]
    else:
        filename_only = filename

    # Удалить расширение
    stem = Path(filename_only).stem

    # Пробовать парсеры в порядке приоритета
    # (более специфичные форматы раньше)
    for parser in (_parse_fmt2, _parse_fmt3, _parse_fmt1, _parse_fmt4, _parse_fmt5):
        result = parser(stem)
        if result is not None:
            return result

    # Неизвестный формат
    return CallMetadata(
        phone=None,
        call_datetime=None,
        direction="UNKNOWN",
        contact_name=None,
        raw_filename=filename_only,
    )
