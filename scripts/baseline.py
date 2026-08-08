"""T-00: machine-readable baseline report. No GPU/DB/models required.

Usage: python scripts/baseline.py [--out docs/baseline-report.json]
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TRACKED_PACKAGES = [
    "torch",
    "numpy",
    "pyyaml",
    "requests",
    "fastapi",
    "uvicorn",
    "jinja2",
    "python-telegram-bot",
    "psutil",
    "faster-whisper",
    "pyannote.audio",
    "soundfile",
    "librosa",
    "pytest",
    "ruff",
]


def package_versions() -> dict:
    out = {}
    for name in TRACKED_PACKAGES:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = None
    return out


def run_pytest() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    m = re.search(
        r"(?:(\d+) failed, )?(?:(\d+) passed)?(?:, (\d+) skipped)?", tail
    )
    passed = int(m.group(2)) if m and m.group(2) else 0
    failed = int(m.group(1)) if m and m.group(1) else 0
    skipped = int(m.group(3)) if m and m.group(3) else 0
    return {
        "exit_code": proc.returncode,
        "summary_line": tail,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }


def run_ruff() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--output-format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        issues = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        issues = None
    return {
        "exit_code": proc.returncode,
        "issue_count": len(issues) if issues is not None else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="write JSON report to this path too")
    args = ap.parse_args()

    report = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "packages": package_versions(),
        "pytest": run_pytest(),
        "ruff": run_ruff(),
    }

    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
