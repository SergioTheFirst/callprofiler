# -*- coding: utf-8 -*-
"""test_ingester.py — тесты year/month bucketing в Ingester._copy_original."""

import hashlib
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from callprofiler.ingest.ingester import Ingester


@pytest.fixture
def ingester(tmp_path):
    cfg = MagicMock()
    cfg.data_dir = str(tmp_path)
    repo = MagicMock()
    return Ingester(repo=repo, config=cfg), tmp_path


def _make_src(tmp_path: Path, name: str = "call.mp3", content: bytes = b"audio") -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def _md5(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def test_copy_original_with_datetime_creates_year_month(ingester):
    obj, tmp_path = ingester
    src = _make_src(tmp_path)
    dt = datetime(2025, 3, 14)

    dest = obj._copy_original("user1", src, "abc123", call_datetime=dt)

    dest_path = Path(dest)
    assert dest_path.exists()
    # должен содержать YYYY/MM
    assert "2025" in dest_path.parts
    assert "03" in dest_path.parts


def test_copy_original_without_datetime_uses_flat(ingester):
    obj, tmp_path = ingester
    src = _make_src(tmp_path, "call2.mp3")

    dest = obj._copy_original("user1", src, "def456", call_datetime=None)

    dest_path = Path(dest)
    assert dest_path.exists()
    # flat — сразу под originals/
    parts = dest_path.parts
    orig_idx = next(i for i, p in enumerate(parts) if p == "originals")
    assert dest_path.name == parts[orig_idx + 1]  # filename immediately after originals


def test_copy_original_idempotent_same_md5(ingester):
    obj, tmp_path = ingester
    content = b"audio idempotent"
    src = _make_src(tmp_path, "call3.mp3", content)
    dt = datetime(2025, 6, 1)
    md5 = _md5(content)

    dest1 = obj._copy_original("user1", src, md5, call_datetime=dt)
    dest2 = obj._copy_original("user1", src, md5, call_datetime=dt)

    assert dest1 == dest2
    assert Path(dest1).exists()


def test_copy_original_different_md5_renames(ingester):
    obj, tmp_path = ingester
    content1 = b"audio v1"
    src1 = _make_src(tmp_path, "conflict.mp3", content1)
    dt = datetime(2025, 1, 1)

    dest1 = obj._copy_original("user1", src1, _md5(content1), call_datetime=dt)

    # second file — same name, different content
    content2 = b"audio v2 different"
    src2 = tmp_path / "conflict.mp3"
    src2.write_bytes(content2)

    dest2 = obj._copy_original("user1", src2, _md5(content2), call_datetime=dt)

    assert dest1 != dest2
    assert Path(dest1).exists()
    assert Path(dest2).exists()


def test_copy_original_year_month_path_structure(ingester):
    obj, tmp_path = ingester
    content = b"audio structured"
    src = _make_src(tmp_path, "structured.mp3", content)
    dt = datetime(2024, 11, 5)

    dest = obj._copy_original("user1", src, _md5(content), call_datetime=dt)

    dest_path = Path(dest)
    # full expected suffix: originals/2024/11/structured.mp3
    assert dest_path.parent.name == "11"
    assert dest_path.parent.parent.name == "2024"
    assert dest_path.parent.parent.parent.name == "originals"
