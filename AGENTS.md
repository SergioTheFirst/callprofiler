# AGENTS.md — Руководство для AI-агентов

Точка входа для **любого** AI-агента (Claude Code, Codex, Cursor, облачные routine-сессии).
Claude-специфика (тиры моделей, субагенты, плагины) — в `CLAUDE.md`; этот файл — общий контракт.
Не заменяет `CONSTITUTION.md` (merge-blocking правила, 19 статей), `CONTINUITY.md` (где мы
остановились) и `CHANGELOG.md` — связывает их в рабочий процесс.

> **TL;DR для агента:**
> 1. Прочитай `CONTINUITY.md` целиком и последние 20 строк `CHANGELOG.md`.
> 2. `git status -sb` + `gh pr list` — открытый PR другой сессии влить/закрыть ДО своей работы.
> 3. Текущий план — `docs/sintezdiharea.md` (T-00…T-25); делай задачу маленьким вертикальным срезом.
> 4. Не ломай: GPU-порядок, `WHERE user_id = ?`, атомарность файлов, миграции через `db/migrations.py`.
> 5. `python -m pytest -q` + `ruff check --select F821,E9,F7,F63,F82 src tests` перед коммитом.
> 6. Сперва память (`CONTINUITY.md`, `CHANGELOG.md`, `.claude/rules/*`), потом `commit` + `push origin main`.

---

## 1. Что это за проект

CallProfiler — локальная система пост-обработки записей телефонных разговоров и построения
психологического досье собеседников:

```
аудио (C:\calls\in) → ingest (MD5, архив originals) → normalize (ffmpeg) → pyannote (роли, ref-embedding владельца)
  → GigaAM v3 RNN-T (ASR) → SQLite → Qwen3.5-9B @ llama-server (анализ) → caller card / Telegram / dashboard
  → graph (entities/events/BS-index) → insight (архетипы, возраст, тиры, обязательства) → biography (книга)
```

Целевая машина («бокс»): Windows 10/11 + RTX 3060 12GB + Python 3.12 + torch 2.6.0+cu124.
Код пишется на dev-машине **без** GPU/БД/ffmpeg/моделей — всё тестируемое офлайн (mock/synth);
реальный прогон = «проверка на боксе», фиксируется в `CONTINUITY.md`.
Никаких облаков, Docker, Redis, PostgreSQL, ORM, Ollama (`CONSTITUTION.md` Ст. 4, 5).

**Владелец/домен:** `[me]` = Сергей Станиславович Медведев (всегда owner), `[s2]` = собеседник.
Пользовательский вывод ≤300 символов на факт, без счётчиков/длительностей.

---

## 2. Структура репозитория

