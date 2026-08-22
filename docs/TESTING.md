# Testing (Windows, no venv)

## Setup from zero

```
python -m pip install -e .[dev,full]
```

`torch`/`pyannote.audio`/`faster-whisper`/`soundfile`/`librosa` come from the `full`
extra (pinned to what's verified working — see `requirements-lock.txt` for the exact
dev-machine snapshot); `pyyaml`/`numpy`/etc. are unconditional `dependencies`.
`pytest`/`ruff` come from the `dev` extra. `full` is a separate extra (not part of
`dependencies`) precisely so a cloud/CI runner can skip it — see `.[cloud]` below;
pip extras only ADD packages, they cannot subtract from `dependencies`, so the ML
stack had to live in its own extra rather than the base list.

GPU-box only (ASR/diarization roles) — NOT needed to run the test suite, which
runs fully mocked/offline: see `requirements-gigaam.txt` (needs Python 3.12 for
CUDA wheels). Without `full`, module-level `pytest.importorskip("torch")` skips the
3 files that test the ML runners themselves (`test_pyannote_runner`,
`test_whisper_runner`, `test_pyannote_ref_isolation`) — everything else runs.
Cloud/CI without GPU: `python -m pip install -e .[cloud]` (~40MB, no ML/audio deps).

## Run tests

```
python -m pytest
```

No manual `PYTHONPATH` needed — `[tool.pytest.ini_options]` in `pyproject.toml`
sets `pythonpath = ["src"]` and `testpaths = ["tests"]`.

## Tiers (T-24)

- **PR tier** (всегда): `python -m pytest -q` — офлайн, без GPU/ffmpeg/боевой БД; включает гейты
  `tests/test_tenant_matrix.py` (изоляция арендаторов по read-методам Repository — добавляйте новые
  user-scoped методы в `MATRIX`), `tests/test_cleanup.py::test_purge_user_introspection_classifies_all_tables`
  (каждая таблица имеет правило purge), `tests/test_db_migrations.py` (schema.sql ↔ миграции).
- **Box tier**: тесты с маркером `box` / skip без ffmpeg-GPU — запускаются на боксе по
  `docs/ops/box-canary-checklist.md`.

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
