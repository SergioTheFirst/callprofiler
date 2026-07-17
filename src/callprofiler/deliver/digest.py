# -*- coding: utf-8 -*-
"""
digest.py — A1 (ozalupennieStrategic5.md §A1): реестр обязательств (promises+debts)
в ОБЕИХ сторонах (владелец должен / контакту должны), с цитатой и датой.

Источники — UNION events(promise/debt) и legacy promises, дедуп по (call_id, what).
events приоритетнее (несёт verbatim-цитату из транскрипта).

Инвариант 25 (плановые пуши — РОВНО два: F5 вечерний, F6 doctor; см. .claude/rules
и OzaluplivanieFable.md §1 п.25): этот модуль НЕ шлёт Telegram и не планирует .bat/
Task Scheduler — только строит markdown-текст. Отправка появится КАК СЕКЦИЯ внутри
F5, когда тот будет реализован (задача F5, ozalup2.md/Fable §2).
"""

from __future__ import annotations

from datetime import date, datetime

_MAX_ITEM_CHARS = 300  # CLAUDE.md: "Output: ≤300 chars/item"
_MAX_ITEMS_PER_SECTION = 10


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except ValueError:
        return None


def _has_table(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _year_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "год"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "года"
    return "лет"


def on_this_day(conn, user_id: str, today: str | None = None) -> list[str]:
    """D1: годовщины — сцены той же MM-DD в прошлые годы, importance>70.

    БД без biography (нет bio_scenes) -> [], не исключение.
    """
    if not _has_table(conn, "bio_scenes"):
        return []
    ref = _parse_date(today) or date.today()
    ref_iso = ref.isoformat()
    rows = conn.execute(
        """SELECT call_datetime, synopsis, key_quote FROM bio_scenes
            WHERE user_id = ? AND importance > 70
              AND strftime('%m-%d', call_datetime) = strftime('%m-%d', ?)
              AND strftime('%Y', call_datetime) < strftime('%Y', ?)
            ORDER BY call_datetime DESC""",
        (user_id, ref_iso, ref_iso),
    ).fetchall()

    lines = []
    for r in rows:
        scene_date = _parse_date(r["call_datetime"])
        if scene_date is None:
            continue
        n = ref.year - scene_date.year
        line = f"{n} {_year_word(n)} назад: {_truncate(r['synopsis'] or '', 200)}"
        quote = _truncate(r["key_quote"] or "", 100)
        if quote:
            line += f" — «{quote}»"
        lines.append(line)
    return lines


def _side(who: str | None) -> str | None:
    if who == "OWNER":
        return "owner"
    if who == "OTHER":
        return "contact"
    return None  # UNKNOWN/None — исключено (шум-доктрина: не приписываем сторону наугад)


def _dedup_key(call_id: int, what: str | None) -> tuple:
    return (call_id, (what or "").strip().lower()[:40])


def _rows_from_events(conn, user_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT e.id AS item_id, e.call_id, e.who, e.payload AS what, e.deadline,
                  e.source_quote AS quote, e.contact_id,
                  date(c.call_datetime) AS call_date,
                  COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164, '?') AS contact_name
             FROM events e
             JOIN calls c ON c.call_id = e.call_id
             LEFT JOIN contacts ct ON ct.contact_id = e.contact_id
            WHERE e.user_id = ? AND e.event_type IN ('promise', 'debt')
              AND e.status = 'open' AND e.deadline IS NOT NULL""",
        (user_id,),
    ).fetchall()
    items = []
    for r in rows:
        side = _side(r["who"])
        if side is None:
            continue
        items.append({
            "side": side, "contact_id": r["contact_id"], "contact_name": r["contact_name"],
            "what": r["what"], "deadline": r["deadline"], "call_date": r["call_date"],
            "quote": r["quote"], "origin": "events", "call_id": r["call_id"],
            "item_kind": "event", "item_key": str(r["item_id"]),
        })
    return items


def _rows_from_promises(conn, user_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT p.promise_id AS item_id, p.call_id, p.who, p.what, p.due AS deadline,
                  p.contact_id, date(c.call_datetime) AS call_date,
                  COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164, '?') AS contact_name
             FROM promises p
             JOIN calls c ON c.call_id = p.call_id
             LEFT JOIN contacts ct ON ct.contact_id = p.contact_id
            WHERE p.user_id = ? AND p.status = 'open' AND p.due IS NOT NULL""",
        (user_id,),
    ).fetchall()
    items = []
    for r in rows:
        side = _side(r["who"])
        if side is None:
            continue
        items.append({
            "side": side, "contact_id": r["contact_id"], "contact_name": r["contact_name"],
            "what": r["what"], "deadline": r["deadline"], "call_date": r["call_date"],
            "quote": None, "origin": "promises", "call_id": r["call_id"],
            "item_kind": "promise", "item_key": str(r["item_id"]),
        })
    return items


