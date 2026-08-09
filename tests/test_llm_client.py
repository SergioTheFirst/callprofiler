# -*- coding: utf-8 -*-
"""Regression tests for LLMClient (analyze/llm_client.py).

Covers: init (no network, T-13), liveness/readiness probes, generate/complete,
error handling, backwards compat. Uses unittest.mock — no live llama-server required.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from callprofiler.analyze.llm_client import LLMClient, LLMDecodeError, OllamaClient


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
        client = LLMClient("http://localhost:8080/v1/chat/completions/")
        assert client.base_url == "http://localhost:8080/v1/chat/completions"

    def test_base_url_no_trailing_slash(self):
        client = LLMClient("http://localhost:8080/v1/chat/completions")
        assert client.base_url == "http://localhost:8080/v1/chat/completions"

    def test_default_timeout(self):
        client = LLMClient("http://localhost:8080/v1/chat/completions")
        assert client.timeout == 300

    def test_custom_timeout(self):
        client = LLMClient("http://localhost:8080/v1/chat/completions", timeout=60)
        assert client.timeout == 60

    def test_constructor_makes_no_http_requests(self):
        """T-13/P-LLM-01: конструктор дешёвый, ни одного сетевого вызова."""
        with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
            LLMClient("http://localhost:8080/v1/chat/completions")
        mock_post.assert_not_called()
        mock_get.assert_not_called()

    def test_constructor_works_without_live_server(self):
        """Раньше требовало живой сервер (или mock) — теперь создаётся всегда."""
        client = LLMClient("http://127.0.0.1:1/dead")  # заведомо недоступный адрес
        assert client is not None
        assert client.model_fingerprint == ""


class TestReadinessProbes:
    """check_live / check_ready / ensure_ready — T-13."""

    def test_check_live_true_on_200(self):
        client = LLMClient("http://localhost:8080/v1/chat/completions")
        with patch("requests.get", return_value=MagicMock(status_code=200)) as mock_get:
            assert client.check_live() is True
        assert mock_get.call_args[0][0] == "http://localhost:8080/health"

    def test_check_live_false_on_connection_error(self):
        from requests import ConnectionError as ReqConnectionError

        client = LLMClient("http://localhost:8080/v1/chat/completions")
        with patch("requests.get", side_effect=ReqConnectionError("refused")):
            assert client.check_live() is False

    def test_check_live_false_on_non_200(self):
        client = LLMClient("http://localhost:8080/v1/chat/completions")
        with patch("requests.get", return_value=MagicMock(status_code=500)):
            assert client.check_live() is False

    def test_check_live_does_not_write_cache(self, tmp_path):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        client = LLMClient(
            "http://localhost:8080/v1/chat/completions", cache_conn=conn,
        )
        with patch("requests.get", return_value=MagicMock(status_code=200)):
            client.check_live()
        n = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
        assert n == 0

    def test_check_ready_true_via_v1_models_and_captures_fingerprint(self):
        client = LLMClient("http://localhost:8080/v1/chat/completions")
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"data": [{"id": "qwen3.5-9b-q8_0"}]}
        with patch("requests.get", return_value=resp) as mock_get:
            assert client.check_ready() is True
        assert mock_get.call_args[0][0] == "http://localhost:8080/v1/models"
        assert client.model_fingerprint == "qwen3.5-9b-q8_0"

    def test_check_ready_falls_back_to_completion_when_v1_models_missing(self):
        """Старые сборки llama-server без /v1/models: 404 != "не готов"."""
        client = LLMClient("http://localhost:8080/v1/chat/completions")
        with patch("requests.get", return_value=MagicMock(status_code=404)), \
             patch("requests.post", return_value=MockResponse({"ok": True})) as mock_post:
            assert client.check_ready() is True
        assert mock_post.called
        assert client.model_fingerprint == ""  # недоступен дёшево — не выдумываем

    def test_check_ready_false_when_both_probes_fail(self):
        from requests import ConnectionError as ReqConnectionError

        client = LLMClient("http://localhost:8080/v1/chat/completions")
        with patch("requests.get", side_effect=ReqConnectionError("down")), \
             patch("requests.post", side_effect=ReqConnectionError("down")):
            assert client.check_ready() is False

    def test_check_ready_does_not_write_cache(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        client = LLMClient("http://localhost:8080/v1/chat/completions", cache_conn=conn)
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"data": [{"id": "m"}]}
        with patch("requests.get", return_value=resp):
            client.check_ready()
        n = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
        assert n == 0

    def test_ensure_ready_raises_connection_error_when_not_ready(self):
        from requests import ConnectionError as ReqConnectionError

        client = LLMClient("http://localhost:8080/v1/chat/completions")
        with patch("requests.get", side_effect=ReqConnectionError("down")), \
             patch("requests.post", side_effect=ReqConnectionError("down")):
            with pytest.raises(ConnectionError, match="Не удаётся подключиться"):
                client.ensure_ready()

    def test_ensure_ready_no_raise_when_ready(self):
        client = LLMClient("http://localhost:8080/v1/chat/completions")
        with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: {})):
            client.ensure_ready()  # no raise


class TestLLMClientGenerate:

    @pytest.fixture
    def client(self):
        return LLMClient("http://localhost:8080/v1/chat/completions")

    def test_generate_returns_content(self, client):
        with patch("requests.post", return_value=MockResponse(
            {"choices": [{"message": {"content": '{"result": "test"}'}}]}
        )):
            result = client.generate([{"role": "user", "content": "hello"}])
            assert result == '{"result": "test"}'

    def test_generate_sends_messages_as_json_body(self, client):
        mock_post = MagicMock(return_value=MockResponse(
            {"choices": [{"message": {"content": "ok"}}]}
        ))
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
        """generate() — обратная совместимость: LLMDecodeError → None, не raise."""
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

        with patch("requests.post", side_effect=Timeout("timeout")), \
             patch("callprofiler.analyze.llm_client.time.sleep"):
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


class TestLLMClientComplete:
    """T-13: complete() — типизированная ошибка декодирования, ретрай 5xx."""

    @pytest.fixture
    def client(self):
        return LLMClient("http://localhost:8080/v1/chat/completions")

    def test_complete_raises_llm_decode_error_on_invalid_json(self, client):
        resp = MockResponse({"choices": [{"message": {"content": "ok"}}]})
        resp.json = MagicMock(side_effect=json.JSONDecodeError("bad json", "", 0))
        with patch("requests.post", return_value=resp):
            with pytest.raises(LLMDecodeError):
                client.complete([{"role": "user", "content": "hello"}])

    def test_complete_raises_llm_decode_error_on_missing_choices(self, client):
        with patch("requests.post", return_value=MockResponse({})):
            with pytest.raises(LLMDecodeError):
                client.complete([{"role": "user", "content": "hello"}])

    def test_complete_retries_on_5xx_then_succeeds(self, client):
        responses = [
            MockResponse({}, status_code=503, text="overloaded"),
            MockResponse({}, status_code=503, text="overloaded"),
            MockResponse({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}),
        ]
        mock_post = MagicMock(side_effect=responses)
        with patch("requests.post", mock_post), patch("callprofiler.analyze.llm_client.time.sleep") as mock_sleep:
            result = client.complete([{"role": "user", "content": "hello"}])
        assert result.text == "ok"
        assert mock_post.call_count == 3
        assert mock_sleep.call_count == 2

    def test_complete_4xx_not_retried(self, client):
        mock_post = MagicMock(return_value=MockResponse({}, status_code=400, text="bad request"))
        with patch("requests.post", mock_post):
            result = client.complete([{"role": "user", "content": "hello"}])
        assert result.text is None
        assert mock_post.call_count == 1

    def test_complete_5xx_exhausted_returns_none(self, client):
        mock_post = MagicMock(return_value=MockResponse({}, status_code=500, text="down"))
        with patch("requests.post", mock_post), patch("callprofiler.analyze.llm_client.time.sleep"):
            result = client.complete([{"role": "user", "content": "hello"}])
        assert result.text is None
        assert mock_post.call_count == 3


class TestBackwardsCompat:

    def test_ollama_client_is_llm_client(self):
        assert OllamaClient is LLMClient

    def test_ollama_client_creates_llm_client(self):
        client = OllamaClient("http://localhost:8080/v1/chat/completions")
        assert isinstance(client, LLMClient)
