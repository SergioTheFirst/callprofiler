# -*- coding: utf-8 -*-
"""T-22: контракт кодов выхода CLI."""
from __future__ import annotations

import sys

import pytest

from callprofiler.cli import exit_codes as ec
from callprofiler.cli import main as cli_main


@pytest.mark.parametrize("exc,code", [
    (FileNotFoundError("x"), ec.EXIT_NOT_FOUND), (KeyError("u"), ec.EXIT_NOT_FOUND),
    (ConnectionError("llm"), ec.EXIT_RETRYABLE), (TimeoutError(), ec.EXIT_RETRYABLE),
    (ValueError("bad"), ec.EXIT_USAGE), (RuntimeError("boom"), ec.EXIT_FATAL),
    (KeyboardInterrupt(), ec.EXIT_INTERRUPTED),
])
def test_map_exception(exc, code):
    assert ec.map_exception(exc) == code


def _run(monkeypatch, argv, handler):
    from types import SimpleNamespace
    monkeypatch.setattr(sys, "argv", ["callprofiler", *argv])
    monkeypatch.setitem(cli_main._DISPATCH, "status", ("fake.module", "cmd"))
    monkeypatch.setattr(cli_main.importlib, "import_module", lambda name: SimpleNamespace(cmd=handler))
    with pytest.raises(SystemExit) as e:
        cli_main.main()
    return e.value.code


def test_main_maps_handler_result_and_exceptions(monkeypatch):
    assert _run(monkeypatch, ["status"], lambda a: None) == ec.EXIT_OK
    assert _run(monkeypatch, ["status"], lambda a: 4) == ec.EXIT_PARTIAL
    assert _run(monkeypatch, ["status"], lambda a: (_ for _ in ()).throw(ConnectionError("x"))) == ec.EXIT_RETRYABLE
    assert _run(monkeypatch, ["status"], lambda a: (_ for _ in ()).throw(FileNotFoundError("x"))) == ec.EXIT_NOT_FOUND


def test_reprocess_requires_user_or_all(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["callprofiler", "reprocess"])
    with pytest.raises(SystemExit) as e:
        cli_main.main()
    assert e.value.code == ec.EXIT_USAGE
    assert "--user" in capsys.readouterr().err
