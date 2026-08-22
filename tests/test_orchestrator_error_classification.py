# -*- coding: utf-8 -*-
"""T-09: Orchestrator._fail — единый владелец status=error с классификацией FATAL/retryable (без БД)."""
from __future__ import annotations

import pytest

from callprofiler.config import Config
from callprofiler.pipeline.orchestrator import Orchestrator


class _RepoSpy:
    def __init__(self):
        self.calls = []

    def update_call_status(self, user_id, call_id, status, message=None, **kw):
        self.calls.append((user_id, call_id, status, message))
        return True


@pytest.mark.parametrize("exc,prefix", [
    (ValueError("bad"), "FATAL[transcribe]:"), (FileNotFoundError("x"), "FATAL[transcribe]:"),
    (KeyError("k"), "FATAL[transcribe]:"), (ConnectionError("down"), "transcribe:"),
    (RuntimeError("llm"), "transcribe:"), (OSError("io"), "transcribe:"),
])
def test_fail_classification(exc, prefix):
    spy = _RepoSpy()
    o = Orchestrator(Config(), spy)
    o._fail("u1", 7, exc, "transcribe")
    assert spy.calls and spy.calls[-1][2] == "error" and spy.calls[-1][3].startswith(prefix)