```
callprofiler/
├── CLAUDE.md / AGENTS.md        ← инструкции агентам (Claude-специфика / общий контракт)
├── CONSTITUTION.md              ← merge-blocking правила (19 статей)
├── CONTINUITY.md / CHANGELOG.md ← память: текущее состояние (overwrite) / журнал (append)
├── ARCHITECTURE_v5.md           ← 4 слоя системы (pipeline, graph, biography, dashboard)
├── docs/
│   ├── sintezdiharea.md         ← ТЕКУЩИЙ план исполнения T-00…T-25 (production-ready фундамент)
│   ├── decisions/CP-0-contracts.md ← контракты C-01…C-05 (ASR, card 512B, pyannote, Telegram, git)
│   ├── routines/continue-sintezdiharea.md ← промпт автономного облачного прогона
│   ├── TESTING.md · baseline-report.json · superpowers/{plans,specs}/
├── .claude/rules/*.md           ← КАРТЫ слоёв: pipeline, db, graph, llm, insight, dashboard,
│                                   biography-{data,prompts,style}, bugs (root causes), decisions (WHY)
├── .claude/skills/              ← filename-parser/, journal-keeper/, db-migration.md, fix-bug.md
├── configs/                     ← base.yaml (пути/модели), features.yaml (флаги), prompts/*_vNNN.txt
├── *.bat (корень) · scripts/baseline.py ← бокс-скрипты (watch/dashboard/reset/…); воспроизводимый baseline
├── src/callprofiler/
│   ├── cli/                     ← `python -m callprofiler <cmd>` (~60 команд, `--help`)
│   ├── config.py · identity.py · artifacts.py · torch_patch.py · doctor.py · llm_cache.py · textnorm.py
│   ├── db/                      ← schema.sql, repository.py (sqlite3, без ORM), migrations.py (ALL_MIGRATIONS,
│   │                               checksummed), connection.py (factory, WAL, busy_timeout), uow.py
│   ├── ingest/ audio/ diarize/ transcribe/ analyze/ pipeline/   ← конвейер (см. rules/pipeline.md)
│   ├── aggregate/ events/ graph/                                ← summaries, events, knowledge graph
│   ├── deliver/                 ← card_generator, telegram_bot, digest, reminders, daily report
│   ├── dashboard/               ← FastAPI read-only (PRAGMA query_only), SSE, досье личности
│   ├── insight/                 ← архетипы, возраст, тиры, deep-extract, promise_outcomes, … (numpy-only)
│   ├── biography/               ← 9-pass книжный pipeline (свои bio_* таблицы)
│   ├── bulk/ ops/ quality/      ← массовые операции, backup/restore, extraction_eval (canary — analyze/canary.py)
└── tests/                       ← pytest; 0 failed обязательно, текущее число passed — в CONTINUITY.md
```

---

## 3. Обязательный рабочий процесс

