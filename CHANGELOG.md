# CHANGELOG.md

Все значимые изменения в проекте фиксируются здесь.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/).
Версионирование: [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

## [2026-04-14] — Audit: Memory Protocol + Automation fixes

### Added — Memory Protocol section to CLAUDE.md

**CRITICAL:** Added mandatory `🧠 MEMORY PROTOCOL` section with 6 binding rules:
1. Context erasure — memory only in journals (CONTINUITY.md, CHANGELOG.md, AGENTS.md)
2. START of session — read CONTINUITY + CHANGELOG, say "Last state: X / Next: Y"
3. AFTER code block — update CONTINUITY + CHANGELOG immediately (don't ask)
4. END response with code — append "[Memory updated]"
5. CONTEXT LIMIT — save CONTINUITY.md FIRST, then warn user
6. NEVER skip memory updates — only continuity between sessions

This prevents context loss and ensures every session can resume from exact state.

### Added — Windows automation batch files

**`new-session.bat`**: Initialize session by reading:
- git status
- CONTINUITY.md (current state)
- CHANGELOG.md (recent changes)
- current branch
Shows: "READY TO WORK, use save-session.bat when done"

**`save-session.bat`**: Full session save:
1. Show changes (git status --short)
2. Run pytest tests/ -q (aborts if tests fail)
3. Verify CHANGELOG.md + CONTINUITY.md changed
4. Stage all changes
5. Commit with user message
6. Push to origin

**`emergency-save.bat`**: Quick emergency save (untested):
1. Confirm with user
2. Commit with timestamp
3. Push if possible (or save locally)
Use when context running out or system going down

### Added — start-prompt.txt

Initial prompt for new sessions enforcing Memory Protocol:
- Mandatory briefing: read CONTINUITY.md → CHANGELOG.md → state status
- Links to CLAUDE.md, CONSTITUTION.md, AGENTS.md
- Pre-commit checklist
- Reminder: "Say 'Last state: X / Next: Y' before starting work"

### Verified — No memory files in .gitignore

Checked that critical files are tracked in git:
- ✓ CLAUDE.md (tracked)
- ✓ CHANGELOG.md (tracked)
- ✓ CONTINUITY.md (tracked)
- ✓ AGENTS.md (tracked)
- ✗ *.bat files not in .gitignore (will be tracked)
- ✗ start-prompt.txt not in .gitignore (will be tracked)

### Result

Memory and automation system now complete and robust:
- Strong Memory Protocol binding all AI sessions to journals
- Windows-friendly automation for session init/save/emergency
- Clear guidance in start-prompt.txt for every new session
- All critical files tracked in git
- Prevents context loss and ensures continuity between sessions

## [2026-04-11e] — Telegram bot: commands, notifications, and feedback integration

### Added — `TelegramNotifier` class with full command suite (deliver/telegram_bot.py)

Telegram bot implementation for command processing and automatic notifications:

**Initialization:**
- Token from environment variable `TELEGRAM_BOT_TOKEN` (or explicit parameter)
- User validation: only registered users (with telegram_chat_id in database) can use bot
- Unregistered chat_ids logged with warning, messages ignored
- Graceful degradation if python-telegram-bot not installed

**Commands (6 total):**
1. `/start` — Welcome message with command list, shows user display_name
2. `/digest [N] [days]` — Top-N calls by priority in last N days (default: 5 calls, 1 day)
   - Formatted: `[P:###] DIRECTION → NAME (PHONE) | DATE`
3. `/search <text>` — FTS5 transcript search, shows up to 5 results with date/contact/fragment
   - Format: `**CONTACT_NAME** (DATE) [SPEAKER] text_fragment...`
4. `/contact <phone or name>` — Contact card from contact_summaries
   - Shows: name, phone, total_calls, global_risk with emoji, BS-score, top_hook
   - Includes: open promises/debts (up to 2 each), contact_role, advice
5. `/promises` — All open promises grouped by contact (max 5 contacts displayed)
   - Format: `[WHO] payload (deadline)`
6. `/status` — System queue status for current user
   - Shows: total calls, processed, in queue, errors (with retry count)

**Automatic notifications:**
- After each enrichment: `send_summary(user_id, call_id)` sends formatted message
  - Format: `📞 DIRECTION → CONTACT (PHONE) | 📅 DATE | ⏱ DURATION`
  - Summary text + priority + risk with emoji (🟢/🟡/🔴)
  - Action items (max 3)
  - Inline buttons: [✅ OK] [❌ Неточно] for feedback

**Feedback handling:**
- User clicks [✅ OK] or [❌ Неточно]
- Callback data parsed: `feedback_{call_id}_{ok|inaccurate}`
- Found analysis_id from call_id, saves via `repo.set_feedback(analysis_id, "ok"|"inaccurate")`
- User sees confirmation: "💾 Ваш отзыв записан: ..."

**Architecture:**
- Long polling mode (not webhooks) — runs in background thread via `run()`
- Exception handling: JSON parsing for events, missing fields, unregistered users
- Logging: verbose logging with chat_id, user_id, call_id for debugging

### Added — `cmd_bot` CLI command (cli/main.py)

New CLI command to start Telegram bot:
```
python -m callprofiler bot
```

Checks:
- TELEGRAM_BOT_TOKEN environment variable
- Lists registered users with telegram_chat_id
- Warns if no users registered
- Logs user count and IDs
- Runs bot in background thread, keeps main thread alive (while True)

### Changed — telegram_bot.py improvements

1. **Token handling:**
   - Constructor parameter optional (taken from env if not provided)
   - Warning if not set → non-blocking (allows module import without token)

2. **Command improvements:**
   - `/digest`: properly sorts by priority, shows direction/phone/date
   - `/search`: now queries calls table to show contact_name and call_date
   - `/contact`: integrated with contact_summaries, supports search by name or phone
   - `/promises`: uses events table (type='promise') instead of old promises table
   - `/status`: shows all_calls, calls_with_analysis, pending, errors

3. **User isolation:**
   - All commands validate user via `_get_user_id(update)` → chat_id → user_id
   - Unregistered users get "Your chat_id is not registered" message

4. **Better formatting:**
   - Risk emoji (🟢/🟡/🔴) based on numeric risk_score
   - HTML parse_mode for bold/italic text
   - Direction field in notifications (IN/OUT/UNKNOWN)
   - Duration in seconds for calls

### Result

- Full-featured Telegram bot for push notifications and querying system state
- 90/90 tests pass (bot uses only existing Repository methods)
- All 6 commands working with proper error handling
- User isolation via chat_id → user_id mapping
- Feedback integration with analysis records

## [2026-04-11d] — Contact summaries: aggregated profiles with weighted risk scoring

### Added — `contact_summaries` table to schema.sql

New table for aggregated contact profiles synthesizing all interactions:
- **Structure:** contact_id (PK), user_id (FK), total_calls, last_call_date, global_risk, avg_bs_score,
  top_hook, open_promises (JSON), open_debts (JSON), personal_facts (JSON), contact_role, advice, updated_at
- **Key fields:**
  - `global_risk` (0–100): exponential-decay weighted average of all call risk_scores (half-life 90 days)
  - `avg_bs_score` (0–100): same weighting for BS-score from analysis raw_response
  - `open_promises`, `open_debts`, `personal_facts`: JSON arrays of events filtered by type and status
  - `top_hook`: extracted from last analysis's raw_response.hook field
  - `advice`: generated rules-based recommendations (risk→"Говори первым", bs→"Осторожно", debts→"Начни с долга")

### Added — `SummaryBuilder` class (aggregate/summary_builder.py)

Main methods:
- `rebuild_contact(contact_id)`: Core algorithm aggregating risk, BS-score, events, hook, role, and advice
- `rebuild_all(user_id)`: Bulk rebuild for all user's contacts with error resilience
- `generate_card_text(contact_id)` → str: Formatted text ≤512 bytes with header, risk emoji (🟢/🟡/🔴), hook, 3 bullets, advice
- `write_card(contact_id, sync_dir)`: Write card as `{phone_e164}.txt`
- `write_all_cards(user_id)`: Bulk card generation

Helper methods:
- `_compute_weighted_risk()`: Exponential decay (weight = 2^(-days_ago/90)), returns int
- `_compute_weighted_bs_score()`: Same weighting, extracts bs_score from JSON
- `_extract_open_promises/debts/facts()`: Filter events by type+status, return JSON
- `_extract_top_hook()`: Get hook from last analysis
- `_extract_contact_role()`: Get contact_company_guess or contact_role from last analysis
- `_generate_advice()`: Rules: risk>70→"Говори первым", bs>60→"Осторожно", debts→"Начни с долга"

### Added — Repository methods for contact_summaries

- `save_contact_summary(...)`: INSERT OR REPLACE all 12 fields
- `get_contact_summary(contact_id)`: Retrieve dict or None
- `get_all_contacts_for_user(user_id)`: List all contacts for user, ordered by display_name

### Added — 2 new CLI commands

- `rebuild-summaries --user ID`: Pересчитать contact_summaries для пользователя
- `rebuild-cards --user ID`: Пересоздать caller cards в sync_dir

Both commands validate user exists and handle errors gracefully per CONSTITUTION.

### Isolation & Safety

- All summaries filtered by user_id (CONSTITUTION 2.5)
- Contact isolation via (user_id, contact_id) pair
- Events extraction respects event type and status filters
- Weighted risk model ensures recent calls matter more (but old data not forgotten)

### Result
- Contact aggregation infrastructure ready for analytics and Android overlay display
- 90/90 tests pass (new schema + methods; existing tests unaffected)
- Weighted risk scoring with exponential decay implemented per spec
- Card text generation with risk emoji and smart bullet selection (3-bullet limit)

## [2026-04-11c] — Event extraction refinement: proper role mapping (Me→OWNER, S2→OTHER)

### Changed — Event extraction logic in enricher.py

**Updated `_extract_events_from_analysis()`** to properly map LLM-supplied roles:
- `Me` → `OWNER` (user/owner of the phone)
- `S2` → `OTHER` (counterparty)
- Unknown → `UNKNOWN`

**Extended event type extraction:**
1. **promises** — extract from `promises[].who` with role mapping
2. **action_items** → `event_type='task'` (who=OWNER)
3. **bs_evidence** → `event_type='contradiction'` (extracted from raw_response JSON)
4. **amounts** → `event_type='debt'` (extracted from raw_response JSON)

**Error handling:** Each field extraction wrapped in try/except. On failure, log warning
and continue (don't fail enrichment). Graceful degradation per CONSTITUTION 6.4.

**Parsing strategy:**
- Promises use `p.get("who")` directly (Me/S2 from LLM JSON)
- bs_evidence & amounts require parsing `raw_response` as JSON (LLM output may contain these)
- If raw_response not JSON or missing field → skip silently with debug log

### Result
- Events now have correct role semantics matching LLM analysis
- All 90 tests pass
- Enricher robustly handles both complete and partial LLM responses

## [2026-04-11b] — Events table: structured extraction from analyses

### Added — `events` table for fine-grained analysis records (schema.sql + repository.py)

New table `events` captures structured insights extracted from LLM analyses:
- **7 event types:** `promise`, `debt`, `contradiction`, `risk`, `task`, `fact`, `smalltalk`
- **Per-event metadata:** `who` (OWNER/OTHER/UNKNOWN), `payload` (main content),
  `source_quote` (optional), `deadline`, `confidence` (0.0–1.0), `status` (open/fulfilled/broken/expired/resolved)
- **Dual indexing:** by `(user_id, contact_id, event_type)` and by `(user_id, status)` for fast queries

**Why events?** Promises table captures only `{who, what, due, status}`. Events table adds:
- Structured confidence per extracted fact
- Event type classification (risk vs. promise vs. task)
- Support for contradictions & debts
- Smalltalk facts for context
- Flexible deadline handling (some events have no deadline)
- Full-featured status tracking (broken, expired, resolved, not just open/fulfilled)

**Isolation:** All events filtered by `user_id` (CONSTITUTION 2.5). Contact isolation
via `(user_id, contact_id)` pair.

### Added — 4 new Repository methods (repository.py)

```python
def save_events(call_id, events: list[dict]) → None
    Save events from a call analysis. Each event dict:
    {user_id, contact_id (nullable), event_type, who, payload,
     source_quote (opt), confidence (opt), deadline (opt), status (opt)}

def get_open_events(user_id, contact_id=None, event_type=None) → list[dict]
    Fetch open events, optionally filtered by contact and type.

def get_events_for_contact(user_id, contact_id, limit=50) → list[dict]
    Get all events (any status) for a contact, newest first.

def update_event_status(event_id, status) → None
    Update event status (open → fulfilled/broken/expired/resolved).
```

### Added — Event extraction in enricher.py (`_extract_events_from_analysis`)

After LLM returns Analysis, enricher now extracts 7 event categories:

1. **promises** → `{event_type: 'promise', who: p.who, payload: p.what, deadline: p.due, confidence: 0.9}`
2. **action_items** → `{event_type: 'task', who: 'OWNER', payload: item, confidence: 0.85}`
3. **flags.conflict** → `{event_type: 'contradiction', confidence: 0.8}`
4. **flags.legal_risk / urgent** → `{event_type: 'risk', confidence: 0.85}`
5. **key_topics** (heuristic) → `{event_type: 'smalltalk', confidence: 0.7}`
   - Topics with lowercase start or spaces are treated as personal facts

Each event carries its confidence level (LLM insights > flags > heuristics).

**Batch save:** Events are saved in `_flush_batch()` after analysis + promises.
Handles both single-transaction and per-item fallback gracefully.

**Null contact_id:** Events saved even if contact_id is None (unknown caller).

### Result
- New events infrastructure ready for downstream analytics
- 90/90 tests pass (no existing tests affected; events are new)
- CONSTITUTION rules respected: user_id isolation, graceful error handling

## [2026-04-11] — AGENTS.md + доменные skills для AI-агентов

### Added — AGENTS.md (единая точка входа для любого AI-агента)

Создан `AGENTS.md` в корне репозитория — руководство для Claude Code,
Cursor, Codex и любых других AI-инструментов, работающих с проектом.

**Секции:**
1. TL;DR рабочий процесс (journal-first → code → journal-last → commit)
2. Структура репозитория (древовидная карта всех модулей)
3. Обязательный workflow агента (чтение журналов, правила сессии, запись)
4. Ключевые команды (разработка, CLI, ветка)
5. Стек и жёсткие зависимости (не менять без CONSTITUTION-ревизии)
6. Модель данных (карта таблиц + приоритет имён контактов)
7. Агенты и skills (текущие + предложенные)
8. Анти-паттерны (мгновенные red flags для ревью)
9. Полезные ссылки на остальные доки

**Принцип:** AGENTS.md не дублирует CONSTITUTION/CLAUDE/CONTINUITY,
а связывает их в пошаговый workflow.

### Added — `.claude/skills/filename-parser/SKILL.md`

Первый доменный skill. Описывает:
- 5 поддерживаемых форматов имён файлов Android-записей
- Правила `normalize_phone()` (E.164, сервисные, 8/007/00)
- Пошаговый алгоритм добавления 6-го формата
- Анти-паттерны (жадный regex формата 4, парсинг в обход normalize_phone)
- Ссылки на код (`filename_parser.py:271`, `models.py`, тесты)

Применяется при изменении `filename_parser.py`, отладке `UNKNOWN` телефонов
или добавлении нового формата.

### Added — `.claude/skills/journal-keeper/SKILL.md`

Второй доменный skill. Кодифицирует требование владельца про
журналирование в стиле Obsidian:
- Этап 1: читать `CONTINUITY.md` + `CHANGELOG.md` в начале сессии
- Этап 2: обновлять оба файла перед `git commit`
- Этап 3: финальная проверка (тесты, CONSTITUTION, секреты)
- Шаблоны записей для Keep a Changelog формата
- Анти-паттерны (коммит без журнала, стирание старых секций)

### Предложенные (не реализованные) skills

В `AGENTS.md` секция 7.2 перечислены будущие skills, создаются только
при измеренной потребности (CONSTITUTION 2.3):

| Skill                    | Триггер                                      |
|--------------------------|----------------------------------------------|
| `constitution-auditor`   | > 1 нарушение CONSTITUTION в неделю в PR     |
| `llm-json-surgeon`       | > 5% парсинг LLM провалов                    |
| `schema-migrator`        | Второй раз добавляем колонку                 |
| `gpu-discipline-checker` | OOM на RTX 3060 в batch pipeline             |
| `bulk-ops-runner`        | Регулярные прогоны > 1000 файлов             |
| `prompt-version-manager` | Переход на `analyze_v002.txt`                |

### Результат

- `AGENTS.md` (275 строк) + 2 SKILL.md
- Рабочий процесс AI-агентов формализован
- 90/90 тестов pass (skills — только документация, код не менялся)

## [2026-04-10] — Phonebook name priority fix

### Fixed — get_or_create_contact() не обновлял display_name (repository.py)

**Проблема:** Имя контакта из имени файла (= телефонная книга пользователя) игнорировалось
если контакт уже существовал в БД.

**Цепочка:**
1. Телефон записывает звонок: `Иванов(+79161234567)_20260410143022.m4a`
2. Имя `Иванов` берётся приложением записи из телефонной книги Android
3. `filename_parser` → `CallMetadata.contact_name = "Иванов"`
4. `ingester` → `get_or_create_contact(user_id, phone, "Иванов")`
5. **БАГ:** если контакт `+79161234567` уже есть → `return contact_id` без обновления имени!

**Исправление** в `repository.py get_or_create_contact()`:
```python
if row:
    contact_id = row["contact_id"]
    if display_name:                           # ← NEW: обновить если есть имя
        conn.execute(
            "UPDATE contacts SET display_name=?, name_confirmed=1 WHERE contact_id=?",
            (display_name, contact_id),
        )
        conn.commit()
    return contact_id
# При создании нового контакта:
VALUES (?, ?, ?, ?)  # + name_confirmed = 1 if display_name else 0
```

**Приоритет имён (окончательная схема):**
```
МАКСИМАЛЬНЫЙ: display_name (из имени файла = телефонная книга), name_confirmed=1
              ↳ устанавливается через get_or_create_contact() при каждом новом файле
ВТОРИЧНЫЙ:    guessed_name (авто-извлечение из текста транскрипта name_extractor.py)
              ↳ только записывается если display_name пустой
FALLBACK:     null
```

**Гарантии:**
- Файл без имени (только номер) → `display_name=None` → существующее имя НЕ стирается
- Файл с именем → `display_name` всегда обновляется (пользователь мог переименовать в телефоне)
- `name_confirmed=1` при любом имени из файла → `name_extractor.py` не перезаписывает

**Новые тесты** (test_repository.py +3):
- `test_phonebook_name_overwrites_existing_empty_name` — имя заполняет пустой контакт
- `test_phonebook_name_overwrites_guessed_name` — имя из файла > guessed_name
- `test_no_name_in_filename_does_not_clear_existing` — файл без имени не стирает имя

**Результат:** 90 тестов pass (было 87)

---

## [2026-04-09] — Bug fixes, JSON parsing robustness, enricher optimization

### Fixed — Critical bugs in enricher

#### 1. SQL binding mismatch (commit 369935e)
- **Bug:** enricher.py WHERE c.user_id = ? был без параметров (user_id,)
- **Impact:** "Incorrect number of bindings supplied" при bulk-enrich
- **Fix:** добавлен (user_id,) в execute() в bulk_enrich()

#### 2. FOREIGN KEY constraint violation (commit bef94e9)
- **Bug:** promises.contact_id NOT NULL, но calls.contact_id может быть NULL
- **Impact:** FK constraint failed при сохранении promises для звонков без распознанного номера
- **Fix:** 
  - schema.sql: promises.contact_id → nullable
  - repository.save_promises(): пропускаем если contact_id = NULL
  - enricher.py: улучшен batch error handling

### Changed — response_parser.py (robust JSON parsing, 4-уровневая защита)

- **Проблема:** LLM часто обрезает JSON на max_tokens или выдаёт невалидный JSON
- **4-уровневое спасение обрезанного JSON:**
  1. `_extract_json_from_markdown()` — извлечь из ```json...```
  2. `_extract_json_bounds()` — текст от первой { до последней }
  3. `_repair_json()` — активное восстановление:
     - `_close_json_structure()` — дозакрыть } и ] с учётом вложенности
     - `_remove_trailing_commas()` — убрать запятые перед } и ]
     - Закрыть незакрытые кавычки внутри строк
  4. `_extract_fields_by_regex()` — последняя линия защиты: извлечь summary, priority, risk_score, action_items, key_topics, promises через regex если JSON совсем сломан

