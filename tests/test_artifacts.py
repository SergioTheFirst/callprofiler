# -*- coding: utf-8 -*-
"""test_artifacts.py — atomic publication helpers (T-08)."""
import hashlib
import os

import pytest

from callprofiler.artifacts import atomic_copy_file, atomic_write_bytes, atomic_write_text


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def test_atomic_write_text_roundtrip(tmp_path):
    dest = tmp_path / "out.txt"
    p = atomic_write_text(dest, "привет\n")
    assert p == dest
    assert dest.read_text(encoding="utf-8") == "привет\n"
    # no orphan tmp files left
    assert list(tmp_path.iterdir()) == [dest]


def test_atomic_write_text_idempotent_rerun(tmp_path):
    dest = tmp_path / "out.txt"
    atomic_write_text(dest, "v1")
    atomic_write_text(dest, "v2")
    assert dest.read_text(encoding="utf-8") == "v2"
    assert list(tmp_path.iterdir()) == [dest]


def test_atomic_write_creates_parent_dirs(tmp_path):
    dest = tmp_path / "a" / "b" / "out.txt"
    atomic_write_text(dest, "x")
    assert dest.read_text(encoding="utf-8") == "x"


def test_atomic_copy_file_hash_and_size_match(tmp_path):
    src = tmp_path / "src.bin"
    data = os.urandom(1024 * 1024 + 17)  # >1 buffer chunk, uneven tail
    src.write_bytes(data)
    dest = tmp_path / "dest.bin"

    out_path, digest = atomic_copy_file(src, dest)

    assert digest == _md5(data)
    assert out_path.read_bytes() == data
    assert out_path.stat().st_size == src.stat().st_size


def test_atomic_copy_file_verifies_expected_hash(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"hello world")
    dest = tmp_path / "dest.bin"

    atomic_copy_file(src, dest, expected_hash=_md5(b"hello world"))
    assert dest.read_bytes() == b"hello world"


def test_atomic_copy_file_hash_mismatch_leaves_no_dest_or_orphan(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"hello world")
    dest = tmp_path / "dest.bin"

    with pytest.raises(ValueError):
        atomic_copy_file(src, dest, expected_hash="0" * 32)

    assert not dest.exists()
    assert list(tmp_path.iterdir()) == [src]


def test_atomic_copy_file_interrupted_leaves_no_partial_or_orphan(tmp_path, monkeypatch):
    src = tmp_path / "src.bin"
    src.write_bytes(os.urandom(4096))
    dest = tmp_path / "dest.bin"

    real_fsync = os.fsync

    def boom(fd):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):
        atomic_copy_file(src, dest)
    monkeypatch.setattr(os, "fsync", real_fsync)

    assert not dest.exists()
    assert list(tmp_path.iterdir()) == [src]


def test_atomic_copy_file_idempotent_rerun(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dest = tmp_path / "dest.bin"

    atomic_copy_file(src, dest)
    atomic_copy_file(src, dest)

    assert dest.read_bytes() == b"payload"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dest.bin", "src.bin"]


def test_atomic_write_unicode_and_long_filename(tmp_path):
    name = "звонок_" + ("длинное_имя_" * 8) + ".txt"
    dest = tmp_path / name
    atomic_write_text(dest, "проверка")
    assert dest.read_text(encoding="utf-8") == "проверка"


def test_atomic_write_bytes_orphan_removed_on_write_failure(tmp_path, monkeypatch):
    dest = tmp_path / "out.bin"

    def boom_fsync(fd):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", boom_fsync)
    with pytest.raises(OSError):
        atomic_write_bytes(dest, b"data")

    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []
