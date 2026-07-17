# -*- coding: utf-8 -*-
"""
card_generator.py — генерация структурированных caller cards для Android overlay.

ПК генерирует {79XXXXXXXXXX}.txt (≤512 байт) → FolderSync синхронизирует
на телефон → MacroDroid при входящем звонке читает файл → показывает overlay.

Формат карточки v2 (MacroDroid-compatible, ≤512 байт, A6 + Fable §4.3):
    header: {display_name или guessed_name или phone} — {contact_role}
    risk: {global_risk} {🔴🟡🟢}
    due: {просроченное обязательство контакта, если есть}
    grade: {Admiralty-грейд источника, всегда}
    call: {лучшее время звонка, если уверенно}
    bullet1..3: {open promise/debt/personal_fact}
    hook: {top_hook}
    обновлено {DD.MM HH:MM}   — последняя строка, бюджет зарезервирован первым

Контур-сепарация (инвариант 16): archetype/age/style/психо-поля на карточку
никогда не попадают. `advice` (мнение некалиброванной модели) убран v2.

Данные берутся из contact_summaries (materialized aggregate).
Если summary нет — минимальная карточка: header + "Нет истории" + штамп.

Integration (A4 — risk-threshold calibration):
- Используется risk_thresholds (insight/risk_calibration.py) для data-driven risk
  emoji на основе перцентилей risk_score юзера (НЕ BS-index — другая метрика,
  другое распределение; см. .claude/rules/decisions.md 2026-07-17).
- Fallback: дефолт 30/70 если calibration недоступна для user_id
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.db.repository import Repository

from callprofiler.insight.risk_calibration import get_latest_risk_thresholds
from callprofiler.insight.risk_calibration import risk_emoji as _calibrated_risk_emoji

logger = logging.getLogger(__name__)

MAX_CARD_BYTES = 512


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
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes - 3].decode("utf-8", errors="ignore")
    return truncated + "..."


def _canonical_phone(phone: str | None) -> str | None:
    """Канон имени файла карточки (A6/Fable §4.3 п.6): только цифры, ведущая 8->7."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return None
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    return digits


