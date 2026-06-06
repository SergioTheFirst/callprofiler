# Bugs & Ideas

## Known Bugs (Active)

### 🔴 High Priority

None currently identified.

### 🟡 Medium Priority

1. **FTS5 index not used in /search — FIXED** (2026-04-17)
   - **Issue:** `search_transcripts()` used `LIKE` O(n) scan; FTS5 table existed but was never queried
   - **Fix:** Replaced with FTS5 MATCH subquery + BM25 ranking + LIMIT 50
   - **Status:** RESOLVED (2026-04-17)

2. **.bat file encoding** (2026-04-14)
   - **Issue:** new-session.bat, save-session.bat might have BOM on Windows
   - **Fixed:** Converted to ASCII encoding (no UTF-8 BOM)
   - **Status:** RESOLVED - removed BOM from all .bat files

3. **Telegram bot long-polling stability** (2026-04-11)
   - **Issue:** If bot process dies, notifications are lost (no message queue)
   - **Impact:** User misses real-time summaries during call processing
   - **Solution:** Implement in-memory buffer with crash recovery
   - **Status:** BACKLOG (Phase 6 optimization)

### 🟢 Low Priority / Ideas

1. **Contact card text truncation** (2026-04-11)
   - **Observation:** Card text limited to 512 bytes - some info may be cut
   - **Idea:** Implement card versioning (short vs. full) based on user preference
   - **Status:** IDEA - gather user feedback first

2. **Risk emoji scale clarity** (2026-04-14)
   - **Observation:** 🟢<30, 🟡 30-70, 🔴>70 thresholds are arbitrary
   - **Idea:** Calculate thresholds from historical data (percentiles across all contacts)
   - **Status:** IDEA - needs data collection first

3. **Promises deadline warnings** (2026-04-11)
   - **Idea:** /promises command should highlight overdue promises (deadline < today)
   - **Implementation:** Add formatting (emoji/bold) for overdue items
   - **Status:** BACKLOG - easy, low priority

4. **Contact relationship graph** (2026-04-14)
   - **Idea:** /contact command could show "mentioned Vasya in 3 calls" (person->person links)
   - **Requires:** NER (Named Entity Recognition) in LLM analysis
   - **Status:** FUTURE (Phase 8 analytics)

5. **Multi-language support for commands** (2026-04-14)
   - **Observation:** Telegram commands are hardcoded (/start, /digest, etc)
   - **Idea:** Allow Russian aliases (/дайджест, /поиск) for user convenience
   - **Status:** IDEA - low value, high complexity

6. **Call recording integration** (2026-04-09)
   - **Observation:** Currently system waits for user to copy audio files to incoming_dir
   - **Idea:** Direct integration with Android recorder (auto-upload when call ends)
   - **Requires:** Mobile app + backend API
   - **Status:** FUTURE (Phase 7 scale)

7. **CRM integration** (2026-04-14)
   - **Idea:** Sync contact names from Salesforce/HubSpot, not just from call filenames
   - **Benefits:** Better name accuracy, company context, deal tracking
   - **Status:** FUTURE (Phase 9 integration)

8. **LLM fine-tuning** (2026-04-14)
   - **Idea:** Fine-tune Ollama model on user's past calls for better extraction
   - **Benefits:** Better context understanding, personalized risk scoring
   - **Requires:** 50+ calls minimum for fine-tuning
   - **Status:** FUTURE (Phase 10 intelligence)

---

## Bug Report Template

```markdown
### Title
- **Issue:** Clear description
- **Impact:** Who/what is affected
- **Reproduction:** Steps to reproduce
- **Expected:** What should happen
- **Actual:** What happens instead
- **Solution:** Proposed fix (if known)
- **Status:** ACTIVE / RESOLVED / BACKLOG / IDEA
- **Date Found:** YYYY-MM-DD
- **Priority:** 🔴 High / 🟡 Medium / 🟢 Low
```

---

## Recent Fixes (Closed)

✅ **WAV копились: `load_config` не читал 2 поля из YAML** (2026-06-06)
- **Root cause (non-obvious):** `delete_normalized_after_transcribe` и `batch_chunk_size` объявлены
  в датаклассе `PipelineConfig` И в `base.yaml`, но конструктор `PipelineConfig(...)` в `load_config`
  их не присваивал → бралось дефолтное `False`/значение датакласса → флаг удаления wav всегда False
  → normalized .wav не удалялись никогда. Выглядело как «удаление не работает», хотя
  `_maybe_delete_normalized` исправен — он лишь гейтится этим флагом.