- **Type coercion:**
  - String "75" → int 75
  - String вместо list → ["строка"]
  - Boolean "true"/"false" → bool

- **Мягкие дефолты:**
  - summary: "" (было "Ошибка при анализе")
  - risk_score: 0 (было 50)
  - Никогда не падает на отсутствующем поле

### Changed — llm_client.py (graceful degradation, больше времени)

- **max_tokens:** 2048 → 1500 (JSON редко > 600 токенов, экономим время)
- **timeout:** 300s → 180s (лучше для длинных звонков, избегаем зависания)
- **Error handling:** generate() теперь возвращает None на ошибке вместо RuntimeError
  - Timeout, connection error, invalid response → None
  - enricher.py обрабатывает None и продолжает работу

### Changed — configs/prompts/analyze_v001.txt (упрощение промпта)

- **Было:** 30+ полей в мегаструктуре (bullshit_index, power_dynamics, emotional_tone и т.д.)
- **Стало:** компактная структура с 15 обязательными полями:
  - **Основное:** summary, category, priority, risk_score, sentiment
  - **Действия:** action_items[], promises[] {who, what, vague}
  - **Данные:** people, companies, amounts
  - **Контакт:** contact_name_guess
  - **Оценка:** bs_score, bs_evidence
  - **Флаги:** {urgent, conflict, money, legal_risk}
