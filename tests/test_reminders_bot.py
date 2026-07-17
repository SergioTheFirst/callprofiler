# -*- coding: utf-8 -*-
"""test_reminders_bot.py — F2: бот-сторона напоминаний (remask/remdone/remsnooze,
handle_plain_text «жду дату», предложение «🔔 Напомнить» после confirmed)."""
import asyncio
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from callprofiler.db.repository import Repository
from callprofiler.deliver.reminders import create_reminder, mark_sent
from callprofiler.insight.repository import apply_insight_schema


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
            apply_insight_schema(conn)
            conn.commit()
        yield Repository(str(db_path))


class FakeMessage:
    def __init__(self, text=None):
        self.text = text
        self.reply_text = AsyncMock()


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()
        self.message = FakeMessage()


class FakeUpdate:
    def __init__(self, data=None, text=None, chat_id=555):
        self.callback_query = FakeQuery(data) if data is not None else None
        self.message = FakeMessage(text=text)
        self.effective_user = SimpleNamespace(id=chat_id)


# ── handle_remind_ask ──────────────────────────────────────────────────────

def test_handle_remind_ask_sets_pending_and_asks_date(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("remask|event|9", chat_id=555)
    asyncio.run(notifier.handle_remind_ask(update, context=None))

    assert 555 in notifier._pending_reminders
    pending = notifier._pending_reminders[555]
    assert pending["item_kind"] == "event" and pending["item_key"] == "9"
    assert "вернуть долг" in pending["text"]
    update.callback_query.edit_message_text.assert_awaited_once()
    assert "Когда" in update.callback_query.edit_message_text.await_args.kwargs["text"]


def test_handle_remind_ask_unknown_item_not_found(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("remask|event|999", chat_id=555)
    asyncio.run(notifier.handle_remind_ask(update, context=None))

    assert 555 not in notifier._pending_reminders
    update.callback_query.edit_message_text.assert_awaited_once_with(text="❌ Не нашёл этот пункт")


def test_handle_remind_ask_malformed_callback(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("garbage", chat_id=555)
    asyncio.run(notifier.handle_remind_ask(update, context=None))

    update.callback_query.edit_message_text.assert_awaited_once_with(text="⏳ Устарело")


# ── handle_plain_text ────────────────────────────────────────────────────

def test_handle_plain_text_no_pending_does_nothing(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)

    update = FakeUpdate(text="завтра", chat_id=555)
    asyncio.run(notifier.handle_plain_text(update, context=None))

    update.message.reply_text.assert_not_awaited()


def test_handle_plain_text_valid_date_creates_reminder(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")
    notifier._pending_reminders[555] = {
        "user_id": "me", "item_kind": "event", "item_key": "9",
        "text": "[OTHER] вернуть долг",
        "expires_at": datetime.now() + timedelta(minutes=5),
    }

    update = FakeUpdate(text="завтра", chat_id=555)
    asyncio.run(notifier.handle_plain_text(update, context=None))

    assert 555 not in notifier._pending_reminders
    update.message.reply_text.assert_awaited_once()
    conn = temp_repo._get_conn()
    row = conn.execute("SELECT text, chat_id FROM reminders").fetchone()
    assert row[0] == "[OTHER] вернуть долг"
    assert row[1] == 555


def test_handle_plain_text_invalid_date_keeps_pending(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")
    notifier._pending_reminders[555] = {
        "user_id": "me", "item_kind": "event", "item_key": "9", "text": "x",
        "expires_at": datetime.now() + timedelta(minutes=5),
    }

    update = FakeUpdate(text="какая-то фигня", chat_id=555)
    asyncio.run(notifier.handle_plain_text(update, context=None))

    assert 555 in notifier._pending_reminders  # можно повторить попытку
    update.message.reply_text.assert_awaited_once_with("Не понял дату, напиши как DD.MM")


def test_handle_plain_text_expired_pending_ignored(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")
    notifier._pending_reminders[555] = {
        "user_id": "me", "item_kind": "event", "item_key": "9", "text": "x",
        "expires_at": datetime.now() - timedelta(seconds=1),
    }

    update = FakeUpdate(text="завтра", chat_id=555)
    asyncio.run(notifier.handle_plain_text(update, context=None))

    assert 555 not in notifier._pending_reminders
    update.message.reply_text.assert_not_awaited()


# ── handle_reminder_done / handle_reminder_snooze ─────────────────────────

def test_handle_reminder_done_closes_event(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("remdone|event|9")
    asyncio.run(notifier.handle_reminder_done(update, context=None))

    conn = temp_repo._get_conn()
    status = conn.execute("SELECT status FROM events WHERE id = 9").fetchone()[0]
    assert status == "fulfilled"
    update.callback_query.edit_message_text.assert_awaited_once_with(text="✅ Отмечено выполненным")


def test_handle_reminder_done_malformed(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("garbage")
    asyncio.run(notifier.handle_reminder_done(update, context=None))
    update.callback_query.edit_message_text.assert_awaited_once_with(text="⏳ Устарело")


def test_handle_reminder_snooze_no_user_id_does_not_snooze(temp_repo):
    """Regress (CRITICAL, security-review 2026-07-17 до коммита): снуз без
    allowlisted user_id должен отказать, не менять due_at чужого reminder."""
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    conn = temp_repo._get_conn()
    due = datetime(2020, 1, 1, 10, 0).astimezone()
    rid = create_reminder(conn, "me", item_kind="event", item_key="9", text="x",
                           due_at=due, chat_id=555)
    mark_sent(conn, rid)

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value=None)
    update = FakeUpdate(f"remsnooze|{rid}")
    asyncio.run(notifier.handle_reminder_snooze(update, context=None))

    row = conn.execute("SELECT due_at, sent_at FROM reminders WHERE reminder_id = ?", (rid,)).fetchone()
    assert row[1] is not None  # sent_at не сброшен — снуз не выполнился
    assert row[0].startswith("2020-01-01")  # due_at не сдвинут
    update.callback_query.edit_message_text.assert_awaited_once_with(
        text="❌ Не найден ваш user_id"
    )


def test_handle_reminder_snooze_moves_due_at(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    conn = temp_repo._get_conn()
    due = datetime(2020, 1, 1, 10, 0).astimezone()
    rid = create_reminder(conn, "me", item_kind="event", item_key="9", text="x",
                           due_at=due, chat_id=555)
    mark_sent(conn, rid)

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")
    update = FakeUpdate(f"remsnooze|{rid}")
    asyncio.run(notifier.handle_reminder_snooze(update, context=None))

    row = conn.execute("SELECT due_at, sent_at FROM reminders WHERE reminder_id = ?", (rid,)).fetchone()
    assert row[1] is None
    assert row[0].startswith("2020-01-02")
    update.callback_query.edit_message_text.assert_awaited_once_with(text="🕐 Напомню завтра")


# ── confirmed verdict offers reminder button ──────────────────────────────

def test_confirmed_verdict_offers_remind_button(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("fv|event|9|c")
    asyncio.run(notifier.handle_fact_verdict(update, context=None))

    update.callback_query.message.reply_text.assert_awaited_once()
    call = update.callback_query.message.reply_text.await_args
    assert "Подтверждено" in call.args[0]
    keyboard = call.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "remask|event|9"


def test_rejected_verdict_does_not_offer_remind_button(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("fv|event|9|r")
    asyncio.run(notifier.handle_fact_verdict(update, context=None))

    update.callback_query.message.reply_text.assert_not_awaited()