- **Fix:** чтение обоих полей в `PipelineConfig(...)` (`config.py` load_config). `_maybe_delete_normalized`
  также сдвинут ПОСЛЕ `update_call_status` в терминальных путях `process_call`.
- **Status:** RESOLVED (2026-06-06).

✅ **Дашборд показывал нули — запросы по несуществующим статусам** (2026-06-06)
- **Root cause (non-obvious):** `DashboardTools.get_status` считал `WHERE status='pending'` и
  `status='processed'`. Таких статусов в пайплайне НЕТ (реальные: new/normalizing/diarizing/
  transcribing/analyzing/delivering/done/transcribed/error) → оба COUNT всегда 0 → дашборд «пустой»
  даже при идущей обработке. Бэкенд real-time (updated_at/SSE) при этом исправен — искать в SQL tools.
- **Fix:** pending = `status NOT IN ('done','error','transcribed')` (все не-терминальные),
  processed = `status='done'`. Regress: `test_dashboard_tools.py::test_counts_different_statuses`
  (реальные статусы). `dashboard/tools.py`.
- **Status:** RESOLVED (2026-06-06).

✅ **watch не возобновлял зависшие + сиротские WAV копились** (2026-06-06)
- **Root cause:** (1) `run_loop` звал только `process_batch(new_ids)` — звонки с готовым wav, но
  не-терминальным статусом (краш до анализа) не подхватывались → залипали навсегда, wav оставался.
  (2) `cleanup_normalized` пропускал wav без call-записи в БД (краш до/во время ingest) → сироты копились.
- **Fix:** (1) `process_pending()` каждый цикл `run_loop`. (2) нет call → `wav.unlink()` (сирота).
  Regress: `test_watcher_cleanup.py`. `watcher.py`.
- **Status:** RESOLVED (2026-06-06).

✅ **reset.py не сносил C:\calls — защита блокировала родителя** (2026-06-06)
- **Root cause (non-obvious):** `_overlaps_protected(C:\calls)` → True из-за ветки `pr.startswith(t+"\\")`
  («путь СОДЕРЖИТ защищённый in/source»). Корень data в `C:\calls`, который содержит защищённые
  `in`/`source` → reset отказывался чистить родителя → «чистый лист» не срабатывал.
- **Fix:** блокировать только `path==protected` или `path ВНУТРИ protected`; родительские папки
  разрешены — `_walk_and_remove` сама пропускает защищённые подпапки. + bootstrap через env `PYTHON312`
  (py3.12+cu124). `reset.py`.
- **Status:** RESOLVED (2026-06-06).

✅ **OOM-риск: выгрузка ASR/pyannote ПОСЛЕ LLM-фазы (в присланном коде)** (2026-06-06)
- **Root cause (non-obvious):** в `callprofiler_20260606` `_unload_models()` стоял после Фазы 4 →
  GigaAM+pyannote (~5GB) висели в VRAM во время Фазы 3 (llama-server Qwen 9B **Q8_0** ~10GB) →
  15GB > 12GB RTX 3060 → OOM. Автор заложил «llama ≤7GB» — для Q8_0 неверно. Нарушение Hard
  Constraint «GPU sequential, never concurrent».
- **Fix:** выгрузка перенесена в `finally` Фазы 2 — ДО Фазы 3. Ко-резидентность GigaAM+pyannote
  сохранена ВНУТРИ Фазы 2 (без LLM, ~5GB < 12GB). Regress: `test_orchestrator_roles.py`
  (`_diarize_batch`→unload=0; `_unload_models()`→unload=1). `orchestrator.py`.
- **Status:** RESOLVED код (2026-06-06). Реальный VRAM — проверка на боксе.

✅ **ffmpeg код 4294967274 на нормализации — атомарный `.part` ломает выбор мукса** (2026-06-05)
- **Симптом:** `[ERROR] нормализация call_id=NNNN: ffmpeg завершился с кодом 4294967274 для …mp3`,
  раньше нормализация проходила ОК. Регресс ВНЁС я в тот же день (атомарная запись wav).
- **Root cause (non-obvious):** `4294967274` = unsigned(-22) = `AVERROR(EINVAL)`. Я добавил
  атомарную запись: ffmpeg стал писать выход во временный `{dst}.wav.part`. ffmpeg выбирает
  выходной **мукс по расширению файла** → `.part` неизвестно → `av_guess_format` фейлит →
  "Unable to find a suitable output format" → EINVAL(-22). Имя/спецсимволы источника ни при чём
  (sanitize корректен); единственное отличие от рабочего пути — суффикс `.part` на выходе.