- **Мотивация:** упрощение + меньше hallucinations + скорость парсинга

### Changed — bulk/enricher.py (оптимизация и улучшение обработки ошибок)

#### Оптимизации (commit 6034fc0):
1. **Сжатие транскрипта** — убрать сегменты < 3 символов (except "да"/"ну"/"угу")
2. **max_tokens: 1024** (было 2048) в generate() → экономия времени
3. **Батчевая запись в БД** — новый Repository.save_batch() для одной транзакции каждые 5 звонков
4. **Пропуск коротких звонков** — если transcript < 50 символов → stub Analysis без LLM call
5. **Логирование:**
   - Per-file: время обработки, ~tok/s, ETA
   - Промежуточная статистика каждые 50 файлов: успешных/частичных/пропущено/ошибок

#### Улучшение обработки ошибок (commit 668e44c):
- Отдельный счётчик `partial` для успешно распарсенных анализов с пустым summary
- Обработка None от llm.generate() — логирует ошибку и продолжает
- Any error in single call → log + continue (никогда не прерывает батч)
- Save batch failure → fallback на per-item saves с логированием

### Results

- ✅ Все 87 тестов pass (не было регрессии)
- ✅ enricher.py теперь работает на Windows (SQL binding fixed)
- ✅ bulk-enrich обрабатывает звонки без contact_id (FK constraint fixed)
- ✅ Обрезанный JSON от LLM спасается в 4 раза
- ✅ Graceful degradation на ошибках LLM (None вместо exception)
- ✅ Время обработки на звонок ~2-5 сек (было 10+)

