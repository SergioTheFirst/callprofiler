# -*- coding: utf-8 -*-
"""
response_parser.py — парсинг JSON ответов от LLM.

Обрабатывает:
  1. Валидный JSON
  2. JSON в markdown-обёртках (```json ... ```)
  3. Невалидный JSON (пытается исправить)
  4. Отсутствующие поля (использует defaults)

При критичной ошибке парсинга возвращает Analysis с дефолтами и сохраняет
raw_response для отладки.
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

    # Попытка 3: Очистить и попробовать ещё раз
    if parsed is None:
        json_str = _clean_json(raw)
        if json_str:
            parsed = _try_parse_json(json_str)

    # Если всё ещё None, используем дефолты
    if parsed is None:
        logger.warning(
            "Не удалось распарсить JSON из ответа LLM (первые 200 символов): %s",
            raw[:200],
        )
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
    """Извлечь JSON из markdown-обёртки (```json ... ```).

    Возвращает:
        JSON строка или None
    """
    # Поиск ```json ... ``` или ``` ... ```
    patterns = [
        r"```json\n(.*?)\n```",
        r"```\n(.*?)\n```",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            logger.debug("Найден JSON в markdown-обёртке")
            return match.group(1)

    return None


def _clean_json(text: str) -> str | None:
    """Попытка очистить невалидный JSON (убрать лишние кавычки, скобки и т.д.).

    Возвращает:
        Очищенная JSON строка или None
    """
    # Найти первый { и последний }
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or start >= end:
        logger.debug("Не найдены { и } в ответе")
        return None

    json_candidate = text[start:end + 1]

    # Попытаться распарсить (уже сделано выше, но на всякий случай)
    try:
        json.loads(json_candidate)
        logger.debug("JSON очищен и валиден")
        return json_candidate
    except json.JSONDecodeError:
        logger.debug("Очищенный JSON всё ещё невалиден")
        return None


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
    return Analysis(
        priority=_get_int(parsed, "priority", 50, 0, 100),
        risk_score=_get_int(parsed, "risk_score", 50, 0, 100),
        summary=_get_str(parsed, "summary", "Не удалось распарсить анализ"),
        action_items=_get_list(parsed, "action_items", []),
        promises=_get_list(parsed, "promises", []),
        flags=_get_dict(parsed, "flags", {}),
        key_topics=_get_list(parsed, "key_topics", []),
        raw_response=raw_response,
        model=model,
        prompt_version=prompt_version,
    )


def _default_analysis(
    raw_response: str = "",
    model: str = "unknown",
    prompt_version: str = "v001",
) -> Analysis:
    """Вернуть Analysis с дефолтными значениями при критичной ошибке парсинга.

    Параметры:
        raw_response    — сырой ответ для отладки
        model           — название модели
        prompt_version  — версия промпта

    Возвращает:
        Analysis с нейтральными дефолтами
    """
    logger.warning("Возврат Analysis с дефолтными значениями (парсинг не удался)")
    return Analysis(
        priority=50,
        risk_score=50,
        summary="Ошибка при анализе звонка LLM. Проверьте логи.",
        action_items=[],
        promises=[],
        flags={},
        key_topics=[],
        raw_response=raw_response,
        model=model,
        prompt_version=prompt_version,
    )


# ── Вспомогательные функции для безопасного получения значений ──────────

def _get_int(data: dict, key: str, default: int, min_val: int = None, max_val: int = None) -> int:
    """Получить int значение из dict с валидацией и дефолтом.

    Параметры:
        data     — dict для поиска
        key      — ключ
        default  — дефолтное значение
        min_val  — минимальное значение (опционально)
        max_val  — максимальное значение (опционально)

    Возвращает:
        Int значение в диапазоне [min_val, max_val] или default
    """
    try:
        value = int(data.get(key, default))
        if min_val is not None and value < min_val:
            value = min_val
        if max_val is not None and value > max_val:
            value = max_val
        return value
    except (ValueError, TypeError):
        logger.debug("Ошибка при получении int для ключа %s, используем дефолт", key)
        return default


def _get_str(data: dict, key: str, default: str = "") -> str:
    """Получить str значение из dict с дефолтом."""
    try:
        value = data.get(key, default)
        return str(value) if value else default
    except (ValueError, TypeError):
        logger.debug("Ошибка при получении str для ключа %s, используем дефолт", key)
        return default


def _get_list(data: dict, key: str, default: list = None) -> list:
    """Получить list значение из dict с дефолтом."""
    try:
        value = data.get(key, default or [])
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