- **Fix:** форсировать формат ЯВНО — `-f wav` перед `dst` в обоих ffmpeg-командах
  (`_convert_raw` + `_normalize_two_pass` pass-2). Расширение temp теперь не важно. Атомарность
  (`.part`→`os.replace`) сохранена — она нужна для skip-if-exists (битый `.part` не подхватится).
- **Regression:** `tests/test_normalizer_atomic.py` (реальный ffmpeg, skip без него; пишет в
  `.wav` с temp `.part`, проверяет RIFF/WAVE + отсутствие `.part`-орфана). Локально skip (нет
  ffmpeg) — отработает на боксе.
- **Status:** RESOLVED код (2026-06-05). Проверка на боксе при следующем прогоне.

ℹ️ **«Файл не найден …originals…» после cleanup+startprocess — не баг, неверный инструмент** (2026-06-05)
- **Симптом:** `[ERROR] нормализация call_id=NNNN: Файл не найден: …\users\me\audio\originals\YYYY\MM\*.mp3`.
- **Причина:** `cleanup keep-only` СОХРАНЯЕТ данные `me`; у части звонков оригиналы пропали → watch реклеймит →
  normalize не находит mp3. Для «чистого листа / нового компа» нужен `reset.bat --apply` (сносит всю data,
  пустая БД + me), НЕ keep-only. Подробно — `.claude/rules/decisions.md` («cleanup keep-only ≠ reset»).
- **Status:** РАЗЪЯСНЕНО (2026-06-05). reset.py закоммичен в main.

✅ **Дашборд «устаревшие данные» — SSE-тик гейтился вкладкой overview** (2026-06-05)
- **Root cause (non-obvious):** бэкенд real-time исправен (poller свежий reader + `MAX(updated_at)`,
  `update_call_status`/`update_pipeline_stage` бампают `updated_at`, db_reader с WAL-фиксом). НО фронт
  `app.js` в `es.onmessage`: `if (data.type==='tick' && state.activeTab==='overview')` — живой тик применялся
  ТОЛЬКО на вкладке overview и только к карточкам (`updateStatCards`), даже не к степперу. На Calls/Entities/
  System и на самом степпере — ничего не обновлялось → данные замерзали на снимке загрузки (`/api/overview`
  при входе работает → выглядит как «устаревшие»). Бэкенд ни при чём — искать в JS-обработчике, не в Python.
- **Fix:** тик обновляет АКТИВНУЮ вкладку (`loadCalls/loadEntities/loadSystem`) + `renderPipeline(by_stage)` на
  overview; карточки — всегда. `POLL_INTERVAL_SEC=2` уже стоял.
- **Status:** RESOLVED код (2026-06-05). Визуальная проверка — на боксе во время прогона.

✅ **normalized .wav накапливаются — удаление только на success-пути той же партии** (2026-06-05)
- **Root cause (non-obvious):** `_maybe_delete_normalized` зовётся в orchestrator лишь сразу после save_transcripts
  (stage 2) В ТОЙ ЖЕ обработке. Звонки, упавшие в `error` ДО stage 2 (norm wav уже создан), и resume-звонки
  (stage>=2 на входе в батч → Phase 2 transcribe пропущена → delete не зовётся) оставляют wav навсегда → копится
  на больших прогонах. wav при этом всегда регенерируется из mp3-архива (`originals/YYYY/MM`) → его снос безопасен.
- **Fix:** `watcher.cleanup_normalized()` — sweep каждый цикл: по всем `users/{uid}/audio/normalized/*.wav`
  парсит call_id, и если звонок stage>=2 или терминальный (done/transcribed/error) → unlink. Гейт
  `delete_normalized_after_transcribe`. Ловит все орфаны независимо от пути.
- **Status:** RESOLVED (2026-06-05).

✅ **Дашборд не показывал real-time — `?mode=ro` не видит WAL-записи** (2026-06-04)
- **Root cause (non-obvious):** пайплайн пишет в WAL (`repository.py` → `PRAGMA
  journal_mode=WAL`), а `dashboard/db_reader.py` открывал БД через
  `file:...?mode=ro`. Read-only коннект в WAL НЕ цепляется к WAL-индексу и читает
  снимок до последнего checkpoint → счётчики «замёрзшие», хотя обработка шла.
  Свежий reader на каждый тик поллера не спасал — `mode=ro` каждый раз даёт старый
  снимок. Бэкенд (`updated_at` бампается) и фронт (EventSource `/api/sse`) исправны.
