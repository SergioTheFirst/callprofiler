# -*- coding: utf-8 -*-
"""test_bootstrap_no_torch.py — T-01: `--help`/`doctor` must not import torch.

Real proof requires a subprocess: a stub ``torch`` module that raises on
import is put first on PYTHONPATH. If callprofiler package import (or
--help/doctor) transitively imports torch, this stub blows up with a
traceback; if it doesn't, the command runs normally.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SRC = REPO_ROOT / "src"


def _run_without_torch(args: list[str], tmp_path: Path) -> subprocess.CompletedProcess:
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    (stub_dir / "torch.py").write_text(
        "raise ImportError('torch intentionally unavailable for this test')\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(stub_dir), str(SRC)])
    env["PYTHONIOENCODING"] = "utf-8"  # help text has non-ASCII (→), avoid cp1251 crash
    return subprocess.run(
        [sys.executable, "-m", "callprofiler", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_help_works_without_torch(tmp_path):
    result = _run_without_torch(["--help"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert "torch intentionally unavailable" not in result.stderr


def test_doctor_works_without_torch(tmp_path):
    result = _run_without_torch(["doctor"], tmp_path)
    # doctor.py's own deps-gpu check catches ImportError explicitly (WARN) —
    # any *unhandled* exception involving the stub torch module is the bug
    # this test guards against (package-level import used to crash here).
    assert "Traceback" not in result.stderr, result.stderr
    assert "torch intentionally unavailable" not in result.stderr
    # doctor prints a report table regardless of exit code (FAIL/OK checks)
    assert "python" in result.stdout.lower()
