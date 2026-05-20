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
        self._cache: dict[str, str] = {}
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"Директория prompts не найдена: {prompts_dir}")
        logger.info("PromptBuilder инициализирован: %s", self.prompts_dir)

    def _load_template(self, version: str = "v001") -> str:
        """Загрузить и кэшировать шаблон промпта из файла."""
        if version not in self._cache:
            prompt_file = self.prompts_dir / f"analyze_{version}.txt"
            if not prompt_file.exists():
                raise FileNotFoundError(f"Шаблон промпта не найден: {prompt_file}")
            self._cache[version] = prompt_file.read_text(encoding="utf-8")
        return self._cache[version]

    def build(
        self,
        transcript_text: str,
        metadata: dict[str, str | int | None],
        previous_summaries: list,
        version: str = "v001",
    ) -> dict[str, str]:
        """Build LLM messages dict from template + context.

        Returns:
            {"system": str, "user": str}  — для OpenAI-совместимого API.
        """
        system_prompt = self._load_template(version)

        context_block = "\n\n".join(
            (
                f"Предыдущий анализ: {s}"
                if isinstance(s, str)
                else f"Анализ от {s.get('call_datetime', '?')}: {s.get('summary', '')}"
            )
            for s in (previous_summaries or [])
            if s
        )

        contact_name = metadata.get("contact_name") or "Неизвестно"
        phone = metadata.get("phone") or ""
        call_datetime = str(metadata.get("call_datetime") or "")
        direction = str(metadata.get("direction") or "")
        duration_ms = int(metadata.get("duration_ms", 0) or 0)
        duration_str = f"{duration_ms / 1000:.1f} сек"

        user_parts = [
            "Метаданные звонка:",
            f"Контакт: {contact_name} ({phone})",
            f"Дата/время: {call_datetime}",
            f"Направление: {direction}",
            f"Длительность: {duration_str}",
        ]
        if context_block:
            user_parts.append(f"\nКонтекст (предыдущие звонки):\n{context_block}")
        user_parts.append(f"\nСтенограмма:\n{transcript_text or '(пусто)'}")

        user_message = "\n".join(user_parts)

        logger.debug(
            "Built prompt: system=%d chars, user=%d chars",
            len(system_prompt),
            len(user_message),
        )
        return {"system": system_prompt, "user": user_message}

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