- **Fix:** обычный read/write коннект (видит живой WAL) + `PRAGMA query_only=ON`
  (без записи, не мешает пайплайну; WAL = N читателей + 1 писатель без блокировок).
  `POLL_INTERVAL_SEC` 5→2. Проба живости: `dash-check.bat` / `dash_check.py`.
- **Status:** RESOLVED код (2026-06-04). Проверка на боксе во время прогона.

✅ **Роли UNKNOWN даже при готовом окружении — pyannote 4.x декодирует через torchcodec** (2026-06-04)
- **Root cause (non-obvious):** diag #5 — env на боксе ПОЛНОСТЬЮ готов (py3.12, torch 2.6+cu124,
  CUDA True, HF_TOKEN задан, pyannote.audio **4.0.4**, GigaAM на GPU). Легко решить, что роли
  обязаны работать. НО pyannote.audio 4.x по умолчанию декодирует аудиофайл ПО ПУТИ через
  `torchcodec`, а его `libtorchcodec_core{4..8}.dll` на Windows не грузятся (нужна full-shared
  сборка ffmpeg + точная version-совместимость с torch). → `self.pipeline(wav_path)` упал бы на
  декодировании → `_diarize_turns` ловит → роли UNKNOWN. ASR при этом РАБОТАЕТ: GigaAM не трогает
  torchcodec (свой `prepare_wav` через ffmpeg-CLI), поэтому симптом избирательный (текст есть, ролей нет).
- **Fix:** `pyannote_runner` подаёт аудио pyannote ТОЛЬКО в памяти (`{waveform, sample_rate}`),
  загрузка через soundfile (+librosa для ресемпла) — torchcodec не вызывается вообще. Убраны
  temp-wav в `_find_owner_label` (эмбеддинги из in-memory срезов). Никакой возни с DLL не нужно.
- **Regression:** `tests/test_pyannote_runner.py::TestInMemoryAudio` (4: waveform-dict shape,
  L2-norm, diarize передаёт dict а не path, owner-label in-memory). Полный путь pyannote — на боксе.
- **Status:** RESOLVED код (2026-06-04). Реальная диаризация — проверка на боксе.

✅ **754 звонка навсегда зависли в 'normalizing' — resume их не видел** (2026-06-04)
- **Root cause (non-obvious):** `update_call_status(call_id,'normalizing')` ставится ДО
  `update_pipeline_stage(call_id,1)`. Крах/прерывание во время нормализации → строка остаётся
  `status='normalizing'` на `pipeline_stage=0`. `get_stalled_calls` фильтровал `pipeline_stage > 0`
  → такие звонки не подхватывал ни resume (не >0), ни pending (status≠'new') → сирота навсегда.
- **Fix:** условие → `status NOT IN ('new','done','error')` (любой промежуточный статус = воркер
  начал, но не закончил, на любой стадии). `process_batch` идемпотентен по stage, переподхват с 0 безопасен.
- **Regression:** `tests/test_repository.py` (`test_stalled_reclaims_normalizing_stage0` +
  midstage/terminal+new/per-user).
- **Status:** RESOLVED (2026-06-04).

✅ **Роли молча UNKNOWN — hf_token-мусор маскировал причину** (2026-06-04)
- **Root cause (non-obvious):** на Windows `os.path.expandvars("${HF_TOKEN}")` при НЕзаданной
  переменной возвращает строку `"${HF_TOKEN}"` (truthy!), а не "". `config.hf_token` становился
  мусором → pyannote получал `use_auth_token="${HF_TOKEN}"` → 401 на gated-моделях → диаризация
  падала → ВСЕ роли UNKNOWN. Тот же мусор ломал guard `if not cfg.hf_token` (был truthy).
- **Сопутствующее:** `_diarize_turns` сваливал любую причину сбоя (нет ref / нет pyannote /
  нет токена / gated не принят) в один невнятный warning → пользователь не понимал, ЧТО чинить.
- **Fix:** `config._resolve_secret()` — незаданная `${VAR}`/`%VAR%` → ""; strip. `_warn_once(key)`
  в orchestrator — каждая причина логируется раз с командой фикса. Деградация остаётся graceful.
- **Env (истинный блокер на боксе):** pyannote.audio/librosa/soundfile НЕ установлены + HF_TOKEN
  не задан + gated-модели не приняты → `install-roles.bat` + `setx HF_TOKEN` + accept 3 моделей.
- **Версия pyannote (non-obvious):** unpinned install ставит pyannote, где `from_pretrained`
  ждёт `token=`, а не `use_auth_token=` → `TypeError` при РАБОЧЕМ токене. Fix: `_load_pretrained`
  пробует оба аргумента. Токен READ корректен (gated download проходит, HTTP 302).
