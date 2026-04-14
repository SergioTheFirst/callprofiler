# -*- coding: utf-8 -*-
"""
card_generator.py — генерация caller cards для Android overlay.

ПК генерирует {phone_e164}.txt (≤500 символов) → FolderSync синхронизирует
на телефон → MacroDroid при входящем звонке читает файл → показывает overlay.

Формат карточки (CONSTITUTION.md Статья 10.2):
    {display_name} | {категория}
    Последний: {дата} | Звонков: {count} | Risk: {avg_risk}
    ─────────────────────────
    {summary последнего звонка, 2-3 строки}
    ─────────────────────────
    Обещания: {открытые promises}
    Actions: {незакрытые action items}
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.db.repository import Repository

logger = logging.getLogger(__name__)

SEPARATOR = "─" * 25
MAX_CARD_LENGTH = 500


class CardGenerator:
    """Генератор caller cards для overlay на Android.

    Использование:
        generator = CardGenerator(repo)
        text = generator.generate_card(user_id="serhio", contact_id=1)
        generator.write_card("serhio", 1, "/path/to/sync/cards")
        generator.update_all_cards("serhio")
    """

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def generate_card(self, user_id: str, contact_id: int) -> str:
        """Собрать caller card для контакта.

        Параметры:
            user_id     — идентификатор пользователя
            contact_id  — идентификатор контакта

        Возвращает:
            Текст карточки ≤ 500 символов
        """
        # Данные контакта
        contact = self.repo.get_contact(contact_id)
        if not contact:
            logger.warning("Контакт %d не найден", contact_id)
            return ""

        display_name = contact.get("display_name") or "Неизвестный"

        # Количество звонков
        call_count = self.repo.get_call_count_for_contact(user_id, contact_id)

        # Последний анализ
        analyses = self.repo.get_recent_analyses(user_id, contact_id, limit=1)
        last_analysis = analyses[0] if analyses else None

        # Открытые обещания
        promises = self.repo.get_contact_promises(user_id, contact_id)
        open_promises = [p for p in promises if p.get("status") == "open"]

        # Построить карточку
        lines = []

        # Строка 1: имя
        lines.append(display_name)

        # Строка 2: статистика
        if last_analysis:
            last_date = last_analysis.get("created_at", "?")
            if len(last_date) > 10:
                last_date = last_date[:10]
            risk = last_analysis.get("risk_score", 0)
            lines.append(
                f"Последний: {last_date} | Звонков: {call_count} | Risk: {risk}"
            )
        else:
            lines.append(f"Звонков: {call_count} | Нет анализа")

        lines.append(SEPARATOR)

        # Саммари последнего звонка
        if last_analysis:
            summary = last_analysis.get("summary", "")
            if summary:
                lines.append(summary)
            else:
                lines.append("Нет саммари")
        else:
            lines.append("Нет данных об анализе")

        lines.append(SEPARATOR)

        # Обещания
        if open_promises:
            promise_texts = []
            for p in open_promises[:3]:
                who = p.get("who", "?")
                what = p.get("what", "?")
                promise_texts.append(f"{who}: {what}")
            lines.append("Обещания: " + "; ".join(promise_texts))
        else:
            lines.append("Обещания: нет")

        # Action items
        if last_analysis:
            action_items = last_analysis.get("action_items", [])
            if action_items:
                items_text = "; ".join(action_items[:3])
                lines.append(f"Actions: {items_text}")
            else:
                lines.append("Actions: нет")
        else:
            lines.append("Actions: нет")

        card_text = "\n".join(lines)

        # Обрезка до 500 символов
        if len(card_text) > MAX_CARD_LENGTH:
            card_text = card_text[:MAX_CARD_LENGTH - 3] + "..."
            logger.debug(
                "Карточка для contact_id=%d обрезана до %d символов",
                contact_id, MAX_CARD_LENGTH,
            )

        return card_text

    def write_card(self, user_id: str, contact_id: int, sync_dir: str) -> None:
        """Записать карточку контакта в файл {phone_e164}.txt.

        Параметры:
            user_id     — идентификатор пользователя
            contact_id  — идентификатор контакта
            sync_dir    — директория синхронизации (для FolderSync)
        """
        contact = self.repo.get_contact(contact_id)
        if not contact:
            logger.warning("Контакт %d не найден, карточка не записана", contact_id)
            return

        phone = contact.get("phone_e164")
        if not phone:
            logger.warning(
                "У контакта %d нет phone_e164, карточка не записана", contact_id
            )
            return

        card_text = self.generate_card(user_id, contact_id)
        if not card_text:
            logger.warning("Пустая карточка для contact_id=%d", contact_id)
            return

        sync_path = Path(sync_dir)
        sync_path.mkdir(parents=True, exist_ok=True)

        card_path = sync_path / f"{phone}.txt"
        card_path.write_text(card_text, encoding="utf-8")

        logger.info(
            "Карточка записана: %s (%d символов)", card_path, len(card_text)
        )

    def update_all_cards(self, user_id: str) -> None:
        """Пересоздать карточки для всех контактов пользователя.

        Параметры:
            user_id  — идентификатор пользователя
        """
        user = self.repo.get_user(user_id)
        if not user:
            logger.error("Пользователь %s не найден", user_id)
            return

        sync_dir = user.get("sync_dir", "")
        if not sync_dir:
            logger.error("У пользователя %s не задан sync_dir", user_id)
            return

        contacts = self.repo.get_all_contacts_for_user(user_id)
        if not contacts:
            logger.info("У пользователя %s нет контактов", user_id)
            return

        count = 0
        for contact in contacts:
            contact_id = contact["contact_id"]
            phone = contact.get("phone_e164")
            if not phone:
                logger.debug(
                    "Пропуск контакта %d без phone_e164", contact_id
                )
                continue
            try:
                self.write_card(user_id, contact_id, sync_dir)
                count += 1
            except Exception as exc:
                logger.error(
                    "Ошибка при записи карточки для contact_id=%d: %s",
                    contact_id, exc,
                )

        logger.info(
            "Обновлено %d карточек для пользователя %s", count, user_id
        )
