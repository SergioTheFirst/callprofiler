# -*- coding: utf-8 -*-
"""Regression tests for LLMClient — OpenAI-compatible Chat Completions contract."""

from __future__ import annotations

import json
import unittest.mock as mock

import pytest
import requests

from callprofiler.analyze.llm_client import LLMClient, OllamaClient


def _fake_response(content: str, status: int = 200) -> mock.MagicMock:
    resp = mock.MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.text = json.dumps({"choices": [{"message": {"content": content}}]})
    resp.raise_for_status.return_value = None
    return resp


class TestLLMClient:
    def test_generate_returns_content(self, monkeypatch):
        monkeypatch.setattr(requests, "post", lambda *a, **kw: _fake_response("test answer"))
        client = LLMClient(base_url="http://127.0.0.1:8080/v1/chat/completions")
        result = client.generate(messages=[{"role": "user", "content": "hi"}])
        assert result == "test answer"

    def test_generate_sends_messages_correctly(self, monkeypatch):
        post_mock = mock.MagicMock(return_value=_fake_response("ok"))
        monkeypatch.setattr(requests, "post", post_mock)
        client = LLMClient(base_url="http://127.0.0.1:8080/v1/chat/completions")
        client.generate(messages=[{"role": "user", "content": "hello"}], temperature=0.5, max_tokens=200)
        payload = post_mock.call_args[1]["json"]
        assert payload["messages"] == [{"role": "user", "content": "hello"}]
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 200

    def test_generate_returns_none_on_timeout(self, monkeypatch):
        monkeypatch.setattr(requests, "post", mock.MagicMock(side_effect=requests.Timeout("timed out")))
        client = LLMClient(base_url="http://127.0.0.1:8080/v1/chat/completions")
        result = client.generate(messages=[{"role": "user", "content": "hi"}])
        assert result is None

    def test_generate_returns_none_on_missing_choices(self, monkeypatch):
        resp = mock.MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.json.return_value = {"something": "else"}
        resp.text = '{"something": "else"}'
        resp.raise_for_status.return_value = None
        monkeypatch.setattr(requests, "post", lambda *a, **kw: resp)
        client = LLMClient(base_url="http://127.0.0.1:8080/v1/chat/completions")
        result = client.generate(messages=[{"role": "user", "content": "hi"}])
        assert result is None

    def test_ollama_client_is_llm_client(self):
        assert OllamaClient is LLMClient

    def test_ollama_client_works(self, monkeypatch):
        monkeypatch.setattr(requests, "post", lambda *a, **kw: _fake_response("via alias"))
        client = OllamaClient(base_url="http://127.0.0.1:8080/v1/chat/completions")
        assert isinstance(client, LLMClient)
        assert client.generate(messages=[{"role": "user", "content": "test"}]) == "via alias"

    def test_no_model_parameter_in_payload(self, monkeypatch):
        post_mock = mock.MagicMock(return_value=_fake_response("ok"))
        monkeypatch.setattr(requests, "post", post_mock)
        client = LLMClient(base_url="http://127.0.0.1:8080/v1/chat/completions")
        client.generate(messages=[{"role": "user", "content": "x"}])
        payload = post_mock.call_args[1]["json"]
        assert "model" not in payload