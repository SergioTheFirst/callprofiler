# -*- coding: utf-8 -*-
"""
test_telegram_bot.py — integration test stubs for TelegramNotifier.

Tests verify module importability, constructor contract, and key method
signatures without requiring a real Telegram Bot API token.
"""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestTelegramNotifierConstruction:
    """Verify TelegramNotifier can be constructed with mocked dependencies."""

    def test_import_module(self):
        from callprofiler.deliver import telegram_bot
        assert hasattr(telegram_bot, "TelegramNotifier")

    def test_construct_with_mocked_repo(self):
        from callprofiler.deliver.telegram_bot import TelegramNotifier
        repo = MagicMock()
        notifier = TelegramNotifier(repo, token=None)
        assert notifier.repo is repo
        assert notifier.token is None

    def test_construct_with_token(self):
        from callprofiler.deliver.telegram_bot import TelegramNotifier
        repo = MagicMock()
        notifier = TelegramNotifier(repo, token="12345:abc")
        assert notifier.token == "12345:abc"

    def test_get_user_id_method_exists(self):
        from callprofiler.deliver.telegram_bot import TelegramNotifier
        repo = MagicMock()
        notifier = TelegramNotifier(repo, token=None)
        assert hasattr(notifier, "_get_user_id")
        assert callable(notifier._get_user_id)

    def test_run_method_exists(self):
        from callprofiler.deliver.telegram_bot import TelegramNotifier
        repo = MagicMock()
        notifier = TelegramNotifier(repo, token=None)
        assert hasattr(notifier, "run")
        assert callable(notifier.run)

    def test_command_methods_exist(self):
        from callprofiler.deliver.telegram_bot import TelegramNotifier
        repo = MagicMock()
        notifier = TelegramNotifier(repo, token=None)
        for cmd in ["cmd_help", "cmd_start", "cmd_digest", "cmd_search",
                     "cmd_contact", "cmd_promises", "cmd_status"]:
            assert hasattr(notifier, cmd), f"Missing {cmd}"
            assert callable(getattr(notifier, cmd)), f"{cmd} not callable"

    def test_no_token_app_is_none(self):
        from callprofiler.deliver.telegram_bot import TelegramNotifier
        repo = MagicMock()
        notifier = TelegramNotifier(repo, token=None)
        assert notifier.app is None


class TestTelegramNotifierRunGuard:
    """Verify run() behaves correctly when bot is not initialized."""

    def test_run_without_token_logs_and_exits(self):
        from callprofiler.deliver.telegram_bot import TelegramNotifier
        repo = MagicMock()
        notifier = TelegramNotifier(repo, token=None)
        notifier.run()
        assert notifier.app is None

    def test_run_with_token_is_callable(self):
        from callprofiler.deliver.telegram_bot import TelegramNotifier
        repo = MagicMock()
        notifier = TelegramNotifier(repo, token="12345:abc")
        assert callable(notifier.run)
