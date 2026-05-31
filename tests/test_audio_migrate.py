# -*- coding: utf-8 -*-
"""test_audio_migrate.py — тесты команды audio-migrate."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pathlib import Path
from unittest.mock import patch, MagicMock
import argparse
import pytest

from callprofiler.cli.commands.bulk import cmd_audio_migrate


def _make_args(tmp_path, user_id="u1", dry_run=False, limit=0):
    args = argparse.Namespace(
        user_id=user_id,
        dry_run=dry_run,
        limit=limit,
        config="configs/base.yaml",
        verbose=False,
    )
    return args


def _make_flat_audio(originals_dir: Path, name: str = "call.mp3") -> Path:
    f = originals_dir / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"audio")
    return f


@pytest.fixture
def setup_migrate(tmp_path):
    """Создать fake config + repo с одним flat звонком."""
    from callprofiler.db.repository import Repository
    db_path = tmp_path / "db" / "test.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    repo = Repository(str(db_path))
    repo.init_db()
    repo.add_user(
        user_id="u1", display_name="Test",
        telegram_chat_id=None,
        incoming_dir=str(tmp_path / "in"),
        sync_dir=str(tmp_path / "sync"),
        ref_audio=str(tmp_path / "ref.wav"),
    )

    # Create flat originals file
    originals = tmp_path / "users" / "u1" / "audio" / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    audio_file = originals / "call_2024-03-15.mp3"
    audio_file.write_bytes(b"audio data")

    contact_id = repo.get_or_create_contact("u1", "+79161234567")
    call_id = repo.create_call(
        user_id="u1",
        contact_id=contact_id,
        direction="IN",
        call_datetime="2024-03-15T10:30:00",
        source_filename="call_2024-03-15.mp3",
        source_md5="abc123",
        audio_path=str(audio_file),
    )
    return repo, call_id, audio_file, tmp_path


def test_audio_migrate_moves_flat_file(setup_migrate):
    repo, call_id, audio_file, tmp_path = setup_migrate
    cfg = MagicMock()
    cfg.log_file = None

    args = _make_args(tmp_path)

    with patch("callprofiler.cli.commands.bulk.load_config_and_repo", return_value=(cfg, repo)), \
         patch("callprofiler.cli.commands.bulk.setup_logging"):
        rc = cmd_audio_migrate(args)

    assert rc == 0

    # Verify DB updated to YYYY/MM path
    conn = repo._get_conn()
    row = conn.execute("SELECT audio_path FROM calls WHERE call_id=?", (call_id,)).fetchone()
    new_path = Path(row["audio_path"])
    assert new_path.exists()
    assert new_path.parent.name == "03"
    assert new_path.parent.parent.name == "2024"


def test_audio_migrate_dry_run_no_changes(setup_migrate, capsys):
    repo, call_id, audio_file, tmp_path = setup_migrate
    original_audio_path = str(audio_file)
    cfg = MagicMock()
    cfg.log_file = None

    args = _make_args(tmp_path, dry_run=True)

    with patch("callprofiler.cli.commands.bulk.load_config_and_repo", return_value=(cfg, repo)), \
         patch("callprofiler.cli.commands.bulk.setup_logging"):
        rc = cmd_audio_migrate(args)

    assert rc == 0
    # DB not changed in dry-run
    conn = repo._get_conn()
    row = conn.execute("SELECT audio_path FROM calls WHERE call_id=?", (call_id,)).fetchone()
    assert row["audio_path"] == original_audio_path


def test_audio_migrate_idempotent(setup_migrate):
    repo, call_id, audio_file, tmp_path = setup_migrate
    cfg = MagicMock()
    cfg.log_file = None

    args = _make_args(tmp_path)

    with patch("callprofiler.cli.commands.bulk.load_config_and_repo", return_value=(cfg, repo)), \
         patch("callprofiler.cli.commands.bulk.setup_logging"):
        rc1 = cmd_audio_migrate(args)

    # Run again — second run should skip already-migrated file
    with patch("callprofiler.cli.commands.bulk.load_config_and_repo", return_value=(cfg, repo)), \
         patch("callprofiler.cli.commands.bulk.setup_logging"):
        rc2 = cmd_audio_migrate(args)

    assert rc1 == 0
    assert rc2 == 0


def test_audio_migrate_skips_already_bucketed(setup_migrate):
    repo, call_id, audio_file, tmp_path = setup_migrate
    cfg = MagicMock()
    cfg.log_file = None

    # Manually set audio_path to already-bucketed path
    bucketed = audio_file.parent / "2024" / "03" / audio_file.name
    bucketed.parent.mkdir(parents=True, exist_ok=True)
    bucketed.write_bytes(b"audio data")
    conn = repo._get_conn()
    conn.execute("UPDATE calls SET audio_path=? WHERE call_id=?", (str(bucketed), call_id))
    conn.commit()

    args = _make_args(tmp_path)

    with patch("callprofiler.cli.commands.bulk.load_config_and_repo", return_value=(cfg, repo)), \
         patch("callprofiler.cli.commands.bulk.setup_logging"):
        rc = cmd_audio_migrate(args)

    assert rc == 0
    # Path unchanged
    row = conn.execute("SELECT audio_path FROM calls WHERE call_id=?", (call_id,)).fetchone()
    assert row["audio_path"] == str(bucketed)


def test_db_indexes_created_on_init():
    """Проверить что _migrate() создаёт indexes для dashboard/poller."""
    from callprofiler.db.repository import Repository
    repo = Repository(":memory:")
    repo.init_db()

    conn = repo._get_conn()
    index_names = {
        row[1]
        for row in conn.execute("SELECT * FROM sqlite_master WHERE type='index'").fetchall()
    }
    assert "idx_calls_user_status" in index_names
    assert "idx_calls_updated_at" in index_names
    assert "idx_calls_user_datetime" in index_names
