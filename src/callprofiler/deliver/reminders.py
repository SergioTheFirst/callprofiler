# -*- coding: utf-8 -*-
"""
reminders.py — F2: напоминания по подтверждённым (F1) обещаниям.

Только по явному действию владельца (инвариант 18) — бот никогда не планирует
напоминание сам, только по кнопке «🔔 Напомнить» + владелец сам называет дату.
Даты — ДЕТЕРМИНИРОВАННЫЙ RU-парсер (никакого LLM). Self-disabling: 5 подряд
ошибок отправки -> enabled=0 (сломанная job не спамит логи вечно).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_ERRORS = 5

_WEEKDAYS_RU = {
    "понедельник": 0, "вторник": 1, "среду": 2, "четверг": 3,
    "пятницу": 4, "субботу": 5, "воскресенье": 6,
}
_WEEKDAY_RE = re.compile(r"^во?\s+(" + "|".join(_WEEKDAYS_RU) + r")$")
_THROUGH_DAYS_RE = re.compile(r"^через\s+(\d{1,3})\s+дн(?:я|ей)?$")
_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$")
_TIME_TAIL_RE = re.compile(r"\s+в\s+(\d{1,2})(?::(\d{2}))?$")


def parse_due_ru(text: str, now: datetime) -> datetime | None:
    """Ровно формы: сегодня/завтра/послезавтра, в <день недели> (ближайший
    будущий — сегодня не считается), через N дней, DD.MM, DD.MM.YYYY;
    опц. хвост " в HH[:MM]" (по умолчанию 10:00). Не распозналось -> None,
    никаких догадок."""
    if not text:
        return None
    if now.tzinfo is None:
        now = now.astimezone()

    raw = text.strip().lower()
    hour, minute = 10, 0
    time_match = _TIME_TAIL_RE.search(raw)
    if time_match:
        h = int(time_match.group(1))
        m = int(time_match.group(2) or 0)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        hour, minute = h, m
        raw = raw[: time_match.start()].strip()

    target_date = None
    if raw == "сегодня":
        target_date = now.date()
    elif raw == "завтра":
        target_date = now.date() + timedelta(days=1)
    elif raw == "послезавтра":
        target_date = now.date() + timedelta(days=2)
    elif (m := _WEEKDAY_RE.match(raw)) is not None:
        target_wd = _WEEKDAYS_RU[m.group(1)]
        delta = (target_wd - now.weekday()) % 7
        if delta == 0:
            delta = 7  # «ближайший будущий» — сегодняшний день не считается
        target_date = now.date() + timedelta(days=delta)
    elif (m := _THROUGH_DAYS_RE.match(raw)) is not None:
        target_date = now.date() + timedelta(days=int(m.group(1)))
    elif (m := _DATE_RE.match(raw)) is not None:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            candidate = datetime(year, month, day).date()
        except ValueError:
            return None
        if m.group(3) is None and candidate < now.date():
            # DD.MM без года и дата уже прошла в этом году -> следующий год
            try:
                candidate = datetime(year + 1, month, day).date()
            except ValueError:
                return None
        target_date = candidate

    if target_date is None:
        return None
    return datetime(target_date.year, target_date.month, target_date.day, hour, minute,
                     tzinfo=now.tzinfo)


def create_reminder(conn, user_id: str, *, item_kind: str, item_key: str, text: str,
                     due_at: datetime, chat_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO reminders(user_id, item_kind, item_key, text, due_at, chat_id) "
        "VALUES (?,?,?,?,?,?)",
        (user_id, item_kind, str(item_key), text, due_at.isoformat(), chat_id),
    )
    conn.commit()
    return cur.lastrowid


def due_reminders(conn, now: datetime) -> list[dict]:
    """sent_at IS NULL AND enabled=1 AND due_at<=now. ISO-8601 строковое сравнение
    ponytail: корректно для фиксированного локального оффсета весь год кроме
    редких DST-переходов дважды в год — не критично для personal-tool self-alert."""
    if now.tzinfo is None:
        now = now.astimezone()
    rows = conn.execute(
        "SELECT reminder_id, user_id, item_kind, item_key, text, due_at, chat_id, "
        "sent_at, enabled, consecutive_errors FROM reminders "
        "WHERE sent_at IS NULL AND enabled = 1 AND due_at <= ? ORDER BY due_at",
        (now.isoformat(),),
    ).fetchall()
    cols = ["reminder_id", "user_id", "item_kind", "item_key", "text", "due_at",
            "chat_id", "sent_at", "enabled", "consecutive_errors"]
    return [dict(zip(cols, r)) for r in rows]


def mark_sent(conn, reminder_id: int) -> None:
    conn.execute(
        "UPDATE reminders SET sent_at = CURRENT_TIMESTAMP, consecutive_errors = 0 "
        "WHERE reminder_id = ?", (reminder_id,),
    )
    conn.commit()


def mark_error(conn, reminder_id: int) -> bool:
    """Возврат True если этой ошибкой напоминание было отключено (для one-time алерта)."""
    conn.execute(
        "UPDATE reminders SET consecutive_errors = consecutive_errors + 1 WHERE reminder_id = ?",
        (reminder_id,),
    )
    row = conn.execute(
        "SELECT consecutive_errors, enabled FROM reminders WHERE reminder_id = ?",
        (reminder_id,),
    ).fetchone()
    disabled_now = False
    if row is not None and row[0] >= MAX_CONSECUTIVE_ERRORS and row[1]:
        conn.execute("UPDATE reminders SET enabled = 0 WHERE reminder_id = ?", (reminder_id,))
        disabled_now = True
    conn.commit()
    return disabled_now


def snooze_reminder(conn, reminder_id: int, user_id: str) -> None:
    """«🕐 Завтра»: due_at+1 день, sent_at сброшен -> сработает на следующем тике.
    user_id обязателен — без него чужой reminder_id можно было бы перенести (CVE
    найден security-review 2026-07-17 до коммита: снятого auth-гейта в боте было
    достаточно для эксплуатации, WHERE user_id закрывает и на уровне SQL тоже)."""
    conn.execute(
        "UPDATE reminders SET due_at = datetime(due_at, '+1 day'), sent_at = NULL "
        "WHERE reminder_id = ? AND user_id = ?",
        (reminder_id, user_id),
    )
    conn.commit()


def close_item(repo, user_id: str, item_kind: str, item_key: str) -> None:
    """«✅ Сделано»: закрыть обещание/факт под напоминанием. deep_fact — no-op
    (M8 не реализован, таблицы нет).

    P-TEN-04: user_id ОБЯЗАН дойти до repo.update_event_status — чужой
    item_key иначе закрывал бы событие другого пользователя. Несовпадение
    владельца/несуществующий id логируется явно (не тихий no-op, в отличие
    от штатных мутаторов — это callback-путь Telegram)."""
    if item_kind == "event":
        try:
            event_id = int(item_key)
        except (ValueError, TypeError):
            return
        if not repo.update_event_status(user_id, event_id, "fulfilled"):
            logger.warning(
                "close_item: event_id=%s не принадлежит user_id=%s (или не найден)",
                event_id, user_id,
            )
    elif item_kind == "promise":
        conn = repo._get_conn()
        conn.execute(
            "UPDATE promises SET status = 'fulfilled' WHERE promise_id = ? AND user_id = ?",
            (item_key, user_id),
        )
        conn.commit()
