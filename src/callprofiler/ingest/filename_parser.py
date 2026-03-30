# -*- coding: utf-8 -*-
"""
filename_parser.py — парсинг имён аудиофайлов в CallMetadata.

Поддерживаемые форматы:
  1. BCR:      20260328_143022_OUT_+79161234567_Иванов.mp3
  2. Скобочный: (28.03.2026 14-30-22) Иванов +79161234567 OUT.m4a
  3. ACR:      +79161234567_20260328143022_OUT.wav
  4. Неизвестный → phone=None, direction=UNKNOWN
"""

import re
from datetime import datetime
from pathlib import Path

from callprofiler.models import CallMetadata

# ---------------------------------------------------------------
# Нормализация телефонного номера
# ---------------------------------------------------------------

_DIGITS_RE = re.compile(r"\D")


def normalize_phone(raw: str) -> str | None:
    """
    Привести номер к формату E.164 (+7XXXXXXXXXX).
    Поддерживает: +7..., 8..., 7..., скобки, дефисы, пробелы.
    Возвращает None если не удаётся распознать.
    """
    if not raw:
        return None
    digits = _DIGITS_RE.sub("", raw)
    if len(digits) == 11 and digits[0] in ("7", "8"):
        return "+7" + digits[1:]
    if len(digits) == 12 and digits[:2] == "79":
        return "+" + digits
    if len(digits) == 10 and digits[0] == "9":
        return "+7" + digits
    # Оставить как есть с + если начинается с +
    if raw.startswith("+") and len(digits) >= 10:
        return "+" + digits
    return None


# ---------------------------------------------------------------
# Форматы имён файлов
# ---------------------------------------------------------------

# 1. BCR: 20260328_143022_OUT_+79161234567_Иванов.mp3
_BCR_RE = re.compile(
    r"^(\d{8})_(\d{6})_(IN|OUT|UNKNOWN|in|out)[_\-]"
    r"(\+?\d[\d\-\(\)\s]{6,})"
    r"(?:[_\-](.+))?$",
    re.IGNORECASE,
)

# 2. Скобочный: (28.03.2026 14-30-22) Иванов +79161234567 OUT.m4a
_BRACKET_RE = re.compile(
    r"^\((\d{2})\.(\d{2})\.(\d{4})\s+(\d{2})-(\d{2})-(\d{2})\)"
    r"\s*(.*?)\s*(\+?\d[\d\-\(\)]{6,}\d)"
    r"(?:\s+(IN|OUT|UNKNOWN|in|out))?",
    re.IGNORECASE,
)

# 3. ACR: +79161234567_20260328143022_OUT.wav
_ACR_RE = re.compile(
    r"^(\+?\d[\d\-\(\)\s]{6,})_(\d{14})_(IN|OUT|UNKNOWN|in|out)",
    re.IGNORECASE,
)


def _parse_bcr(stem: str) -> CallMetadata | None:
    m = _BCR_RE.match(stem)
    if not m:
        return None
    date_s, time_s, direction, phone_raw, name = m.groups()
    try:
        dt = datetime.strptime(date_s + time_s, "%Y%m%d%H%M%S")
    except ValueError:
        dt = None
    phone = normalize_phone(phone_raw.strip())
    contact = name.strip() if name else None
    return CallMetadata(
        phone=phone,
        call_datetime=dt,
        direction=direction.upper(),
        contact_name=contact,
        raw_filename=stem,
    )


def _parse_bracket(stem: str) -> CallMetadata | None:
    m = _BRACKET_RE.match(stem)
    if not m:
        return None
    dd, mm, yyyy, hh, mi, ss, name_raw, phone_raw, dir_raw = m.groups()
    try:
        dt = datetime(int(yyyy), int(mm), int(dd), int(hh), int(mi), int(ss))
    except ValueError:
        dt = None
    phone = normalize_phone(phone_raw.strip())
    contact = name_raw.strip() if name_raw.strip() else None
    direction = dir_raw.upper() if dir_raw else "UNKNOWN"
    return CallMetadata(
        phone=phone,
        call_datetime=dt,
        direction=direction,
        contact_name=contact,
        raw_filename=stem,
    )


def _parse_acr(stem: str) -> CallMetadata | None:
    m = _ACR_RE.match(stem)
    if not m:
        return None
    phone_raw, dt_s, direction = m.groups()
    phone = normalize_phone(phone_raw.strip())
    try:
        dt = datetime.strptime(dt_s, "%Y%m%d%H%M%S")
    except ValueError:
        dt = None
    return CallMetadata(
        phone=phone,
        call_datetime=dt,
        direction=direction.upper(),
        contact_name=None,
        raw_filename=stem,
    )


# ---------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------

def parse_filename(filename: str) -> CallMetadata:
    """
    Распарсить имя файла (или полный путь) и вернуть CallMetadata.
    При неизвестном формате: phone=None, direction='UNKNOWN'.
    """
    stem = Path(filename).stem

    for parser in (_parse_bcr, _parse_bracket, _parse_acr):
        result = parser(stem)
        if result is not None:
            return result

    return CallMetadata(
        phone=None,
        call_datetime=None,
        direction="UNKNOWN",
        contact_name=None,
        raw_filename=stem,
    )
