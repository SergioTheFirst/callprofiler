# Architecture Decisions

## ASR Backend: Whisper → GigaAM v3 RNN-T (2026-06-01)

**Decision:** Replace Whisper (faster-whisper) with GigaAM v3 RNN-T as the primary ASR backend.

**Why:** User decision — GigaAM v3 RNN-T targets Russian-language call transcription with higher accuracy. Model lives LOCALLY at `C:\models\GigaAM-v3-rnnt` (HF custom: config.json + modeling_gigaam.py + pytorch_model.bin).

**Architecture:** `ASRRunner` Protocol (`transcribe/asr_runner.py`). Factory `_make_asr_runner(config)` selects backend via `config.models.asr_backend`. Switching = YAML field `asr_backend: gigaam` + `gigaam_model_dir: C:\models\GigaAM-v3-rnnt`.

**Update (2026-06-03) — local in-process, supersedes HTTP plan:** Модель не сервер, а локальная HF-модель → `GigaAMRunner` ПЕРЕПИСАН с HTTP-stub на in-process: `AutoModel.from_pretrained(dir, trust_remote_code=True)`, GPU load/unload. `model.transcribe_longform` НЕ используется — он тянет gated `pyannote/segmentation-3.0` (нужен HF_TOKEN); вместо него СВОЯ нарезка фиксированными окнами (<25с, `gigaam_chunk_sec`) → `asr.forward`+`decoding.decode`. Спикеры `UNKNOWN` (диаризация выключена: `enable_diarization:false`). Поля `gigaam_url`/HTTP оставлены в конфиге как legacy, не используются.

**Blast-radius:** HIGH. Transcript quality change invalidates:
- `events.quote` (graph facts linked to transcript quotes)
- `bio_scenes.key_quote` (biography scene quotes)
After switching: run `graph-replay --user X` + `biography-run --user X --passes p1_scene,p2_entities` to rebuild from new transcripts.

**Current state (2026-06-03):** `asr_backend: gigaam` (default). `GigaAMRunner` = local in-process, fixed-window chunking, no pyannote. Stage-1 (audio→текст→БД+.txt) собран и покрыт mock-тестами; ещё НЕ прогнан на реальной модели/GPU (рабочая машина — см. `RUN_STAGE1.md`).

## Core Stack Decisions

### Why SQLite (not PostgreSQL/cloud)?
- **CONSTITUTION Rule 4:** Local-only, no external dependencies
- Single-file database fits Windows deployment
- User isolation via schema design (all queries filter by user_id)
- Fast enough for single-user 100+ calls/week

### Why Ollama (not OpenAI/cloud)?
- **CONSTITUTION Rule 4:** Local inference, full privacy
- Qwen 2.5 14B fits RTX 3060 12GB (float16)
- No API calls = no latency, no costs, no rate limits
- Can swap models without code changes

### Why Whisper (not WhisperX)?
- Simpler pipeline, fewer dependencies
- Good enough accuracy for business context extraction
- No speaker clustering (use Pyannote separately)
- faster-whisper = fast inference on GPU