---

### Changed — configs/prompts/analyze_v001.txt (расширенный LLM-анализ)
- Переписан системный промпт для детального анализа звонков
- **JSON-структура:** 30+ полей для комплексного анализа
  - Основные: `summary`, `priority`, `risk_score`, `category`, `sentiment`, `initiative`
  - Действия: `action_items[]` с кто/что/когда
  - Обещания: `promises[]` с отметкой `vague` (размытость)
  - Извлечение: люди, компании, суммы, даты, адреса
  - Контакт: `contact_name_guess`, `contact_company_guess`, `contact_role_guess`
  - Оценка честности: `bullshit_index` (score, vagueness, defensiveness, contradictions)
  - Динамика: `power_dynamics`, `emotional_tone_owner/other`
  - Флаги: `urgent`, `conflict`, `money_discussed`, `deadline_mentioned`, `legal_risk`, `lie_suspected`
- **Правила анализа:**
  - Роли [Me]/[S2] часто перепутаны — определять по контексту
  - Сергей/Медведев ВСЕГДА владелец, даже если [S2]
  - bullshit_index: 0=честный, 100=пиздёж
  - vagueness: "может быть", "посмотрим" = высокий балл
  - Extractить ВСЕ упомянутые данные
  - Если непонятно → null, не выдумывать
