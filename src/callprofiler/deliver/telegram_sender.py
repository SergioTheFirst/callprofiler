# -*- coding: utf-8 -*-
"""
telegram_sender.py — синхронная отправка Telegram-сообщения через голый Bot API.

Инвариант 25 (плановые пуши — ровно два: F5 вечерний, F6 doctor): оба живут в
СИНХРОННОМ watcher-цикле, не в асинхронном процессе бота (telegram_bot.py —
там self.app появляется только внутри run_polling(), т.е. отправка из
watcher через TelegramNotifier.send_summary молча no-op). Прямой HTTP POST
не требует запущенного бот-процесса.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def send_telegram_message(chat_id: str | int, text: str, token: str | None = None) -> bool:
    """Отправить текст через sendMessage. Возвращает True при HTTP 2xx."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN не установлен, сообщение не отправлено")
        return False
    try:
        import requests

        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if not resp.ok:
            logger.warning("sendMessage HTTP %d: %s", resp.status_code, resp.text[:200])
        return resp.ok
    except Exception as exc:  # noqa: BLE001 — сеть/бот недоступны, вызывающий решает про ретрай
        logger.warning("sendMessage упал: %s", exc)
        return False