- **Regression:** `tests/test_config_hf_token.py` (6), `tests/test_orchestrator_roles.py`
  (no_ref/no_pyannote/no_token/warn_once). 19 зелёных локально.
- **Status:** RESOLVED код (2026-06-04). Реальные роли — после env-настройки на боксе.

✅ **Stage-1 GPU-прогон: 7 проблем из rez.txt** (2026-06-03)
- **B1 (env, не код):** бокс на Python 3.14 → PyTorch не даёт CUDA-колёс (только torch 2.12+cpu) → GPU простаивает, GigaAM в 20-50× медленнее. Fix: Python 3.12 + torch==2.6.0+cu124 + torchaudio==2.6.0 + transformers<5. На 3.12 патчи A/B (см. rez.txt) не нужны. Зафиксировано в `requirements-gigaam.txt`/`RUN_STAGE1.md`.
- **B2:** `orchestrator` инстанцировал `PyannoteRunner` на старте → лишняя связанность для Stage-1. Fix: lazy в `_diarize_segments`, `self.pyannote_runner=None` в `__init__`, guard в finally.
- **B3:** `process_call()` не писал `pipeline_stage` (в отличие от `process_batch`) → нет видимости/cleanup. Fix: stage 1→4 добавлены.
- **B4/B5 (потеря данных):** watcher удалял исходник дубликата из incoming БЕЗ проверки, что звонок реально транскрибирован → error/завис терял исходник. Fix: `_scan_user_dir` MD5-first через `repo.get_call_by_md5()`, удаление только при `pipeline_stage>=2`. Regression: `tests/test_watcher_cleanup.py::test_scan_keeps_untranscribed_duplicate` + `::test_scan_removes_transcribed_duplicate`.
- **B6:** `prompts_dir` резолвился от `data_dir` (`C:\calls\configs\prompts` — не существует) в 3 местах. Fix: `Config.prompts_dir` от корня проекта.
- **B7:** dashboard не стартовал — `__init__` импортировал несуществующие `app`/`set_user_id`; `DashboardDBReader` получал каталог вместо `.db`. Fix: фабрика `server._build_app()`, db_reader резолвит `data_dir/db/callprofiler.db`.
- **Status:** RESOLVED (код), B1 — требует Python 3.12 на боксе.

✅ **Diarization exception lost transcript + leaked VRAM** (2026-05-30)
- **Issue:** In `orchestrator.py` (`process_call` & `process_batch`), if `pyannote.diarize()`/`load()` threw, `save_transcripts()` was skipped (Whisper transcript lost) AND `pyannote_runner.unload()` was skipped (VRAM leaked before the ~10GB LLM phase → OOM risk). Violated `.claude/rules/pipeline.md` (continue with speaker=UNKNOWN) + CONSTITUTION Ст.9.3.
- **Found by:** strategic audit (2026-05-29), verified by reading `orchestrator.py:294-305`.
- **Fix:** extracted `Orchestrator._diarize_segments()` — try/except → return UNKNOWN segments on failure, `finally: unload()`. Both call sites rewired (de-duplicated). Transcript always saved; GPU always freed.
- **Companion fix:** `normalizer.py` ffmpeg/ffprobe presence check moved from import-time to call-time (`_require_ffmpeg()`), so the package is importable without ffmpeg (`config._validate()` still fail-fasts at startup). Unblocked the first orchestrator-level unit test.
- **Regression tests:** `tests/test_regressions.py::test_diarization_failure_keeps_transcript_and_frees_gpu`, `::test_diarization_disabled_returns_segments_without_loading`. Suite 414/414. Code-review: clean.
- **Status:** RESOLVED (2026-05-30)

✅ **BOM in .bat files** (2026-04-14)
- Removed UTF-8 BOM from all batch files
- Converted to ASCII encoding for Windows compatibility

✅ **Missing Memory Protocol** (2026-04-14)
- Added 6-rule Memory Protocol to CLAUDE.md
- Ensures AI session continuity via journals

✅ **Missing automation scripts** (2026-04-14)
- Created new-session.bat, save-session.bat, emergency-save.bat
- Provides Windows-friendly workflow

---

## Statistics

| Category | Count |
|----------|-------|
| Active Bugs | 3 |
| Resolved | 4 |
| Ideas/Backlog | 5 |
| Future Phase Items | 3 |
| **Total** | **14** |

**Burn Rate:** 3 issues fixed in Phase 5 (audit focus). Ready for Phase 6 (optimization).
