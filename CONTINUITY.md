# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history (2253 lines of session logs) preserved in git @ commit `702ec13` and earlier.
> Read this at the start of every turn; update when goal/constraints/decisions/state change.

**Goal (incl. success criteria):**
- Приоритет пользователя (2026-06-03): рабочий авто-pipeline `C:\calls\in` → текст (GigaAM v3 локально) → БД → LLM, с видимостью стадий в UI почти в реальном времени. Stage-1 (audio→текст в БД) — критично и срочно.
- Success: watcher берёт файлы из incoming, GigaAM транскрибирует, транскрипт в БД + `.txt`, LLM-анализ пишет analyses/events; стадии видны в dashboard.

**Constraints/Assumptions:**
- 100% local. Windows + system Python 3.10. LLM = llama-server @127.0.0.1:8080. SQLite, no ORM. Каждый запрос фильтрует `user_id`. Never swallow errors. GPU sequential: ASR (GigaAM) выгружается перед LLM.
- **Обработка идёт на ДРУГОЙ машине** (с transformers/torchaudio/ffmpeg/GPU). Моя задача — код; пользователь запускает на рабочей машине. В ЭТОЙ среде стоит только torch+numpy (нет transformers/torchaudio/pyannote/faster_whisper/ffmpeg) → реальный GigaAM-прогон здесь невозможен.
- `data_dir = C:\calls\data`. Direct push to `main`. No attribution footer.
- ASR: **flat text, без pyannote** (выбор пользователя). Роли (`[me]/[s2]`) — следующий шаг.

**Key decisions:**
- GigaAM = **локальная in-process** модель (`C:\models\GigaAM-v3-rnnt`), НЕ HTTP. `GigaAMRunner` переписан: своя нарезка окнами <25с, без `transcribe_longform`/pyannote (он gated). См. `.claude/rules/decisions.md`.
- Папки: **per-user дерево** (выбор пользователя). Один юзер `me`, `incoming_dir=C:\calls\in`. Архив = `users/{uid}/audio/originals/YYYY/MM` (ingester копирует). Исходник из `in` убирается watcher'ом после транскрибации.
- `.txt` транскрипт (явное требование) → `C:\calls\text\<имя_исходника>.txt`.
- Realtime UI = существующий dashboard (SSE+DB-poll) + per-stage `update_call_status`; живой лог — консоль `watch -v`.

**State:**

Сделано (НЕ закоммичено, этой сессии):
- `transcribe/gigaam_runner.py` переписан (HTTP-stub → local in-process, chunking, GPU load/unload, lazy imports).
- `transcribe/text_export.py` NEW + `orchestrator._export_text` (после save_transcripts, оба пути).
- `pipeline/watcher.py` — трекинг call_id→source + `cleanup_sources()` (убирает из incoming после stage≥2; gate `remove_source_on_success`; чистит дубликаты и пустые подпапки).
- `config.py`+`base.yaml`: `gigaam_model_dir/device/chunk_sec/overlap_sec`, `text_export_dir`, `remove_source_on_success`, `asr_backend: gigaam`. `features.yaml`: `enable_diarization:false`.
- `cli` команда `bootstrap` (папки+БД+юзер `me`).
- `requirements-gigaam.txt`, `RUN_STAGE1.md`.
- Tests: `test_gigaam_runner.py`/`test_text_export.py`/`test_watcher_cleanup.py` — 11/11 зелёные локально. py_compile всех правок OK; CLI-парсер `bootstrap` парсится; pure-модули импортируются.

Прогон на боксе (2026-06-03, ветка-клон, отчёт `rez.txt`): Stage-1 РАБОТАЕТ end-to-end
(process call_id=17623 → 4 сегмента → .txt + карточка, exit 0; watch инжестит/дедупит
2127 mp3). НО на CPU: бокс на Python 3.14 → нет CUDA-колёс PyTorch (torch 2.12+cpu),
GPU простаивает. Найдено 7 проблем (B1-B7) — все обработаны (B2-B7 код, B1 env).

Исправлено этой сессией (НЕ закоммичено): B2 (lazy pyannote), B3 (pipeline_stage в
process_call), B4/B5 (watcher MD5-first + `repo.get_call_by_md5`, не теряем исходники),
B6 (`Config.prompts_dir` от корня проекта; service.py/enricher.py), B7 (dashboard
`_build_app` + db_reader резолвит `data_dir/db/callprofiler.db`). Тесты 15/15.

Next:
- **GPU:** на боксе поставить Python 3.12 + `torch==2.6.0+cu124` + `torchaudio==2.6.0` +
  `transformers<5` (см. `requirements-gigaam.txt`). Тогда GigaAM на GPU и патчи A/B не нужны.
- Перепрогнать: `bootstrap` → `process … -v` → `watch -v` (+ `dashboard --user me` — теперь чинится).
- Полный pytest на боксе: `python -m pytest tests/ -q`.
- `git add -A && commit && push origin main` (после согласования).
- Затем: роли (pyannote VAD + диаризация) при HF_TOKEN.

**Open questions (UNCONFIRMED):**
- Совпадение версии `torchaudio` с `torch 2.6.0+cu124` на рабочей машине (ставить с cu124 index).
- `from_pretrained` weights_only на torch 2.6 — добавлен защитный патч в `GigaAMRunner.load()`; проверить на реальной загрузке.
- Качество нарезки окнами на стыках (раз в ~20с возможен разрез слова) — оценить на реальных звонках, при необходимости включить overlap или VAD.

**Working set (files/ids/commands):**
- Touched: `transcribe/{gigaam_runner,text_export}.py`, `pipeline/{orchestrator,watcher}.py`, `config.py`, `configs/{base,features}.yaml`, `cli/commands/admin.py`, `cli/main.py`, tests×3, `requirements-gigaam.txt`, `RUN_STAGE1.md`.
- Run tests (рабочая машина): `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
- Last pushed commit: `67d950f` (main). Эта сессия + Фаза 4 ещё не закоммичены.
