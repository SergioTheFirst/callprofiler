# -*- coding: utf-8 -*-
"""test_llm_json_mode.py — M4: response_format json_object flag (ozalup2.md §3.4)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from callprofiler.analyze.llm_client import LLMClient


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


def _ok(content="hi"):
    return MockResponse({"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})


def test_json_mode_true_adds_response_format():
    msgs = [{"role": "user", "content": "hello"}]
    mock_post = MagicMock(return_value=_ok())
    with patch("requests.post", mock_post):
        client = LLMClient("http://localhost:8080/v1/chat/completions")
        client.complete(msgs, temperature=0.3, max_tokens=100, json_mode=True)
    body = mock_post.call_args[1]["json"]
    assert body["response_format"] == {"type": "json_object"}


def test_json_mode_false_omits_response_format():
    msgs = [{"role": "user", "content": "hello"}]
    mock_post = MagicMock(return_value=_ok())
    with patch("requests.post", mock_post):
        client = LLMClient("http://localhost:8080/v1/chat/completions")
        client.complete(msgs, temperature=0.3, max_tokens=100, json_mode=False)
    body = mock_post.call_args[1]["json"]
    assert "response_format" not in body


def test_json_mode_default_is_false():
    msgs = [{"role": "user", "content": "hello"}]
    mock_post = MagicMock(return_value=_ok())
    with patch("requests.post", mock_post):
        client = LLMClient("http://localhost:8080/v1/chat/completions")
        client.complete(msgs, temperature=0.3, max_tokens=100)
    body = mock_post.call_args[1]["json"]
    assert "response_format" not in body
