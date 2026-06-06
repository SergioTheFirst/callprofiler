# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history preserved in git. Overwrite each session; append-only logs live in CHANGELOG.md.

**Goal (incl. success criteria):**
- Рабочий локальный pipeline `C:\calls\in` → текст (GigaAM v3) → БД → LLM-анализ (Qwen) → дашборд/Telegram.
- Полный путь: pyannote-роли → GigaAM(GPU ASR) → Qwen 9B Q8_0(GPU LLM). Unattended-прогон ~4.6k+ файлов.

**Workflow (durable):**
- Claude **коммитит и пушит в `main` БЕЗ пер-действенного согласования** (2026-06-04).
- **Каждый значимый шаг сперва в файлы памяти** (CONTINUITY/CHANGELOG/.claude/rules/*), **потом** `commit`+`push origin main`.
- **Отвечать кратко, по делу, без воды** (2026-06-05). Не перечитывать код на простой вопрос — брать из `.claude/rules/*` карт (`pipeline.md` → Pipeline Map).

**Constraints/Assumptions:**
- 100% local. Windows. LLM = llama-server @127.0.0.1:8080. SQLite, no ORM, каждый запрос фильтрует `user_id`.
- **Код пишем на ЭТОЙ машине (без GPU/моделей/данных), запускаем на ДРУГОЙ (бокс с GPU).** БД здесь пустая.
- `data_dir = C:\calls\data`. Лог запуска: `C:\calls\callprofiler.log` (был `…Desktop\rez.txt`).
- **GPU sequential (Hard Constraint):** ASR+pyannote и LLM НИКОГДА одновременно в VRAM (12GB RTX 3060).

**State (2026-06-06):**

🧠 **НОВЫЙ workstream (этот ПК, офлайн): Insight Engine — архетипы личности из звонков.**
Дизайн+план готовы: `docs/superpowers/specs/2026-06-06-insight-archetypes-design.md`,
`docs/superpowers/plans/2026-06-06-insight-archetypes-mvp.md`. Скоуп MVP = Фазы 0-1 (метадата-
архетипы, numpy-only, синт-корпус с ground-truth, ARI-гейт). Разработка/тесты офлайн без БД.
Окружение: py3.10.11, numpy 1.26.4, pytest 8.4.2. Исполняю инлайн (executing-plans), ревью-агенты
на чекпойнтах. 11 осей фич / 4 тира устойчивости к ASR — детали в design-doc.

🟢 **Применён присланный улучшенный код (`callprofiler_20260606`) + моя коррекция OOM.** Реальных
изменений 6 src/cfg + `startprocess.bat` (остальные 30+ «изменённых» файлов = только EOL CRLF↔LF,
не трогал; все 22 «изменённых» теста — EOL-only). Тесты: **523 passed, 2 skipped** локально (py3.10).

⚡ **PERF-приёмы (новое, см. `decisions.md` 2026-06-06):**
- **Параллельный ffmpeg** в Фазе 1 `process_batch` — `ThreadPoolExecutor(min(8,n))`, I/O-bound, до ×8.
- **Ко-резидентность GigaAM+pyannote ВНУТРИ Фазы 2** — грузятся раз на батч (не на звонок).
- **Выгрузка `_unload_models()` в `finally` Фазы 2 — ДО Фазы 3 (LLM).** ИСПРАВИЛ присланный код:
  там выгрузка стояла ПОСЛЕ LLM → ASR+pyannote (~5GB) + Qwen Q8_0 (~10GB) > 12GB → OOM. Теперь
  GPU-sequential соблюдён, ко-резидентность сохранена там, где безопасна.

🐛 **Фиксы (root cause — `bugs.md` 2026-06-06):**
- `load_config` не читал `delete_normalized_after_transcribe`/`batch_chunk_size` из YAML → wav копились.
- Дашборд считал несуществующие статусы (`pending`/`processed`) → всегда нули. Теперь реальные статусы.
- `watch` не звал `process_pending` → зависшие (wav готов, не-терминал) не возобновлялись. + сиротские wav.
- `reset.py._overlaps_protected` блокировал родительский `C:\calls` (он содержит in/source) → не чистил.
- `startprocess.bat` теперь поднимает дашборд (kill :8765 → старт в окне → watch), явный `C:\Python312`.

🎯 **Конфиг прогона:** `features.yaml` `enable_llm_analysis:true`, `enable_diarization:true` (роли
обязательны). НЕ менялся этой сессией.

**Next (этот ПК — Insight MVP):**
- Исполнять `…plans/2026-06-06-insight-archetypes-mvp.md` Tasks 2-13 (TDD, per-task commit).
- Гейт: `python -m pytest tests/insight/ -v` зелёный, включая ARI-восстановление заложенных архетипов.
- По завершении MVP — карта `.claude/rules/insight.md` (контракт фич/тиров/ARI) + Фаза 2 (текст-фичи).

**Next (на боксе):**
- `git pull origin main` (забрать этот набор).
- Чистый лист: ОСТАНОВИТЬ watch/dashboard → `reset.bat --apply` → дашборд ноль.
- (1) llama-server с `C:\models\Qwen3.5-9B.Q8_0.gguf`; (2) роли — `install-roles.bat` + `setx HF_TOKEN …`
  + принять gated pyannote-модели + `C:\pro\mbot\ref\manager.wav`; (3) аудио в `C:\calls\in`; (4) `startprocess.bat`.
- Мониторить `C:\calls\callprofiler.log`. Убедиться: НЕТ VRAM OOM (выгрузка до LLM), дашборд real-time,
  normalized wav не копятся (удаление + sweep сирот), зависшие добираются `process_pending` каждый цикл.
- ПОТОМ (Stage-2): graph v2/профили/биография; biography→analysis resilience (мемоизация+retry, task-бюджеты).

**Open questions (UNCONFIRMED):**
- Реальный footprint llama-server Qwen 9B Q8_0 на боксе (если headroom есть — ко-резидентность с LLM
  теоретически возможна, но не делаем без замера; сейчас безопасная выгрузка-до-LLM).
- Дальнейшие perf (`-np 4` batch LLM, skip-LLM коротких, in-memory audio) — за флагом, с замером.

**Working set (files/commands):**
- Эта сессия (закоммичено): `config.py`, `dashboard/tools.py`, `pipeline/{orchestrator,watcher}.py`,
  `reset.py`, `configs/base.yaml`, `startprocess.bat`, тесты `test_{orchestrator_roles,dashboard_tools}.py`,
  память (CHANGELOG/CONTINUITY/.claude/rules/{pipeline,decisions,bugs}.md).
- Tests (бокс): `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
