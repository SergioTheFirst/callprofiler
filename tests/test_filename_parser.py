# -*- coding: utf-8 -*-
"""
test_filename_parser.py — минимум 15 кейсов, включая грязные имена.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime

from callprofiler.ingest.filename_parser import parse_filename, normalize_phone


# ---------------------------------------------------------------
# normalize_phone
# ---------------------------------------------------------------

def test_norm_8_format():
    assert normalize_phone("89161234567") == "+79161234567"

def test_norm_plus7():
    assert normalize_phone("+79161234567") == "+79161234567"

def test_norm_brackets_dashes():
    assert normalize_phone("8(916)123-45-67") == "+79161234567"

def test_norm_10_digits():
    assert normalize_phone("9161234567") == "+79161234567"

def test_norm_empty():
    assert normalize_phone("") is None


# ---------------------------------------------------------------
# BCR format: 20260328_143022_OUT_+79161234567_Иванов.mp3
# ---------------------------------------------------------------

def test_bcr_full():
    m = parse_filename("20260328_143022_OUT_+79161234567_Иванов.mp3")
    assert m.phone == "+79161234567"
    assert m.direction == "OUT"
    assert m.call_datetime == datetime(2026, 3, 28, 14, 30, 22)
    assert m.contact_name == "Иванов"

def test_bcr_no_name():
    m = parse_filename("20260328_143022_IN_+79161234567.wav")
    assert m.phone == "+79161234567"
    assert m.direction == "IN"
    assert m.contact_name is None

def test_bcr_lowercase_direction():
    m = parse_filename("20260328_143022_out_+79161234567.mp3")
    assert m.direction == "OUT"

def test_bcr_8_phone():
    m = parse_filename("20260328_143022_OUT_89161234567_Петров.mp3")
    assert m.phone == "+79161234567"
    assert m.contact_name == "Петров"


# ---------------------------------------------------------------
# Bracket format: (28.03.2026 14-30-22) Иванов +79161234567 OUT.m4a
# ---------------------------------------------------------------

def test_bracket_full():
    m = parse_filename("(28.03.2026 14-30-22) Иванов +79161234567 OUT.m4a")
    assert m.phone == "+79161234567"
    assert m.direction == "OUT"
    assert m.call_datetime == datetime(2026, 3, 28, 14, 30, 22)
    assert m.contact_name == "Иванов"

def test_bracket_no_direction():
    m = parse_filename("(28.03.2026 14-30-22) Смирнов +79991112233.m4a")
    assert m.phone == "+79991112233"
    assert m.direction == "UNKNOWN"
    assert m.contact_name == "Смирнов"

def test_bracket_no_name():
    m = parse_filename("(01.01.2026 09-00-00) +79161234567 IN.mp3")
    assert m.phone == "+79161234567"
    assert m.direction == "IN"


# ---------------------------------------------------------------
# ACR format: +79161234567_20260328143022_OUT.wav
# ---------------------------------------------------------------

def test_acr_format():
    m = parse_filename("+79161234567_20260328143022_OUT.wav")
    assert m.phone == "+79161234567"
    assert m.direction == "OUT"
    assert m.call_datetime == datetime(2026, 3, 28, 14, 30, 22)
    assert m.contact_name is None

def test_acr_in():
    m = parse_filename("+79031234567_20260101120000_IN.mp3")
    assert m.phone == "+79031234567"
    assert m.direction == "IN"


# ---------------------------------------------------------------
# Unknown / грязные имена
# ---------------------------------------------------------------

def test_unknown_random_name():
    m = parse_filename("запись_разговора.mp3")
    assert m.phone is None
    assert m.direction == "UNKNOWN"
    assert m.call_datetime is None

def test_unknown_digits_only():
    m = parse_filename("123456.wav")
    assert m.direction == "UNKNOWN"

def test_full_path_handled():
    m = parse_filename(r"D:\calls\audio\subdir\20260328_143022_OUT_+79161234567.mp3")
    assert m.phone == "+79161234567"
    assert m.direction == "OUT"

def test_raw_filename_stored():
    m = parse_filename("something_weird.mp3")
    assert m.raw_filename == "something_weird.mp3"
