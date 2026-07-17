# -*- coding: utf-8 -*-
"""test_promises_verdict_bot.py — F1: /promises с ✓/✗ на item + handle_fact_verdict.

Шаблон Fake*/asyncio.run — по образцу test_feedback_loop.py (0.2/A5).
"""
import asyncio
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from callprofiler.db.repository import Repository


@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "callprofiler.db"
        schema_path = (
            Path(__file__).parent.parent / "src" / "callprofiler" / "db" / "schema.sql"
        )
        with sqlite3.connect(db_path) as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO users (user_id, display_name, incoming_dir, sync_dir, ref_audio) "
                "VALUES ('me', 'Me', '/tmp/in', '/tmp/sync', '/tmp/ref.wav')"
            )
            conn.execute(
                "INSERT INTO contacts (contact_id, user_id, phone_e164, display_name) "
                "VALUES (1, 'me', '+79001112233', 'Иван')"
            )
            conn.execute(
                "INSERT INTO calls (call_id, user_id, contact_id, source_filename, "
                "source_md5, status) VALUES (1, 'me', 1, 'a.mp3', 'md5a', 'done')"
            )
            conn.execute(
                "INSERT INTO events (id, user_id, contact_id, call_id, event_type, who, "
                "payload, deadline, status) VALUES "
                "(9, 'me', 1, 1, 'promise', 'OTHER', 'вернуть долг', '2020-01-05', 'open')"
            )
            conn.commit()
        yield Repository(str(db_path))


class FakeMessage:
    def __init__(self):
        self.reply_text = AsyncMock()


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()
        self.message = FakeMessage()


class FakeUpdate:
    def __init__(self, data=None, chat_id=555):
        self.callback_query = FakeQuery(data) if data is not None else None
        self.message = FakeMessage()
        self.effective_user = SimpleNamespace(id=chat_id)


def test_cmd_promises_sends_keyboard_with_one_row_per_item(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate()
    asyncio.run(notifier.cmd_promises(update, context=None))

    update.message.reply_text.assert_awaited_once()
    call = update.message.reply_text.await_args
    text = call.args[0]
    assert "1." in text
    keyboard = call.kwargs["reply_markup"]
    assert len(keyboard.inline_keyboard) == 1
    row = keyboard.inline_keyboard[0]
    assert row[0].callback_data == "fv|event|9|c"
    assert row[1].callback_data == "fv|event|9|r"


def test_cmd_promises_no_user_id_replies_error(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value=None)

    update = FakeUpdate()
    asyncio.run(notifier.cmd_promises(update, context=None))

    update.message.reply_text.assert_awaited_once_with("❌ Не найден ваш user_id")


def test_handle_fact_verdict_confirmed_persists_and_marks_message(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("fv|event|9|c")
    asyncio.run(notifier.handle_fact_verdict(update, context=None))

    conn = temp_repo._get_conn()
    row = conn.execute(
        "SELECT verdict FROM fact_feedback WHERE user_id='me' AND item_kind='event' AND item_key='9'"
    ).fetchone()
    assert row[0] == "confirmed"

    update.callback_query.edit_message_text.assert_awaited_once()
    text = update.callback_query.edit_message_text.await_args.kwargs["text"]
    assert "✓" in text


def test_handle_fact_verdict_rejected_removes_item_from_view(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("fv|event|9|r")
    asyncio.run(notifier.handle_fact_verdict(update, context=None))

    update.callback_query.edit_message_text.assert_awaited_once()
    kwargs = update.callback_query.edit_message_text.await_args.kwargs
    assert kwargs["text"] == "✅ Нет открытых обещаний"
    assert kwargs["reply_markup"] is None


def test_handle_fact_verdict_malformed_callback_no_write(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("garbage")
    asyncio.run(notifier.handle_fact_verdict(update, context=None))

    update.callback_query.edit_message_text.assert_awaited_once_with(text="⏳ Устарело")
    conn = temp_repo._get_conn()
    has_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_feedback'"
    ).fetchone()
    assert has_table is None  # ранний return до apply_insight_schema — таблица не создана


def test_handle_fact_verdict_no_user_id(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value=None)

    update = FakeUpdate("fv|event|9|c")
    asyncio.run(notifier.handle_fact_verdict(update, context=None))

    update.callback_query.edit_message_text.assert_awaited_once_with(
        text="❌ Не найден ваш user_id"
    )
