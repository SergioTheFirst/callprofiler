# -*- coding: utf-8 -*-
"""test_watcher_autofit.py — debounced авто-запуск insight-fit в watcher (Ф0 плана досье)."""
import sqlite3
from unittest import mock

from callprofiler.config import Config, PipelineConfig
from callprofiler.pipeline.watcher import FileWatcher


class _Repo:
    def __init__(self, users=None, conn=None):
        self._users = users or []
        self._conn = conn

    def get_all_users(self):
        return self._users

    def _get_conn(self):
        return self._conn


def _watcher(autofit=True, min_new=2, min_interval=0, repo=None):
    cfg = Config()
    cfg.pipeline = PipelineConfig(
        insight_autofit=autofit,
        insight_autofit_min_new=min_new,
        insight_autofit_min_interval_sec=min_interval,
    )
    return FileWatcher(cfg, repo or _Repo(), ingester=None, orchestrator=None)


def test_autofit_triggers_after_threshold():
    w = _watcher(autofit=True, min_new=2, min_interval=0)
    w._new_terminal_since_fit = 2
    with mock.patch.object(w, "_run_insight_fit") as m:
        w._maybe_autofit()
    assert m.call_count == 1
    assert w._new_terminal_since_fit == 0


def test_autofit_below_threshold_skips():
    w = _watcher(autofit=True, min_new=5, min_interval=0)
    w._new_terminal_since_fit = 4
    with mock.patch.object(w, "_run_insight_fit") as m:
        w._maybe_autofit()
    assert m.call_count == 0
    assert w._new_terminal_since_fit == 4  # счётчик не сбрасывается без запуска


def test_autofit_disabled_flag():
    w = _watcher(autofit=False, min_new=1, min_interval=0)
    w._new_terminal_since_fit = 100
    with mock.patch.object(w, "_run_insight_fit") as m:
        w._maybe_autofit()
    assert m.call_count == 0


def test_autofit_swallows_errors(caplog):
    w = _watcher(autofit=True, min_new=1, min_interval=0)
    w._new_terminal_since_fit = 1
    with mock.patch.object(w, "_run_insight_fit", side_effect=RuntimeError("boom")):
        with caplog.at_level("ERROR"):
            w._maybe_autofit()  # не должен поднять исключение
    assert "autofit" in caplog.text.lower()


def test_autofit_respects_interval():
    w = _watcher(autofit=True, min_new=1, min_interval=3600)
    w._new_terminal_since_fit = 5
    with mock.patch.object(w, "_run_insight_fit") as m:
        w._maybe_autofit()              # первый — проходит
        w._new_terminal_since_fit = 5
        w._maybe_autofit()              # второй — рано (interval не прошёл)
    assert m.call_count == 1


def test_terminal_counter_baseline_then_delta():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE calls (user_id TEXT, status TEXT)")
    conn.executemany(
        "INSERT INTO calls VALUES (?,?)",
        [("me", "done")] * 3 + [("me", "error"), ("other", "done")],
    )
    repo = _Repo(users=[{"user_id": "me"}], conn=conn)
    w = _watcher(repo=repo)

    w._update_terminal_counter()  # baseline: исторические звонки НЕ считаем
    assert w._new_terminal_since_fit == 0

    conn.executemany(
        "INSERT INTO calls VALUES (?,?)",
        [("me", "done"), ("me", "transcribed"), ("other", "done")],
    )
    w._update_terminal_counter()
    assert w._new_terminal_since_fit == 2  # только me, только терминальные (error не в счёт)
