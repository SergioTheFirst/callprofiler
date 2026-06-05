# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history preserved in git. Overwrite each session; append-only logs live in CHANGELOG.md.

**Goal (incl. success criteria):**
- Рабочий локальный pipeline `C:\calls\in` → текст (GigaAM v3) → БД → LLM-анализ → дашборд/Telegram.
- Текущий фокус: Stage-1 (audio→текст→БД) для unattended-прогона 17k + видимость в дашборде.

**Workflow (durable):**
- Claude **коммитит и пушит в `main` БЕЗ пер-действенного согласования** (2026-06-04).
- **Каждый значимый шаг сперва в файлы памяти** (CONTINUITY/CHANGELOG/.claude/rules/*), **потом** `commit`+`push origin main`.
- **Отвечать кратко, по делу, без воды** (2026-06-05). Не перечитывать код на простой вопрос — брать из `.claude/rules/*` карт (см. `pipeline.md` → Pipeline Map).

**Constraints/Assumptions:**
- 100% local. Windows. LLM = llama-server @127.0.0.1:8080. SQLite, no ORM, каждый запрос фильтрует `user_id`.
- **Код пишем на ЭТОЙ машине (без GPU/моделей/данных), запускаем на ДРУГОЙ (бокс с GPU).** БД здесь пустая.
- `data_dir = C:\calls\data`.

**State (2026-06-05):**

🎯 **АКТИВНЫЙ ПРИОРИТЕТ: Stage-1 audio→БД.** План — `.claude/rules/decisions.md` («Stage-1 … НЕМЕДЛЕННЫЙ
приоритет»). Прогон: `enable_llm_analysis:false` + `enable_diarization:false` = чистый audio→текст→БД,
терминал `transcribed`. Роли/LLM/граф/биография — ПОТОМ.

🟢 **Pipeline: удаление normalized wav** — `delete_normalized_after_transcribe:true` в `base.yaml`
(подтверждено 2026-06-05). wav сносится после stage 2, регенерируется из mp3-архива (`originals/YYYY/MM`),
экономит ~1.9 MB/мин на 17k. Скорость НЕ меняет (ASR на GPU = 95% времени), страхует диск от переполнения.

🟢 **Pipeline Map** добавлена в `.claude/rules/pipeline.md` — watcher cycle + stage/status таблица +
архив/удаление файлов. Источник ответов про конвейер: НЕ перечитывать код. Правила «кратко/память-first/
commit-push main» прописаны в `CLAUDE.md` (Communication + Memory Protocol).

🟢 **Дашборд: переключатель профилей (user_id)** — рабочие данные под юзером `me` (~16645 done); `serhio` битый.

**Prod-данные на боксе:** ~16645 done под `me`, 2349 error, 754 normalizing(stage0); `serhio` битый
(кандидат на `cleanup.bat purge-user`). Legacy-транскрипты speaker=UNKNOWN.

**Next:**
- На боксе Stage-1: `enable_llm_analysis:false`+`enable_diarization:false`, файлы в `C:\calls\in`,
  `startprocess.bat` (watch). Цель: audio → транскрипты в БД + `.txt`, терминал `transcribed`, wav сносится.
- ПОТОМ (Stage-2): llama-server → bulk-enrich над `status='transcribed'`; затем роли (без ре-ASR:
  наложение pyannote-спанов на `transcripts.start_ms/end_ms`), граф v2, профили, биография.
- biography→analysis resilience (`.claude/rules/decisions.md` «Port biography resilience…»): мемоизация+retry,
  task-бюджеты, gated-проходы за флагом+canary.

**Open questions (UNCONFIRMED):**
- Общий `llm_cache` (новый модуль/таблица `llm_calls`) vs переиспользовать `bio_llm_calls`.
- Гейты P-deep: priority≥70 или + длина/structured_facts.

**Working set (files/commands):**
- Эта сессия (коммитится): `.claude/rules/pipeline.md`, `CLAUDE.md`, `CHANGELOG.md`, `CONTINUITY.md`.
- Tests (бокс): `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
