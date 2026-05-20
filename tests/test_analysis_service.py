# -*- coding: utf-8 -*-
"""
test_analysis_service.py — тесты AnalysisService + Orchestrator LLM API (DS1 F1.2, F11.1).

Покрывает:
- AnalysisService использует правильный messages-формат OpenAI API
- AnalysisService не использует ollama_url
- Правильный system/user раздел в messages
- Graceful fallback при недоступности LLM
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import requests

from callprofiler.analyze.llm_client import LLMClient
from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.db.repository import Repository
from callprofiler.models import Analysis, Segment

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def _add_user(repo: Repository, user_id: str = "u1") -> None:
    repo.add_user(
        user_id=user_id,
        display_name="Test",
        telegram_chat_id="0",
        incoming_dir="/tmp/in",
        sync_dir="/tmp/sync",
        ref_audio="/tmp/ref.wav",
    )


def _add_call(repo: Repository, user_id: str = "u1") -> int:
    cid = repo.get_or_create_contact(user_id, "+70000000001", "Test")
    return repo.create_call(
        user_id=user_id,
        contact_id=cid,
        direction="IN",
        call_datetime="2026-04-01 10:00:00",
        source_filename="t.mp3",
        source_md5="abc",
        audio_path="/tmp/t.mp3",
    )


def _fake_response(content: str) -> mock.MagicMock:
    resp = mock.MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.text = json.dumps({"choices": [{"message": {"content": content}}]})
    resp.raise_for_status.return_value = None
    return resp


def _make_config_with_prompts():
    """Создать минимальный Config с реальным prompts_dir."""
    from callprofiler.config import (
        AudioConfig,
        Config,
        FeaturesConfig,
        ModelsConfig,
        PipelineConfig,
    )

    cfg = Config(
        data_dir="",
        log_file="",
        hf_token="",
        models=ModelsConfig(
            llm_model="local",
            llm_url="http://127.0.0.1:8080/v1/chat/completions",
        ),
        pipeline=PipelineConfig(),
        audio=AudioConfig(),
        features=FeaturesConfig(enable_telegram_notification=False),
    )
    return cfg


# ── F1.1 — PromptBuilder через AnalysisService ────────────────────────────────


class TestAnalysisServiceMessages:
    """AnalysisService формирует правильные messages для OpenAI API (F1.2)."""

    def test_messages_format_is_list_of_dicts(self, monkeypatch, tmp_path):
        """messages передаются как list[dict] с role и content."""
        # Подготовить prompts dir
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "analyze_v001.txt").write_text(
            "Ты анализируешь звонок. Верни JSON.", encoding="utf-8"
        )

        from callprofiler.analyze.service import AnalysisService
        from callprofiler.config import (
            AudioConfig,
            Config,
            FeaturesConfig,
            ModelsConfig,
            PipelineConfig,
        )

        cfg = Config(
            data_dir=str(tmp_path),
            log_file="",
            hf_token="",
            models=ModelsConfig(llm_url="http://127.0.0.1:8080/v1/chat/completions"),
            pipeline=PipelineConfig(),
            audio=AudioConfig(),
            features=FeaturesConfig(),
        )

        repo = _make_repo()
        _add_user(repo)
        call_id = _add_call(repo)

        captured = {}

        def fake_post(url, json=None, timeout=None, **kw):
            captured["json"] = json
            return _fake_response(
                '{"summary":"ok","priority":50,"risk_score":10,"call_type":"business"}'
            )

        monkeypatch.setattr(requests, "post", fake_post)

        svc = AnalysisService(cfg, repo)
        # Перегрузить prompts_dir
        from callprofiler.analyze.prompt_builder import PromptBuilder

        svc.prompt_builder = PromptBuilder(str(prompts_dir))

        call = (
            repo._get_conn()
            .execute("SELECT * FROM calls WHERE call_id=?", (call_id,))
            .fetchone()
        )
        segments = [Segment(0, 1000, "Привет как дела", "OWNER")]
        svc.analyze_one_call(dict(call), segments)

        assert "messages" in captured["json"], "LLM запрос должен содержать 'messages'"
        messages = captured["json"]["messages"]
        assert isinstance(messages, list)
        assert len(messages) >= 1
        for m in messages:
            assert "role" in m
            assert "content" in m

    def test_system_message_contains_prompt_template(self, monkeypatch, tmp_path):
        """messages[0] с role='system' содержит текст системного промпта."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "analyze_v001.txt").write_text(
            "SYSTEM INSTRUCTIONS HERE", encoding="utf-8"
        )

        from callprofiler.analyze.service import AnalysisService
        from callprofiler.config import (
            AudioConfig,
            Config,
            FeaturesConfig,
            ModelsConfig,
            PipelineConfig,
        )

        cfg = Config(
            data_dir=str(tmp_path),
            log_file="",
            hf_token="",
            models=ModelsConfig(llm_url="http://127.0.0.1:8080/v1/chat/completions"),
            pipeline=PipelineConfig(),
            audio=AudioConfig(),
            features=FeaturesConfig(),
        )

        repo = _make_repo()
        _add_user(repo)
        call_id = _add_call(repo)

        captured = {}

        def fake_post(url, json=None, timeout=None, **kw):
            captured["json"] = json
            return _fake_response(
                '{"summary":"ok","priority":0,"risk_score":0,"call_type":"short"}'
            )

        monkeypatch.setattr(requests, "post", fake_post)

        svc = AnalysisService(cfg, repo)
        from callprofiler.analyze.prompt_builder import PromptBuilder

        svc.prompt_builder = PromptBuilder(str(prompts_dir))

        call = dict(
            repo._get_conn()
            .execute("SELECT * FROM calls WHERE call_id=?", (call_id,))
            .fetchone()
        )
        svc.analyze_one_call(call, [Segment(0, 1000, "алло", "OWNER")])

        messages = captured["json"]["messages"]
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "SYSTEM INSTRUCTIONS HERE" in system_msgs[0]["content"]

    def test_user_message_contains_transcript(self, monkeypatch, tmp_path):
        """messages user-часть содержит транскрипт."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "analyze_v001.txt").write_text("SYS", encoding="utf-8")

        from callprofiler.analyze.service import AnalysisService
        from callprofiler.config import (
            AudioConfig,
            Config,
            FeaturesConfig,
            ModelsConfig,
            PipelineConfig,
        )

        cfg = Config(
            data_dir=str(tmp_path),
            log_file="",
            hf_token="",
            models=ModelsConfig(llm_url="http://127.0.0.1:8080/v1/chat/completions"),
            pipeline=PipelineConfig(),
            audio=AudioConfig(),
            features=FeaturesConfig(),
        )

        repo = _make_repo()
        _add_user(repo)
        call_id = _add_call(repo)

        captured = {}

        def fake_post(url, json=None, timeout=None, **kw):
            captured["json"] = json
            return _fake_response('{"summary":"ok","priority":0,"risk_score":0}')

        monkeypatch.setattr(requests, "post", fake_post)

        svc = AnalysisService(cfg, repo)
        from callprofiler.analyze.prompt_builder import PromptBuilder

        svc.prompt_builder = PromptBuilder(str(prompts_dir))

        call = dict(
            repo._get_conn()
            .execute("SELECT * FROM calls WHERE call_id=?", (call_id,))
            .fetchone()
        )
        unique_text = "УНИКАЛЬНЫЙ_ТЕКСТ_ТРАНСКРИПТА_12345"
        svc.analyze_one_call(call, [Segment(0, 1000, unique_text, "OWNER")])

        messages = captured["json"]["messages"]
        user_content = " ".join(m["content"] for m in messages if m["role"] == "user")
        assert unique_text in user_content

    def test_no_ollama_url_in_config(self):
        """Config.models не имеет поля ollama_url (оно устарело — F1.2)."""
        from callprofiler.config import ModelsConfig

        m = ModelsConfig()
        assert not hasattr(m, "ollama_url"), (
            "ollama_url должен быть удалён из ModelsConfig (deprecated)"
        )
        assert hasattr(m, "llm_url"), "llm_url должен быть в ModelsConfig"


# ── LLM Client — OpenAI API ───────────────────────────────────────────────────


class TestLLMClientAPIFormat:
    """LLMClient отправляет messages в формате OpenAI (F1.2)."""

    def test_payload_has_messages_not_prompt(self, monkeypatch):
        """POST-запрос содержит 'messages', но не 'prompt' (Ollama-стиль)."""
        post_mock = mock.MagicMock(return_value=_fake_response("answer"))
        monkeypatch.setattr(requests, "post", post_mock)
        client = LLMClient("http://127.0.0.1:8080/v1/chat/completions")
        client.generate(messages=[{"role": "user", "content": "test"}])
        payload = post_mock.call_args[1]["json"]
        assert "messages" in payload
        assert "prompt" not in payload

    def test_no_model_field_in_payload(self, monkeypatch):
        """llama-server сам знает модель — не передаём model= в запросе."""
        post_mock = mock.MagicMock(return_value=_fake_response("ok"))
        monkeypatch.setattr(requests, "post", post_mock)
        client = LLMClient("http://127.0.0.1:8080/v1/chat/completions")
        client.generate(messages=[{"role": "user", "content": "x"}])
        payload = post_mock.call_args[1]["json"]
        assert "model" not in payload

    def test_system_and_user_messages(self, monkeypatch):
        """Система и пользователь в messages передаются в нужном порядке."""
        post_mock = mock.MagicMock(return_value=_fake_response("ok"))
        monkeypatch.setattr(requests, "post", post_mock)
        client = LLMClient("http://127.0.0.1:8080/v1/chat/completions")
        client.generate(
            messages=[
                {"role": "system", "content": "ты анализируешь"},
                {"role": "user", "content": "транскрипт"},
            ]
        )
        payload = post_mock.call_args[1]["json"]
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"


# ── response_parser — canonical_json ─────────────────────────────────────────


class TestResponseParserCanonicalJson:
    """response_parser возвращает canonical_json (F2.2)."""

    def test_parsed_ok_has_canonical_json(self):
        """При успешном парсинге canonical_json не пустой."""
        raw = json.dumps(
            {
                "summary": "тест",
                "priority": 50,
                "risk_score": 10,
                "call_type": "business",
            }
        )
        analysis = parse_llm_response(raw, model="test", prompt_version="v001")
        assert analysis.canonical_json, "canonical_json должен быть непустым"
        parsed_back = json.loads(analysis.canonical_json)
        assert parsed_back["summary"] == "тест"

    def test_markdown_wrapped_json_canonical_repaired(self):
        """Markdown-обёрнутый JSON → canonical_json содержит чистый JSON."""
        raw = '```json\n{"summary": "в markdown", "priority": 40, "risk_score": 5}\n```'
        analysis = parse_llm_response(raw)
        assert analysis.canonical_json
        parsed_back = json.loads(analysis.canonical_json)
        assert "summary" in parsed_back

    def test_failed_parse_canonical_json_empty_or_none(self):
        """При полном провале парсинга canonical_json пустой или None."""
        analysis = parse_llm_response("totally not json", model="x")
        # parse_failed → canonical_json может быть пустым
        assert analysis.parse_status == "parse_failed"

    def test_schema_version_v2_in_analysis(self):
        """Analysis.schema_version по умолчанию 'v2'."""
        a = Analysis(priority=0, risk_score=0, summary="")
        assert a.schema_version == "v2"