class CardGenerator:
    """Генератор структурированных caller cards для Android overlay.

    Использование:
        generator = CardGenerator(repo)
        text = generator.generate_card(user_id="serhio", contact_id=1)
        generator.write_card("serhio", 1, "/path/to/sync/cards")
        generator.update_all_cards("serhio")

    Integration (A4):
    - Использует risk_thresholds (perцентили risk_score юзера) для data-driven emoji
    - Fallback на дефолт 30/70 если calibration недоступна
    """

    def __init__(self, repo: Repository) -> None:
        self.repo = repo
        self._db_conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection | None:
        """Ленивый коннект к основной БД для чтения risk_thresholds (A4)."""
        if self._db_conn is not None:
            return self._db_conn
        if not hasattr(self.repo, '_db_path'):
            return None
        self._db_conn = sqlite3.connect(self.repo._db_path)
        self._db_conn.row_factory = sqlite3.Row
        return self._db_conn

    def _risk_emoji_with_calibration(self, risk: int, user_id: str) -> str:
        """Emoji для risk_score с учётом user-specific percentile-порогов (A4).

        Args:
            risk: Risk score (0-100)
            user_id: User ID для поиска calibration thresholds

        Returns:
            Emoji (🔴🟡🟢) — калиброванные пороги юзера или дефолт 30/70
        """
        thresholds = None
        try:
            conn = self._get_conn()
            if conn is not None:
                thresholds = get_latest_risk_thresholds(conn, user_id)
        except Exception as e:
            logger.debug("Failed to get risk thresholds: %s", e)
        return _calibrated_risk_emoji(risk, thresholds)

    def _due_line(self, user_id: str, contact_id: int, now: datetime) -> str | None:
        """`due:` — самое просроченное обязательство контакта (A1 леджер)."""
        try:
            from callprofiler.deliver.digest import overdue_items

            conn = self._get_conn()
            if conn is None:
                return None
            today = now.date().isoformat()
            items = [i for i in overdue_items(conn, user_id, today) if i.get("contact_id") == contact_id]
            if not items:
                return None
            item = items[0]
            what = (item.get("what") or "").strip()[:60]
            return f"due: {what} (просрочено {item['days_overdue']} дн.)"
        except Exception as e:
            logger.debug("Не удалось собрать due-строку: %s", e)
            return None

    def _grade_line(self, user_id: str, contact_id: int) -> str:
        """`grade:` — Admiralty-грейд источника (A6 п.2). Всегда рендерится (F6 в худшем случае)."""
        from callprofiler.insight.admiralty import grade_line, info_grade, source_grade

        bs_label = None
        avg_confidence = None
        conn = self._get_conn()

        if conn is not None:
            try:
                row = conn.execute(
                    """SELECT em.bs_index FROM entity_contact_map ecm
                         JOIN entity_metrics em ON em.entity_id = ecm.entity_id
                        WHERE ecm.user_id = ? AND ecm.contact_id = ?
                        ORDER BY ecm.confidence DESC LIMIT 1""",
                    (user_id, contact_id),
                ).fetchone()
                if row is not None:
                    from callprofiler.graph.calibration import BSCalibrator
                    from callprofiler.graph.repository import GraphRepository

                    bs_label, _ = BSCalibrator(GraphRepository(conn)).get_label(row["bs_index"], user_id)
            except Exception as e:
                logger.debug("Не удалось резолвить bs_label: %s", e)

            try:
                row = conn.execute(
                    """SELECT AVG(confidence) AS avg_conf FROM events
                        WHERE user_id = ? AND contact_id = ?
                          AND created_at >= datetime('now', '-180 days')""",
                    (user_id, contact_id),
                ).fetchone()
                if row is not None:
                    avg_confidence = row["avg_conf"]
            except Exception as e:
                logger.debug("Не удалось посчитать avg_confidence: %s", e)

        kept_ratio = kept_n = None
        if conn is not None:
            try:
                from callprofiler.insight.promise_outcomes import contact_reliability
                rel = contact_reliability(conn, user_id, contact_id)
                if rel:
                    kept_ratio, kept_n = rel["kept_ratio"], rel["n"]
            except Exception as e:
                logger.debug("Не удалось получить contact_reliability: %s", e)

        src = source_grade(bs_label, kept_ratio, kept_n or 0)
        info = info_grade(avg_confidence)
        return f"grade: {grade_line(src, info)}"

    def _call_time_line(self, user_id: str, contact_id: int) -> str | None:
        """`call:` — лучшее время звонка (A6 п.1); None если сигнал не уверенный."""
        try:
            from callprofiler.insight.call_time import best_call_time

            calls = self.repo.get_calls_for_contact(user_id, contact_id)
            phrase = best_call_time(calls)
            return f"call: {phrase}" if phrase else None
        except Exception as e:
            logger.debug("Не удалось посчитать call-time: %s", e)
            return None

    @staticmethod
    def _finalize_card(body_lines: list[str], now: datetime) -> str:
        """Штамп свежести — последняя строка, бюджет 512 байт резервируется под неё первым."""
        timestamp_line = f"обновлено {now.strftime('%d.%m %H:%M')}"
        reserved = len(timestamp_line.encode("utf-8")) + 1  # +1 за перевод строки
        body = _truncate_bytes("\n".join(body_lines), MAX_CARD_BYTES - reserved)
        return f"{body}\n{timestamp_line}"

    def generate_card(self, user_id: str, contact_id: int, *, now: datetime | None = None) -> str:
        """Собрать структурированную caller card v2 для контакта.

        Параметры:
            user_id     — идентификатор пользователя
            contact_id  — идентификатор контакта
            now         — момент генерации (для штампа свежести; по умолчанию datetime.now())

        Возвращает:
            Текст карточки ≤ 512 байт (MacroDroid-compatible key:value формат)
        """
        now = now or datetime.now()
        contact = self.repo.get_contact(user_id, contact_id)
        if not contact:
            logger.warning("Контакт %d не найден", contact_id)
            return ""

        name = _best_name(contact)
        summary = self.repo.get_contact_summary(user_id, contact_id)

        # Минимальная карточка если нет summary
        if not summary:
            header = name
            role = contact.get("guessed_company") or ""
            if role:
                header = f"{name} — {role}"
            return self._finalize_card([f"header: {header}", "Нет истории"], now)

        # Полная карточка из contact_summaries
        role = summary.get("contact_role") or contact.get("guessed_company") or ""
        header = f"{name} — {role}" if role else name

        risk = summary.get("global_risk") or 0
        emoji = self._risk_emoji_with_calibration(risk, user_id)

        hook = summary.get("top_hook") or ""

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

        due = self._due_line(user_id, contact_id, now)
        if due:
            lines.append(due)
        lines.append(self._grade_line(user_id, contact_id))
        call = self._call_time_line(user_id, contact_id)
        if call:
            lines.append(call)

        # Приоритет содержательных строк (Fable §4.3 п.4): confirmed-факты (F1,
        # ещё нет) > открытые обещания/долги > hook. advice убран (п.4).
        for i, bullet in enumerate(bullets[:3], 1):
            lines.append(f"bullet{i}: {bullet}")
        if hook:
            lines.append(f"hook: {hook[:100]}")

        return self._finalize_card(lines, now)

    def write_card(self, user_id: str, contact_id: int, sync_dir: str) -> None:
        """Записать карточку контакта в файл {79XXXXXXXXXX}.txt (канон A6/§4.3 п.6).

        Параметры:
            user_id     — идентификатор пользователя
            contact_id  — идентификатор контакта
            sync_dir    — директория синхронизации (для FolderSync)
        """
        contact = self.repo.get_contact(user_id, contact_id)
        if not contact:
            logger.warning("Контакт %d не найден, карточка не записана", contact_id)
            return

        canonical = _canonical_phone(contact.get("phone_e164"))
        if not canonical:
            logger.warning("У контакта %d нет phone_e164, карточка не записана", contact_id)
            return

        card_text = self.generate_card(user_id, contact_id)
        if not card_text:
            logger.warning("Пустая карточка для contact_id=%d", contact_id)
            return

        sync_path = Path(sync_dir)
        sync_path.mkdir(parents=True, exist_ok=True)

        card_path = sync_path / f"{canonical}.txt"
        card_path.write_text(card_text, encoding="utf-8")

        logger.info("Карточка записана: %s (%d байт)", card_path, len(card_text.encode("utf-8")))

    def _remove_legacy_cards(self, sync_dir: str) -> None:
        """Снести старые карточки с нецифровым именем (до канона §4.3 п.6, напр. '+7...')."""
        sync_path = Path(sync_dir)
        if not sync_path.is_dir():
            return
        for card_file in sync_path.glob("*.txt"):
            if not card_file.stem.isdigit():
                try:
                    card_file.unlink()
                except OSError as exc:
                    logger.warning("Не удалось удалить устаревшую карточку %s: %s", card_file, exc)

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

        self._remove_legacy_cards(sync_dir)

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
