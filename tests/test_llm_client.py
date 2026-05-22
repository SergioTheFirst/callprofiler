# -*- coding: utf-8 -*-
"""Regression tests for LLMClient (analyze/llm_client.py).

Covers: init, connection verification, generate, error handling, backwards compat.
Uses unittest.mock — no live llama-server required.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from callprofiler.analyze.llm_client import LLMClient, OllamaClient


class MockResponse:
    def __init__(self, json_data, status_code=200, text=""):
        self._json = json_data
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import HTTPError
            raise HTTPError(f"{self.status_code} Error", response=self)


class TestLLMClientInit:

    def test_base_url_rstrip_trailing_slash(self):
        with patch("requests.post", return_value=MockResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        )):
            client = LLMClient("http://localhost:8080/v1/chat/completions/")
            assert client.base_url == "http://localhost:8080/v1/chat/completions"

    def test_base_url_no_trailing_slash(self):
        with patch("requests.post", return_value=MockResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        )):
            client = LLMClient("http://localhost:8080/v1/chat/completions")
            assert client.base_url == "http://localhost:8080/v1/chat/completions"

    def test_default_timeout(self):
        with patch("requests.post", return_value=MockResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        )):
            client = LLMClient("http://localhost:8080/v1/chat/completions")
            assert client.timeout == 300

    def test_custom_timeout(self):
        with patch("requests.post", return_value=MockResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        )):
            client = LLMClient("http://localhost:8080/v1/chat/completions", timeout=60)
            assert client.timeout == 60

    def test_raises_connection_error(self):
        from requests import ConnectionError as ReqConnectionError

        with patch("requests.post", side_effect=ReqConnectionError("refused")):
            with pytest.raises(ConnectionError, match="Не удаётся подключиться"):
                LLMClient("http://localhost:8080/v1/chat/completions")

    def test_warns_on_other_request_exception(self):
        from requests import RequestException

        with patch("requests.post", side_effect=RequestException("unknown")):
            client = LLMClient("http://localhost:8080/v1/chat/completions")
            assert client is not None


class TestLLMClientGenerate:

    @pytest.fixture
    def client(self):
        with patch("requests.post", return_value=MockResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        )):
            return LLMClient("http://localhost:8080/v1/chat/completions")

    def test_generate_returns_content(self, client):
        with patch("requests.post", return_value=MockResponse(
            {"choices": [{"message": {"content": '{"result": "test"}'}}]}
        )):
            result = client.generate([{"role": "user", "content": "hello"}])
            assert result == '{"result": "test"}'

    def test_generate_sends_messages_as_json_body(self):
        mock_post = MagicMock(return_value=MockResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        ))
        with patch("requests.post", mock_post):
            with patch("requests.post", return_value=MockResponse(
                {"choices": [{"message": {"content": "ok"}}]}
            )):
                client = LLMClient("http://localhost:8080/v1/chat/completions")
                with patch("requests.post", mock_post):
                    client.generate([{"role": "user", "content": "test"}])
                    call_args = mock_post.call_args
                    assert call_args[0][0] == "http://localhost:8080/v1/chat/completions"
                    body = call_args[1]["json"]
                    assert body["messages"] == [{"role": "user", "content": "test"}]
                    assert body["temperature"] == 0.3
                    assert body["max_tokens"] == 1500

    def test_generate_custom_temperature_and_tokens(self, client):
        with patch("requests.post", return_value=MockResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        )):
            client.generate(
                [{"role": "user", "content": "hello"}],
                temperature=0.7,
                max_tokens=500,
            )

    def test_generate_returns_none_on_json_error(self, client):
        resp = MockResponse({"choices": [{"message": {"content": "ok"}}]})
        resp.json = MagicMock(side_effect=json.JSONDecodeError("bad json", "", 0))
        with patch("requests.post", return_value=resp):
            result = client.generate([{"role": "user", "content": "hello"}])
            assert result is None

    def test_generate_returns_none_on_missing_choices(self, client):
        with patch("requests.post", return_value=MockResponse({})):
            result = client.generate([{"role": "user", "content": "hello"}])
            assert result is None

    def test_generate_returns_none_on_timeout(self, client):
        from requests import Timeout

        with patch("requests.post", side_effect=Timeout("timeout")):
            result = client.generate([{"role": "user", "content": "hello"}])
            assert result is None

    def test_generate_returns_none_on_request_exception(self, client):
        from requests import RequestException

        with patch("requests.post", side_effect=RequestException("error")):
            result = client.generate([{"role": "user", "content": "hello"}])
            assert result is None

    def test_generate_uses_instance_timeout(self, client):
        with patch("requests.post", return_value=MockResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        )) as mock_post:
            client.generate([{"role": "user", "content": "hello"}])
            assert mock_post.call_args[1]["timeout"] == 300


class TestBackwardsCompat:

    def test_ollama_client_is_llm_client(self):
        assert OllamaClient is LLMClient

    def test_ollama_client_creates_llm_client(self):
        with patch("requests.post", return_value=MockResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        )):
            client = OllamaClient("http://localhost:8080/v1/chat/completions")
            assert isinstance(client, LLMClient)