### 3.1. Старт
1. `CONTINUITY.md` — briefing: состояние, следующая задача, открытые хвосты.
2. Последние 20 строк `CHANGELOG.md`.
3. `git status -sb`, `gh pr list` — чужой открытый PR влить/закрыть; две параллельные сессии над
   одним планом запрещены (2026-08-21: PR #17 и #18 сделали один и тот же фикс дважды).
4. Вопросы про слой — из `.claude/rules/<слой>.md`, код читать только если карта не покрывает
   (и тогда дополнить карту).
5. Архитектурное решение → найти статью `CONSTITUTION.md`; противоречие = бракованный PR.

### 3.2. Во время работы
- **Вертикальный срез** (Ст. 2.1), не «рефакторинг всей БД».
- **`WHERE user_id = ?` в каждом запросе** (Ст. 2.5, T-03): мутаторы принимают `user_id`
  обязательно, без дефолта `None`; `tests/test_tenant_ownership.py` — инвентарный тест.
- **GPU-дисциплина** (Ст. 2.4, 9.3): GigaAM+pyannote ко-резидентны в Фазе 2 → `_unload_models()`
  → только потом LLM. Три GPU-модели одновременно = OOM на 12GB.
- **Ошибки не проглатываются** (Ст. 6.4): try/except → `update_call_status('error', msg)` → continue.
  `except: pass` запрещён.
- **Файлы атомарно** (T-08): любая публикация артефакта через `artifacts.atomic_*` (`.part` → `os.replace`).
  Оригиналы в `audio/originals/` неприкосновенны (Ст. 6.1). Удаление/перемещение данных — только
  через существующие пути (`cleanup`, `reset`, `purge_user`), с dry-run по умолчанию.
- **Схема БД** (T-05): новая запись в `db/migrations.py::ALL_MIGRATIONS` + `schema.sql` в sync.
  Применённую миграцию не править (checksum упадёт громко — это намеренно).
- **LLM**: промпты версионируются (`configs/prompts/*_vNNN.txt`, `PROMPT_VERSION`); смена промпта =
  инвалидация кэша (`llm_calls` / `bio_llm_calls`). Модель зафиксирована (decisions.md 2026-07-16).
- **Дашборд** — read-only, никогда не зовёт LLM и не пишет в БД (`rules/dashboard.md`).

### 3.3. Финал
1. Память: `CHANGELOG.md` (одна строка на изменение) + `CONTINUITY.md` (overwrite: state/next) +
   при необходимости `bugs.md` (root cause + regression test) / `decisions.md` (WHY).
2. `python -m pytest -q` (~3 мин, один раз перед коммитом) + ruff-гейт из TL;DR.
3. Коммит + `push origin main` (C-05). Облачный harness навязал ветку → PR и немедленный merge.
   Сломал `main` → `git revert` + push (никогда `--force`/reset удалённой истории).

> Контекст AI-сессии стирается. Журналы — единственная преемственность (Ст. 19).

---

## 4. Команды

```bash
# Установка
pip install -e ".[dev,full]"      # бокс / dev: полный ML-стек (torch без floor — бокс на cu124)
pip install -e ".[cloud]"         # CI / облако: без ML-стека (~40 МБ)

# Проверка
python -m pytest -q                                  # PYTHONPATH не нужен
ruff check --select F821,E9,F7,F63,F82 src tests     # CI-гейт (ловит NameError-класс, 2026-08-21)
python scripts/baseline.py                           # воспроизводимый baseline-отчёт
python -m callprofiler doctor                        # здоровье окружения/БД без GPU

# Эксплуатация (бокс)
python -m callprofiler watch                         # основной режим: C:\calls\in → pipeline
python -m callprofiler process FILE --user me
python -m callprofiler dashboard --user me [--port 8765]
python -m callprofiler backup | verify-backup | restore   # T-20: restore боевой БД только так
python -m callprofiler bulk-enrich --user me · graph-replay --user me · biography-run --user me
python -m callprofiler features-build / archetypes-fit / age-estimate [--llm] --user me
```

Пути: проект `C:\pro\callprofiler`, данные `C:\calls\data` (БД `db\callprofiler.db`), вход
`C:\calls\in` (reset не трогает), ref-голос `C:\pro\mbot\ref\manager.wav`.

---

## 5. Стек (не менять без CONSTITUTION-ревизии)

| Слой | Решение | Примечание |
|------|---------|------------|
| ASR | GigaAM-v3-RNNT, локальная HF-модель, in-process, GPU обязателен | Whisper (faster-whisper) — только fallback, C-01 |
| Диаризация | runtime pyannote.audio 4.0.4 + модель speaker-diarization-3.1 + ref-embedding владельца | C-03, решение владельца 2026-08-07 |
| LLM | llama-server (llama.cpp, OpenAI-совместимый), Qwen3.5-9B Q8_0 | `requests.post`, без SDK; JSON-repair парсер |
| БД | sqlite3 + FTS5 + WAL, без ORM; миграции с checksum | `db/` |
| Dashboard | FastAPI + SSE, loopback, request-scoped профиль | T-18 |
| Telegram | python-telegram-bot, opt-in, whitelist полей | C-04 |
| GPU | RTX 3060 12GB, torch 2.6.0+cu124, Python 3.12 | floor у torch/numpy в pyproject снят намеренно |

**Обязательные хаки** (без них не работает; подробности — `rules/bugs.md`):
- `torch.load(weights_only=False)` — ТОЧЕЧНО через `callprofiler.torch_patch.patch_weights_only_false()`
  вокруг загрузки чекпоинтов (T-01); глобальный патч в `__init__` тянул torch даже в `--help`.
- pyannote `from_pretrained`: `use_auth_token=` (3.x) vs `token=` (4.x) — `_load_pretrained` пробует оба.
- pyannote вход — ТОЛЬКО in-memory `{waveform, sample_rate}`: декод по пути идёт через torchcodec,
  чьи DLL на Windows не грузятся (роли молча UNKNOWN при исправном ASR).
- `load()` pyannote идемпотентен ПО ОТПЕЧАТКУ ref-файла, не по факту загрузки (T-10, утечка
  эмбеддинга между профилями).
- Недозаданная `${HF_TOKEN}` на Windows — truthy-мусор; `config._resolve_secret()` → "".
- `restore_backup` после `os.replace` удаляет `-wal`/`-shm` назначения, иначе stale WAL реплеится
  поверх восстановленного файла (T-20, 2026-08-21).

---

## 6. Модель данных (карта — детали в `db/schema.sql`, `rules/db.md`)

```
users ─ contacts (display_name > guessed_name; name_confirmed) ─ calls (status, pipeline_stage, source_md5, role_fragile)
  calls ─ transcripts (+FTS5) · analyses (schema_version v1|v2, raw_response) · promises · events (graph-facts)
graph:     entities · relations · entity_metrics (BS-index) · entity_contact_map   ← DERIVED из events, graph-replay
insight:   contact_features · contact_archetypes · contact_age_* · contact_tiers · deep_facts · promise_outcomes · …
biography: bio_* (своё id-пространство, НЕ равно graph entities)     ops: llm_calls (кэш), migrations-журнал
```
Три id-пространства — `contact_id` ≠ graph `entities.id` ≠ `bio_entities` — связывать только через
`entity_contact_map` / имя; прямое численное совпадение = тихая порча данных (bugs.md 2026-07-02).

---

## 7. Верификация (уроки, которые стоили прогонов)

- **Отчёт субагента ≠ доказательство**: после агента проверить `git diff` и пересчитать ключевую
  метрику канонической функцией (2026-06-06, 2026-08-08 — агент отчитался о правках, которых не было).
- **«Работает без X» верифицировать реальной командой в чистом venv**, не симуляцией отсутствия
  импорта (2026-08-21: `[cloud]` ставил полный ML-стек; restore тихо откатывал БД).
- **Зелёный suite ≠ модуль импортируется**: `biography/prompts.py` полгода падал NameError — ни один
  тест его не импортировал. Отсюда ruff-гейт F821 в CI и в TL;DR.
- CI (`.github/workflows/ci.yml`) зелёный с 2026-08-21 — держать зелёным.

---

## 8. Анти-паттерны (мгновенный red flag)

- SQL без `WHERE user_id = ?`; мутатор с `user_id=None` по умолчанию.
- `except: pass`; `print()` вместо logger в prod-модулях.
- Запись артефакта мимо `artifacts.atomic_*`; правка файла в `audio/originals/`.
- ASR/pyannote и LLM одновременно в VRAM.
- `ALTER TABLE` в обход `db/migrations.py`; правка уже применённой миграции.
- Новая зависимость без «замерено — нужно» в `decisions.md`; ML-пакет в базовых `dependencies`
  (только extra `full`).
- Docker / Redis / PostgreSQL / ORM / Ollama / LangChain / WhisperX / cloud LLM.
- Авто-слияние контактов; вывод пользователю >300 символов или со счётчиками.
- Коммит без `CHANGELOG.md` + `CONTINUITY.md`; `git push --force`; вторая параллельная сессия.

---

## 9. Skills (`.claude/skills/`)

| Skill | Что делает |
|-------|------------|
| `filename-parser/` | 5 форматов имён Android-записей → `CallMetadata` |
| `journal-keeper/` | workflow записи в `CHANGELOG.md` + `CONTINUITY.md` |
| `db-migration.md` | шаблон миграции через `ALL_MIGRATIONS` |
| `fix-bug.md` | порядок разбора бага: репро → root cause → regression test → `bugs.md` |

Новый skill — только при измеренной повторяющейся потребности (Ст. 2.3): узко доменный,
self-contained, со ссылками `file:line`, обновляется вместе с кодом.

---

**Принцип команды:** работающий код важнее идеальной архитектуры, но не важнее конституции.
Конституцию можно менять — только с замером, а не «потому что красивее».
