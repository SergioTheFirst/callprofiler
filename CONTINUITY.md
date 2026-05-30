# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history (2253 lines of session logs) preserved in git @ commit `702ec13` and earlier.
> Read this at the start of every turn; update when goal/constraints/decisions/state change.

**Goal (incl. success criteria):**
- Drive CallProfiler (local Windows call-analysis system) to a stable, production-like single-machine state via the post-audit strategy.
- Success: pipeline robust + unattended-safe; docs reflect code; dashboard usable as admin; personas coherent; exports work; tests green.

**Constraints/Assumptions:**
- 100% local. Windows + system Python. LLM = llama-server (NOT Ollama) @ 127.0.0.1:8080. SQLite only (no ORM). Every query filters `user_id`. Never swallow errors. GPU sequential: Whisper+pyannote (~4.5GB) then unload before LLM (~10GB).
- `data_dir = C:\calls\data` (`configs/base.yaml`). Direct push to `main` (no feature branches). No attribution footer in commits.
- Source of truth = code + configs + `ARCHITECTURE_v5.md`; `CONSTITUTION.md` = principles.
- This shell: ffmpeg NOT in PATH; `pytest-asyncio` installed ad-hoc.

**Key decisions:**
- Code is source of truth; `ARCHITECTURE_v5` supersedes v4 (`702ec13`).
- Diarization failure → speakers UNKNOWN + pipeline continues; pyannote always unloaded.
- `normalizer` ffmpeg check is call-time, not import-time.
- Strategy order: A (truth + last-mile) → B.1 persona facade → D.2 pipeline resume.
- `.codegraph/` is gitignored (local index).

**State:**

Done:
- Step 1 — docs reconciliation v5 (pushed `702ec13`).
- Step 2 (A.1) — diarization graceful degradation + normalizer call-time ffmpeg check (pushed `702ec13`).
- Step 3 (A.3) dashboard last-mile — change-driven SSE (`_poller` via `get_latest_timestamp`), reprocess config-bug fix (Retry-failed now works), CSV export endpoint + `export_calls()` + frontend wire; 417/417; code-review addressed.

Now:
- Commit/push Step 3 → then Step 4 (B.1) persona read-facade: one "character" read-model over graph entities + `bio_portraits` + `psychology_profiler` + `contact_summaries`.

Next:
- Deferred: P0-019 BUDGETS migration; year/month audio storage (B.4); pipeline crash-resume (D.2); reconcile CONSTITUTION Ст.19 wording to ledger format.

**Open questions (UNCONFIRMED):**
- None blocking. Resolved: `DashboardTools.run_*` ARE real logic (`_reprocess_sync` had a config bug, now fixed). `events.event_bus` is disconnected from the SSE endpoint AND cross-process — so DB-poll change-detection (implemented in `_poller`) is the correct event source; the in-memory bus stays unused/dead (candidate for later removal).

**Working set (files/ids/commands):**
- Step 4 (persona facade) likely files: `dashboard/db_reader.py` (`get_character_profile`/`get_entity_profile` already exist — consolidate into one Persona read-model), `biography/psychology_profiler.py`, `graph/repository.py`, `aggregate/summary_builder.py`.
- Tests: `tests/test_dashboard_server.py`, `test_dashboard_tools.py`, `test_psychology_profiler.py`.
- Run tests: `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
- Last commit: `702ec13` (main); Step 3 commit pending.