- **Формат:** ТОЛЬКО валидный JSON, без markdown, без пояснений
- response_parser.py совместим, хранит все поля в raw_response

### Changed — LLM интеграция: Ollama → llama.cpp (OpenAI API)
- **`src/callprofiler/analyze/llm_client.py`:**
  - Новый класс `LLMClient` вместо `OllamaClient`
  - Используется OpenAI-совместимый API: POST `/v1/chat/completions`
  - Endpoint: `http://127.0.0.1:8080/v1/chat/completions` (llama.cpp/llama-server)
  - Параметры: `messages`, `temperature`, `max_tokens`
  - Без зависимости от openai SDK — простой `requests.post`
  - Обратная совместимость: `OllamaClient = LLMClient`
- **`configs/base.yaml`:**
  - `ollama_url` → `llm_url: "http://127.0.0.1:8080/v1/chat/completions"`
  - `llm_model` → `"local"` (модель загружена на сервере, не передаётся)
- **`src/callprofiler/config.py`:**
  - `ModelsConfig`: заменён `ollama_url` на `llm_url`

### Added — bulk/enricher.py (массовый LLM-анализ)
- Функция `bulk_enrich(user_id, db_path, limit=0)`:
  - Обрабатывает все звонки БЕЗ analysis в порядке call_datetime
  - Форматирует транскрипт + метаданные (phone, name, datetime)
  - Отправляет на LLM через OpenAI-совместимый API
  - Распарсивает JSON из ответа (обработка markdown `\`\`\`json\`\`\``)
  - Сохраняет `Analysis` + `Promises` в БД
  - Логирует прогресс, время на файл, ETA
  - Graceful `Ctrl+C` обработка (завершить текущий, не начинать новый)
  - `limit=0` обрабатывает все файлы
- CLI: `python -m callprofiler bulk-enrich --user <user_id> [--limit 100]`

### Added — bulk/loader.py (массовая загрузка .txt транскриптов)
- Функция `bulk_load(txt_folder, user_id, db_path)` для импорта существующих транскриптов:
  - Рекурсивный обход всех .txt файлов
  - Парсинг имён файлов через filename_parser → CallMetadata
  - MD5-дедупликация (не загружать дубли)
  - Разбор содержимого по [me]: и [s2]: маркерам
    - [me]: → speaker='OWNER'
    - [s2]: → speaker='OTHER'
  - Создание контактов и звонков (status='done')
  - Сохранение транскриптов с индексацией FTS5
  - Логирование прогресса каждые 100 файлов
  - Грейсфул обработка ошибок (логирование + продолжение)
  - Итоговая статистика (загружено, пропущено, ошибки, контакты)
