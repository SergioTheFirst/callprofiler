# -*- coding: utf-8 -*-
"""test_feedback_loop.py — задача 0.2 (A5): замыкание feedback-петли.

Regression: handle_feedback (telegram_bot.py) ссылался на неопределённую
переменную user_id -> NameError на каждое нажатие [OK]/[Неточно].
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
                "INSERT INTO calls (call_id, user_id, source_filename, source_md5, status) "
                "VALUES (1, 'me', 'a.mp3', 'md5a', 'done')"
            )
            conn.execute("INSERT INTO analyses (call_id, prompt_version) VALUES (1, 'v1')")
            conn.commit()
        yield Repository(str(db_path))


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()


class FakeUpdate:
    def __init__(self, data, chat_id=555):
        self.callback_query = FakeQuery(data)
        self.effective_user = SimpleNamespace(id=chat_id)


def test_handle_feedback_writes_analyses_feedback(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("feedback_1_inaccurate")
    asyncio.run(notifier.handle_feedback(update, context=None))

    analysis = temp_repo.get_analysis("me", 1)
    assert analysis["feedback"] == "inaccurate"
    update.callback_query.edit_message_text.assert_awaited_once()


def test_handle_feedback_ok_writes_ok(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("feedback_1_ok")
    asyncio.run(notifier.handle_feedback(update, context=None))

    analysis = temp_repo.get_analysis("me", 1)
    assert analysis["feedback"] == "ok"


def test_handle_feedback_no_user_id_replies_error_and_does_not_write(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value=None)

    update = FakeUpdate("feedback_1_ok")
    asyncio.run(notifier.handle_feedback(update, context=None))

    analysis = temp_repo.get_analysis("me", 1)
    assert analysis["feedback"] is None
    update.callback_query.edit_message_text.assert_awaited_once_with(
        text="❌ Не найден ваш user_id"
    )


def test_handle_feedback_bad_callback_data(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    notifier._get_user_id = MagicMock(return_value="me")

    update = FakeUpdate("garbage")
    asyncio.run(notifier.handle_feedback(update, context=None))

    update.callback_query.edit_message_text.assert_awaited_once()
    analysis = temp_repo.get_analysis("me", 1)
    assert analysis["feedback"] is None
