# -*- coding: utf-8 -*-
"""
card_generator.py — генерация структурированных caller cards для Android overlay.

ПК генерирует {phone_e164}.txt (≤512 байт) → FolderSync синхронизирует
на телефон → MacroDroid при входящем звонке читает файл → показывает overlay.

Формат карточки (MacroDroid-compatible, ≤512 байт):
    header: {display_name или guessed_name или phone} — {contact_role}
    risk: {global_risk} {🔴🟡🟢}
    hook: {top_hook}
    bullet1: {первый open promise/debt}
    bullet2: {второй}
    bullet3: {personal_fact}
    advice: {advice}

Данные берутся из contact_summaries (materialized aggregate).
Если summary нет — минимальная карточка: header + "Нет истории".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.db.repository import Repository

logger = logging.getLogger(__name__)

MAX_CARD_BYTES = 512


def _risk_emoji(risk: int) -> str:
    if risk >= 70:
        return "🔴"
    if risk >= 30:
        return "🟡"
    return "🟢"


def _best_name(contact: dict) -> str:
    """Выбрать лучшее отображаемое имя для контакта."""
    return (
        contact.get("display_name")
        or contact.get("guessed_name")
        or contact.get("phone_e164")
        or "Неизвестный"
    )


def _parse_json_field(value: str | None) -> list:
    """Безопасный парсинг JSON-поля из contact_summaries."""
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _truncate_bytes(text: str, max_bytes: int) -> str:
    """Обрезать строку до max_bytes (по UTF-8 байтам)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes - 3].decode("utf-8", errors="ignore")
    return truncated + "..."


class CardGenerator:
    """Генератор структурированных caller cards для Android overlay.

    Использование:
        generator = CardGenerator(repo)
        text = generator.generate_card(user_id="serhio", contact_id=1)
        generator.write_card("serhio", 1, "/path/to/sync/cards")
        generator.update_all_cards("serhio")
    """

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def generate_card(self, user_id: str, contact_id: int) -> str:
        """Собрать структурированную caller card для контакта.

        Параметры:
            user_id     — идентификатор пользователя
            contact_id  — идентификатор контакта

        Возвращает:
            Текст карточки ≤ 512 байт (MacroDroid-compatible key:value формат)
        """
        contact = self.repo.get_contact(contact_id)
        if not contact:
            logger.warning("Контакт %d не найден", contact_id)
            return ""

        name = _best_name(contact)
        summary = self.repo.get_contact_summary(contact_id)

        # Минимальная карточка если нет summary
        if not summary:
            header = name
            role = contact.get("guessed_company") or ""
            if role:
                header = f"{name} — {role}"
            card = f"header: {header}\nНет истории"
            return _truncate_bytes(card, MAX_CARD_BYTES)

        # Полная карточка из contact_summaries
        role = summary.get("contact_role") or contact.get("guessed_company") or ""
        header = f"{name} — {role}" if role else name

        risk = summary.get("global_risk") or 0
        emoji = _risk_emoji(risk)

        hook = summary.get("top_hook") or ""
        advice = summary.get("advice") or ""

        # Bullets: приоритет долгам → promises → personal_facts
        bullets: list[str] = []

        debts = _parse_json_field(summary.get("open_debts"))
        for debt in debts[:1]:
            payload = debt.get("payload") or str(debt)
            bullets.append(payload[:80])

        promises = _parse_json_field(summary.get("open_promises"))
        for promise in promises[:2 - len(bullets)]:
            payload = promise.get("payload") or str(promise)
            bullets.append(payload[:80])

        facts = _parse_json_field(summary.get("personal_facts"))
        if len(bullets) < 3 and facts:
            payload = facts[0].get("payload") if isinstance(facts[0], dict) else str(facts[0])
            bullets.append((payload or "")[:80])

        lines = [f"header: {header}", f"risk: {risk} {emoji}"]
        if hook:
            lines.append(f"hook: {hook[:100]}")
        for i, bullet in enumerate(bullets[:3], 1):
            lines.append(f"bullet{i}: {bullet}")
        if advice:
            lines.append(f"advice: {advice[:100]}")

        card = "\n".join(lines)
        return _truncate_bytes(card, MAX_CARD_BYTES)

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
            logger.warning("У контакта %d нет phone_e164, карточка не записана", contact_id)
            return

        card_text = self.generate_card(user_id, contact_id)
        if not card_text:
            logger.warning("Пустая карточка для contact_id=%d", contact_id)
            return

        sync_path = Path(sync_dir)
        sync_path.mkdir(parents=True, exist_ok=True)

        card_path = sync_path / f"{phone}.txt"
        card_path.write_text(card_text, encoding="utf-8")

        logger.info("Карточка записана: %s (%d байт)", card_path, len(card_text.encode("utf-8")))

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
                logger.debug("Пропуск контакта %d без phone_e164", contact_id)
                continue
            try:
                self.write_card(user_id, contact_id, sync_dir)
                count += 1
            except Exception as exc:
                logger.error("Ошибка при записи карточки для contact_id=%d: %s", contact_id, exc)

        logger.info("Обновлено %d карточек для пользователя %s", count, user_id)
