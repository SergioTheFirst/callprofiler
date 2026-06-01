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

Done (on `main`, pushed): Steps 1–4 · Фаза 1 (reliability) · Фаза 2 (audio bucketing/indexes) · Фаза 3 (tech-debt + GigaAM ASR abstraction). Suite was 429/429.

Done (Фаза 4 — этой сессии, готово к пушу). 435/435.
- **Feature 1 (persona detail)** — оказалась УЖЕ завершённой в B.1: `db_reader.get_character_profile()` отдаёт metrics+temperament/big_five/motivation+patterns+contradictions+contact+open_promises+recent_calls; `app.js` рендерит все 3 вкладки. Работу не фабриковали.
- **Feature 2 (book export)** — `db_reader.export_book_markdown(user_id)` (prose_full → иначе склейка bio_chapters по chapter_num + рамка книги; placeholder если пусто; user_id-scoped, read-only) + `GET /api/export/book.md` (md-вложение) + кнопка «Export Book (MD)» на вкладке Entities. TDD: 4 real-DB теста + 2 endpoint.
- **Feature 3 (URL-state)** — `app.js`: `syncURL()` (`URLSearchParams`+`replaceState`) на смене вкладки/фильтров; `restoreFromURL()` на загрузке. JS-тестов нет (в проекте нет JS-инфры; соответствует существующей конвенции — app.js не покрыт).

Next:
- `git add -A && git commit && git push origin main` (эта сессия).
- Получить адрес GigaAM сервера → `gigaam_url` + `asr_backend: gigaam` в base.yaml → прогон на тестовом звонке.
- Фаза 5 (качество/тесты): реальный E2E pipeline-тест на мини-фикстуре; починить coverage-тулинг; eval-харнесс LLM-JSON.
- Отложено (ТОЛЬКО по явному запросу, предупреждать): аудиоплеер, Telegram end-to-end.

**Open questions (UNCONFIRMED):**
- HF_TOKEN expandvars — RESOLVED в Фазе 1 (`config.py` зовёт `os.path.expandvars()`).
- `events.event_bus` мёртв (disconnected + cross-process) — `_poller` DB-poll корректен; шина — кандидат на удаление позже.
- Latent: dashboard prod передаёт `_CONFIG.data_dir` в `DashboardDBReader(db_path)` — проверить, что это путь к .db, а не каталог (вне Фазы 4; reads работают в тестах через путь к файлу).

**Working set (files/ids/commands):**
- Phase 4 touched: `dashboard/db_reader.py` (export_book_markdown), `dashboard/server.py` (/api/export/book.md), `dashboard/static/app.js` (syncURL/restoreFromURL + export btn), `dashboard/templates/index.html` (Entities header btn).
- Tests: `tests/test_dashboard_export.py` (new, real-DB), `tests/test_dashboard_server.py::TestExport`.
- Run tests: `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
- Last pushed commit: `5c0cb79` (main). Фаза 4 ещё не закоммичена.