def _apply_verdicts(conn, user_id: str, items: list[dict]) -> list[dict]:
    """F1: rejected выбрасываем, confirmed помечаем. Один choke-point для
    overdue_items/open_items (оба идут через _merged_open_items)."""
    from callprofiler.insight.repository import apply_insight_schema, get_verdicts

    apply_insight_schema(conn)
    by_kind: dict[str, list[str]] = {}
    for item in items:
        by_kind.setdefault(item["item_kind"], []).append(item["item_key"])
    verdicts = {
        kind: get_verdicts(conn, user_id, kind, keys) for kind, keys in by_kind.items()
    }

    out = []
    for item in items:
        verdict = verdicts.get(item["item_kind"], {}).get(item["item_key"])
        if verdict == "rejected":
            continue
        item = dict(item)
        item["confirmed"] = verdict == "confirmed"
        out.append(item)
    return out


def _merged_open_items(conn, user_id: str) -> list[dict]:
    """UNION events+promises, дедуп по (call_id, what[:40]) — events приоритетнее."""
    merged: dict[tuple, dict] = {}
    for item in _rows_from_promises(conn, user_id):
        merged[_dedup_key(item["call_id"], item["what"])] = item
    for item in _rows_from_events(conn, user_id):
        merged[_dedup_key(item["call_id"], item["what"])] = item  # events перезаписывают
    return _apply_verdicts(conn, user_id, list(merged.values()))


def overdue_items(conn, user_id: str, today: str | None = None) -> list[dict]:
    """Открытые promise/debt с deadline < today, с days_overdue."""
    ref = _parse_date(today) or date.today()
    out = []
    for item in _merged_open_items(conn, user_id):
        deadline = _parse_date(item["deadline"])
        if deadline is None or deadline >= ref:
            continue
        item = dict(item)
        item["days_overdue"] = (ref - deadline).days
        out.append(item)
    out.sort(key=lambda i: i["days_overdue"], reverse=True)
    return out


def open_items(conn, user_id: str, today: str | None = None) -> list[dict]:
    """Открытые promise/debt с deadline >= today (ещё не просрочены)."""
    ref = _parse_date(today) or date.today()
    out = []
    for item in _merged_open_items(conn, user_id):
        deadline = _parse_date(item["deadline"])
        if deadline is None or deadline < ref:
            continue
        item = dict(item)
        item["days_until"] = (deadline - ref).days
        out.append(item)
    out.sort(key=lambda i: i["days_until"])
    return out


def _truncate(text: str, n: int = _MAX_ITEM_CHARS) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _amount_suffix(item: dict) -> str:
    """B7: сумма из what+quote САМОГО item (не агрегат по контакту) — «(~40 тыс ₽)»."""
    from callprofiler.insight.finance import extract_amounts, format_amount_range

    text = f"{item.get('what') or ''} {item.get('quote') or ''}"
    by_currency: dict[str, float] = {}
    for value, currency in extract_amounts(text):
        by_currency[currency] = max(by_currency.get(currency, 0.0), value)
    if not by_currency:
        return ""
    parts = [format_amount_range(v, v, cur) for cur, v in by_currency.items()]
    return "(" + " + ".join(parts) + ")"


def _format_item(item: dict) -> list[str]:
    what = _truncate(item["what"], 160)
    mark = "✓ " if item.get("confirmed") else ""
    line = f"- {mark}**{item['contact_name']}**: {what} — обещано {item['call_date'] or '?'}, срок {item['deadline']}"
    if "days_overdue" in item:
        amount = _amount_suffix(item)
        if amount:
            line += f" {amount}"
    lines = [_truncate(line)]
    if item.get("quote"):
        lines.append(_truncate(f"  > «{item['quote']}»"))
    return lines


def build_digest(
    conn, user_id: str, today: str | None = None,
    extra_sections: list[tuple[str, list[str]]] | None = None,
) -> str:
    """Markdown-отчёт: просрочено ИМИ / просрочено ВАМИ / открыто (14 дней).

    ``extra_sections`` — [(заголовок, [строка, ...])] от других модулей (M8:
    recent_deep_lines); пустые секции (нет строк) пропускаются молча."""
    overdue = overdue_items(conn, user_id, today)
    owner_overdue = [i for i in overdue if i["side"] == "owner"]
    contact_overdue = [i for i in overdue if i["side"] == "contact"]
    upcoming = [i for i in open_items(conn, user_id, today) if i["days_until"] <= 14]

    lines = ["# Обязательства\n"]

    lines.append("## Просрочено ВАМИ")
    if owner_overdue:
        for item in owner_overdue[:_MAX_ITEMS_PER_SECTION]:
            lines.extend(_format_item(item))
    else:
        lines.append("- нет")

    lines.append("\n## Просрочено ИМИ")
    if contact_overdue:
        for item in contact_overdue[:_MAX_ITEMS_PER_SECTION]:
            lines.extend(_format_item(item))
    else:
        lines.append("- нет")

    lines.append("\n## Открыто — срок в ближайшие 14 дней")
    if upcoming:
        for item in upcoming[:_MAX_ITEMS_PER_SECTION]:
            lines.extend(_format_item(item))
    else:
        lines.append("- нет")

    onthisday_lines = on_this_day(conn, user_id, today)
    if onthisday_lines:
        lines.append("\n## 🗓 В этот день")
        lines.extend(onthisday_lines)

    for title, section_lines in (extra_sections or []):
        if not section_lines:
            continue
        lines.append(f"\n## {title}")
        lines.extend(section_lines)

    return "\n".join(lines)
