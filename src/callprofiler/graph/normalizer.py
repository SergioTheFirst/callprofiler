# -*- coding: utf-8 -*-
"""
normalizer.py — детерминированная нормализация ключей сущностей.

LLM может предложить normalized_key, но Python пересчитывает детерминированно.
Источник истины — функции в этом модуле, не LLM.
"""

import re
import unicodedata


_CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E',
    'Ё': 'Yo', 'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K',
    'Л': 'L', 'М': 'M', 'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R',
    'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'H', 'Ц': 'Ts',
    'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch', 'Ъ': '', 'Ы': 'Y', 'Ь': '',
    'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
}


def _transliterate_cyrillic(text: str) -> str:
    """Транслитерация кириллицы на латиницу по простому словарю."""
    result = []
    for char in text:
        result.append(_CYRILLIC_TO_LATIN.get(char, char))
    return ''.join(result)


def normalize_key(name: str, entity_type: str = "person") -> str:
    """
    Детерминированная нормализация ключа сущности.

    Args:
        name: Каноническое имя (из LLM или пользователя)
        entity_type: Тип сущности (person, organization, place, etc.)

    Returns:
        Нормализованный ключ: lowercase, латиница, пробелы → подчёркивания,
        только буквы, цифры, подчёркивания.

    Примеры:
        normalize_key("Иван Петров", "person") → "ivan_petrov"
        normalize_key("ООО Акме Инк", "organization") → "ooo_akme_ink"
        normalize_key("Москва, Россия", "place") → "moskva_rossiya"
        normalize_key("John Smith", "person") → "john_smith"
    """
    if not name or not isinstance(name, str):
        return ""

    # Шаг 1: Транслитерация кириллицы
    text = _transliterate_cyrillic(name)

    # Шаг 2: Удаление диакритики (ударения, умлауты)
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))

    # Шаг 3: Lowercase
    text = text.lower()

    # Шаг 4: Замена пробелов на подчёркивания (до замены остальных символов)
    text = re.sub(r'\s+', '_', text)

    # Шаг 5: Удаление символов, оставляя только букв, цифры, подчёркивания
    text = re.sub(r'[^a-z0-9_]', '', text)

    # Шаг 6: Схлопывание множественных подчёркиваний в одно
    text = re.sub(r'_+', '_', text)

    # Шаг 7: Удаление подчёркиваний с краёв
    text = text.strip('_')

    return text


def normalize_phone(phone: str) -> str:
    """
    Нормализация номера телефона к международному формату E.164 (если возможно).
    Оставляет только цифры и '+'.

    Примеры:
        normalize_phone("+7 916 123-4567") → "+79161234567"
        normalize_phone("79161234567") → "+79161234567"
        normalize_phone("+1-415-555-0100") → "+14155550100"
    """
    if not phone:
        return ""

    # Оставляем только цифры и '+'
    clean = re.sub(r'[^\d+]', '', phone)

    # Если нет '+', добавляем (предполагаем +7 для России, но это приблизительно)
    # На самом деле лучше использовать phonenumbers lib, но оставляем простой вариант
    if clean and not clean.startswith('+'):
        # Если начинается на 8, заменяем на 7 (Россия)
        if clean.startswith('8') and len(clean) == 11:
            clean = '7' + clean[1:]
        if not clean.startswith('+'):
            clean = '+' + clean

    return clean
