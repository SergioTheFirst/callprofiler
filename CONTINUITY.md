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

🎯 **ПОЛНЫЙ ПАЙПЛАЙН (2026-06-05, запрос юзера):** pyannote-роли → GigaAM(GPU ASR) → Qwen 9B Q8_0(GPU LLM).
`features.yaml`: `enable_llm_analysis:true`, `enable_diarization:true` (роли [me]/[s2] обязательны).
`gigaam_runner` падает, если `gigaam_device=cuda` а CUDA нет (GPU обязателен). На боксе перед watch:
(а) llama-server с `C:\models\Qwen3.5-9B.Q8_0.gguf`; (б) для ролей — pyannote+HF_TOKEN+принятые
gated-модели+`C:\pro\mbot\ref\manager.wav` (иначе роли graceful UNKNOWN + `_warn_once` в лог).

🧹 **ЧИСТЫЙ ЛИСТ («новый комп») = `reset.bat --apply`, НЕ `cleanup keep-only`.** keep-only ОСТАВЛЯЕТ
данные `me`; reset сносит всю `data` (БД+originals+wav) → пустая БД + `me` (ref_audio дефолтом) →
ноль во всех профилях → startprocess реобрабатывает `C:\calls\in` с нуля. Останови watch/dashboard
перед reset. Фантомные «Файл не найден …originals…» = старые записи me после keep-only.

🟢 **Pipeline: удаление normalized wav** — `delete_normalized_after_transcribe:true` в `base.yaml`
(подтверждено 2026-06-05). wav сносится после stage 2, регенерируется из mp3-архива (`originals/YYYY/MM`),
экономит ~1.9 MB/мин на 17k. Скорость НЕ меняет (ASR на GPU = 95% времени), страхует диск от переполнения.

🟢 **Pipeline Map** добавлена в `.claude/rules/pipeline.md` — watcher cycle + stage/status таблица +
архив/удаление файлов. Источник ответов про конвейер: НЕ перечитывать код. Правила «кратко/память-first/
commit-push main» прописаны в `CLAUDE.md` (Communication + Memory Protocol).

🟢 **reset.py = чистый лист** (2026-06-05). Сносит ВСЁ кроме `C:\calls\in` (вход) и `C:\calls\source`
(мастер): вся `data` (БД+профили+logs+biography)+`text`+`sync` → bootstrap (me, incoming=in) →
`startprocess.bat` прогоняет in с нуля. Бэкап БД ВНЕ data. dry-run по умолч., `--apply` сносит.
WHY/священно-vs-расходник — `.claude/rules/decisions.md`.

🟢 **Дашборд: переключатель профилей (user_id)** — рабочие данные под юзером `me` (~16645 done); `serhio` битый.

🟢 **keep-only: один профиль `me`** (2026-06-05). `cleanup.bat keep-only --user me [--apply]` сносит
ВСЕХ юзеров кроме keeper (инверсия purge-user, dry-run по умолч., guard «keeper обязан быть»).
`purge_user` теперь чистит и `bio_*` (junction по scene_id, FK-safe). Legacy `serhio` = старый owner-id
того же человека → под снос. «Все работы в одном профиле» (решение юзера 2026-06-05).

**Prod-данные на боксе:** ~16645 done под `me`, 2349 error, 754 normalizing(stage0); `serhio` битый
(под снос: `cleanup.bat keep-only --user me --apply`). Legacy-транскрипты speaker=UNKNOWN.

**Next:**
- На боксе консолидировать профиль: `cleanup.bat keep-only --user me` (dry-run → проверить план) →
  `--apply` (снести `serhio` и прочих, оставить `me`). Затем дашборд/обработка — один профиль.
- На боксе чистый прогон: (0) ОСТАНОВИТЬ watch/dashboard → `reset.bat --apply` (чистый лист) →
  убедиться: дашборд ноль; (1) поднять llama-server (Qwen 9B Q8_0); (2) для ролей — install-roles.bat
  + `setx HF_TOKEN …` + принять gated pyannote-модели + проверить `C:\pro\mbot\ref\manager.wav`;
  (3) аудио в `C:\calls\in`; (4) `startprocess.bat`. Путь: pyannote-роли → GigaAM(GPU) → текст в БД+`.txt`
  → Qwen LLM-анализ → `done`. wav сносится сразу (+ sweep). Дашборд real-time все вкладки.
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
