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

from callprofiler.analyze.prompt_budget import clip_transcript_for_llm

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
            version="v002"
        )
    """

    def __init__(self, prompts_dir: str, prompt_max_chars: int = 12000) -> None:
        """Инициализировать PromptBuilder.

        Параметры:
            prompts_dir  — директория с шаблонами (например, "configs/prompts")
            prompt_max_chars  — максимум символов транскрипта перед клипом (default 12000)
        """
        self.prompts_dir = Path(prompts_dir)
        self.prompt_max_chars = prompt_max_chars
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
        # Clip transcript if needed
        max_chars = metadata.get("prompt_max_chars") or self.prompt_max_chars
        clipped = clip_transcript_for_llm(transcript_text, max_chars)
        final_transcript = clipped["text"]
        if clipped["truncated"]:
            logger.info(
                "Transcript clipped: %d → %d chars",
                clipped["original_chars"],
                clipped["final_chars"],
            )

        # Load template and substitute owner_name
        system_prompt = self._load_template(version)
        # T-14: имя владельца — одна строка ≤80 символов (display_name не может внести инструкции)
        owner_name = " ".join(str(metadata.get("owner_name") or "").split())[:80] or "владелец телефона (имя неизвестно)"
        system_prompt = system_prompt.replace("{{owner_name}}", owner_name)

        # Build context block
        context_block = "\n\n".join(
            (
                f"Предыдущий анализ: {s}"
                if isinstance(s, str)
                else f"Анализ от {s.get('call_datetime', '?')}: {s.get('summary', '')}"
            )
            for s in (previous_summaries or [])
            if s
        )

        # Metadata
        contact_name = metadata.get("contact_name") or "Неизвестно"
        phone = metadata.get("phone") or ""
        call_datetime = str(metadata.get("call_datetime") or "")
        direction = str(metadata.get("direction") or "")

        # Duration: prefer duration_ms, fallback to duration_sec, then 0
        duration_ms = int(metadata.get("duration_ms", 0) or 0)
        if not duration_ms:
            duration_sec = int(metadata.get("duration_sec", 0) or 0)
            duration_ms = duration_sec * 1000

        if duration_ms > 0:
            duration_str = f"{duration_ms / 1000:.1f} сек"
        else:
            duration_str = "неизвестна"

        # Build user message wrapped in <данные>…</данные>
        data_lines = [
            f"Контакт: {contact_name} ({phone})",
            f"Дата/время: {call_datetime}",
            f"Направление: {direction}",
            f"Длительность: {duration_str}",
        ]

        if context_block:
            data_lines.append(f"\nКонтекст (предыдущие звонки):\n{context_block}")

        data_lines.append(f"\nСтенограмма:\n{final_transcript or '(пусто)'}")

        # T-14: данные не могут закрыть конверт — закрывающий тег внутри данных нейтрализуется
        data_block = "\n".join(data_lines).replace("</данные>", "</данные >")

        user_message = (
            "Метаданные звонка:\n"
            f"<данные>\n{data_block}\n</данные>"
        )

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
