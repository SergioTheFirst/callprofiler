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
        self,
        transcript_text: str,
        metadata: dict,
        previous_summaries: list[str] | None = None,
        version: str = "v001",
    ) -> str:
        """Построить промпт для анализа звонка.

        Параметры:
            transcript_text     — стенограмма (с временами и ролями)
            metadata           — метаданные звонка (CallMetadata или dict):
                - contact_name (str | None)
                - phone (str | None)
                - call_datetime (datetime | None)
                - direction (str)  # IN / OUT / UNKNOWN
            previous_summaries — список саммари последних анализов этого контакта (для контекста)
            version            — версия промпта (например, "v001", "v002")

        Возвращает:
            Готовый промпт с подставленными переменными

        Raises:
            FileNotFoundError  — если файл шаблона не найден
        """
        # Загрузить шаблон
        template_path = self.prompts_dir / f"analyze_{version}.txt"
        if not template_path.exists():
            raise FileNotFoundError(f"Шаблон промпта не найден: {template_path}")

        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()

        # Подготовить переменные
        contact_name = metadata.get("contact_name") or "Неизвестный"
        phone = metadata.get("phone") or "Неизвестный номер"
        call_datetime = metadata.get("call_datetime")
        direction = metadata.get("direction", "UNKNOWN")

        # Форматировать дату/время
        if isinstance(call_datetime, datetime):
            datetime_str = call_datetime.strftime("%d.%m.%Y %H:%M")
        else:
            datetime_str = str(call_datetime) if call_datetime else "Неизвестно"

        # Вычислить длительность (если есть временные метки в стенограмме)
        duration = self._extract_duration(transcript_text)

        # Построить блок контекста (предыдущие анализы)
        context_block = self._build_context_block(previous_summaries)

        # Подставить переменные
        prompt = template.format(
            contact_name=contact_name,
            phone=phone,
            call_datetime=datetime_str,
            direction=direction,
            duration=duration,
            context_block=context_block,
            transcript=transcript_text,
        )

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
