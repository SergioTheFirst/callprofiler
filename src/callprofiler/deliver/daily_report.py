# -*- coding: utf-8 -*-
"""
daily_report.py — F5: вечерний отчёт дня (21:00) + случайное воспоминание.

Секции опускаются, если пусты. Обязательства (📌/⏰) переиспользуют A1
(deliver/digest.py) — единый источник, единая F1-фильтрация (rejected скрыт).
"""
from __future__ import annotations

import html
from datetime import datetime, timedelta

from callprofiler.deliver import digest as _digest

_MAX_REPORT_CHARS = 4096
_MAX_ITEMS_PER_SECTION = 5


def _esc(text: str | None) -> str:
    return html.escape((text or "").strip())


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _section_today(conn, user_id: str, date: str) -> str:
    rows = conn.execute(
        """SELECT c.duration_sec,
                  COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164, '?') AS name
             FROM calls c
             LEFT JOIN contacts ct ON ct.contact_id = c.contact_id
            WHERE c.user_id = ? AND c.call_type IS NULL
              AND date(COALESCE(c.call_datetime, c.created_at)) = ?""",
        (user_id, date),
    ).fetchall()
    if not rows:
        return ""
    total_min = sum((r["duration_sec"] or 0) for r in rows) // 60
    top = sorted(rows, key=lambda r: r["duration_sec"] or 0, reverse=True)[:3]
    lines = [f"📞 <b>Сегодня</b>: {len(rows)} звонков, {total_min} мин"]
    for r in top:
        mins = (r["duration_sec"] or 0) // 60
        lines.append(f"  • {_esc(r['name'])} — {mins} мин")
    return "\n".join(lines)


def _section_new_obligations(conn, user_id: str, date: str) -> str:
    items = [i for i in _digest._merged_open_items(conn, user_id) if i["call_date"] == date]
    if not items:
        return ""
    lines = ["📌 <b>Новое</b>"]
    for item in items[:_MAX_ITEMS_PER_SECTION]:
        mark = "✓ " if item.get("confirmed") else ""
        what = _truncate(item["what"] or "", 160)
        lines.append(f"  • {mark}{_esc(item['contact_name'])}: {_esc(what)}")
    return "\n".join(lines)


def _section_tomorrow(conn, user_id: str, date: str) -> str:
    tomorrow = (datetime.fromisoformat(date) + timedelta(days=1)).date().isoformat()
    rem_rows = conn.execute(
        """SELECT text FROM reminders
            WHERE user_id = ? AND enabled = 1 AND sent_at IS NULL AND date(due_at) = ?
            ORDER BY due_at""",
        (user_id, tomorrow),
    ).fetchall()
    overdue = _digest.overdue_items(conn, user_id, today=date)

    lines: list[str] = []
    for r in rem_rows[:_MAX_ITEMS_PER_SECTION]:
        lines.append(f"  • 🔔 {_esc(_truncate(r['text'], 160))}")
    for item in overdue[:_MAX_ITEMS_PER_SECTION]:
        what = _truncate(item["what"] or "", 140)
        lines.append(
            f"  • ⚠ {_esc(item['contact_name'])}: {_esc(what)} "
            f"(просрочено {item['days_overdue']}д)"
        )
    if not lines:
        return ""
    return "\n".join(["⏰ <b>Завтра</b>"] + lines)


def _section_errors(conn, user_id: str, date: str) -> str:
    rows = conn.execute(
        """SELECT source_filename, error_message FROM calls
            WHERE user_id = ? AND status = 'error'
              AND date(COALESCE(call_datetime, created_at)) = ?""",
        (user_id, date),
    ).fetchall()
    if not rows:
        return ""
    lines = ["⚠️ <b>Ошибки</b>"]
    for r in rows[:_MAX_ITEMS_PER_SECTION]:
        err = _truncate(r["error_message"] or "?", 100)
        lines.append(f"  • {_esc(r['source_filename'])}: {_esc(err)}")
    return "\n".join(lines)


def _section_memory(conn, user_id: str, date: str) -> str:
    row = conn.execute(
        """SELECT e.source_quote AS quote,
                  COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164, '?') AS name,
                  date(COALESCE(c.call_datetime, c.created_at)) AS call_date
             FROM events e
             JOIN calls c ON c.call_id = e.call_id
             LEFT JOIN contacts ct ON ct.contact_id = e.contact_id
            WHERE e.user_id = ? AND e.source_quote IS NOT NULL AND e.source_quote != ''
              AND date(COALESCE(c.call_datetime, c.created_at)) < date(?, '-180 days')
            ORDER BY RANDOM() LIMIT 1""",
        (user_id, date),
    ).fetchone()
    if not row:
        return ""
    quote = _truncate(row["quote"], 200)
    return f"🎲 <b>Воспоминание</b>\n  «{_esc(quote)}» — {_esc(row['name'])}, {row['call_date']}"


def build_daily_report(conn, user_id: str, date: str) -> str:
    """Собрать вечерний отчёт (Telegram-HTML) за календарный день ``date`` (YYYY-MM-DD)."""
    sections = [
        f"🗓 <b>Итоги дня — {date}</b>",
        _section_today(conn, user_id, date),
        _section_new_obligations(conn, user_id, date),
        _section_tomorrow(conn, user_id, date),
        _section_errors(conn, user_id, date),
        _section_memory(conn, user_id, date),
    ]
    text = "\n\n".join(s for s in sections if s)
    if len(text) > _MAX_REPORT_CHARS:
        text = text[: _MAX_REPORT_CHARS - 1].rstrip() + "…"
    return text
