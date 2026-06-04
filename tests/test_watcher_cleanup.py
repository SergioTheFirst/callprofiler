# -*- coding: utf-8 -*-
"""test_watcher_cleanup.py — очистка incoming + безопасная дедупликация."""
from callprofiler.config import Config, PipelineConfig
from callprofiler.pipeline.watcher import FileWatcher


class _Repo:
    """Фейк репозитория: get_call по id + get_call_by_md5 по хешу."""

    def __init__(self, calls=None, by_md5=None):
        self._calls = calls or {}
        self._by_md5 = by_md5 or {}
        self.reset_called = []

    def get_all_users(self):
        return []

    def get_call(self, user_id, call_id):
        return self._calls.get(call_id)

    def get_call_by_md5(self, user_id, md5):
        return self._by_md5.get(md5)

    def reset_call(self, call_id):
        self.reset_called.append(call_id)


class _Ingester:
    def __init__(self, ret=100):
        self.calls = []
        self._ret = ret

    def ingest_file(self, user_id, path):
        self.calls.append(path)
        return self._ret


def _watcher(cfg, repo, ingester=None):
    return FileWatcher(cfg, repo, ingester, orchestrator=None)


# ── cleanup_sources ─────────────────────────────────────────────────────

def test_cleanup_removes_transcribed_keeps_pending(tmp_path):
    cfg = Config()  # remove_source_on_success=True по умолчанию
    f1 = tmp_path / "a.mp3"
    f1.write_bytes(b"x")
    f2 = tmp_path / "b.mp3"
    f2.write_bytes(b"x")
    repo = _Repo(calls={1: {"pipeline_stage": 2}, 2: {"pipeline_stage": 0}})
    w = _watcher(cfg, repo)
    w._last_sources = {1: ("me", tmp_path, f1), 2: ("me", tmp_path, f2)}

    assert w.cleanup_sources() == 1
    assert not f1.exists()
    assert f2.exists()


def test_cleanup_respects_flag(tmp_path):
    cfg = Config()
    cfg.pipeline = PipelineConfig(remove_source_on_success=False)
    f1 = tmp_path / "a.mp3"
    f1.write_bytes(b"x")
    repo = _Repo(calls={1: {"pipeline_stage": 2}})
    w = _watcher(cfg, repo)
    w._last_sources = {1: ("me", tmp_path, f1)}

    assert w.cleanup_sources() == 0
    assert f1.exists()


def test_cleanup_never_deletes_incoming_root_prunes_subdir(tmp_path):
    cfg = Config()
    root = tmp_path / "in"
    sub = root / "2026-06"
    sub.mkdir(parents=True)
    f_root = root / "top.mp3"
    f_root.write_bytes(b"x")
    f_sub = sub / "deep.mp3"
    f_sub.write_bytes(b"x")
    repo = _Repo(calls={1: {"pipeline_stage": 2}, 2: {"pipeline_stage": 2}})
    w = _watcher(cfg, repo)
    w._last_sources = {1: ("me", root, f_root), 2: ("me", root, f_sub)}

    assert w.cleanup_sources() == 2
    assert root.exists()
    assert not f_root.exists()
    assert not sub.exists()


# ── _scan_user_dir: безопасная дедупликация (B5/B4) ─────────────────────

def _scan_cfg():
    cfg = Config()
    cfg.pipeline = PipelineConfig(file_settle_sec=0)  # файл сразу «устоялся»
    return cfg


def test_scan_ingests_new_file(tmp_path):
    root = tmp_path / "in"
    root.mkdir()
    f = root / "x.mp3"
    f.write_bytes(b"audio")
    repo = _Repo(by_md5={})  # нет существующего → новый
    ing = _Ingester(ret=100)
    w = _watcher(_scan_cfg(), repo, ing)

    ids = w._scan_user_dir("me", root)

    assert ids == [100]
    assert ing.calls == [str(f)]
    assert f.exists()                 # исходник остаётся до транскрибации
    assert 100 in w._last_sources


def test_scan_removes_transcribed_duplicate(tmp_path):
    root = tmp_path / "in"
    root.mkdir()
    f = root / "x.mp3"
    f.write_bytes(b"audio")
    md5 = FileWatcher._file_md5(f)
    repo = _Repo(by_md5={md5: {"pipeline_stage": 2}})
    ing = _Ingester()
    w = _watcher(_scan_cfg(), repo, ing)

    ids = w._scan_user_dir("me", root)

    assert ids == []
    assert ing.calls == []            # дубликат не инжестим повторно
    assert not f.exists()             # транскрибированный дубль убран


def test_scan_keeps_untranscribed_duplicate_when_archive_present(tmp_path):
    """Звонок есть, не транскрибирован, архив НА МЕСТЕ → не реингестим, файл цел."""
    root = tmp_path / "in"
    root.mkdir()
    f = root / "x.mp3"
    f.write_bytes(b"audio")
    md5 = FileWatcher._file_md5(f)
    archive = tmp_path / "arch" / "x.mp3"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"audio")  # архив существует
    repo = _Repo(by_md5={md5: {"call_id": 7, "pipeline_stage": 0, "audio_path": str(archive)}})
    ing = _Ingester()
    w = _watcher(_scan_cfg(), repo, ing)

    ids = w._scan_user_dir("me", root)

    assert ids == []
    assert ing.calls == []
    assert repo.reset_called == []    # не сбрасывали
    assert f.exists()


def test_scan_heals_missing_archive(tmp_path):
    """Звонок есть, архив ПОТЕРЯН → восстановить из incoming + сброс на переобработку."""
    root = tmp_path / "in"
    root.mkdir()
    f = root / "x.mp3"
    f.write_bytes(b"audio-bytes")
    md5 = FileWatcher._file_md5(f)
    archive = tmp_path / "arch" / "2021" / "03" / "x.mp3"  # НЕ создан → потерян
    repo = _Repo(by_md5={md5: {"call_id": 55, "pipeline_stage": 0, "audio_path": str(archive)}})
    ing = _Ingester()
    w = _watcher(_scan_cfg(), repo, ing)

    ids = w._scan_user_dir("me", root)

    assert ids == [55]                       # поставлен на переобработку
    assert archive.exists()                  # архив восстановлен из incoming
    assert archive.read_bytes() == b"audio-bytes"
    assert repo.reset_called == [55]         # звонок сброшен
    assert ing.calls == []                   # не реингестим — переиспользуем call_id
    assert 55 in w._last_sources
