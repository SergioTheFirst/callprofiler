# Testing (Windows, no venv)

## Setup from zero

```
python -m pip install -e .[dev]
```

`torch`/`pyyaml`/`numpy`/etc. install from `pyproject.toml` lower bounds (pinned
to what's verified working — see `requirements-lock.txt` for the exact dev-machine
snapshot). `pytest`/`ruff` come from the `dev` extra.

GPU-box only (ASR/diarization roles) — NOT needed to run the test suite, which
runs fully mocked/offline: see `requirements-gigaam.txt` (needs Python 3.12 for
CUDA wheels).

## Run tests

```
python -m pytest
```

No manual `PYTHONPATH` needed — `[tool.pytest.ini_options]` in `pyproject.toml`
sets `pythonpath = ["src"]` and `testpaths = ["tests"]`.

## Lint

```
python -m ruff check .
```

Known-fail ledger: baseline is 163 findings (not fixed by T-00 — out of scope,
see `docs/baseline-report.json`).

## Machine-readable baseline

```
python scripts/baseline.py --out docs/baseline-report.json
```

Prints/saves Python+OS+package versions, pytest pass/fail/skip counts + exit
code, ruff issue count + exit code. Needs no GPU/DB/models.
