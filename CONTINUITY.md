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

🧠 **Insight Engine — архетипы личности (этот ПК, офлайн). Фазы 0-1-2-3 СОБРАНЫ.**
Карта: `.claude/rules/insight.md`. **610 passed, 2 skipped** (87 insight, numpy-only, синт ground-truth).
Конвейер: `features-build`→`archetypes-fit`. Единица = `contact`. Фичи: META(метаданные)+TEXT(речь)+
AFFECTIVE(risk/profanity/темы из `analyses`).
**Фаза 2:** текст развёл business/fading (мета k=3/0.71 → +текст k=4/ARI=1.0, noise0.3→0.968).
**Фаза 3:** affective восстановил twin (volatile≡business по мета+тексту, отличим лишь по risk) — при
истинном k=5: text 0.71 → +affective **1.0**. Силуэт-авто-k сливает близнецов → вклад мерим при true-k.
**Уроки про агентов (оба раза ловил независимой проверкой ARI):** (1) Ф2 — агент выдал свою ARI>1 +
дубль kmeans; (2) Ф3 — мерил value через авто-k, где выбор k маскирует вклад фичи. Фичи агента ОБА раза
верны; ломались его ТЕСТЫ. **Пересчитывать ключевую метрику каноникой + при контроле k.**

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

**Next (этот ПК — Insight):**
- Фаза 4: dominance (talk-ratio/turns из ролей, gated по доле UNKNOWN) — последний тир фич.
- ИЛИ Фаза 5-6: именование кластеров (LLM на боксе) + карточки `person-archetype` (польза СЕЙЧАС).
- ИЛИ запуск на боксе на РЕАЛЬНЫХ 16k: `features-build --user me` → `archetypes-fit --user me`.

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
