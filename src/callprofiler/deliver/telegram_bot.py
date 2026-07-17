# -*- coding: utf-8 -*-
"""
telegram_bot.py — Telegram-бот для доставки саммари и команд.

Один бот на всех пользователей. Различает по chat_id.
Команды: /start, /digest [N] [days], /search текст, /contact +7..., /promises, /status
Автосообщения: саммари после каждого обработанного звонка с кнопками [OK]/[Неточно].

ВАЖНО: python-telegram-bot подгружается лениво, при вызове run().
Для импорта модуля не требуется установленная телеграм-библиотека.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from callprofiler.deliver.reminders import (
    MAX_CONSECUTIVE_ERRORS,
    close_item,
    create_reminder,
    due_reminders,
    mark_error,
    mark_sent,
    parse_due_ru,
    snooze_reminder,
)

if TYPE_CHECKING:
    from callprofiler.db.repository import Repository

logger = logging.getLogger(__name__)

_FV_VERDICT_LETTERS = {"c": "confirmed", "r": "rejected"}
_FV_KINDS = ("promise", "event", "deep_fact")
_PENDING_REMINDER_TTL_SEC = 300
_REMINDER_TICK_SEC = 60

_REMASK_RE = re.compile(r"^remask\|([a-z_]+)\|(.+)$")
_REMDONE_RE = re.compile(r"^remdone\|([a-z_]+)\|(.+)$")
_REMSNOOZE_RE = re.compile(r"^remsnooze\|(\d+)$")


def parse_fv_callback(data: str) -> tuple[str, str, str] | None:
    """Разобрать callback_data='fv|{kind}|{key}|{c|r}' (F1). None — битые данные
    (старая кнопка/чужой формат), вызывающий должен ответить «устарело», не падать."""
    parts = (data or "").split("|")
    if len(parts) != 4 or parts[0] != "fv":
        return None
    _, kind, key, letter = parts
    if kind not in _FV_KINDS or letter not in _FV_VERDICT_LETTERS or not key:
        return None
    return kind, key, _FV_VERDICT_LETTERS[letter]


class TelegramNotifier:
    """Telegram-бот для уведомлений и команд.

    Использование:
        notifier = TelegramNotifier(repo=repo)  # Токен из TELEGRAM_BOT_TOKEN
        await notifier.send_summary(user_id="serhio", call_id=42)
        notifier.run()  # Запустить polling в отдельном потоке
    """

    def __init__(self, repo: Repository, token: str | None = None) -> None:
        """Инициализировать Telegram-бот.

        Параметры:
            repo   — Repository для доступа к данным
            token  — токен бота (если None, берётся из TELEGRAM_BOT_TOKEN)
        """
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.repo = repo
        self.app = None
        # F2: chat_id -> {user_id,item_kind,item_key,text,expires_at} пока бот ждёт
        # дату после «🔔 Напомнить». TTL 5 мин, упрощение сознательное (spec F2 §2).
        self._pending_reminders: dict[int, dict] = {}

        if not self.token:
            logger.warning(
                "TELEGRAM_BOT_TOKEN не установлен. "
                "Бот не будет работать. "
                "Установите переменную окружения TELEGRAM_BOT_TOKEN"
            )
        else:
            logger.info("TelegramNotifier инициализирован")

    async def send_summary(self, user_id: str, call_id: int) -> None:
        """Отправить саммари звонка пользователю по его chat_id.

        Параметры:
            user_id  — идентификатор пользователя
            call_id  — идентификатор звонка
        """
        # Лениво загрузить Telegram классы только при отправке
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        except (ImportError, Exception):
            logger.error("python-telegram-bot не установлен")
            return

        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN не установлен, саммари не отправлен")
            return

        user = self.repo.get_user(user_id)
        if not user:
            logger.error("Пользователь %s не найден", user_id)
            return

        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            logger.debug(
                "У пользователя %s не установлен telegram_chat_id",
                user_id,
            )
            return

        call = self.repo._get_conn().execute(
            "SELECT * FROM calls WHERE user_id=? AND call_id=?",
            (user_id, call_id),
        ).fetchone()
        if not call:
            logger.error("Звонок %d не найден", call_id)
            return

        call = dict(call)
        contact_id = call.get("contact_id")
        contact = self.repo.get_contact(user_id, contact_id) if contact_id else None
        contact_name = contact.get("display_name", "?") if contact else "?"
        phone = contact.get("phone_e164", "?") if contact else "?"

        analysis = self.repo.get_analysis(user_id, call_id)
        if not analysis:
            logger.warning("Анализ для звонка %d не найден", call_id)
            return

        summary = analysis.get("summary", "Нет саммари")
        priority = analysis.get("priority", 0)
        risk_score = analysis.get("risk_score", 0)
        action_items = analysis.get("action_items", [])
        direction = call.get("direction", "?")
        call_datetime = call.get("call_datetime", "?")
        duration_sec = call.get("duration_sec", 0) or 0

        # Risk emoji
        risk_emoji = "🟢" if risk_score < 30 else "🟡" if risk_score < 70 else "🔴"

        # Форматирование сообщения
        msg = (
            f"📞 {direction} → <b>{contact_name}</b> ({phone})\n"
            f"📅 {call_datetime} | ⏱ {duration_sec}s\n"
            f"───────────────────\n"
            f"{summary}\n"
            f"⚡ Priority: {priority} | Risk: {risk_score} {risk_emoji}\n"
        )

        if action_items:
            msg += "\n📌 Действия:\n"
            for item in action_items[:3]:
                msg += f"  • {item}\n"

        # Кнопки обратной связи
        keyboard = [
            [
                InlineKeyboardButton("✅ OK", callback_data=f"feedback_{call_id}_ok"),
                InlineKeyboardButton(
                    "❌ Неточно",
                    callback_data=f"feedback_{call_id}_inaccurate",
                ),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            if self.app:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                logger.info(
                    "Саммари отправлен пользователю %s (chat_id=%s, call_id=%d)",
                    user_id, chat_id, call_id,
                )
            else:
                logger.warning(
                    "App не инициализирован, саммари не отправлен"
                )
        except Exception as exc:
            logger.error(
                "Ошибка при отправке саммари для call_id=%d: %s", call_id, exc
            )

    async def handle_feedback(self, update, context) -> None:
        """Обработать нажатие [OK] / [Неточно].

        Параметры:
            update   — объект события Telegram
            context  — контекст бота
        """
        query = update.callback_query
        await query.answer()

        data = query.data  # "feedback_{call_id}_{ok|inaccurate}"
        parts = data.split("_")
        if len(parts) < 3:
            await query.edit_message_text(text="❌ Невалидный callback")
            return

        try:
            call_id = int(parts[1])
            feedback_type = parts[2]
        except (ValueError, IndexError):
            await query.edit_message_text(text="❌ Ошибка обработки")
            return

        feedback_text = "ok" if feedback_type == "ok" else "inaccurate"
        feedback_display = "✅ OK" if feedback_type == "ok" else "❌ Неточно"

        user_id = self._get_user_id(update)
        if user_id is None:
            await query.edit_message_text(text="❌ Не найден ваш user_id")
            return

        try:
            # Получить analysis_id для call_id
            analysis = self.repo.get_analysis(user_id, call_id)
            if analysis:
                analysis_id = analysis.get("analysis_id")
                if analysis_id:
                    self.repo.set_feedback(analysis_id, feedback_text)
                    await query.edit_message_text(
                        text=f"💾 Ваш отзыв записан: {feedback_display}"
                    )
                    logger.info(
                        "Feedback для call_id=%d (analysis_id=%d): %s",
                        call_id, analysis_id, feedback_text
                    )
                else:
                    await query.edit_message_text(text="❌ Analysis не найдена")
            else:
                await query.edit_message_text(text="❌ Анализ звонка не найден")
        except Exception as exc:
            logger.error("Ошибка при сохранении feedback для call_id=%d: %s", call_id, exc)
            await query.edit_message_text(text="❌ Ошибка сохранения")


    async def cmd_help(self, update, context) -> None:
        """/help — список доступных команд."""
        msg = (
            "🤖 <b>CallProfiler — команды:</b>\n\n"
            "/digest [N] [дни] — дайджест важных звонков\n"
            "/search текст — найти разговор\n"
            "/contact +7... или имя — карточка контакта\n"
            "/promises — открытые обещания\n"
            "/status — очередь и ошибки\n"
            "/help — этот список"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_start(self, update, context) -> None:
        """/start — приветствие и список команд."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text(
                "❌ Ваш chat_id не зарегистрирован. "
                "Попросите администратора добавить вас: `add-user ... --telegram-chat-id <ваш_id>`"
            )
            return

        user = self.repo.get_user(user_id)
        display_name = user.get("display_name", user_id) if user else user_id

        msg = (
            f"👋 Добро пожаловать, <b>{display_name}</b>!\n\n"
            f"<b>📞 Доступные команды:</b>\n"
            f"/digest [N] [days] — топ-N звонков по priority за days дней (по умолчанию 5 звонков, 1 день)\n"
            f"/search &lt;текст&gt; — поиск по транскриптам (до 5 результатов)\n"
            f"/contact &lt;номер или имя&gt; — карточка контакта\n"
            f"/promises — все открытые обещания\n"
            f"/status — состояние очереди обработки\n\n"
            f"<b>💬 Как это работает:</b>\n"
            f"После каждого нового звонка вы получите саммари с кнопками [✅ OK] или [❌ Неточно] "
            f"для обратной связи."
        )

        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_digest(self, update, context) -> None:
        """/digest [N] [days] — топ-N звонков по priority за days дней."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text("❌ Не найден ваш user_id")
            return

        # Parse arguments: [N] [days]
        # Default: N=5, days=1
        limit = 5
        days = 1

        if context.args:
            try:
                if len(context.args) >= 1:
                    limit = int(context.args[0])
                if len(context.args) >= 2:
                    days = int(context.args[1])
            except ValueError:
                pass

        calls = self.repo.get_calls_for_user(user_id, limit=max(limit + 5, 20))
        if not calls:
            await update.message.reply_text("📭 Нет звонков")
            return

        # Фильтруем по дате
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        recent = [c for c in calls if c.get("created_at", "") >= cutoff]

        if not recent:
            await update.message.reply_text(
                f"📭 Нет звонков за последние {days} дней"
            )
            return

        # Сортируем по priority и берём топ limit
        call_with_priority = []
        for call in recent:
            analysis = self.repo.get_analysis(user_id, call["call_id"])
            priority = analysis.get("priority", 0) if analysis else 0
            call_with_priority.append((priority, call, analysis))

        call_with_priority.sort(key=lambda x: x[0], reverse=True)

        msg = f"📊 Топ-{min(limit, len(call_with_priority))} звонков за {days} дней (по priority):\n\n"
        for priority, call, analysis in call_with_priority[:limit]:
            contact_id = call.get("contact_id")
            contact = (
                self.repo.get_contact(user_id, contact_id) if contact_id else None
            )
            name = contact.get("display_name", "?") if contact else "?"
            phone = contact.get("phone_e164", "?") if contact else "?"
            direction = call.get("direction", "?")
            created = (call.get("created_at") or "")[:16]
            msg += f"[P:{priority:3d}] {direction} → {name} ({phone}) | {created}\n"

        await update.message.reply_text(msg)

    async def cmd_search(self, update, context) -> None:
        """/search {текст} — поиск по транскриптам (до 5 результатов)."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text("❌ Не найден ваш user_id")
            return

        if not context.args:
            await update.message.reply_text("❌ Используйте: /search <текст>")
            return

        query_text = " ".join(context.args)
        results = self.repo.search_transcripts(user_id, query_text)

        if not results:
            await update.message.reply_text(
                f"🔍 Ничего не найдено по '<i>{query_text}</i>'", parse_mode="HTML"
            )
            return

        msg = f"🔍 Найдено {len(results)} совпадений (показаны первые 5):\n\n"
        for res in results[:5]:
            call_id = res.get("call_id")
            call = self.repo.get_call(user_id, call_id)

            if call:
                call = dict(call)
                contact_id = call.get("contact_id")
                contact = (
                    self.repo.get_contact(user_id, contact_id) if contact_id else None
                )
                contact_name = (
                    contact.get("display_name", "?") if contact else "?"
                )
                call_date = (call.get("call_datetime") or "")[:10]
            else:
                contact_name = "?"
                call_date = "?"

            text = res.get("text", "?")[:80]
            speaker = res.get("speaker", "?")
            msg += (
                f"<b>{contact_name}</b> ({call_date})\n"
                f"[{speaker}] <i>{text}</i>...\n\n"
            )

        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_contact(self, update, context) -> None:
        """/contact <номер или имя> — карточка контакта из contact_summaries."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text("❌ Не найден ваш user_id")
            return

        if not context.args:
            await update.message.reply_text(
                "❌ Используйте: /contact <номер или имя>"
            )
            return

        query = " ".join(context.args)
        contact = None

        # Сначала попробуем по номеру (если начинается с +, 7, или 8)
        if query.replace("+", "").replace("-", "").replace("(", "").replace(")", "").replace(" ", "").isdigit():
            contact = self.repo.get_contact_by_phone(user_id, query)

        # Если не найден по номеру, ищем по имени в списке контактов
        if not contact:
            all_contacts = self.repo.get_all_contacts_for_user(user_id)
            for c in all_contacts:
                name = c.get("display_name", "")
                if name.lower() == query.lower():
                    contact = c
                    break

        if not contact:
            await update.message.reply_text(
                f"❌ Контакт '<i>{query}</i>' не найден", parse_mode="HTML"
            )
            return

        contact_id = contact["contact_id"]
        name = contact.get("display_name", "?")
        phone = contact.get("phone_e164", "?")

        summary = self.repo.get_contact_summary(user_id, contact_id)

        if not summary:
            await update.message.reply_text(
                f"ℹ️ Контакт <b>{name}</b> ({phone}) найден, но саммари ещё не построена",
                parse_mode="HTML"
            )
            return

        # Форматируем карточку
        total_calls = summary.get("total_calls", 0)
        global_risk = summary.get("global_risk", 0)
        avg_bs_score = summary.get("avg_bs_score", 0)
        top_hook = summary.get("top_hook", "")
        contact_role = summary.get("contact_role", "")
        advice = summary.get("advice", "")
        open_promises = summary.get("open_promises", "")
        open_debts = summary.get("open_debts", "")

        # Risk emoji
        risk_emoji = "🟢" if global_risk < 30 else "🟡" if global_risk < 70 else "🔴"

        msg = (
            f"👤 <b>{name}</b> ({phone})\n"
        )
        if contact_role:
            msg += f"💼 {contact_role}\n"
        msg += (
            f"📞 Звонков: {total_calls}\n"
            f"⚡ Risk: {global_risk} {risk_emoji} | BS: {avg_bs_score}\n"
        )

        if top_hook:
            msg += f"🎣 Hook: <i>{top_hook}</i>\n"

        # Обещания и долги
        try:
            import json
            if open_promises and open_promises != "[]":
                promises = json.loads(open_promises)
                if promises:
                    msg += f"\n🤝 Обещания:\n"
                    for p in promises[:2]:
                        payload = p.get("payload", "?")
                        msg += f"  • {payload}\n"

            if open_debts and open_debts != "[]":
                debts = json.loads(open_debts)
                if debts:
                    msg += f"\n💰 Долги:\n"
                    for d in debts[:2]:
                        payload = d.get("payload", "?")
                        msg += f"  • {payload}\n"
        except (json.JSONDecodeError, TypeError):
            pass

        if advice:
            msg += f"\n💡 <i>{advice}</i>\n"

        await update.message.reply_text(msg, parse_mode="HTML")

    def _render_promises_view(self, user_id: str):
        """Собрать текст+клавиатуру /promises (F1): rejected скрыты, confirmed
        помечены ✓; каждый item — своя пара кнопок ✓N/✗N в общей клавиатуре
        сообщения (Telegram не даёт кнопки внутри текста, только грид на сообщение).
        Реюз: первичная отправка (cmd_promises) и refresh после тапа (handle_fact_verdict)."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        from callprofiler.insight.repository import apply_insight_schema, get_verdicts

        promises = self.repo.get_open_events(user_id, event_type="promise")

        conn = self.repo._get_conn()
        apply_insight_schema(conn)
        keys = [str(p["id"]) for p in promises]
        verdicts = get_verdicts(conn, user_id, "event", keys)
        promises = [p for p in promises if verdicts.get(str(p["id"])) != "rejected"]

        if not promises:
            return "✅ Нет открытых обещаний", None

        by_contact: dict = {}
        for p in promises:
            by_contact.setdefault(p.get("contact_id"), []).append(p)

        lines = [f"📌 Открытые обещания ({len(promises)}):", ""]
        keyboard = []
        shown_contacts = 0
        for contact_id, contact_promises in by_contact.items():
            if shown_contacts >= 5:  # Максимум 5 контактов в сообщении
                lines.append(f"... и ещё {len(by_contact) - shown_contacts} контактов")
                break

            contact = self.repo.get_contact(user_id, contact_id) if contact_id else None
            name = contact.get("display_name", "?") if contact else "?"
            lines.append(f"👤 <b>{name}</b>")

            for p in contact_promises[:3]:
                n = len(keyboard) + 1
                mark = "✓ " if verdicts.get(str(p["id"])) == "confirmed" else ""
                payload = p.get("payload", "?")
                who = p.get("who", "?")
                deadline = p.get("deadline", "—")
                lines.append(f"  {n}. {mark}[{who}] {payload} (до {deadline})")
                keyboard.append([
                    InlineKeyboardButton(f"✓{n}", callback_data=f"fv|event|{p['id']}|c"),
                    InlineKeyboardButton(f"✗{n}", callback_data=f"fv|event|{p['id']}|r"),
                ])

            lines.append("")
            shown_contacts += 1

        return "\n".join(lines), InlineKeyboardMarkup(keyboard)

    async def cmd_promises(self, update, context) -> None:
        """/promises — открытые обещания, сгруппированные по контакту, с ✓/✗ на item (F1)."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text("❌ Не найден ваш user_id")
            return

        msg, keyboard = self._render_promises_view(user_id)
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=keyboard)

    async def handle_fact_verdict(self, update, context) -> None:
        """Обработать тап ✓/✗ по одному факту/обещанию (F1).

        Параметры:
            update   — объект события Telegram
            context  — контекст бота
        """
        query = update.callback_query
        await query.answer()

        parsed = parse_fv_callback(query.data)
        if parsed is None:
            await query.edit_message_text(text="⏳ Устарело")
            return
        item_kind, item_key, verdict = parsed

        user_id = self._get_user_id(update)
        if user_id is None:
            await query.edit_message_text(text="❌ Не найден ваш user_id")
            return

        try:
            from callprofiler.insight.repository import apply_insight_schema, set_fact_verdict

            conn = self.repo._get_conn()
            apply_insight_schema(conn)
            set_fact_verdict(conn, user_id, item_kind=item_kind, item_key=item_key, verdict=verdict)
        except Exception as exc:
            logger.error("Ошибка сохранения вердикта fv %s: %s", query.data, exc)
            await query.edit_message_text(text="❌ Ошибка сохранения")
            return

        # Единственный сегодняшний источник fv-кнопок — /promises: перерисовать
        # тот же вид (rejected пропадёт из списка, confirmed получит ✓).
        msg, keyboard = self._render_promises_view(user_id)
        await query.edit_message_text(text=msg, parse_mode="HTML", reply_markup=keyboard)

        if verdict == "confirmed":
            # F2: предложить напоминание. Только по явному тапу владельца дальше
            # (инвариант 18) — эта кнопка НЕ создаёт reminder сама, лишь спрашивает.
            promise_text = self._promise_text_for(user_id, item_kind, item_key)
            if promise_text:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                remind_kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔔 Напомнить", callback_data=f"remask|{item_kind}|{item_key}")]])
                await query.message.reply_text(
                    f"✓ Подтверждено: {promise_text}", reply_markup=remind_kb)

    def _promise_text_for(self, user_id: str, item_kind: str, item_key: str) -> str | None:
        """Человеко-читаемый текст обещания для кнопки-предложения/reminders.text (F2).
        None — не удалось найти/описать (напр. deep_fact — таблицы ещё нет, M8)."""
        if item_kind == "event":
            for p in self.repo.get_open_events(user_id, event_type="promise"):
                if str(p.get("id")) == str(item_key):
                    return f"[{p.get('who', '?')}] {p.get('payload', '?')}"
            return None
        if item_kind == "promise":
            conn = self.repo._get_conn()
            row = conn.execute(
                "SELECT who, what FROM promises WHERE promise_id = ? AND user_id = ?",
                (item_key, user_id),
            ).fetchone()
            return f"[{row[0]}] {row[1]}" if row else None
        return None

    async def handle_remind_ask(self, update, context) -> None:
        """«🔔 Напомнить» -> спросить дату (F2). Следующее текстовое сообщение
        этого chat_id разбирается parse_due_ru (handle_plain_text)."""
        query = update.callback_query
        await query.answer()

        m = _REMASK_RE.match(query.data or "")
        if not m:
            await query.edit_message_text(text="⏳ Устарело")
            return
        item_kind, item_key = m.group(1), m.group(2)

        user_id = self._get_user_id(update)
        if user_id is None:
            await query.edit_message_text(text="❌ Не найден ваш user_id")
            return

        text = self._promise_text_for(user_id, item_kind, item_key)
        if text is None:
            await query.edit_message_text(text="❌ Не нашёл этот пункт")
            return

        chat_id = update.effective_user.id
        self._pending_reminders[chat_id] = {
            "user_id": user_id, "item_kind": item_kind, "item_key": item_key, "text": text,
            "expires_at": datetime.now() + timedelta(seconds=_PENDING_REMINDER_TTL_SEC),
        }
        await query.edit_message_text(text="Когда напомнить? (завтра / в пятницу / 15.07)")

    async def handle_plain_text(self, update, context) -> None:
        """Текст вне команд (F2): сейчас разбирает ТОЛЬКО «жду дату» после «🔔
        Напомнить». Иначе — молча игнор (F3 добавит ask-путь СЮДА ЖЕ веткой
        else, после проверки pending — не заменять эту функцию, дополнять).

        Security (defense-in-depth, review 2026-07-17): _pending_reminders
        сегодня заполняется ТОЛЬКО из handle_remind_ask (который сам гейтит
        _get_user_id) — но re-check здесь на случай будущего бага, который
        занесёт в словарь chat_id без allowlist-проверки."""
        user_id = self._get_user_id(update)
        if user_id is None:
            return
        chat_id = update.effective_user.id if update.effective_user else None
        if chat_id is None:
            return
        pending = self._pending_reminders.get(chat_id)
        if pending is None or pending["user_id"] != user_id:
            return
        if datetime.now() > pending["expires_at"]:
            del self._pending_reminders[chat_id]
            return

        due = parse_due_ru(update.message.text, datetime.now())
        if due is None:
            await update.message.reply_text("Не понял дату, напиши как DD.MM")
            return

        from callprofiler.insight.repository import apply_insight_schema

        conn = self.repo._get_conn()
        apply_insight_schema(conn)
        create_reminder(conn, pending["user_id"], item_kind=pending["item_kind"],
                         item_key=pending["item_key"], text=pending["text"],
                         due_at=due, chat_id=chat_id)
        del self._pending_reminders[chat_id]
        await update.message.reply_text(
            f"🔔 Напомню {due.strftime('%d.%m %H:%M')}: {pending['text']}"
        )

    async def handle_reminder_done(self, update, context) -> None:
        """«✅ Сделано» на сработавшем напоминании — закрыть обещание/факт (F2)."""
        query = update.callback_query
        await query.answer()

        m = _REMDONE_RE.match(query.data or "")
        if not m:
            await query.edit_message_text(text="⏳ Устарело")
            return
        item_kind, item_key = m.group(1), m.group(2)

        user_id = self._get_user_id(update)
        if user_id is None:
            await query.edit_message_text(text="❌ Не найден ваш user_id")
            return

        try:
            close_item(self.repo, user_id, item_kind, item_key)
        except Exception as exc:
            logger.error("Ошибка закрытия item по напоминанию %s: %s", query.data, exc)

        await query.edit_message_text(text="✅ Отмечено выполненным")

    async def handle_reminder_snooze(self, update, context) -> None:
        """«🕐 Завтра» на сработавшем напоминании — перенести due_at на день (F2).

        Security (2026-07-17, найдено security-review до коммита, CRITICAL):
        без _get_user_id-гейта чужой reminder_id можно было перенести — снуз
        обязан быть user-scoped, как и все остальные callback-хендлеры."""
        query = update.callback_query
        await query.answer()

        m = _REMSNOOZE_RE.match(query.data or "")
        if not m:
            await query.edit_message_text(text="⏳ Устарело")
            return

        user_id = self._get_user_id(update)
        if user_id is None:
            await query.edit_message_text(text="❌ Не найден ваш user_id")
            return

        conn = self.repo._get_conn()
        snooze_reminder(conn, int(m.group(1)), user_id)
        await query.edit_message_text(text="🕐 Напомню завтра")

    async def _reminder_tick_loop(self) -> None:
        """Фоновый тикер (60с, F2 §3): due_reminders -> отправка + mark_sent/
        mark_error. Ничего не ПЛАНИРУЕТ сама — только досылает уже созданные
        владельцем reminders (инвариант 18 не нарушается)."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        from callprofiler.insight.repository import apply_insight_schema

        conn = self.repo._get_conn()
        apply_insight_schema(conn)
        while True:
            try:
                for r in due_reminders(conn, datetime.now()):
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "✅ Сделано",
                            callback_data=f"remdone|{r['item_kind']}|{r['item_key']}"),
                        InlineKeyboardButton(
                            "🕐 Завтра", callback_data=f"remsnooze|{r['reminder_id']}"),
                    ]])
                    try:
                        await self.app.bot.send_message(
                            chat_id=r["chat_id"], text=f"🔔 Напоминание: {r['text']}",
                            reply_markup=kb,
                        )
                        mark_sent(conn, r["reminder_id"])
                    except Exception as exc:
                        logger.error("Ошибка отправки напоминания %d: %s",
                                     r["reminder_id"], exc)
                        disabled = mark_error(conn, r["reminder_id"])
                        if disabled:
                            try:
                                await self.app.bot.send_message(
                                    chat_id=r["chat_id"],
                                    text=f"⚠ Напоминание отключено после "
                                         f"{MAX_CONSECUTIVE_ERRORS} неудачных попыток: "
                                         f"{r['text']}",
                                )
                            except Exception:
                                pass
            except Exception as exc:
                logger.error("Ошибка тика напоминаний: %s", exc)
            await asyncio.sleep(_REMINDER_TICK_SEC)

    async def _on_post_init(self, application) -> None:
        application.create_task(self._reminder_tick_loop())

    async def cmd_status(self, update, context) -> None:
        """/status — состояние очереди и БД."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text("❌ Не найден ваш user_id")
            return

        # Общее состояние очереди
        pending = self.repo.get_pending_calls(user_id)
        errors = self.repo.get_error_calls(user_id=user_id, max_retries=3)

        # Фильтр для конкретного пользователя
        pending_for_user = [c for c in pending if c.get("user_id") == user_id]
        errors_for_user = [c for c in errors if c.get("user_id") == user_id]

        # Статистика звонков пользователя
        all_calls = self.repo.get_calls_for_user(user_id, limit=1000)
        calls_with_analysis = sum(
            1 for c in all_calls if self.repo.get_analysis(user_id, c["call_id"]) is not None
        )

        msg = (
            f"⚙️ <b>Статус системы</b>\n\n"
            f"<b>Ваши звонки:</b>\n"
            f"  📱 Всего: {len(all_calls)}\n"
            f"  ✅ Обработано: {calls_with_analysis}\n"
            f"  ⏳ В очереди: {len(pending_for_user)}\n"
            f"  ❌ Ошибки: {len(errors_for_user)}\n"
        )

        if pending_for_user:
            msg += f"\n<b>⏳ Ожидают обработки ({len(pending_for_user)}):</b>\n"
            for call in pending_for_user[:3]:
                contact_id = call.get("contact_id")
                contact = (
                    self.repo.get_contact(user_id, contact_id) if contact_id else None
                )
                name = contact.get("display_name", "?") if contact else "?"
                status = call.get("status", "new")
                msg += f"  • {name} ({status})\n"
            if len(pending_for_user) > 3:
                msg += f"  ... и ещё {len(pending_for_user) - 3}\n"

        if errors_for_user:
            msg += f"\n<b>❌ С ошибками ({len(errors_for_user)}):</b>\n"
            for call in errors_for_user[:3]:
                contact_id = call.get("contact_id")
                contact = (
                    self.repo.get_contact(user_id, contact_id) if contact_id else None
                )
                name = contact.get("display_name", "?") if contact else "?"
                retry_count = call.get("retry_count", 0)
                msg += f"  • {name} (попытка {retry_count}/3)\n"
            if len(errors_for_user) > 3:
                msg += f"  ... и ещё {len(errors_for_user) - 3}\n"

        if not pending_for_user and not errors_for_user and all_calls:
            msg += f"\n✅ Все звонки обработаны!"

        await update.message.reply_text(msg, parse_mode="HTML")

    def _get_user_id(self, update) -> str | None:
        """Определить user_id по chat_id пользователя.

        Параметры:
            update  — объект события Telegram

        Возвращает:
            user_id или None если не найден
        """
        chat_id = update.effective_user.id if update.effective_user else None
        if not chat_id:
            return None

        # Найти пользователя по chat_id
        users = self.repo.get_all_users()
        for user in users:
            if user.get("telegram_chat_id") == str(chat_id):
                return user.get("user_id")

        return None

    def run(self) -> None:
        """Запустить бота в отдельном потоке (polling)."""
        if not self.token:
            logger.error(
                "TELEGRAM_BOT_TOKEN не установлен. "
                "Установите переменную окружения и попробуйте снова"
            )
            return

        # Лениво загрузить Telegram классы только при запуске
        try:
            from telegram.ext import (
                Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
            )
        except (ImportError, Exception):
            logger.error(
                "python-telegram-bot не установлен. "
                "Установите: pip install python-telegram-bot"
            )
            return

        import threading

        def run_polling():
            try:
                logger.info("Запуск Telegram-бота (long polling, token: %s...)",
                           self.token[:10])

                self.app = (
                    Application.builder().token(self.token)
                    .post_init(self._on_post_init).build()
                )

                # Обработчики команд (добавляем /start)
                self.app.add_handler(
                    CommandHandler("start", self.cmd_start)
                )
                self.app.add_handler(
                    CommandHandler("digest", self.cmd_digest)
                )
                self.app.add_handler(
                    CommandHandler("search", self.cmd_search)
                )
                self.app.add_handler(
                    CommandHandler("contact", self.cmd_contact)
                )
                self.app.add_handler(
                    CommandHandler("promises", self.cmd_promises)
                )
                self.app.add_handler(
                    CommandHandler("status", self.cmd_status)
                )

                # Обработчики callback-кнопок: feedback (по звонку) и fv (F1, по факту).
                # pattern обязателен на обоих — иначе безусловный feedback-хендлер
                # перехватит fv|... первым (первое совпадение в порядке регистрации).
                self.app.add_handler(
                    CallbackQueryHandler(self.handle_feedback, pattern=r"^feedback_")
                )
                self.app.add_handler(
                    CallbackQueryHandler(self.handle_fact_verdict, pattern=r"^fv\|")
                )
                # F2: предложение напомнить + тикер-кнопки на сработавшем напоминании.
                self.app.add_handler(
                    CallbackQueryHandler(self.handle_remind_ask, pattern=r"^remask\|")
                )
                self.app.add_handler(
                    CallbackQueryHandler(self.handle_reminder_done, pattern=r"^remdone\|")
                )
                self.app.add_handler(
                    CallbackQueryHandler(self.handle_reminder_snooze, pattern=r"^remsnooze\|")
                )
                # Простой текст (не команда) — сейчас только «жду дату» после
                # «🔔 Напомнить» (handle_plain_text); F3 (ask) дополнит той же функцией.
                self.app.add_handler(
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_plain_text)
                )

                logger.info("✓ Telegram-бот запущен и слушает команды")
                self.app.run_polling()
                logger.info("Telegram-бот остановлен")
            except Exception as exc:
                logger.error("Ошибка в run_polling: %s", exc)

        thread = threading.Thread(target=run_polling, daemon=True)
        thread.start()
        logger.info("Telegram-бот запущен в отдельном потоке")
