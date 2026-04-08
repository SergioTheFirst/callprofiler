# -*- coding: utf-8 -*-
"""
test_filename_parser.py — тесты парсера имён файлов (5 форматов).

30+ тестов покрывают:
- Формат 1: номер с дефисами + дубль в скобках
- Формат 2: 8(код)номер + дубль в скобках
- Формат 3: 8 без скобок вокруг кода
- Формат 4: имя контакта + номер в скобках (с опциональным префиксом Вызов@)
- Формат 5: только имя + дата (без номера)
- Сервисные номера (3-4 цифры)
- Edge cases и нераспознанные форматы
"""

import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from callprofiler.ingest.filename_parser import parse_filename, normalize_phone


# ─────────────────────────────────────────────────────────────────
# Тесты нормализации телефонных номеров
# ─────────────────────────────────────────────────────────────────

class TestNormalizePhone:
    """Тесты нормализации телефонных номеров."""

    def test_normalize_007_to_plus7(self):
        """007XXXXXXXXXX → +7XXXXXXXXXX"""
        assert normalize_phone("0074964510797") == "+74964510797"
        assert normalize_phone("007-496-451-07-97") == "+74964510797"
        assert normalize_phone("0074951978711") == "+74951978711"

    def test_normalize_8_to_plus7(self):
        """8 + 11 цифр → +7..."""
        assert normalize_phone("84964510797") == "+74964510797"
        assert normalize_phone("8(495)197-87-11") == "+74951978711"
        assert normalize_phone("88002505105") == "+78002505105"
        assert normalize_phone("89161234567") == "+79161234567"

    def test_normalize_with_parentheses_and_dashes(self):
        """Убрать скобки и дефисы."""
        assert normalize_phone("8(800)250-51-05") == "+78002505105"
        assert normalize_phone("8(921)325-34-88") == "+79213253488"
        assert normalize_phone("8(495)197-87-11") == "+74951978711"

    def test_short_service_numbers(self):
        """Короткие номера (3-4 цифры) — оставить как есть."""
        assert normalize_phone("900") == "900"
        assert normalize_phone("0500") == "0500"
        assert normalize_phone("0511") == "0511"
        assert normalize_phone("112") == "112"

    def test_invalid_phone(self):
        """Невалидные номера → None."""
        assert normalize_phone("") is None
        assert normalize_phone("abc") is None
        assert normalize_phone("12") is None  # менее 3 цифр
        assert normalize_phone(None) is None

    def test_00_prefix_not_007(self):
        """00... (не 007) → +..."""
        assert normalize_phone("00123456789") == "+123456789"
        assert normalize_phone("00364023") == "+364023"

    def test_7_prefix_11_digits(self):
        """+7 или 7 + 11 цифр"""
        assert normalize_phone("79161234567") == "+79161234567"
        assert normalize_phone("+79161234567") == "+79161234567"

    def test_normalize_with_spaces(self):
        """Убрать пробелы."""
        assert normalize_phone("8 (916) 123 45 67") == "+79161234567"


# ─────────────────────────────────────────────────────────────────
# Тесты парсера имён файлов — Форматы 1-5
# ─────────────────────────────────────────────────────────────────

