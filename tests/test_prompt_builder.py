# -*- coding: utf-8 -*-
"""
test_prompt_builder.py — тесты для PromptBuilder (DS1 F1.1).

Покрывает:
- Загрузку шаблона из файла
- Отсутствие KeyError при наличии JSON-фигурных скобок в шаблоне
- Параметр version
- Возврат dict {system, user}
- Поддержку list[str] и list[dict] для previous_summaries
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from callprofiler.analyze.prompt_builder import PromptBuilder


def _make_builder(template_content: str, version: str = "v001") -> PromptBuilder:
    """Создать PromptBuilder с кастомным шаблоном во временной папке."""
    tmp = tempfile.mkdtemp()
    (Path(tmp) / f"analyze_{version}.txt").write_text(
        template_content, encoding="utf-8"
    )
    return PromptBuilder(tmp)


# ── Базовая функциональность ─────────────────────────────────────────────────


def test_builder_loads_template_file():
    """PromptBuilder загружает шаблон из файла (не AttributeError)."""
    b = _make_builder("System: Ты анализируешь звонки. Верни JSON.")
    result = b.build("текст", {}, [])
    assert isinstance(result, dict)
    assert "system" in result
    assert "user" in result


def test_builder_returns_system_and_user_keys():
    """build() возвращает dict с ключами 'system' и 'user'."""
    b = _make_builder("SYSTEM PROMPT")
    result = b.build("transcript text", {}, [])
    assert set(result.keys()) >= {"system", "user"}
    assert result["system"] == "SYSTEM PROMPT"
    assert "transcript text" in result["user"]


def test_builder_json_braces_in_template_no_error():
    """Шаблон с JSON-фигурными скобками не вызывает KeyError (DS1 F1.1)."""
    template = (
        "Верни ТОЛЬКО JSON:\n"
        '{"summary": "...", "risk_score": 0, "call_type": "unknown"}\n'
        "Правила:\n- priority: 0-100\n"
    )
    b = _make_builder(template)
    # Должно отработать без KeyError/ValueError/IndexError
    result = b.build("Привет, как дела?", {"contact_name": "Иван"}, [])
    assert isinstance(result, dict)
    assert "system" in result


def test_builder_version_parameter():
    """Параметр version загружает нужный файл шаблона."""
    tmp = tempfile.mkdtemp()
    (Path(tmp) / "analyze_v001.txt").write_text("V001 TEMPLATE", encoding="utf-8")
    (Path(tmp) / "analyze_v002.txt").write_text("V002 TEMPLATE", encoding="utf-8")
    b = PromptBuilder(tmp)
    r1 = b.build("t", {}, [], version="v001")
    r2 = b.build("t", {}, [], version="v002")
    assert r1["system"] == "V001 TEMPLATE"
    assert r2["system"] == "V002 TEMPLATE"


def test_builder_missing_version_raises():
    """Отсутствующий файл версии → FileNotFoundError."""
    b = _make_builder("template", version="v001")
    with pytest.raises(FileNotFoundError):
        b.build("t", {}, [], version="v999")


def test_builder_caches_template():
    """Шаблон кэшируется — повторный вызов не читает файл дважды."""
    b = _make_builder("CACHED")
    r1 = b.build("a", {}, [])
    r2 = b.build("b", {}, [])
    assert r1["system"] == r2["system"] == "CACHED"
    assert len(b._cache) == 1


# ── Метаданные и транскрипт ───────────────────────────────────────────────────


def test_builder_includes_metadata_in_user_message():
    """Метаданные звонка попадают в user-часть сообщения."""
    b = _make_builder("SYS")
    meta = {
        "contact_name": "Иванов Пётр",
        "phone": "+79161234567",
        "call_datetime": "2026-03-28 14:30:00",
        "direction": "IN",
        "duration_ms": 120000,
    }
    result = b.build("текст разговора", meta, [])
    user = result["user"]
    assert "Иванов Пётр" in user
    assert "+79161234567" in user
    assert "IN" in user
    assert "120.0 сек" in user


def test_builder_includes_transcript():
    """Транскрипт попадает в user-часть."""
    b = _make_builder("SYS")
    result = b.build("[me]: Привет\n[s2]: Здравствуйте", {}, [])
    assert "[me]: Привет" in result["user"]


def test_builder_empty_transcript():
    """Пустой транскрипт не вызывает ошибку."""
    b = _make_builder("SYS")
    result = b.build("", {}, [])
    assert isinstance(result, dict)


# ── previous_summaries — оба формата ─────────────────────────────────────────


def test_builder_previous_summaries_as_strings():
    """list[str] в previous_summaries поддерживается."""
    b = _make_builder("SYS")
    result = b.build("text", {}, ["Предыдущий звонок о долге", "Второй анализ"])
    assert "Предыдущий звонок" in result["user"]


def test_builder_previous_summaries_as_dicts():
    """list[dict] в previous_summaries поддерживается."""
    b = _make_builder("SYS")
    summaries = [{"call_datetime": "2026-01-01", "summary": "Разговор о сделке"}]
    result = b.build("text", {}, summaries)
    assert "Разговор о сделке" in result["user"]


def test_builder_previous_summaries_empty():
    """Пустой список previous_summaries не вызывает ошибку."""
    b = _make_builder("SYS")
    result = b.build("text", {}, [])
    assert isinstance(result, dict)


def test_builder_previous_summaries_none():
    """None в previous_summaries обрабатывается gracefully."""
    b = _make_builder("SYS")
    result = b.build("text", {}, None)
    assert isinstance(result, dict)


# ── Инициализация ─────────────────────────────────────────────────────────────


def test_builder_init_nonexistent_dir_raises():
    """Несуществующая директория → FileNotFoundError при инициализации."""
    with pytest.raises(FileNotFoundError):
        PromptBuilder("/nonexistent/path/to/prompts")


def test_builder_has_cache_attribute():
    """PromptBuilder имеет атрибут _cache после инициализации."""
    b = _make_builder("tmpl")
    assert hasattr(b, "_cache")
    assert isinstance(b._cache, dict)
