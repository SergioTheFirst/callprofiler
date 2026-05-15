# -*- coding: utf-8 -*-
"""
prompt_builder.py — построение промптов для LLM анализа звонков.

Загружает шаблоны из configs/prompts/ и подставляет переменные:
  - {transcript} — стенограмма звонка
  - {contact_name} — имя контакта
  - {phone} — номер телефона
  - {call_datetime} — дата/время звонка
  - {direction} — IN/OUT/UNKNOWN
  - {duration} — длительность в секундах
  - {context_block} — контекст (предыдущие анализы)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Построение промптов с подстановкой переменных из метаданных звонка.

    Использование:
        builder = PromptBuilder(prompts_dir="./configs/prompts")
        prompt = builder.build(
            transcript_text="[OWNER]: Привет...",
            metadata={"contact_name": "Иван", "phone": "+79161234567"},
            version="v001"
        )
    """

    def __init__(self, prompts_dir: str) -> None:
        """Инициализировать PromptBuilder.

        Параметры:
            prompts_dir  — директория с шаблонами (например, "configs/prompts")
        """
        self.prompts_dir = Path(prompts_dir)
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"Директория prompts не найдена: {prompts_dir}")
        logger.info("PromptBuilder инициализирован: %s", self.prompts_dir)

def build(
    prompt_template: str,
    *,
    transcript: str,
    contact_name: str | None,
    phone: str,
    call_datetime: str,
    direction: str,
    duration_ms: int,
    context_block: str,
) -> str:
    """Render the LLM prompt, substituting only the known safe placeholders.

    Uses manual replacement instead of str.format() to avoid crashes when the
    prompt template contains literal JSON braces (e.g. example output blocks).
    """
    replacements = {
        "{transcript}": transcript,
        "{contact_name}": contact_name or "неизвестный абонент",
        "{phone}": phone,
        "{call_datetime}": call_datetime,
        "{direction}": direction,
        "{duration}": str(duration_ms),
        "{context_block}": context_block,
    }
    result = prompt_template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result

        logger.debug(
            "Построен промпт для контакта %s (%s), версия %s, длина=%d",
            contact_name, phone, version, len(prompt),
        )
        return prompt

    def _extract_duration(self, transcript_text: str) -> str:
        """Извлечь длительность из стенограммы по последней временной метке.

        Параметры:
            transcript_text  — стенограмма с временными метками

        Возвращает:
            Строка формата "Х минут Y секунд" или "неизвестна"
        """
        # Очень простой парсер: ищем последнюю временную метку [MM:SS]
        import re
        matches = re.findall(r"\[(\d{1,2}):(\d{2})\]", transcript_text)
        if matches:
            last_match = matches[-1]
            minutes, seconds = int(last_match[0]), int(last_match[1])
            total_seconds = minutes * 60 + seconds
            mins = total_seconds // 60
            secs = total_seconds % 60
            if mins > 0:
                return f"{mins} минут {secs} секунд"
            else:
                return f"{secs} секунд"
        return "неизвестна"

    def _build_context_block(self, previous_summaries: list[str] | None) -> str:
        """Построить блок контекста из предыдущих анализов.

        Параметры:
            previous_summaries  — список саммари (последние 3-5)

        Возвращает:
            Строка контекста для подстановки в промпт (или пустая)
        """
        if not previous_summaries:
            return ""

        context_lines = ["Контекст (предыдущие звонки с этим контактом):"]
        for i, summary in enumerate(previous_summaries[-3:], 1):  # Последние 3
            summary_short = summary[:100] + "..." if len(summary) > 100 else summary
            context_lines.append(f"{i}. {summary_short}")

        return "\n".join(context_lines) + "\n"
