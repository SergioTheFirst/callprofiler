# -*- coding: utf-8 -*-
"""test_llm_cache.py — M3: мемоизация analyze-пути по fingerprint (decisions.md 2026-06-04 #1)."""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from requests import ConnectionError as ReqConnectionError

from callprofiler.analyze.llm_client import LLMClient, LLMResult
from callprofiler.llm_cache import get as cache_get
from callprofiler.llm_cache import make_key, put


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


def _ok(content="hello", finish_reason="stop"):
    return MockResponse(
        {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}
    )


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


class TestMakeKey:
    def test_deterministic(self):
        msgs = [{"role": "user", "content": "hi"}]
        k1 = make_key(msgs, 0.3, 1500, "v001")
        k2 = make_key(msgs, 0.3, 1500, "v001")
        assert k1 == k2

    def test_differs_on_prompt_version(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert make_key(msgs, 0.3, 1500, "v001") != make_key(msgs, 0.3, 1500, "v002")

    def test_differs_on_temperature(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert make_key(msgs, 0.3, 1500, "v001") != make_key(msgs, 0.7, 1500, "v001")

    def test_key_order_independent(self):
        # sort_keys=True -> порядок ключей внутри сообщения не важен
        m1 = [{"role": "user", "content": "hi"}]
        m2 = [{"content": "hi", "role": "user"}]
        assert make_key(m1, 0.3, 1500, "v001") == make_key(m2, 0.3, 1500, "v001")


class TestPutGet:
    def test_put_none_text_not_written(self, conn):
        from callprofiler.llm_cache import apply_llm_cache_schema
        apply_llm_cache_schema(conn)
        put(conn, "k1", "me", "v001", LLMResult(text=None))
        n = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
        assert n == 0

    def test_put_then_get_roundtrip(self, conn):
        from callprofiler.llm_cache import apply_llm_cache_schema
        apply_llm_cache_schema(conn)
        put(conn, "k1", "me", "v001", LLMResult(text="hi", finish_reason="stop"))
        result = cache_get(conn, "k1")
        assert result.text == "hi" and result.finish_reason == "stop"

    def test_get_miss_returns_none(self, conn):
        from callprofiler.llm_cache import apply_llm_cache_schema
        apply_llm_cache_schema(conn)
        assert cache_get(conn, "does-not-exist") is None


class TestLLMClientCaching:
    def test_second_identical_call_hits_cache(self, conn):
        msgs = [{"role": "user", "content": "hello"}]
        with patch("requests.post", return_value=_ok("hi", "stop")) as mock_post:
            client = LLMClient(
                "http://localhost:8080/v1/chat/completions",
                cache_conn=conn, cache_user_id="me", prompt_version="v001",
            )
            r1 = client.complete(msgs, temperature=0.3, max_tokens=100)
            r2 = client.complete(msgs, temperature=0.3, max_tokens=100)
        assert r1.text == "hi" and r1.finish_reason == "stop"
        assert r2.text == "hi" and r2.finish_reason == "stop"
        # 1 вызов на _verify_connection (в __init__) + 1 на первый complete() = 2
        assert mock_post.call_count == 2

    def test_connection_error_not_cached_retries_next_time(self, conn):
        msgs = [{"role": "user", "content": "hello"}]
        mock_post = MagicMock(side_effect=[
            _ok("verify-ok"),  # _verify_connection в __init__
            ReqConnectionError("down"), ReqConnectionError("down"), ReqConnectionError("down"),
        ])
        with patch("requests.post", mock_post), patch("callprofiler.analyze.llm_client.time.sleep"):
            client = LLMClient(
                "http://localhost:8080/v1/chat/completions",
                cache_conn=conn, cache_user_id="me", prompt_version="v001",
            )
            r1 = client.complete(msgs, temperature=0.3, max_tokens=100)
        assert r1.text is None
        n = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
        assert n == 0

        # Второй прогон (сбой не закэширован) снова бьёт HTTP, а не отдаёт кэш.
        mock_post2 = MagicMock(return_value=_ok("recovered", "stop"))
        with patch("requests.post", mock_post2):
            r2 = client.complete(msgs, temperature=0.3, max_tokens=100)
        assert r2.text == "recovered"
        assert mock_post2.call_count == 1

    def test_different_prompt_version_writes_two_rows(self, conn):
        msgs = [{"role": "user", "content": "hello"}]
        with patch("requests.post", return_value=_ok("hi", "stop")):
            client_v1 = LLMClient(
                "http://localhost:8080/v1/chat/completions",
                cache_conn=conn, cache_user_id="me", prompt_version="v001",
            )
            client_v1.complete(msgs, temperature=0.3, max_tokens=100)
            client_v2 = LLMClient(
                "http://localhost:8080/v1/chat/completions",
                cache_conn=conn, cache_user_id="me", prompt_version="v002",
            )
            client_v2.complete(msgs, temperature=0.3, max_tokens=100)
        n = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
        assert n == 2

    def test_no_cache_conn_calls_http_every_time(self):
        """Регресс: cache_conn=None -> поведение прежнее (без кэша)."""
        msgs = [{"role": "user", "content": "hello"}]
        with patch("requests.post", return_value=_ok("hi", "stop")) as mock_post:
            client = LLMClient("http://localhost:8080/v1/chat/completions")
            client.complete(msgs, temperature=0.3, max_tokens=100)
            client.complete(msgs, temperature=0.3, max_tokens=100)
        # verify (1) + 2 complete() без кэша = 3
        assert mock_post.call_count == 3

    def test_user_id_written_to_cache_row(self, conn):
        msgs = [{"role": "user", "content": "hello"}]
        with patch("requests.post", return_value=_ok("hi", "stop")):
            client = LLMClient(
                "http://localhost:8080/v1/chat/completions",
                cache_conn=conn, cache_user_id="alice", prompt_version="v001",
            )
            client.complete(msgs, temperature=0.3, max_tokens=100)
        row = conn.execute("SELECT user_id FROM llm_calls").fetchone()
        assert row["user_id"] == "alice"

    def test_truncated_response_cached_as_is(self, conn):
        msgs = [{"role": "user", "content": "hello"}]
        with patch("requests.post", return_value=_ok("partial json", "length")):
            client = LLMClient(
                "http://localhost:8080/v1/chat/completions",
                cache_conn=conn, cache_user_id="me", prompt_version="v001",
            )
            r1 = client.complete(msgs, temperature=0.3, max_tokens=100)
        assert r1.truncated
        cached = cache_get(conn, make_key(msgs, 0.3, 100, "v001"))
        assert cached.text == "partial json" and cached.finish_reason == "length"
