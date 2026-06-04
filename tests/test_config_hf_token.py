# -*- coding: utf-8 -*-
"""test_config_hf_token.py — резолв hf_token из окружения.

Регрессия: на Windows ``os.path.expandvars('${HF_TOKEN}')`` при НЕзаданной
переменной возвращает строку ``'${HF_TOKEN}'`` (truthy!). Этот мусор уходил в
pyannote как ``use_auth_token`` → 401 на gated-моделях → диаризация падала →
все роли UNKNOWN. Незаданный токен ОБЯЗАН резолвиться в "" (пусто).
"""
import os

from callprofiler.config import _resolve_secret


def test_unset_brace_var_resolves_to_empty(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert _resolve_secret("${HF_TOKEN}") == ""


def test_unset_percent_var_resolves_to_empty(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert _resolve_secret("%HF_TOKEN%") == ""


def test_set_var_resolves_to_value(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_REAL123")
    assert _resolve_secret("${HF_TOKEN}") == "hf_REAL123"


def test_plain_token_passes_through():
    assert _resolve_secret("hf_plain_abc") == "hf_plain_abc"


def test_empty_stays_empty():
    assert _resolve_secret("") == ""


def test_whitespace_is_stripped(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "  hf_PADDED  ")
    assert _resolve_secret("${HF_TOKEN}") == "hf_PADDED"
