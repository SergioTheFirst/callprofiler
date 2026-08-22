# -*- coding: utf-8 -*-
"""exit_codes.py — T-22: единый контракт кодов выхода CLI.

0 ok · 1 fatal (необработанная ошибка) · 2 usage/validation (argparse тоже даёт 2) ·
3 not found (файл/пользователь/звонок) · 4 partial (часть элементов не обработана) ·
5 retryable (llama-server/сеть недоступны — повторить позже) · 130 прервано пользователем.
Команды возвращают int; исключения маппит ``map_exception`` в ``cli/main.py``.
"""
from __future__ import annotations

EXIT_OK = 0
EXIT_FATAL = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_PARTIAL = 4
EXIT_RETRYABLE = 5
EXIT_INTERRUPTED = 130


def map_exception(exc: BaseException) -> int:
    """Исключение → код выхода (порядок важен: подклассы раньше базовых)."""
    if isinstance(exc, KeyboardInterrupt):
        return EXIT_INTERRUPTED
    if isinstance(exc, (FileNotFoundError, LookupError)):
        return EXIT_NOT_FOUND
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return EXIT_RETRYABLE
    if isinstance(exc, (ValueError, TypeError, PermissionError)):
        return EXIT_USAGE
    return EXIT_FATAL
