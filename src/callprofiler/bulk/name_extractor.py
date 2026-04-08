# -*- coding: utf-8 -*-
"""
name_extractor.py — извлечение имён собеседников из транскриптов.

Для контактов без display_name ищет имя в первых 10 сегментах разговора
(оба спикера — роли [me] и [s2] часто перепутаны).

Паттерны поиска (регистронезависимо):
  - "привет, {Имя}" / "здравствуйте, {Имя}" / "алло, {Имя}"
  - "это {Имя}" / "меня зовут {Имя}" / "{Имя} беспокоит"
  - "да, {Имя}" / "слушаю, {Имя}" / "говорит {Имя}"

Имена владельца исключаются: Сергей, Серёжа, Серёж, Серёга, Медведев.

Confidence:
  - 1 звонок с именем → "medium"
  - 2+ звонков с тем же именем → "high"

Результат записывается в contacts.guessed_name / guess_source / guess_confidence.
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

log = logging.getLogger(__name__)

# ── Имена владельца (исключаются из кандидатов) ──────────────────────────────
OWNER_NAMES: frozenset[str] = frozenset({
    "сергей", "серёжа", "серёж", "серёга", "медведев",
})

# ── Паттерны для русских имён ─────────────────────────────────────────────────
# Имя: заглавная буква + 1-20 строчных (кириллица)
_NAME_RE = r"([А-ЯЁа-яё][а-яёА-ЯЁ]{1,20})"

GREETING_PATTERNS: list[str] = [
    rf"привет[,\s]+{_NAME_RE}",
    rf"здравствуй(?:те)?[,\s]+{_NAME_RE}",
    rf"добрый\s+\w+[,\s]+{_NAME_RE}",
    rf"алло[,\s]+{_NAME_RE}",
    rf"это\s+{_NAME_RE}",
    rf"меня\s+зовут\s+{_NAME_RE}",
    rf"{_NAME_RE}\s+беспокоит",
    rf"да[,\s]+{_NAME_RE}",
    rf"слушаю[,\s]+{_NAME_RE}",
    rf"говорит\s+{_NAME_RE}",
    rf"на\s+связи\s+{_NAME_RE}",
    rf"компания\s+[\w\s]+,?\s+{_NAME_RE}",
]

_COMPILED: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in GREETING_PATTERNS
]

# Слова, которые выглядят как имена, но ими не являются
_STOPWORDS: frozenset[str] = frozenset({
    "привет", "пожалуйста", "спасибо", "здравствуйте", "добрый",
    "алло", "слушаю", "говорит", "беспокоит", "зовут",
    "компания", "менеджер", "специалист", "оператор",
})


# ── Структура результата ──────────────────────────────────────────────────────

class NameCandidate(NamedTuple):
    name: str
    call_id: int
    confidence: str   # 'low' | 'medium' | 'high'
    source: str = "regex"


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _extract_candidates(segments: list[dict]) -> list[str]:
    """
    Найти имена-кандидаты в первых 10 сегментах (оба спикера).
    Возвращает список нормализованных имён (capitalize).
    """
    candidates: list[str] = []
    for seg in segments[:10]:
        text = seg.get("text", "")
        for pattern in _COMPILED:
            m = pattern.search(text)
            if not m:
                continue
            raw = m.group(1)
            name = raw.strip().capitalize()
            if name.lower() in OWNER_NAMES:
                continue
            if name.lower() in _STOPWORDS:
                continue
            if len(name) < 2:
                continue
            candidates.append(name)
    return candidates


def _best_name(name_votes: dict[str, list[int]]) -> tuple[str, list[int]] | None:
    """Выбрать имя с максимальным количеством звонков-подтверждений."""
    if not name_votes:
        return None
    best = max(name_votes, key=lambda n: len(name_votes[n]))
    return best, name_votes[best]


# ── Основной класс ────────────────────────────────────────────────────────────

class NameExtractor:
    """Извлекает и сохраняет угаданные имена для контактов без display_name."""

    def __init__(self, repo) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    def extract_for_user(self, user_id: str) -> dict[int, NameCandidate]:
        """
        Обойти контакты пользователя без display_name.
        Для каждого — проанализировать транскрипты всех звонков.
        Вернуть dict: contact_id → NameCandidate.
        """
        contacts = self._repo.get_contacts_without_name(user_id)
        if not contacts:
            log.info("[name_extractor] user=%s: нет контактов без имени", user_id)
            return {}

        results: dict[int, NameCandidate] = {}

        for contact in contacts:
            contact_id = contact["contact_id"]
            phone = contact.get("phone_e164", "?")

            calls = self._repo.get_calls_for_contact(user_id, contact_id)
            if not calls:
                continue

            # Накопить голоса: имя → список call_id где оно встречалось
            name_votes: dict[str, list[int]] = {}

            for call in calls:
                call_id = call["call_id"]
                segments = self._repo.get_transcript(call_id)
                for name in _extract_candidates(segments):
                    name_votes.setdefault(name, []).append(call_id)

            best = _best_name(name_votes)
            if best is None:
                log.debug(
                    "[name_extractor] contact_id=%d (%s): имя не найдено",
                    contact_id, phone,
                )
                continue

            best_name, call_ids = best
            confidence = "high" if len(call_ids) >= 2 else "medium"

            log.info(
                "[name_extractor] contact_id=%d (%s) → '%s' "
                "(confidence=%s, звонков=%d)",
                contact_id, phone, best_name, confidence, len(call_ids),
            )
            results[contact_id] = NameCandidate(
                name=best_name,
                call_id=call_ids[0],
                confidence=confidence,
            )

        return results

    # ------------------------------------------------------------------
    def apply_guesses(self, user_id: str, dry_run: bool = False) -> int:
        """
        Применить угаданные имена к contacts.guessed_name.
        Не трогает контакты с name_confirmed=1.

        Args:
            user_id:  идентификатор пользователя
            dry_run:  если True — только вывести, не записывать в БД

        Returns:
            Количество обновлённых контактов.
        """
        guesses = self.extract_for_user(user_id)
        if not guesses:
            return 0

        updated = 0
        for contact_id, candidate in guesses.items():
            if dry_run:
                print(
                    f"  [dry-run] contact_id={contact_id} → "
                    f"'{candidate.name}' ({candidate.confidence})"
                )
            else:
                self._repo.update_contact_guessed_name(
                    contact_id=contact_id,
                    guessed_name=candidate.name,
                    guess_source=candidate.source,
                    guess_call_id=candidate.call_id,
                    guess_confidence=candidate.confidence,
                )
            updated += 1

        return updated
