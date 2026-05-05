# -*- coding: utf-8 -*-
"""
transcript_cleaner.py — очистка транскриптов от hallucinations и артефактов.

Применяется сразу после Whisper, до сохранения в БД.
Основано на deepclear.py (удаление повторов) + дополнительные фильтры.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.models import Segment

logger = logging.getLogger(__name__)


class TranscriptCleaner:
    """Очистка транскриптов от hallucinations и артефактов Whisper.

    Применяет 5 фильтров:
    1. Удаление повторяющихся слов/фраз (3+ подряд → 1)
    2. Удаление мусорных фраз (субтитры, водяные знаки)
    3. Нормализация пунктуации (множественные точки → одна)
    4. Удаление HTML-тегов и эмодзи
    5. Удаление пустых сегментов после очистки
    """

    # Стоп-фразы (водяные знаки, субтитры, мусор)
    STOPWORDS = [
        r"субтитры\s+сделал\s+\w+",
        r"subtitles\s+by\s+\w+",
        r"перевод\s+и\s+субтитры\s+\w+",
        r"спасибо\s+за\s+просмотр",
        r"подписывайтесь\s+на\s+канал",
        r"ставьте\s+лайки",
        r"не\s+забудьте\s+подписаться",
        r"\[музыка\]",
        r"\[аплодисменты\]",
        r"\[смех\]",
    ]

    def __init__(self, min_segment_length: int = 3) -> None:
        """Инициализация очистителя.

        Параметры:
            min_segment_length  — минимальная длина сегмента (символов) после очистки
        """
        self.min_segment_length = min_segment_length
        self.stopwords_pattern = re.compile(
            "|".join(self.STOPWORDS), re.IGNORECASE | re.UNICODE
        )

    def remove_consecutive_repeats(self, text: str) -> tuple[str, bool]:
        """Удаляет повторяющиеся фразы (3+ одинаковых подряд → 1).

        Обрабатывает:
        - Целые предложения (разделены точками)
        - Словосочетания с запятыми
        - Слова с пробелами

        Возвращает:
            (очищенный_текст, был_ли_изменён)
        """
        original_text = text
        result = text
        changed = False
        iterations = 0
        max_iterations = 10  # Защита от бесконечного цикла

        while iterations < max_iterations:
            iterations += 1
            found_match = False

            # Паттерн 1: Целые предложения (разделены точками)
            # "Привет. Привет. Привет." → "Привет."
            pattern_sentences = r"(?i)([^.!?]+[.!?])\s*\1(?:\s*\1)+"
            match = re.search(pattern_sentences, result)

            if match:
                sentence = match.group(1).strip()
                result = result[: match.start()] + " " + sentence + " " + result[match.end() :]
                changed = True
                found_match = True
                continue

            # Паттерн 2: Словосочетания с запятыми
            # "спасибо, спасибо, спасибо" → "спасибо"
            pattern_commas = r"(?i)(\w+(?:\s+\w+){0,4})(?:\s*,\s*)(\1)(?:\s*,\s*)(\1)(?:(?:\s*,\s*)\1)+"
            match = re.search(pattern_commas, result)

            if match:
                phrase = match.group(1)
                # Сохраняем оригинальный регистр первого слова
                first_word_match = re.match(r"(\w+)", match.group(0))
                replacement = first_word_match.group(1) if first_word_match else phrase
                result = result[: match.start()] + replacement + result[match.end() :]
                changed = True
                found_match = True
                continue

            # Паттерн 3: Слова с пробелами (без запятых)
            # "да да да" → "да"
            pattern_spaces = r"(?i)(\w+(?:\s+\w+){0,4})(?:\s+)(\1)(?:\s+)(\1)(?:(?:\s+)\1)+"
            match = re.search(pattern_spaces, result)

            if match:
                phrase = match.group(1)
                first_word_match = re.match(r"(\w+)", match.group(0))
                replacement = first_word_match.group(1) if first_word_match else phrase
                result = result[: match.start()] + replacement + result[match.end() :]
                changed = True
                found_match = True
                continue

            if not found_match:
                break

        return result, changed and result != original_text

    def remove_stopwords(self, text: str) -> tuple[str, bool]:
        """Удаляет мусорные фразы (субтитры, водяные знаки).

        Возвращает:
            (очищенный_текст, был_ли_изменён)
        """
        original_text = text
        result = self.stopwords_pattern.sub("", text)
        return result, result != original_text

    def normalize_punctuation(self, text: str) -> tuple[str, bool]:
        """Нормализует пунктуацию.

        - Множественные точки → одна точка
        - Множественные запятые → одна запятая
        - Множественные пробелы → один пробел

        Возвращает:
            (очищенный_текст, был_ли_изменён)
        """
        original_text = text
        result = text

        # Множественные точки → одна
        result = re.sub(r"\.{2,}", ".", result)
        # Множественные запятые → одна
        result = re.sub(r",{2,}", ",", result)
        # Множественные пробелы → один
        result = re.sub(r"\s{2,}", " ", result)
        # Пробелы перед пунктуацией
        result = re.sub(r"\s+([.,!?;:])", r"\1", result)

        return result.strip(), result != original_text

    def remove_html_and_emoji(self, text: str) -> tuple[str, bool]:
        """Удаляет HTML-теги и эмодзи.

        Возвращает:
            (очищенный_текст, был_ли_изменён)
        """
        original_text = text

        # Удаляем HTML-теги
        result = re.sub(r"<[^>]+>", "", text)

        # Удаляем эмодзи и странные Unicode символы
        # Оставляем: ASCII (0-127), кириллицу (0x0400-0x04FF), неразрывный пробел (0x00A0)
        result = "".join(
            c
            for c in result
            if ord(c) < 0x10000
            and (ord(c) < 128 or 0x0400 <= ord(c) <= 0x04FF or ord(c) == 0x00A0)
        )

        return result.strip(), result != original_text

    def clean_text(self, text: str) -> tuple[str, dict[str, bool]]:
        """Применяет все фильтры очистки к тексту.

        Возвращает:
            (очищенный_текст, {фильтр: был_применён})
        """
        result = text
        changes = {}

        # Фильтр 1: Удаление повторов
        result, changed = self.remove_consecutive_repeats(result)
        changes["repeats_removed"] = changed

        # Фильтр 2: Удаление стоп-слов
        result, changed = self.remove_stopwords(result)
        changes["stopwords_removed"] = changed

        # Фильтр 3: Нормализация пунктуации
        result, changed = self.normalize_punctuation(result)
        changes["punctuation_normalized"] = changed

        # Фильтр 4: Удаление HTML и эмодзи
        result, changed = self.remove_html_and_emoji(result)
        changes["html_emoji_removed"] = changed

        return result.strip(), changes

    def clean_segments(self, segments: list[Segment]) -> list[Segment]:
        """Очищает список сегментов транскрипта.

        Применяет все фильтры к каждому сегменту и удаляет пустые.

        Параметры:
            segments  — список Segment из Whisper

        Возвращает:
            Очищенный список Segment (может быть короче оригинала)
        """
        cleaned_segments = []
        stats = {
            "total": len(segments),
            "cleaned": 0,
            "removed_empty": 0,
            "removed_short": 0,
        }

        for seg in segments:
            # Применяем все фильтры
            cleaned_text, changes = self.clean_text(seg.text)

            # Пропускаем пустые сегменты
            if not cleaned_text:
                stats["removed_empty"] += 1
                continue

            # Пропускаем слишком короткие сегменты (вероятно мусор)
            if len(cleaned_text) < self.min_segment_length:
                stats["removed_short"] += 1
                continue

            # Если текст изменился, создаём новый Segment
            if cleaned_text != seg.text:
                seg.text = cleaned_text
                stats["cleaned"] += 1

            cleaned_segments.append(seg)

        # Логируем статистику
        if stats["cleaned"] > 0 or stats["removed_empty"] > 0 or stats["removed_short"] > 0:
            logger.info(
                "Transcript cleaning: %d segments → %d cleaned, %d empty removed, %d short removed",
                stats["total"],
                stats["cleaned"],
                stats["removed_empty"],
                stats["removed_short"],
            )

        return cleaned_segments