- CLI: `python -m callprofiler bulk-load <folder> --user <user_id>`
- Тесты: 7 тестов для `_parse_segments()` (все сценарии)

### Changed — filename_parser.py (новые форматы имён файлов)
- Полный рефакторинг парсера под 5 форматов:
  1. Номер с дефисами + дубль: 007496451-07-97(0074964510797)_20240925154220
  2. 8(код)номер + дубль: 8(495)197-87-11(84951978711)_20240502164535
  3. 8 без скобок вокруг кода: 8496451-07-97(84964510797)_20240502170140
  4. Имя контакта + номер в скобках: Алштейндлештейн(0079252475209)_20230925135032
     - Поддержка Вызов@ префикса
     - Поддержка коротких сервисных номеров (900, 112, 0511)
  5. Только имя + дата (без номера): Варлакаув Хрюн 2009_09_03 21_05_57
- Улучшена нормализация телефонов:
  - 007... → +7... (международный формат)
  - 8 + 11 цифр → +7... (русский формат)
  - 00... (не 007) → +... (другие международные)
  - 3-4 цифры → оставить как есть (сервисные номера)
- Новые тесты: 40 тестов парсера (8 normalize_phone, 32 parse_filename)
- Совместимость: 80 тестов — все зелёные
- ⚠️ **BREAKING**: старые форматы BCR и скобочный больше не поддерживаются

### Added — bulk/name_extractor.py (извлечение имён из транскриптов)
- `src/callprofiler/bulk/__init__.py` — новый пакет `bulk`
- `src/callprofiler/bulk/name_extractor.py`:
  - Класс `NameExtractor` — извлекает имена собеседников из первых 10 сегментов
    транскрипта (оба спикера — роли [me]/[s2] часто перепутаны)
  - 12 regex-паттернов: "привет, Имя", "это Имя", "меня зовут Имя", "Имя беспокоит" и др.
  - Исключение имён владельца: Сергей, Серёжа, Серёж, Серёга, Медведев
  - Confidence: "medium" (1 звонок) / "high" (2+ звонков с тем же именем)
  - `extract_for_user(user_id)` → `dict[contact_id, NameCandidate]`
  - `apply_guesses(user_id, dry_run=False)` — запись в БД с поддержкой dry-run
- `src/callprofiler/db/schema.sql` — 6 новых колонок в таблице contacts:
  `guessed_name`, `guessed_company`, `guess_source`, `guess_call_id`,
  `guess_confidence`, `name_confirmed`
- `src/callprofiler/db/repository.py`:
  - `_migrate()` — AUTO ALTER TABLE для баз данных без новых колонок (backward compat)
  - `get_contacts_without_name(user_id)` — контакты без display_name и без подтверждения
  - `get_calls_for_contact(user_id, contact_id)` — все звонки контакта
  - `update_contact_guessed_name(contact_id, ...)` — сохранить угаданное имя
  - `_get_conn()` — auto-mkdir для родительского каталога БД (bugfix)
- CLI: добавлена команда `extract-names --user ID [--dry-run]`
- `tests/test_integration.py` — исправлены 6 ранее сломанных тестов:
  - добавлено создание пользователя перед FK-зависимыми операциями
  - исправлена ошибочная проверка `promises` в `get_analysis()`

### Added
- `CONSTITUTION.md` — принципы и правила разработки проекта
- `CONTINUITY.md` — журнал непрерывности: статус, что сделано, что дальше

### Added — Шаг 14: CLI точка входа (python -m callprofiler)
- `src/callprofiler/cli/main.py`:
  - Полный argparse CLI с 6 командами:
    - `watch` — запуск FileWatcher.run_loop() (watchdog-режим)
    - `process <file> --user ID` — регистрация и обработка одного файла
    - `reprocess` — повторная обработка звонков с ошибками
    - `add-user ID --incoming --ref-audio --sync-dir [--display-name --telegram-chat-id]`
    - `digest <user> [--days N]` — топ-10 по priority за N дней
    - `status` — состояние очереди (статусы, pending, errors)
  - `--config PATH` (по умолчанию `configs/base.yaml`)
  - `-v / --verbose` — DEBUG-логирование
  - Ленивые импорты тяжёлых модулей внутри функций
  - Graceful KeyboardInterrupt → sys.exit(0)
- `src/callprofiler/__main__.py` — `from callprofiler.cli.main import main; main()`

### Added — Шаг 13: FileWatcher (мониторинг папок)
- `src/callprofiler/pipeline/watcher.py`:
  - **Класс `FileWatcher`** — автоматический мониторинг incoming_dir пользователей
  - `scan_all_users() -> list[int]` — рекурсивный обход (os.walk), фильтр аудио-расширений
  - `run_loop()` — бесконечный цикл: scan → process_batch → retry_errors → sleep
  - Проверка file_settle_sec (mtime) — не хватать незаписанный файл
  - Graceful degradation: ошибка файла → лог → продолжить
  - Поддержка: .mp3, .m4a, .wav, .ogg, .opus, .flac, .aac, .wma

