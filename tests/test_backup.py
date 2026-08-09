# -*- coding: utf-8 -*-
"""T-20: backup/verify-backup/restore — online backup API, verified-before-rotate."""

from __future__ import annotations

import shutil
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from callprofiler.db.repository import Repository
from callprofiler.ops import backup as bk


def _make_db(path: Path, n_calls: int = 3) -> str:
    """Real on-disk schema-accurate db with a few rows (schema.sql, WAL)."""
    repo = Repository(str(path))
    repo.init_db()
    repo.add_user(
        user_id="me",
        display_name="Test",
        telegram_chat_id=None,
        incoming_dir="C:\\calls",
        sync_dir="C:\\sync",
        ref_audio="C:\\ref.wav",
    )
    for i in range(n_calls):
        repo.create_call(
            user_id="me",
            contact_id=None,
            source_md5=f"md5-{i}",
            direction="IN",
            source_filename=f"call{i}.mp3",
            call_datetime=None,
            audio_path=f"audio{i}.wav",
        )
    return str(path)


@pytest.fixture()
def db_path(tmp_path):
    return _make_db(tmp_path / "data" / "db" / "callprofiler.db", n_calls=3)


@pytest.fixture()
def backup_dir(tmp_path):
    d = tmp_path / "backups"
    d.mkdir()
    return str(d)


# ── happy path ──────────────────────────────────────────────────────────

def test_backup_verify_restore_roundtrip(db_path, backup_dir, tmp_path):
    manifest = bk.create_backup(db_path, backup_dir)
    assert manifest.table_counts["calls"] == 3
    backup_file = str(Path(backup_dir) / manifest.filename)

    result = bk.verify_backup(backup_file)
    assert result.ok, result.problems

    restore_to = str(tmp_path / "restored" / "callprofiler.db")
    rresult = bk.restore_backup(backup_file, restore_to)
    assert rresult.ok, rresult.problems

    conn = sqlite3.connect(restore_to)
    try:
        assert conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 3
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_backup_during_concurrent_write(db_path, backup_dir):
    stop = threading.Event()
    errors = []

    def writer():
        conn = sqlite3.connect(db_path)
        try:
            i = 100
            while not stop.is_set():
                conn.execute(
                    "INSERT INTO calls (user_id, source_md5, direction, source_filename, audio_path, status) "
                    "VALUES ('me', ?, 'IN', 'x.mp3', 'x.wav', 'new')",
                    (f"live-{i}",),
                )
                conn.commit()
                i += 1
                time.sleep(0.01)
        except Exception as exc:  # pragma: no cover - surfaced via errors list
            errors.append(exc)
        finally:
            conn.close()

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    try:
        manifest = bk.create_backup(db_path, backup_dir)
    finally:
        stop.set()
        t.join(timeout=5)

    assert not errors
    backup_file = str(Path(backup_dir) / manifest.filename)
    result = bk.verify_backup(backup_file)
    assert result.ok, result.problems


# ── corruption / tamper ─────────────────────────────────────────────────

def test_verify_rejects_truncated_backup(db_path, backup_dir):
    manifest = bk.create_backup(db_path, backup_dir)
    backup_file = Path(backup_dir) / manifest.filename

    # truncate to simulate a partial/corrupt copy
    data = backup_file.read_bytes()
    backup_file.write_bytes(data[: len(data) // 2])

    result = bk.verify_backup(str(backup_file))
    assert not result.ok
    assert result.problems


def test_verify_rejects_tampered_manifest(db_path, backup_dir):
    manifest = bk.create_backup(db_path, backup_dir)
    backup_file = Path(backup_dir) / manifest.filename
    manifest_file = bk._manifest_path(backup_file)

    text = manifest_file.read_text(encoding="utf-8")
    tampered = text.replace(manifest.sha256, "0" * 64)
    manifest_file.write_text(tampered, encoding="utf-8")

    result = bk.verify_backup(str(backup_file))
    assert not result.ok
    assert any("sha256" in p for p in result.problems)


def test_failed_verification_never_rotates_last_good(db_path, backup_dir, monkeypatch):
    good = bk.create_backup(db_path, backup_dir)
    good_file = Path(backup_dir) / good.filename
    good_manifest_file = bk._manifest_path(good_file)
    before = (good_file.read_bytes(), good_manifest_file.read_bytes())

    def broken_inspect(path):
        raise RuntimeError("simulated corruption during verification")

    monkeypatch.setattr(bk, "_inspect", broken_inspect)
    with pytest.raises(Exception):
        bk.create_backup(db_path, backup_dir)

    # last good backup untouched, no stray tmp files left, no new .db published
    after = (good_file.read_bytes(), good_manifest_file.read_bytes())
    assert before == after
    db_files = list(Path(backup_dir).glob("*.db"))
    assert db_files == [good_file]
    assert list(Path(backup_dir).glob(".tmp-*")) == []


# ── preflight ────────────────────────────────────────────────────────────

def test_dest_inside_source_dir_rejected(db_path):
    source_dir = str(Path(db_path).parent)
    with pytest.raises(ValueError):
        bk.create_backup(db_path, source_dir)


def test_insufficient_free_space_rejected(db_path, backup_dir, monkeypatch):
    class _Usage:
        free = 1  # far below any real db size + margin

    monkeypatch.setattr(bk.shutil, "disk_usage", lambda _p: _Usage())

    with pytest.raises(OSError):
        bk.create_backup(db_path, backup_dir)

    assert list(Path(backup_dir).glob("*.db")) == []


# ── restore safety ──────────────────────────────────────────────────────

def test_restore_refuses_overwrite_without_flag(db_path, backup_dir, tmp_path):
    manifest = bk.create_backup(db_path, backup_dir)
    backup_file = str(Path(backup_dir) / manifest.filename)

    existing = tmp_path / "live.db"
    existing.write_bytes(b"not empty")

    result = bk.restore_backup(backup_file, str(existing), overwrite=False)
    assert not result.ok
    assert existing.read_bytes() == b"not empty"


def test_restore_overwrite_snapshots_current_state_first(db_path, backup_dir, tmp_path):
    manifest = bk.create_backup(db_path, backup_dir)
    backup_file = str(Path(backup_dir) / manifest.filename)

    live = tmp_path / "live" / "callprofiler.db"
    _make_db(live, n_calls=1)

    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()

    result = bk.restore_backup(
        backup_file, str(live), overwrite=True, snapshot_dir_on_overwrite=str(snap_dir)
    )
    assert result.ok, result.problems
    # a pre-restore snapshot of the (1-call) live db was taken before overwrite
    manifests = bk._load_manifests(str(snap_dir))
    assert any(m.kind == "pre-restore" and m.table_counts["calls"] == 1 for m in manifests)

    conn = sqlite3.connect(str(live))
    try:
        assert conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 3
    finally:
        conn.close()


# ── retention ────────────────────────────────────────────────────────────

def test_retention_evicts_oldest_beyond_n_keeps_stray_file(db_path, backup_dir):
    stray = Path(backup_dir) / "unrelated_notes.txt"
    stray.write_text("do not touch")

    filenames = []
    for _ in range(4):
        m = bk.create_backup(db_path, backup_dir, retention_daily=3, retention_weekly=0)
        filenames.append(m.filename)
        time.sleep(0.01)  # keep created_at strictly increasing

    remaining_db = {p.name for p in Path(backup_dir).glob("*.db")}
    assert len(remaining_db) == 3
    assert filenames[0] not in remaining_db  # oldest evicted
    assert filenames[-1] in remaining_db  # newest kept
    assert stray.exists()  # unmanifested file never touched
