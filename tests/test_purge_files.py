# -*- coding: utf-8 -*-
"""T-06: карантин файлов пользователя — dry-run, move в trash, гарды."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from callprofiler.ops.purge_files import purge_user_files, user_file_roots, validate_user_id

NOW = datetime(2026, 8, 22, 12, 30, 45)


def _cfg(tmp_path: Path, text_dir: Path | None = None, sync_dir: Path | None = None):
    return SimpleNamespace(data_dir=str(tmp_path), sync_dir=str(sync_dir) if sync_dir else None,
                           pipeline=SimpleNamespace(text_export_dir=str(text_dir) if text_dir else None))


def _seed(tmp_path: Path) -> Path:
    a = tmp_path / "users" / "a"
    (a / "audio").mkdir(parents=True)
    (a / "audio" / "1.mp3").write_bytes(b"x")
    (a / "note.txt").write_text("n")
    b = tmp_path / "users" / "b"
    b.mkdir(parents=True)
    (b / "keep.txt").write_text("k")
    return a


@pytest.mark.parametrize("bad", ["", "..", "a/b", "a\\b", "../a"])
def test_validate_user_id_rejects_traversal(bad):
    with pytest.raises(ValueError):
        validate_user_id(bad)


def test_roots_only_existing(tmp_path):
    a = _seed(tmp_path)
    text = tmp_path / "text"
    (text / "users" / "a").mkdir(parents=True)
    assert user_file_roots(_cfg(tmp_path, text_dir=text, sync_dir=tmp_path / "sync"), "a") == [a, text / "users" / "a"]
    assert user_file_roots(_cfg(tmp_path), "nobody") == []


def test_dry_run_counts_and_touches_nothing(tmp_path):
    a = _seed(tmp_path)
    assert purge_user_files(_cfg(tmp_path), "a", apply=False) == {str(a): 2}
    assert a.exists() and (tmp_path / "users" / "b" / "keep.txt").exists()
    assert not (tmp_path / "trash").exists()


def test_apply_moves_root_to_trash_other_user_untouched(tmp_path):
    a = _seed(tmp_path)
    counts = purge_user_files(_cfg(tmp_path), "a", apply=True, now=NOW)
    assert counts == {str(a): 2}
    dest = tmp_path / "trash" / "a-20260822123045" / "0-users" / "a"
    assert not a.exists() and (dest / "audio" / "1.mp3").exists() and (dest / "note.txt").exists()
    assert (tmp_path / "users" / "b" / "keep.txt").exists()


def test_two_roots_named_users_do_not_collide(tmp_path):
    a = _seed(tmp_path)
    text = tmp_path / "text"
    (text / "users" / "a").mkdir(parents=True)
    (text / "users" / "a" / "t.txt").write_text("t")
    counts = purge_user_files(_cfg(tmp_path, text_dir=text), "a", apply=True, now=NOW)
    assert counts == {str(a): 2, str(text / "users" / "a"): 1}
    t = tmp_path / "trash" / "a-20260822123045"
    assert (t / "0-users" / "a" / "note.txt").exists() and (t / "1-users" / "a" / "t.txt").exists()


def test_symlink_root_and_symlinked_subdir(tmp_path):
    a = _seed(tmp_path)
    b = tmp_path / "users" / "b"
    try:
        os.symlink(b, a / "link_to_b", target_is_directory=True)
        os.symlink(b, tmp_path / "users" / "c", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink недоступен (Windows без привилегии)")
    # симлинк-папка внутри корня не считается и не следуется
    assert purge_user_files(_cfg(tmp_path), "a", apply=False) == {str(a): 2}
    purge_user_files(_cfg(tmp_path), "a", apply=True, now=NOW)
    assert (b / "keep.txt").exists()  # цель симлинка не тронута
    # корень-симлинк пропускается целиком
    assert purge_user_files(_cfg(tmp_path), "c", apply=True, now=NOW) == {}
    assert (tmp_path / "users" / "c").is_symlink() and (b / "keep.txt").exists()
