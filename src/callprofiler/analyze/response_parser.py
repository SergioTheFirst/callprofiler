# -*- coding: utf-8 -*-
"""
response_parser.py — парсинг JSON ответов от LLM.

Обрабатывает:
  1. Валидный JSON
  2. JSON в markdown-обёртках (```json ... ```)
  3. Невалидный и обрезанный JSON (пытается починить)
  4. Отсутствующие поля (использует defaults)

При критичной ошибке парсинга извлекает критические поля regex-ом
и возвращает Analysis с дефолтами.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from callprofiler.models import Analysis

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def parse_llm_response(raw: str, model: str = "unknown", prompt_version: str = "v001") -> Analysis:
    """Распарсить ответ LLM и вернуть объект Analysis.

    Параметры:
        raw             — сырой ответ от LLM (может быть JSON, текст, markdown)
        model           — название модели (для логирования)
        prompt_version  — версия промпта (для логирования)

    Возвращает:
        Analysis объект (с дефолтами, если парсинг упал)
    """
    logger.debug("Парсинг ответа LLM (длина=%d, модель=%s)", len(raw), model)

    # Попытка 1: Прямое парсинг JSON
    json_str = raw.strip()
    parsed = _try_parse_json(json_str)

    # Попытка 2: Извлечь JSON из markdown-обёрток
    if parsed is None:
        json_str = _extract_json_from_markdown(raw)
        if json_str:
            parsed = _try_parse_json(json_str)

    # Попытка 3: Очистить от текста до/после JSON
    if parsed is None:
        json_str = _extract_json_bounds(raw)
        if json_str:
            parsed = _try_parse_json(json_str)

    # Попытка 4: Починить обрезанный/невалидный JSON
    if parsed is None:
        json_str = _repair_json(raw)
        if json_str:
            parsed = _try_parse_json(json_str)

    # Если всё ещё None, пробуем извлечь критические поля regex-ом
    if parsed is None:
        logger.warning(
            "Не удалось распарсить JSON, пытаемся извлечь поля regex-ом (первые 300 символов): %s...",
            raw[:300],
        )
        parsed = _extract_fields_by_regex(raw)

    # Если даже это не сработало, используем дефолты
    if parsed is None:
        logger.error("Не удалось распарсить JSON и извлечь поля из ответа LLM")
        return _default_analysis(raw_response=raw, model=model, prompt_version=prompt_version)

    # Построить Analysis с подставленными или дефолтными значениями
    return _build_analysis(parsed, raw_response=raw, model=model, prompt_version=prompt_version)


def _try_parse_json(json_str: str) -> dict | None:
    """Попытка распарсить JSON строку.

    Возвращает:
        Dict если успешно, None если ошибка
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.debug(
            "Ошибка JSON парсинга: %s (первые 100 символов): %s",
            exc, json_str[:100],
        )
        return None


