# -*- coding: utf-8 -*-
"""
telegram_bot.py — Telegram-бот для доставки саммари и команд.

Один бот на всех пользователей. Различает по chat_id.
Команды: /digest [N], /search текст, /contact +7..., /promises, /status
Автосообщения: саммари после каждого обработанного звонка с кнопками [OK]/[Неточно].

ВАЖНО: python-telegram-bot подгружается лениво, при вызове run().
Для импорта модуля не требуется установленная телеграм-библиотека.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.db.repository import Repository

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram-бот для уведомлений и команд.

    Использование:
        notifier = TelegramNotifier(token="123:ABC", repo=repo)
        await notifier.send_summary(user_id="serhio", call_id=42)
        notifier.run()  # Запустить polling в отдельном потоке
    """

    def __init__(self, token: str, repo: Repository) -> None:
        """Инициализировать Telegram-бот.

        Параметры:
            token  — токен бота от @BotFather
            repo   — Repository для доступа к данным
        """
        self.token = token
        self.repo = repo
        self.app = None
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

        user = self.repo.get_user(user_id)
        if not user:
            logger.error("Пользователь %s не найден", user_id)
            return

        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            logger.warning(
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
        contact = self.repo.get_contact(contact_id) if contact_id else None
        contact_name = contact.get("display_name", "?") if contact else "?"
        phone = contact.get("phone_e164", "?") if contact else "?"

        analysis = self.repo.get_analysis(call_id)
        if not analysis:
            logger.warning("Анализ для звонка %d не найден", call_id)
            return

        summary = analysis.get("summary", "Нет саммари")
        priority = analysis.get("priority", 0)
        risk_score = analysis.get("risk_score", 0)
        action_items = analysis.get("action_items", [])

        # Форматирование сообщения
        msg = (
            f"📞 <b>{contact_name}</b> ({phone})\n"
            f"Priority: {priority} | Risk: {risk_score}\n"
            f"───────────────────\n"
            f"{summary}\n"
        )

        if action_items:
            msg += "\n🎯 Actions:\n"
            for item in action_items[:3]:
                msg += f"  • {item}\n"

        # Кнопки обратной связи
        keyboard = [
            [
                InlineKeyboardButton("✅ OK", callback_data=f"feedback_{call_id}_ok"),
                InlineKeyboardButton(
                    "❌ Неточно",
                    callback_data=f"feedback_{call_id}_wrong",
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
                    "Саммари отправлен пользователю %s (chat_id=%s)",
                    user_id, chat_id,
                )
            else:
                logger.warning(
                    "App не инициализирован, саммари не отправлен"
                )
        except Exception as exc:
            logger.error(
                "Ошибка при отправке саммари: %s", exc
            )

    async def handle_feedback(self, update, context) -> None:
        """Обработать нажатие [OK] / [Неточно].

        Параметры:
            update   — объект события Telegram
            context  — контекст бота
        """
        query = update.callback_query
        await query.answer()

        data = query.data  # "feedback_{call_id}_{ok|wrong}"
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

        feedback_text = "✅ OK" if feedback_type == "ok" else "❌ Неточно"

        try:
            self.repo.set_feedback(None, feedback_text)
            await query.edit_message_text(
                text=f"💾 Ваш отзыв записан: {feedback_text}"
            )
            logger.info(
                "Feedback для call_id=%d: %s", call_id, feedback_text
            )
        except Exception as exc:
            logger.error("Ошибка при сохранении feedback: %s", exc)
            await query.edit_message_text(text="❌ Ошибка сохранения")

    async def cmd_digest(self, update, context) -> None:
        """/digest [N] — топ звонков по priority за N дней."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text("❌ Не найден ваш user_id")
            return

        days = 7  # По умолчанию за неделю
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError:
                pass

        calls = self.repo.get_calls_for_user(user_id, limit=20)
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

        msg = f"📊 Топ звонков за {days} дней (по priority):\n"
        for call in recent[:5]:
            contact_id = call.get("contact_id")
            contact = (
                self.repo.get_contact(contact_id) if contact_id else None
            )
            name = contact.get("display_name", "?") if contact else "?"
            analysis = self.repo.get_analysis(call["call_id"])
            priority = analysis.get("priority", 0) if analysis else 0
            msg += f"  {priority:3d} — {name}\n"

        await update.message.reply_text(msg)

    async def cmd_search(self, update, context) -> None:
        """/search {текст} — поиск по транскриптам."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text("❌ Не найден ваш user_id")
            return

        if not context.args:
            await update.message.reply_text("❌ Используйте: /search {текст}")
            return

        query_text = " ".join(context.args)
        results = self.repo.search_transcripts(user_id, query_text)

        if not results:
            await update.message.reply_text(
                f"🔍 Ничего не найдено по '{query_text}'"
            )
            return

        msg = f"🔍 Найдено {len(results)} сегментов:\n"
        for res in results[:5]:
            text = res.get("text", "?")[:100]
            speaker = res.get("speaker", "?")
            msg += f"  [{speaker}] {text}...\n"

        await update.message.reply_text(msg)

    async def cmd_contact(self, update, context) -> None:
        """/contact {номер} — карточка контакта."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text("❌ Не найден ваш user_id")
            return

        if not context.args:
            await update.message.reply_text(
                "❌ Используйте: /contact +79161234567"
            )
            return

        phone = context.args[0]
        contact = self.repo.get_contact_by_phone(user_id, phone)

        if not contact:
            await update.message.reply_text(f"❌ Контакт {phone} не найден")
            return

        contact_id = contact["contact_id"]
        name = contact.get("display_name", phone)
        call_count = self.repo.get_call_count_for_contact(user_id, contact_id)
        analyses = self.repo.get_recent_analyses(user_id, contact_id, limit=1)

        msg = f"👤 <b>{name}</b> ({phone})\n"
        msg += f"Звонков: {call_count}\n"

        if analyses:
            analysis = analyses[0]
            risk = analysis.get("risk_score", 0)
            summary = analysis.get("summary", "Нет данных")[:150]
            msg += f"Risk: {risk}\n"
            msg += f"───────────\n{summary}\n"

        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_promises(self, update, context) -> None:
        """/promises — открытые обещания."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text("❌ Не найден ваш user_id")
            return

        promises = self.repo.get_open_promises(user_id)

        if not promises:
            await update.message.reply_text("✅ Нет открытых обещаний")
            return

        msg = f"📌 Открытые обещания ({len(promises)}):\n"
        for p in promises[:10]:
            who = p.get("who", "?")
            what = p.get("what", "?")
            due = p.get("due", "?")
            msg += f"  • [{who}] {what} (до {due})\n"

        await update.message.reply_text(msg)

    async def cmd_status(self, update, context) -> None:
        """/status — состояние очереди."""
        user_id = self._get_user_id(update)
        if not user_id:
            await update.message.reply_text("❌ Не найден ваш user_id")
            return

        pending = self.repo.get_pending_calls()
        errors = self.repo.get_error_calls(max_retries=3)

        pending_for_user = [c for c in pending if c.get("user_id") == user_id]
        errors_for_user = [c for c in errors if c.get("user_id") == user_id]

        msg = (
            f"⚙️ <b>Статус очереди</b>\n"
            f"В работе: {len(pending_for_user)}\n"
            f"Ошибки (макс 3 попытки): {len(errors_for_user)}\n"
        )

        if pending_for_user:
            msg += "\n⏳ Ожидают обработки:\n"
            for call in pending_for_user[:3]:
                contact_id = call.get("contact_id")
                contact = (
                    self.repo.get_contact(contact_id) if contact_id else None
                )
                name = contact.get("display_name", "?") if contact else "?"
                msg += f"  • {name}\n"

        if errors_for_user:
            msg += "\n❌ Ошибки:\n"
            for call in errors_for_user[:3]:
                contact_id = call.get("contact_id")
                contact = (
                    self.repo.get_contact(contact_id) if contact_id else None
                )
                name = contact.get("display_name", "?") if contact else "?"
                retry_count = call.get("retry_count", 0)
                msg += f"  • {name} (попытка {retry_count})\n"

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
        # Лениво загрузить Telegram классы только при запуске
        try:
            from telegram.ext import (
                Application, CommandHandler, CallbackQueryHandler
            )
        except (ImportError, Exception):
            logger.error(
                "python-telegram-bot не установлен, бот не может быть запущен"
            )
            return

        import threading

        def run_polling():
            try:
                logger.info("Запуск Telegram-бота (polling)")
                self.app = Application.builder().token(self.token).build()

                # Обработчики команд
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

                # Обработчик callback кнопок
                self.app.add_handler(
                    CallbackQueryHandler(self.handle_feedback)
                )

                self.app.run_polling()
                logger.info("Telegram-бот остановлен")
            except Exception as exc:
                logger.error("Ошибка в run_polling: %s", exc)

        thread = threading.Thread(target=run_polling, daemon=True)
        thread.start()
        logger.info("Telegram-бот запущен в отдельном потоке")
