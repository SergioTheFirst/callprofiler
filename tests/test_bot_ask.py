# -*- coding: utf-8 -*-
"""test_bot_ask.py — F3: `ask` через Telegram-бот (реюз A2 целиком, бот — транспорт)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from callprofiler.db.repository import Repository


@pytest.fixture
def temp_repo(tmp_path):
    db_path = tmp_path / "ask_bot.db"
    repo = Repository(str(db_path))
    repo.init_db()
    repo.add_user(user_id="me", display_name="Me", telegram_chat_id="555",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    conn = repo._get_conn()
    conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) "
        "VALUES ('me', '+79001112233', 'Вася')"
    )
    cid = conn.execute("SELECT contact_id FROM contacts WHERE user_id='me'").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
        "source_filename, source_md5, status) "
        "VALUES ('me', ?, 'IN', '2026-05-02T10:00:00', 'f.mp3', 'md5x', 'done')",
        (cid,),
    )
    call_id = cur.lastrowid
    conn.execute(
        "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) "
        "VALUES (?, 0, 1000, 'мы решили покрасить гараж в синий цвет', 'OTHER')",
        (call_id,),
    )
    conn.commit()
    yield repo
    repo.close()


class FakeMessage:
    def __init__(self, text=None):
        self.text = text
        self.reply_text = AsyncMock()


class FakeUpdate:
    def __init__(self, text, chat_id=555):
        self.callback_query = None
        self.message = FakeMessage(text=text)
        self.effective_user = SimpleNamespace(id=chat_id)


class MockLLMResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def test_ask_llm_available_formats_answer_with_citations(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    update = FakeUpdate("что решили с гаражом?")

    with patch("callprofiler.ask.llm_available", return_value=True), \
         patch("requests.post", return_value=MockLLMResponse(
             "Вы договорились покрасить гараж в синий цвет [1].")):
        asyncio.run(notifier.handle_plain_text(update, context=None))

    update.message.reply_text.assert_awaited_once()
    call = update.message.reply_text.await_args
    text = call.args[0]
    assert len(text) <= 4096
    assert "гараж" in text
    assert "Источники" in text
    assert "Вася" in text
    assert call.kwargs["parse_mode"] == "HTML"


def test_ask_llm_unavailable_falls_back_to_fts_quotes(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    update = FakeUpdate("что решили с гаражом?")

    with patch("callprofiler.ask.llm_available", return_value=False), \
         patch("requests.post") as mock_post:
        asyncio.run(notifier.handle_plain_text(update, context=None))

    mock_post.assert_not_called()
    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args.args[0]
    assert "LLM спит" in text
    assert "гараж" in text
    assert "Вася" in text
    assert len(text) <= 4096


def test_ask_non_allowlisted_chat_id_ignored(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    update = FakeUpdate("что решили с гаражом?", chat_id=99999)  # не зарегистрирован

    with patch("callprofiler.ask.llm_available", return_value=True) as mock_avail:
        asyncio.run(notifier.handle_plain_text(update, context=None))

    mock_avail.assert_not_called()
    update.message.reply_text.assert_not_awaited()


def test_ask_writes_ask_log(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    update = FakeUpdate("что решили с гаражом?")

    with patch("callprofiler.ask.llm_available", return_value=True), \
         patch("requests.post", return_value=MockLLMResponse("Покрасили гараж [1].")):
        asyncio.run(notifier.handle_plain_text(update, context=None))

    conn = temp_repo._get_conn()
    row = conn.execute("SELECT question, answered FROM ask_log WHERE user_id='me'").fetchone()
    assert row is not None
    assert row["question"] == "что решили с гаражом?"
    assert row["answered"] == 1


def test_ask_question_capped_at_500_chars(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    long_question = "гараж " * 200  # far more than 500 chars
    update = FakeUpdate(long_question)
    captured = {}

    def _fake_answer_question(conn, user_id, question, **kwargs):
        captured["question"] = question
        return {"answer": "ok", "citations": [], "from_cache": False}

    with patch("callprofiler.ask.llm_available", return_value=True), \
         patch("callprofiler.ask.answer_question", side_effect=_fake_answer_question):
        asyncio.run(notifier.handle_plain_text(update, context=None))

    assert len(captured["question"]) <= 500


def test_ask_llm_error_replies_gracefully_no_crash(temp_repo):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    notifier = TelegramNotifier(temp_repo, token=None)
    update = FakeUpdate("что решили с гаражом?")

    with patch("callprofiler.ask.llm_available", return_value=True), \
         patch("callprofiler.ask.answer_question", side_effect=RuntimeError("boom")):
        asyncio.run(notifier.handle_plain_text(update, context=None))

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args.args[0]
    assert "boom" not in text  # исключение не течёт в чат