class TestParseFilename:
    """Тесты парсера имён файлов (5 форматов)."""

    # ─── Формат 1: {номер_с_дефисами}({номер_чистый})_{YYYYMMDDHHMMSS} ───

    def test_fmt1_example1(self):
        """Формат 1: 007496451-07-97(0074964510797)_20240925154220"""
        result = parse_filename("007496451-07-97(0074964510797)_20240925154220.wav")
        assert result.phone == "+74964510797"
        assert result.call_datetime == datetime(2024, 9, 25, 15, 42, 20)
        assert result.direction == "UNKNOWN"
        assert result.contact_name is None

    def test_fmt1_example2(self):
        """Формат 1: 007495197-87-11(0074951978711)_20240207122419"""
        result = parse_filename("007495197-87-11(0074951978711)_20240207122419.mp3")
        assert result.phone == "+74951978711"
        assert result.call_datetime == datetime(2024, 2, 7, 12, 24, 19)

    def test_fmt1_example3(self):
        """Формат 1: 0036402351975(0036402351975)_20241128174725"""
        result = parse_filename("0036402351975(0036402351975)_20241128174725.m4a")
        assert result.phone == "+36402351975"  # 003... → +...
        assert result.call_datetime == datetime(2024, 11, 28, 17, 47, 25)

    # ─── Формат 2: 8({код}){номер}({номер_чистый})_{YYYYMMDDHHMMSS} ───

    def test_fmt2_example1(self):
        """Формат 2: 8(495)197-87-11(84951978711)_20240502164535"""
        result = parse_filename("8(495)197-87-11(84951978711)_20240502164535.wav")
        assert result.phone == "+74951978711"
        assert result.call_datetime == datetime(2024, 5, 2, 16, 45, 35)
        assert result.direction == "UNKNOWN"

    def test_fmt2_example2(self):
        """Формат 2: 8(800)250-51-05(88002505105)_20231105130954"""
        result = parse_filename("8(800)250-51-05(88002505105)_20231105130954.ogg")
        assert result.phone == "+78002505105"
        assert result.call_datetime == datetime(2023, 11, 5, 13, 9, 54)

    def test_fmt2_example3(self):
        """Формат 2: 8(921)325-34-88(89213253488)_20240423124525"""
        result = parse_filename("8(921)325-34-88(89213253488)_20240423124525.flac")
        assert result.phone == "+79213253488"

    # ─── Формат 3: 8{код}{номер}({номер_чистый})_{YYYYMMDDHHMMSS} ───

    def test_fmt3_example1(self):
        """Формат 3: 8496451-07-97(84964510797)_20240502170140"""
        result = parse_filename("8496451-07-97(84964510797)_20240502170140.wav")
        assert result.phone == "+74964510797"
        assert result.call_datetime == datetime(2024, 5, 2, 17, 1, 40)

    def test_fmt3_example2(self):
        """Формат 3: 8495777-77-77(84957777777)_20241008164538"""
        result = parse_filename("8495777-77-77(84957777777)_20241008164538.mp3")
        assert result.phone == "+74957777777"

    def test_fmt3_example3(self):
        """Формат 3: 8800200-90-02(88002009002)_20231210164541"""
        result = parse_filename("8800200-90-02(88002009002)_20231210164541.m4a")
        assert result.phone == "+78002009002"

    # ─── Формат 4: {имя}({номер})_{YYYYMMDDHHMMSS} ───

    def test_fmt4_example1_name_with_number(self):
        """Формат 4: Алштейндлештейн онвел(0079252475209)_20230925135032"""
        result = parse_filename("Алштейндлештейн онвел(0079252475209)_20230925135032.wav")
        assert result.phone == "+79252475209"
        assert result.contact_name == "Алштейндлештейн онвел"
        assert result.call_datetime == datetime(2023, 9, 25, 13, 50, 32)

    def test_fmt4_example2_short_name(self):
        """Формат 4: Пиип(0079641931595)_20230915203305"""
        result = parse_filename("Пиип(0079641931595)_20230915203305.mp3")
        assert result.phone == "+79641931595"
        assert result.contact_name == "Пиип"

    def test_fmt4_example3_long_name(self):
        """Формат 4: Бронштейннивув Дикаун и(0079585390864)_20251205182524"""
        result = parse_filename("Бронштейннивув Дикаун и(0079585390864)_20251205182524.ogg")
        assert result.phone == "+79585390864"
        assert result.contact_name == "Бронштейннивув Дикаун и"

    def test_fmt4_with_call_prefix1(self):
        """Формат 4: Вызов@Ира дледлир(007925291-85-95)_20170828123145"""
        result = parse_filename("Вызов@Ира дледлир(007925291-85-95)_20170828123145.wav")
        assert result.contact_name == "Ира дледлир"  # "Вызов@" убран
        assert result.phone == "+79252918595"
        assert result.call_datetime == datetime(2017, 8, 28, 12, 31, 45)

    def test_fmt4_with_call_prefix2(self):
        """Формат 4: Вызов@он(007957140-33-12)_20170305135408"""
        result = parse_filename("Вызов@он(007957140-33-12)_20170305135408.m4a")
        assert result.contact_name == "он"
        assert result.phone == "+79571403312"

    def test_fmt4_with_service_number_0511(self):
        """Формат 4: Вызов@удлиаиув Билайн(0511)_20170828145731"""
        result = parse_filename("Вызов@удлиаиув Билайн(0511)_20170828145731.wav")
        assert result.contact_name == "удлиаиув Билайн"
        assert result.phone == "0511"  # короткий номер

    def test_fmt4_short_service_number_900(self):
        """Формат 4 с коротким номером 900: name(900)_20231009112764"""
        result = parse_filename("name(900)_20231009112764.wav")
        assert result.phone == "900"
        assert result.contact_name == "name"

    def test_fmt4_short_service_number_0500(self):
        """Формат 4 с сервисным номером 0500: name(0500)_20240205175213"""
        result = parse_filename("name(0500)_20240205175213.wav")
        assert result.phone == "0500"
        assert result.contact_name == "name"

    def test_fmt4_service_number_112(self):
        """Формат 4 с сервисным номером 112: some(112)_20231207134410"""
        result = parse_filename("some(112)_20231207134410.wav")
        assert result.phone == "112"
        assert result.contact_name == "some"

    # ─── Формат 5: {имя} {YYYY_MM_DD} {HH_MM_SS} ───

    def test_fmt5_example1(self):
        """Формат 5: Варлакаув Хрюн 2009_09_03 21_05_57"""
        result = parse_filename("Варлакаув Хрюн 2009_09_03 21_05_57.wav")
        assert result.phone is None  # Формат 5: нет номера
        assert result.contact_name == "Варлакаув Хрюн"
        assert result.call_datetime == datetime(2009, 9, 3, 21, 5, 57)
        assert result.direction == "UNKNOWN"

    def test_fmt5_example2_short(self):
        """Формат 5: Вив 2009_08_17 12_15_49"""
        result = parse_filename("Вив 2009_08_17 12_15_49.mp3")
        assert result.contact_name == "Вив"
        assert result.call_datetime == datetime(2009, 8, 17, 12, 15, 49)
        assert result.phone is None

    def test_fmt5_example3_short_name(self):
        """Формат 5: Дука 2009_09_01 22_12_39"""
        result = parse_filename("Дука 2009_09_01 22_12_39.ogg")
        assert result.contact_name == "Дука"

    def test_fmt5_example4_long_name(self):
        """Формат 5: Ира дледлира каегафун 2009_10_25 15_19_29"""
        result = parse_filename("Ира дледлира каегафун 2009_10_25 15_19_29.wav")
        assert result.contact_name == "Ира дледлира каегафун"
        assert result.call_datetime == datetime(2009, 10, 25, 15, 19, 29)

    def test_fmt5_example5_complex_name(self):
        """Формат 5: штейнгений Анашвштейн Ирштейн кауж 2009_11_20 13_35_15"""
        result = parse_filename("штейнгений Анашвштейн Ирштейн кауж 2009_11_20 13_35_15.m4a")
        assert result.contact_name == "штейнгений Анашвштейн Ирштейн кауж"
        assert result.call_datetime == datetime(2009, 11, 20, 13, 35, 15)

    # ─── Edge cases ───

    def test_unknown_format(self):
        """Нераспознанный формат → phone=None, direction=UNKNOWN"""
        result = parse_filename("some_random_filename_12345.wav")
        assert result.phone is None
        assert result.call_datetime is None
        assert result.direction == "UNKNOWN"
        assert result.contact_name is None

    def test_empty_filename(self):
        """Пустое имя файла"""
        result = parse_filename("")
        assert result.phone is None
        assert result.direction == "UNKNOWN"

    def test_with_path_unix(self):
        """Unix путь: /path/to/file.wav"""
        result = parse_filename("/home/user/calls/007496451-07-97(0074964510797)_20240925154220.wav")
        assert result.phone == "+74964510797"

    def test_with_path_windows(self):
        """Windows путь: C:\\path\\to\\file.wav"""
        result = parse_filename("C:\\Users\\user\\calls\\8(495)197-87-11(84951978711)_20240502164535.mp3")
        assert result.phone == "+74951978711"

    def test_invalid_date_in_fmt1(self):
        """Формат 1 с невалидной датой → call_datetime=None"""
        result = parse_filename("007496451-07-97(0074964510797)_20241331000000.wav")
        assert result.phone == "+74964510797"
        assert result.call_datetime is None  # Дата невалидна (месяц 13)

    def test_invalid_date_in_fmt5(self):
        """Формат 5 с невалидной датой → call_datetime=None"""
        result = parse_filename("SomeName 2024_13_32 23_59_59.wav")
        assert result.contact_name == "SomeName"
        assert result.call_datetime is None  # Дата невалидна

    def test_extension_extraction(self):
        """Расширение файла правильно удаляется"""
        for ext in [".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wma"]:
            result = parse_filename(f"8(495)197-87-11(84951978711)_20240502164535{ext}")
            assert result.phone == "+74951978711"

    def test_raw_filename_stored(self):
        """raw_filename содержит исходное имя файла"""
        result = parse_filename("something.mp3")
        assert result.raw_filename == "something.mp3"

    def test_raw_filename_from_path(self):
        """raw_filename содержит только имя файла, без пути"""
        result = parse_filename("/some/path/to/file.wav")
        assert result.raw_filename == "file.wav"


if __name__ == "__main__":
    # Можно запустить тесты простой командой
    import pytest
    pytest.main([__file__, "-v"])