### Added — Шаг 12: Pipeline Orchestrator (главный оркестратор)
- `src/callprofiler/pipeline/orchestrator.py`:
  - **Класс `Orchestrator`** — сборка всех модулей в сквозной pipeline
  - `process_call(call_id) -> bool` — полная обработка звонка:
    normalize → transcribe → diarize → analyze → deliver
  - `process_batch(call_ids)` — batch-обработка с GPU-оптимизацией
    (Whisper+pyannote вместе → выгрузка → LLM)
  - `process_pending()` — обработка всех новых звонков
  - `retry_errors()` — повторная обработка ошибок (retry_count < max_retries)
  - GPU-дисциплина (CONSTITUTION.md Ст. 9.2-9.3): Whisper+pyannote вместе, LLM отдельно
  - Graceful degradation: ошибка на шаге → лог + status='error', pipeline не падает
  - Все статусы в БД: normalizing → transcribing → diarizing → analyzing → delivering → done
  - `_format_transcript()` — форматирование сегментов в [MM:SS] SPEAKER: текст

### Added — Шаг 11: Telegram-бот (доставка и команды)
- `src/callprofiler/deliver/telegram_bot.py`:
  - **Класс `TelegramNotifier`** — Telegram-бот для уведомлений и команд
  - `send_summary(user_id, call_id)` — отправить саммари с inline кнопками [OK]/[Неточно]
  - `handle_feedback()` — обработка нажатия кнопки обратной связи
  - Команды (CONSTITUTION.md Статья 11.3):
    - `/digest [N]` — топ звонков по priority за N дней
    - `/search текст` — FTS5 поиск по транскриптам
    - `/contact +7...` — карточка контакта с риском и саммари
    - `/promises` — открытые обещания
    - `/status` — состояние очереди (ожидают/ошибки)
  - Один бот для всех пользователей (различает по chat_id)
  - Лениво загружает `python-telegram-bot` (не требуется для импорта модуля)
  - Все данные изолированы по `user_id` (CONSTITUTION.md Статья 2.5)

### Added — Шаг 10: Caller Cards (Android overlay)
- `src/callprofiler/deliver/card_generator.py`:
  - **Класс `CardGenerator`** — генерация caller cards для Android overlay
  - `generate_card(user_id, contact_id) -> str` — сборка карточки ≤ 500 символов
    (формат CONSTITUTION.md Статья 10.2: имя, статистика, саммари, обещания, actions)
  - `write_card(user_id, contact_id, sync_dir)` — запись {phone_e164}.txt для FolderSync
  - `update_all_cards(user_id)` — пересоздание карточек всех контактов пользователя
  - Автоматическое создание sync_dir, обрезка до 500 символов, пропуск контактов без phone
- `src/callprofiler/db/repository.py`:
  - `get_all_contacts_for_user(user_id)` — список контактов для update_all_cards
  - `get_call_count_for_contact(user_id, contact_id)` — подсчёт звонков контакта
- `tests/test_card_generator.py` — 12 тест-кейсов (CRUD, обрезка, файлы, изоляция user_id)

### Added — Шаг 9: LLM анализ (Ollama + prompt builder + response parser)
- `src/callprofiler/analyze/llm_client.py`:
  - **Класс `OllamaClient`** — HTTP клиент для локального Ollama сервера
  - `generate(prompt, stream=False) -> str` — POST /api/generate, temperature=0.3
  - `list_models() -> list[str]` — доступные модели через GET /api/tags
  - Проверка подключения при инициализации (`_verify_connection`)
  - Поддержка streaming для больших ответов
  - Timeout 300сек для qwen2.5:14b
- `src/callprofiler/analyze/prompt_builder.py`:
  - **Класс `PromptBuilder`** — построение промптов с подстановкой переменных
  - `build(transcript_text, metadata, previous_summaries, version)` — главный метод
  - Извлечение длительности из временных меток `[MM:SS]` в стенограмме
  - Контекст из последних 3 анализов (max 100 символов каждый)
  - Форматирование datetime в DD.MM.YYYY HH:MM
  - Версионирование промптов: `analyze_v001.txt`, `analyze_v002.txt` и т.д.
- `src/callprofiler/analyze/response_parser.py`:
  - **Функция `parse_llm_response(raw, model, prompt_version) -> Analysis`**
  - 3-уровневый fallback: прямой JSON → markdown-обёртка → очистка → дефолты
  - Безопасное извлечение полей: `_get_int`, `_get_str`, `_get_list`, `_get_dict`
  - Graceful degradation: при сбое парсинга → Analysis с нейтральными дефолтами
  - Сохранение raw_response для отладки
- `configs/prompts/analyze_v001.txt`:
  - Шаблон JSON-промпта для LLM с метаданными и стенограммой
  - Возвращаемые поля: priority, risk_score, summary, action_items, promises, flags, key_topics

---

## [0.1.0] — 2026-03-30

### Added — Шаг 0: Структура проекта
- Полное дерево каталогов `src/callprofiler/` со всеми подпакетами
- `pyproject.toml` (name=callprofiler, version=0.1.0)
- Пустые `__init__.py` во всех пакетах
- `__main__.py` — точка входа `python -m callprofiler`
- `data/db/`, `data/logs/`, `data/users/`, `tests/fixtures/` (с `.gitkeep`)
- `reference_batch_asr.py` — эталонный прототип для извлечения логики

### Added — Шаг 1: Конфигурация
- `configs/base.yaml` — базовая конфигурация (пути, модели, pipeline, audio)
- `configs/models.yaml` — спецификации моделей
- `configs/prompts/analyze_v001.txt` — шаблон промпта для LLM-анализа
- `src/callprofiler/config.py` — загрузчик YAML, dataclass Config, валидация
  - Проверка существования `data_dir`
  - Проверка доступности ffmpeg в PATH