### Why Pyannote 3.3.2 (not 4.0)?
- 3.3.2 stable with GPU support
- 4.0 requires complex setup
- Reference embedding approach (compare user's voice) works well
- use_auth_token= pattern is proven

### Why exponential decay for risk (not average)?
- Recent calls more relevant than old ones
- 90-day half-life matches human memory (3 months = half-weight)
- Recent context = better decision-making
- Avoids "one bad call 6 months ago" blocking all trust

### Why user_id isolation (not multi-tenant)?
- Simpler model (one user per Windows machine)
- CONSTITUTION Rule 2.5: "Every query filters by user_id"
- Future: can add multiple users to same machine if needed
- Zero data leakage between users

## Data Model Decisions

### Why separate Events + Promises tables?
- **Events:** 7 types (promise, debt, task, fact, risk, contradiction, smalltalk) with confidence
- **Promises:** Legacy table, keeps backward compatibility
- Events = structured extraction; Promises = specific caller debts
- Allows flexible query patterns (open promises ≠ open debts)

### Why contact_summaries (not compute on-read)?
- Telegram commands need fast response (/<1 sec)
- Computing risk from 50+ calls each time = too slow
- Rebuild on call enrichment = O(1) lookup
- Risk calculation is expensive (exponential decay)

### Why JSON fields for arrays (not separate tables)?
- Simpler queries for readonly data (promises, debts, facts)
- No joins needed for UI display
- Bounded size (max 10 promises per contact)
- Trade: harder to search/filter, but acceptable

### Why risk_score 0-100 (not continuous)?
- Easy to understand (>70 = red flag)
- Matches emoji system (🟢 <30, 🟡 30-70, 🔴 >70)
- Simple advice rules (if risk>70 → "speak first")
- Granular enough for business decisions

## Delivery Strategy Decisions

### Why Telegram (not SMS/email)?
- Instant notifications (bot runs in background)
- Rich formatting (HTML, inline buttons)
- Feedback loop (click [OK] / [Wrong])
- User has control (enable/disable per contact)

### Why caller cards (not just Telegram)?
- Android overlay (caller ID screen integration)
- FolderSync = automatic sync to phone
- Offline access (no internet needed)
- Visual risk indicator (emoji at a glance)

### Why inline feedback buttons (not separate message)?
- One-click feedback (no conversation)
- Saved to analyses.feedback field
- Trains LLM for next session (could improve prompts)
- Respects user's time

### Why FastAPI + SSE for dashboard (not WebSockets/polling)?
- **SSE (Server-Sent Events):** One-way real-time push from server to browser
- Simpler than WebSockets (no bidirectional complexity)
- Automatic reconnection built into EventSource API
- Graceful degradation: fallback to 5-second polling after 5 reconnect failures
- Read-only DB access via `file:path?mode=ro` URI = no locks, no interference with pipeline
- FastAPI = async, automatic OpenAPI docs, Pydantic validation
- Polling-based change detection: check MAX(updated_at) every 2 seconds
- No Redis/message queue needed (SQLite timestamp is the event source)

## Process Decisions

### Why Memory Protocol (CONTINUITY.md + CHANGELOG.md)?
- AI context resets between sessions
- Only way to ensure continuity = written logs
- Every change must be recorded immediately
- Prevents "context loss" spirals

### Why direct push to main (no PR)?
- Single developer (you) making decisions
- PR overhead not worth it for 1 person
- CLAUDE.md documents the decision
- Easier to experiment and iterate

### Why .bat automation files?
- Windows-native (no WSL, no bash)
- new-session.bat = reproducible briefing
- save-session.bat = safe commit (runs tests first)
- emergency-save.bat = untested quick save

## Known Trade-offs

| Decision | Benefit | Cost |
|----------|---------|------|
| SQLite | Simple, local | Limited to 1 machine |
| Ollama local | No API calls | Must have GPU |
| Exponential decay | Recent bias | Old context fades |
| JSON arrays | Simple | Hard to search |
| No multi-tenant | Simpler code | Can't scale easily |
| Memory Protocol | Continuity | Must update journals |

## Future Flexibility

- **Model swap:** llama-server model can change (Qwen, Llama, Mistral, etc)
- **Database migration:** Could move to PostgreSQL if needed
- **Multi-user:** Can add user_id branching logic later
- **Cloud option:** Could add cloud fallback if needed
- **Telegram alternative:** Could add Discord/Slack later

## Doc Reconciliation v5 (2026-05-29)

### Why ARCHITECTURE_v5 + factual corrections?
- 5-module code audit found docs drifted hard from code: Knowledge Graph + Biography + Dashboard (~60% of the codebase) were undocumented at architecture level; docs said "Ollama" (code uses llama-server) and "D:\calls" (config is `C:\calls\data`).
- **Decision:** code + `configs/*.yaml` are the source of truth. `ARCHITECTURE_v5.md` documents the 4 real layers; `ARCHITECTURE_v4/v3.md`, `STRATEGIC_PLAN_v4.md`, `memory/roadmap.md` are historical for factual state.
- Constitution **principles** are unchanged — Ст.16 (architecture revision) NOT invoked. Only factual labels were corrected, which Ст.19.1 (continuity of truth) requires.
- **Source-of-truth precedence:** code → CONTINUITY.md + git → ARCHITECTURE_v5 → CONSTITUTION (principles) → historical docs.
- Trade-off: keeping v4/v3 as history (not deleting) costs a little clutter but preserves the decision trail.

## Port biography resilience to call-analysis (DESIGN, 2026-06-04)

**Why:** biography уже умеет то, что нужно основному пути анализа звонка на прогоне
17k unattended. `analyze/` уже взял ВЫХОДНОЙ динамический бюджет (`output_budget.py`,
тиры по длине транскрипта + priority×1.2, потолки n_ctx−prompt−margin и abs_max=4096) и
клип входа (`prompt_budget.py`). НЕ взял ключевую устойчивость biography. Решение —
портировать строго то, что окупается, и НЕ дублировать то, что уже покрыто.

**Брать из biography (по приоритету ROI/риск):**
1. **Мемоизация + retry (`ResilientLLMClient` + `bio_llm_calls`).** `AnalysisService` зовёт
   ПЛОСКИЙ `LLMClient` — без кэша, одна попытка, при `ConnectionError` теряет анализ
   (`status=error`). Биография: MD5(messages+temp+max_tokens+model) → cache HIT минует
   сервер; retry 4× c backoff, НИКОГДА не падает (None → checkpoint→continue). Это и есть
   «ядро многодневного прогона». План: вынести мемоизацию в нейтральный infra-модуль
   `llm_cache` (таблица `llm_calls`), общий для biography и analyze (сохраняет разделение
   graph≠biography, убирает дубль). В hash добавить `prompt_version` явно.
2. **Пер-задачные бюджеты токенов (явный запрос пользователя).** Обобщить `output_budget`
   в реестр TASK-профилей: каждый со своим (floor, тиры, abs_max, temperature). Задачи для
   звонка: `triage` (≤200 out, temp 0.0), `extract` (текущие тиры, temp 0.2),
   `deep` (≤3600, temp 0.3, только priority≥70). «Динамическая величина токенов для
   определённых задач» становится first-class.
3. **Разбить монолитный анализ звонка на gated-проходы (структурный перенос).** Сейчас
   звонок = ОДИН LLM-вызов (summary+risk+promises+entities/structured_facts v2). Биография =
   специализированные проходы. План: `P-triage` (классификация+priority, дёшево) → гейтит
   `P-extract` (полный JSON для graph v2) → опц. `P-deep` (противоречия/реляц. факты,
   только priority≥70/длинные). Рутинные/короткие останавливаются после triage → на 17k это
   чистый ускоритель + качество выше на важных. Минус vs монолит: пере-подача транскрипта на
   проход (KV-стоимость) → ветвиться только по triage/length/priority. Риск средний → за
   флагом `analysis_multipass`, валидировать на canary-50 (parse_fail%, role-UNKNOWN%,
   truncation%, распределение risk) ДО включения на полный прогон.
4. **Входной бюджет как пропорциональная конкуренция (TokenBudget-lite).** Заменить плоский
   клип: transcript(~80%) vs previous_summaries(~15%) vs metadata(~5%), неиспользованное
   перераспределяется. Длинная история не теснит сам звонок; короткий звонок подаётся
   целиком. Дёшево.
5. **Версионирование промптов по задачам (PASS_VERSIONS-style).** Per-task dict версий →
   бамп одной задачи инвалидирует только её кэш. Парно к #1 и #3.

**НЕ брать (анти-оверинжиниринг, CLAUDE.md «add only non-obvious / don't duplicate»):**
- Пер-айтемные checkpoint-таблицы — `call.status` уже даёт resume (`status NOT IN
  ('new','done','error')` reclaim); токен-стоимость покрывает #1. Дублировать незачем.
- Инъекцию психопрофиля в пер-звонковый анализ — это слой graph/biography, не на каждый звонок.
- 9-секционные пропорциональные бюджеты — избыточно; хватает 3-стороннего сплита.

**Порядок реализации:** #1 (мемоизация+retry) первым — макс. ROI надёжности/стоимости, мин.
риск, переиспользует код; затем #2 (task-бюджеты, прямой пример пользователя); затем #3 за
флагом с canary-гейтом. Реализация — после согласования ветки пользователем.

## Stage-1 (audio→БД) — НЕМЕДЛЕННЫЙ приоритет, transcribe-only terminal (PLAN, 2026-06-04)

**Контекст:** пользователь поднял приоритет — «самое важное: завести audio→БД». Biography→analysis
дизайн (выше) ОТЛОЖЕН. Stage-1 = audio→текст→БД, развязан с LLM (Stage-2) и ролями. Флаги
`enable_llm_analysis` и `enable_diarization` уже есть (`config.py`/`features.yaml`/orchestrator).

**Необходимый фикс (единственный реальный код-айтем):** `process_batch` (путь `watch`/17k) НЕ
терминализует transcribe-only звонки. При `enable_llm_analysis=false`: Pass B → статус
`transcribing`; Pass C пишет транскрипт+stage 2, но статус НЕ меняет; Phase 3 analyze пропущена;
Phase 4 deliver гейт `if stage<3: continue` → звонок навсегда застревает status=`transcribing`/stage 2,
`get_stalled_calls` (status NOT IN new/done/error) реклаймит каждый прогон = бесконечный stall-loop,
дашборд вечно «transcribing». (`process_call` single-path терминализует в `done` корректно — фикс
только для batch.)
**Решение:** ввести терминальный статус **`transcribed`** (Stage-1 готов, анализ ждёт). Ставить его
в Pass C при выключенном анализе (или в Phase 4). `get_stalled_calls` считает `transcribed`
терминальным; dashboard stage-map добавляет его; Stage-2 bulk-enrich позже выбирает `status='transcribed'`.

**Run-конфиг Stage-1:** `enable_llm_analysis:false` + `enable_diarization:false` → чистый
audio→текст→БД: без llama-server, без pyannote/torchcodec/otel-телеметрии, максимально быстро/надёжно.

**Роли — потом, БЕЗ повторного ASR:** держим flat сейчас; роли позже выводим наложением
speaker-спанов pyannote на уже сохранённые `transcripts.start_ms/end_ms` (re-attribution по
перекрытию времени, без ре-транскрибации). Flat-first не стоит ролям передёлки.

**Отложить:** LLM-анализ (Stage-2 bulk-enrich над `transcribed`), граф v2/профили/биография,
biography→analysis resilience, чистку error/serhio, VAD/overlap на стыках окон.

## reset.py = «чистый лист»: что священно, что расходник (2026-06-05)

**Решение пользователя:** `reset.py` сносит ВСЁ производное кроме двух папок, затем bootstrap →
`startprocess.bat` (watch) прогоняет обработку заново.

**Священно (reset НЕ трогает, `PROTECTED`):**
- `C:\calls\in` — **вход обработки** (watch читает `users.incoming_dir`, дефолт = in). Исходники для
  перепрогона лежат ЗДЕСЬ (выбор пользователя 2026-06-05: «аудио уже в in»). Снести = нечего обрабатывать.
- `C:\calls\source` — мастер-архив исходников (вне кода, ручной).

**Расходник (reset сносит ЦЕЛИКОМ):** вся `C:\calls\data` (БД + все профили `users/*` с
originals+normalized + logs + biography) + `C:\calls\text` + `C:\calls\sync`. Профильные `originals/` —
КОПИИ входа, не мастер; мастер = in/source. Поэтому их снос безопасен.

**Non-obvious:** БД лежит ВНУТРИ data (`data/db/callprofiler.db`) → бэкап делается ВНЕ data
(`C:\calls\callprofiler.db.bak-<ts>`), иначе снёсся бы вместе с data. dry-run по умолчанию (необратимо,
16645+ звонков): реальный снос только `--apply`. bootstrap-дефолты (`user=me`, `incoming=C:\calls\in`)
восстанавливают рабочий стейт без аргументов.

## Один профиль `me`: keep-only + bio-охват purge_user (2026-06-05)

**Решение пользователя:** «удалить всех user, оставить только `me`; все работы будут в его профиле». Система
из мультиюзерной де-факто становится одно-профильной. `serhio` — НЕ другой человек, а старый owner-id
того же Сергея Медведева (так было в `biography/CLAUDE.md`: «owner user_id=serhio»); данные пересобраны под
`me` (~16645 done), `serhio` остался битым хвостом. Главный CLAUDE.md: `[me]` = Сергей Медведев = always owner.
Источник истины CONTINUITY > модульный CLAUDE.md → keeper = `me`, `serhio` под снос. `serhio` в КОДЕ — только
докстринги-примеры (ingester/card_generator/telegram_bot/bulk/psychology_profiler), runtime не хардкодит →
снос ничего не ломает; устаревший `biography/CLAUDE.md` поправлен (serhio→me).

**Инструмент:** `cleanup.py keep-only --user me` (инверсия `purge-user`) через repo-метод
`purge_other_users(keeper)` = цикл проверенного `purge_user` по не-keeper'ам. Новый SQL удаления НЕ писали —
переиспользовали `purge_user` (мин. риск). Защита: keeper обязан существовать (`ValueError` → отказ), иначе
пустой/опечатанный keeper снёс бы ВСЕХ. Dry-run по умолчанию (как reset/cleanup).

## Полный GPU-пайплайн (диаризация OFF) + GPU-обязательность (2026-06-05)

**Запрос юзера:** «GPU модели нужны и должны использоваться — GigaAM и LLM Qwen 3.5 9B Q8_0 по назначению».
Названы РОВНО две модели. Решение: `enable_llm_analysis:true` + `enable_diarization:false` → пайплайн =
GigaAM(GPU ASR) → Qwen(GPU LLM). pyannote (3-я GPU-модель) НЕ названа, на Windows ломается через torchcodec
(см. bugs.md) и тянет per-turn путь → OFF. Роли не теряем: позже наложением pyannote-спанов на
`transcripts.start_ms/end_ms` без ре-ASR (flat-first решение из Stage-1). Реверс — один флаг.
**GPU-обязательность:** `gigaam_runner` при `gigaam_device=cuda` без CUDA теперь РАЗДАЁТ `RuntimeError`, а не
молча падает на CPU (20-50× медленнее = тихая деградация многочасового прогона, decisions B1). «Должны
использоваться» = если GPU нет — стоп с понятным сообщением, а не делать вид, что работает.

**РЕВЕРС диаризации (2026-06-05, тот же день):** юзер: «диаризация = распределение по ролям ДОЛЖНА работать».
Вернул `enable_diarization:true`. Моя ставка OFF (pyannote не названа) была неверной — роли нужны. Код-путь
`_diarize_batch` исправен и VRAM-безопасен (pyannote load→unload ДО ASR), сбой → graceful UNKNOWN +
`_warn_once`. На боксе для реальных ролей: pyannote.audio+librosa+soundfile (`install-roles.bat`), HF_TOKEN,
принятые gated pyannote-модели, `C:\pro\mbot\ref\manager.wav`. GPU-обязательность GigaAM оставлена.

## cleanup keep-only ≠ reset (чистый лист). Симптом «Файл не найден» (2026-06-05)

**Проблема юзера:** после `cleanup`+`startprocess` сыпались `[ERROR] нормализация call_id=18343: Файл не
найден: …\users\me\audio\originals\2021\03\*.mp3`. Юзер ждал, что «очистка» даёт чистую БД (ноль во всех
профилях, как новый комп).

**Разбор (non-obvious — два разных инструмента):**
- `cleanup keep-only --user me` (задача «оставить me») по дизайну СОХРАНЯЕТ все данные `me` (~16645 звонков).
  У части `me` оригиналы пропали (миграция/прежние чистки) → watch реклеймит их (status≠done) → normalize не
  находит mp3 → error. Это НЕ баг keep-only, а неверный инструмент для «чистого листа».
- **Чистый лист = `reset.py --apply`**: бэкап БД ВНЕ data → сносит ВСЮ `C:\calls` кроме `in`/`source`
  (вся `data`=БД+все профили originals+normalized+logs+biography, +text, +sync) → bootstrap = пустая БД +
  `me` (incoming=`C:\calls\in`, ref_audio дефолтом) → `startprocess` обрабатывает `in` с нуля. Ноль везде.
- reset.py закоммичен (был uncommitted 2 сессии). Перед reset ОСТАНОВИТЬ watch/dashboard (открытый коннект к БД).
- Источник для реобработки — `C:\calls\in` (reset его НЕ трогает). Если аудио только в (сносимом) архиве
  originals и НЕ в `in` — после reset обрабатывать нечего (предупредить юзера).

**Non-obvious — bio-пробел в purge_user:** `purge_user` НЕ трогал `bio_*` (создаются `apply_biography_schema`
отдельно, не в `init_db`). Для удаляемого юзера bio-сцены/сущности/главы сиротели. Дополнил: 12 bio-таблиц с
`user_id` + junction `bio_scene_entities` (без user_id → чистка по `scene_id IN (SELECT … FROM bio_scenes …)`).
Порядок DELETE FK-safe при `foreign_keys=ON`: junction → ссылающиеся на bio_entities → `bio_scenes`/`bio_entities`
ПОСЛЕДНИМИ, и весь bio-блок ДО `calls`/`contacts`/`users` (bio_scenes→calls, bio_entities→contacts, все→users).
Всё guarded `_table_exists` → no-op, если biography не запускалась (текущий бокс). Regression: `test_cleanup.py`
(`test_purge_user_removes_bio_rows` + 3× `purge_other_users`).