def _extract_json_from_markdown(text: str) -> str | None:
    """Извлечь JSON из markdown-обёртки (```json ... ``` или ``` ... ```)."""
    patterns = [
        r"```json\s*(.*?)\s*```",
        r"```\s*(.*?)\s*```",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            logger.debug("Найден JSON в markdown-обёртке")
            return match.group(1).strip()
    return None


def _extract_json_bounds(text: str) -> str | None:
    """Извлечь JSON: текст от первой { до последней }."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return None
    return text[start:end + 1]


def _repair_json(text: str) -> str | None:
    """Попытка починить обрезанный или невалидный JSON.

    Обрабатывает:
      - Обрезанный JSON (недостающие }, ])
      - Открытые кавычки внутри строк
      - Trailing запятые перед } и ]
    """
    # Сначала попробуем извлечь JSON-подобную структуру
    start = text.find("{")
    if start == -1:
        return None

    # Возьмём всё от первой { до конца (может быть обрезано)
    candidate = text[start:]

    # Попытка 1: Простое закрытие if JSON seems incomplete
    if not candidate.rstrip().endswith(("}",)):
        candidate = _close_json_structure(candidate)

    # Попытка 2: Убрать trailing запятые перед } и ]
    candidate = _remove_trailing_commas(candidate)

    logger.debug("Попытка парсинга отремонтированного JSON (первые 100 сим): %s", candidate[:100])
    return candidate if candidate else None


def _close_json_structure(s: str) -> str:
    """Дозакрыть JSON структуру, если она обрезана."""
    s = s.rstrip()

    # Посчитать открытые скобки/кавычки
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape_next = False

    for char in s:
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
        elif not in_string:
            if char == "{":
                open_braces += 1
            elif char == "}":
                open_braces -= 1
            elif char == "[":
                open_brackets += 1
            elif char == "]":
                open_brackets -= 1

    # Если в строке не закрыта кавычка
    if in_string:
        s += '"'

    # Закрыть открытые скобки и кавычки
    s += "]" * open_brackets
    s += "}" * open_braces

    return s


def _remove_trailing_commas(s: str) -> str:
    """Убрать запятые перед } и ]."""
    s = re.sub(r',\s*}', '}', s)
    s = re.sub(r',\s*\]', ']', s)
    return s


def _extract_fields_by_regex(text: str) -> dict | None:
    """Попытка извлечь критические поля JSON через regex.

    Как последняя линия защиты, если JSON совсем не парсится.
    """
    result = {}

    # summary
    match = re.search(r'"summary"\s*:\s*"([^"]*)"', text)
    if match:
        result["summary"] = match.group(1)

    # priority
    match = re.search(r'"priority"\s*:\s*(\d+)', text)
    if match:
        try:
            result["priority"] = int(match.group(1))
        except ValueError:
            pass

    # risk_score
    match = re.search(r'"risk_score"\s*:\s*(\d+)', text)
    if match:
        try:
            result["risk_score"] = int(match.group(1))
        except ValueError:
            pass

    # action_items (примитивное извлечение)
    match = re.search(r'"action_items"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if match:
        items_str = match.group(1)
        items = re.findall(r'"([^"]*)"', items_str)
        if items:
            result["action_items"] = items

    # key_topics
    match = re.search(r'"key_topics"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if match:
        items_str = match.group(1)
        items = re.findall(r'"([^"]*)"', items_str)
        if items:
            result["key_topics"] = items

    # promises (примитивное извлечение)
    match = re.search(r'"promises"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if match:
        items_str = match.group(1)
        # Попытаться распарсить каждый promise
        promises = []
        for promise_match in re.finditer(r'\{([^}]*)\}', items_str):
            promise_content = promise_match.group(1)
            promise = {}
            who_match = re.search(r'"who"\s*:\s*"([^"]*)"', promise_content)
            if who_match:
                promise["who"] = who_match.group(1)
            what_match = re.search(r'"what"\s*:\s*"([^"]*)"', promise_content)
            if what_match:
                promise["what"] = what_match.group(1)
            if promise:
                promises.append(promise)
        if promises:
            result["promises"] = promises

    return result if result else None


def _build_analysis(
    parsed: dict,
    raw_response: str = "",
    model: str = "unknown",
    prompt_version: str = "v001",
) -> Analysis:
    """Построить Analysis из распарсенного JSON.

    Параметры:
        parsed          — распарсенный JSON как dict
        raw_response    — сырой ответ для отладки
        model           — название модели
        prompt_version  — версия промпта

    Возвращает:
        Analysis с дефолтами для отсутствующих полей
    """
    _VALID_CALL_TYPES = {"business", "smalltalk", "short", "spam", "personal", "unknown"}
    call_type = _get_str(parsed, "call_type", "unknown").lower()
    if call_type not in _VALID_CALL_TYPES:
        call_type = "unknown"

    return Analysis(
        priority=_get_int(parsed, "priority", 50, 0, 100),
        risk_score=_get_int(parsed, "risk_score", 0, 0, 100),
        summary=_get_str(parsed, "summary", ""),
        action_items=_get_list(parsed, "action_items", []),
        promises=_get_list(parsed, "promises", []),
        flags=_get_dict(parsed, "flags", {}),
        key_topics=_get_list(parsed, "key_topics", []),
        raw_response=raw_response,
        model=model,
        prompt_version=prompt_version,
        call_type=call_type,
        hook=_get_str(parsed, "hook", None) or None,
    )


def _default_analysis(
    raw_response: str = "",
    model: str = "unknown",
    prompt_version: str = "v001",
) -> Analysis:
    """Вернуть Analysis с дефолтными значениями при критичной ошибке парсинга."""
    logger.warning("Возврат Analysis с дефолтными значениями (парсинг полностью не удался)")
    return Analysis(
        priority=50,
        risk_score=0,
        summary="",
        action_items=[],
        promises=[],
        flags={},
        key_topics=[],
        raw_response=raw_response,
        model=model,
        prompt_version=prompt_version,
        call_type="unknown",
        hook=None,
    )


# ── Вспомогательные функции для безопасного получения значений ──────────

def _get_int(data: dict, key: str, default: int, min_val: int = None, max_val: int = None) -> int:
    """Получить int значение из dict с валидацией и дефолтом."""
    try:
        value = data.get(key, default)
        if isinstance(value, str):
            value = int(value)
        else:
            value = int(value)
        if min_val is not None and value < min_val:
            value = min_val
        if max_val is not None and value > max_val:
            value = max_val
        return value
    except (ValueError, TypeError):
        logger.debug("Ошибка при получении int для ключа %s, используем дефолт %s", key, default)
        return default


def _get_str(data: dict, key: str, default: str = "") -> str:
    """Получить str значение из dict с дефолтом."""
    try:
        value = data.get(key, default)
        return str(value).strip() if value else default
    except (ValueError, TypeError):
        logger.debug("Ошибка при получении str для ключа %s, используем дефолт", key)
        return default


def _get_list(data: dict, key: str, default: list = None) -> list:
    """Получить list значение из dict с дефолтом.

    Если пришла строка вместо списка — обернуть в список.
    """
    try:
        value = data.get(key, default or [])
        if isinstance(value, str):
            # Если строка, обернуть в список
            return [value] if value else (default or [])
        return list(value) if isinstance(value, (list, tuple)) else (default or [])
    except (ValueError, TypeError):
        logger.debug("Ошибка при получении list для ключа %s, используем дефолт", key)
        return default or []


def _get_dict(data: dict, key: str, default: dict = None) -> dict:
    """Получить dict значение из dict с дефолтом."""
    try:
        value = data.get(key, default or {})
        return dict(value) if isinstance(value, dict) else (default or {})
    except (ValueError, TypeError):
        logger.debug("Ошибка при получении dict для ключа %s, используем дефолт", key)
        return default or {}