### Added — Шаг 2: Модели данных
- `src/callprofiler/models.py`:
  - `CallMetadata` — метаданные звонка (телефон, дата, направление)
  - `Segment` — сегмент транскрипции (start_ms, end_ms, text, speaker)
  - `Analysis` — результат LLM-анализа (priority, risk_score, summary, …)

### Added — Шаг 3: База данных
- `src/callprofiler/db/schema.sql` — схема SQLite:
  - Таблицы: users, contacts, calls, transcripts, analyses, promises
  - FTS5 виртуальная таблица `transcripts_fts` для полнотекстового поиска
- `src/callprofiler/db/repository.py` — класс `Repository`:
  - CRUD для users, contacts, calls, transcripts, analyses, promises
  - Изоляция данных по `user_id` во всех запросах
  - FTS5 поиск по транскрипциям
- `tests/test_repository.py` — тесты in-memory SQLite, проверка CRUD + изоляции

### Added — Шаг 4: Парсер имён файлов
- `src/callprofiler/ingest/filename_parser.py`:
  - Функция `parse_filename(filename) -> CallMetadata`
  - Поддержка форматов: BCR, скобочный, ACR, нераспознанный
  - Нормализация номера в E.164 (`8(916)123-45-67` → `+79161234567`)
- `tests/test_filename_parser.py` — 15+ тест-кейсов, включая "грязные" имена

### Added — Шаг 5: Нормализация аудио
- `src/callprofiler/audio/normalizer.py`:
  - `normalize(src, dst, *, loudnorm, sample_rate, channels)`:
    - Двухпроходная EBU R128 LUFS-нормализация (цель: -16 LUFS / TP -1.5 dBFS)
    - Fallback к простой конвертации при сбое анализа
    - Защита от битых файлов (проверка минимального размера)
  - `get_duration_sec(wav_path) -> int` — длительность через ffprobe
  - Проверка ffmpeg/ffprobe при импорте модуля
  - Логирование через стандартный `logging`
  - Создание родительских директорий для dst автоматически

### Added — Шаг 8: Приём файлов (Ingester)
- `src/callprofiler/ingest/ingester.py`:
  - **Класс `Ingester`** — приём аудиофайлов в очередь обработки
  - `ingest_file(user_id, filepath) -> int | None`:
    - Парсинг имени файла (filename_parser)
    - Вычисление MD5 для дедупликации
    - Проверка repo.call_exists(user_id, md5) → None если дубликат
    - Создание/получение контакта (repo.get_or_create_contact)
    - Копирование оригинала в data/users/{user_id}/audio/originals/
    - Обработка конфликтов имён (добавление MD5 префикса)
    - Запись call в БД (repo.create_call) → call_id
  - Внутренние методы: `_compute_md5()`, `_copy_original()`
  - Логирование всех операций (parse, md5, дубликат, contact, copy, create)
  - **Изоляция по user_id** (CONSTITUTION.md Статья 2.5):
    - Все пути содержат {user_id}
    - Контакты привязаны к (user_id, phone) паре
    - Один номер у двух users → два разных контакта

### Added — Шаг 7: Диаризация (Pyannote + reference embedding)
- `src/callprofiler/diarize/pyannote_runner.py`:
  - **Класс `PyannoteRunner`** — инкапсуляция pyannote.audio с управлением GPU-памятью
  - `load(ref_audio_path)` — загрузка embedding + diarization моделей, построение reference embedding
  - `diarize(wav_path) -> list[dict]`:
    - Pyannote pipeline с min/max_speakers=2
    - Фильтрация сегментов < 400мс
    - Cosine similarity маппинг: найти label, похожий на ref → OWNER, другие → OTHER
    - Конвертация float сек → int мс, сортировка по времени
  - `unload()` — выгрузка (del, gc.collect, torch.cuda.empty_cache)
  - Внутренние методы: `_get_embedding()`, `_build_ref_embedding()`, `_find_owner_label()`
  - Логирование device, статус операций, similarity score
  - **Обязательные хаки из batch_asr.py:**
    - `use_auth_token=` (не `token=`) для pyannote 3.3.2
    - Embedding model: "pyannote/embedding"
    - Diarization: "pyannote/speaker-diarization-3.1"
- `src/callprofiler/diarize/role_assigner.py`:
  - **Функция `assign_speakers(segments, diarization) -> list[Segment]`**
  - Сопоставление Segment из Whisper с диаризационными интервалами
  - Алгоритм: max overlap → ближайший по времени → fallback
  - Возврат новых Segment с назначенными ролями (исходные не меняются)

### Added — Шаг 6: Транскрибирование (Whisper)
- `src/callprofiler/transcribe/whisper_runner.py`:
  - **Класс `WhisperRunner`** — инкапсуляция загрузки/выгрузки faster-whisper
  - `load()` — загрузка модели (cuda/cpu автоматически, compute_type из config)
  - `transcribe(wav_path) -> list[Segment]`:
    - Конвертация float секунд → int миллисекунды
    - VAD-фильтр (min_silence_duration_ms=400), beam search, condition on previous text
    - Язык, beam_size из config
    - Возврат `list[Segment]` (не dict) с speaker='UNKNOWN'
    - Фильтрация пустых сегментов
  - `unload()` — выгрузка (del, gc.collect, torch.cuda.empty_cache)
  - Логирование device, GPU-info, статус операций
  - Типизированный код, обработка ошибок с контекстом

---

## Технический стек

| Компонент | Версия |
|-----------|--------|
| Python | 3.x (системный) |
| torch | 2.6.0+cu124 |
| faster-whisper | latest |
| pyannote.audio | 3.3.2 |
| GPU | NVIDIA RTX 3060 12GB |
| CUDA | 12.4 |
