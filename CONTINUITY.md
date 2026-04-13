# CONTINUITY.md — Журнал непрерывности разработки

Этот файл обновляется после **каждой рабочей сессии**.
Цель: любой разработчик или AI-агент может открыть репозиторий и мгновенно
понять, что уже сделано, что в работе, и что делать дальше.

---

## Текущее состояние: 2026-04-11c (Event extraction with proper role mapping)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ` (синхронизирована с origin)

### Что сделано в этой сессии (2026-04-11c)

**Refined event extraction** with proper role mapping from LLM JSON:
- Promises: extract `who` field and map Me→OWNER, S2→OTHER
- Action items: all tagged with who=OWNER
- bs_evidence: parse from raw_response JSON → event_type='contradiction'
- amounts: parse from raw_response JSON → event_type='debt'
- Error handling: per-field try/except, graceful degradation (log warning, continue)

**Роли в данных:**
- LLM выпускает JSON с полями `who: "Me"|"S2"`
- В транскриптах метки `[me]` и `[s2]` (но они уже обработаны pyannote)
- Маппинг: Me→OWNER (владелец), S2→OTHER (собеседник)

---

### Что было в сессии (2026-04-11b)

1. **Added `events` table** to `schema.sql`:
   - 7 event types: promise, debt, contradiction, risk, task, fact, smalltalk
   - Per-event metadata: who, payload, source_quote, deadline, confidence, status
   - Dual indices on (user_id, contact_id, event_type) and (user_id, status)

2. **Added 4 Repository methods** (`repository.py`):
   - `save_events(call_id, events: list[dict])` — batch insert
   - `get_open_events(user_id, contact_id=None, event_type=None)` — filtered query
   - `get_events_for_contact(user_id, contact_id, limit=50)` — contact history
   - `update_event_status(event_id, status)` — status transition

3. **Added event extraction** to `enricher.py`:
   - New function `_extract_events_from_analysis()` converts Analysis → events
   - Extracts from: promises, action_items, flags (conflict, legal_risk, urgent), key_topics
   - Confidence scoring: 0.9 (promises) > 0.85 (flags) > 0.7 (heuristics)
   - Updated `_flush_batch()` to save events alongside analysis

4. **Tестирование:**
   - All 90 tests pass (no existing tests affected; events are new)
   - New code path tested implicitly via enricher (promise extraction already covered)

### Следующий шаг / возможности

- Implement event dashboards / event timelines in deliver module
- Create skill `event-tracker` when event queries become frequent
- Add event deduplication logic (same promise from multiple calls?)
- Implement promise fulfillment tracking via Telegram commands

### Известные ограничения

- Events rely on LLM extraction quality (inherited from Analysis)
- Confidence scores are heuristic (0.9/0.85/0.7) — could be improved with A/B testing
- `key_topics` → `smalltalk` conversion is simplistic (only checks lowercase/spaces)

---

## Предыдущее состояние: 2026-04-11 (AGENTS.md + skills для AI-агентов)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ` (синхронизирована с origin)

### Прогресс
**15/15 основных шагов + доп. модули + инфраструктура AI-агентов**

### Что сделано в этой сессии (2026-04-11)

1. **Создан `AGENTS.md`** — единая точка входа для любого AI-агента над проектом:
   - Структура репозитория, workflow агента, команды, анти-паттерны
   - Связывает `CONSTITUTION.md`, `CLAUDE.md`, `CHANGELOG.md`, `CONTINUITY.md`
     в пошаговый процесс, но не дублирует их
   - Раздел 7.2 — roadmap будущих skills (к созданию по мере нужды)

2. **Создан первый доменный skill: `filename-parser`**
   - Файл: `.claude/skills/filename-parser/SKILL.md`
   - Домен: 5 форматов имён файлов + `normalize_phone()`
   - Алгоритм добавления 6-го формата, ссылки на код, анти-паттерны

3. **Создан второй доменный skill: `journal-keeper`**
   - Файл: `.claude/skills/journal-keeper/SKILL.md`
   - Кодифицирует требование владельца про Obsidian-like журналирование
   - Рабочий процесс: briefing → logging → final check

4. **Обновлены CHANGELOG.md и CONTINUITY.md** (этой записью).

### Тесты
90/90 pass (skills — только документация, кода не трогали).

### Следующий шаг / возможности

- При регулярных прогонах `bulk-enrich` на реальных звонках > 10 мин —
  создать skill `bulk-ops-runner` с per-file метриками и ETA.
- При переходе на `analyze_v002.txt` — создать `prompt-version-manager`.
- При любом баге в filename parsing — первым делом прочитать
  `.claude/skills/filename-parser/SKILL.md`.
- При старте любой новой сессии — прочитать `AGENTS.md` секцию 3.1.

### Известные ограничения / долги (без изменений)
- `configs/base.yaml` содержит `hf_token: "TOKEN"` — перед production заменить.
- `data_dir` в конфиге — Windows пути (`D:\calls\data`).
- Тесты для `normalizer.py`, `whisper_runner.py`, `pyannote_runner.py` (mock ffmpeg/GPU) — технический долг.

---

## Предыдущее состояние: 2026-04-09 (обновлено после bug fixes и оптимизации enricher)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ` (синхронизирована с origin)

### Прогресс
**15/15 шагов завершено (100%) + доп. модуль bulk/name_extractor**
- ✅ ШАГ 5: audio/normalizer.py (LUFS-нормализация)
- ✅ ШАГ 6: transcribe/whisper_runner.py (WhisperRunner)
- ✅ ШАГ 7: diarize/pyannote_runner.py + role_assigner.py
- ✅ ШАГ 8: ingest/ingester.py (приём файлов)
- ✅ ШАГ 9: analyze/llm_client.py + prompt_builder.py + response_parser.py (LLM анализ)
- ✅ ШАГ 10: deliver/card_generator.py (caller cards для Android overlay)
- ✅ ШАГ 11: deliver/telegram_bot.py (Telegram-бот)
- ✅ ШАГ 12: pipeline/orchestrator.py (главный оркестратор)
- ✅ ШАГ 13: pipeline/watcher.py (мониторинг папок)
- ✅ ШАГ 14: cli/main.py + __main__.py (точка входа CLI)
- ✅ ШАГ 15: tests/test_integration.py (интеграционный тест — 58 тестов, все зелёные)
- ✅ ДОППО: bulk/name_extractor.py + schema миграция + CLI extract-names

### Последний коммит
```
(текущий — bulk/name_extractor.py)
```

### Выполненные шаги

| # | Модуль | Статус | Коммит |
|---|--------|--------|--------|
| 0 | Структура проекта + pyproject.toml | ✅ готово | `885d137` |
| 1 | `config.py` + `configs/base.yaml` | ✅ готово | `885d137` |
| 2 | `models.py` (dataclasses) | ✅ готово | `885d137` |
| 3 | `db/schema.sql` + `db/repository.py` | ✅ готово | `885d137` |
| 4 | `ingest/filename_parser.py` + тесты | ✅ готово | `885d137` |
| 5 | `audio/normalizer.py` | ✅ готово | `5dbe6a7` |
| 6 | `transcribe/whisper_runner.py` | ✅ готово | `6f73a99` |
| 7 | `diarize/pyannote_runner.py` + `role_assigner.py` | ✅ готово | `edcbcd8` |
| 8 | `ingest/ingester.py` | ✅ готово | `c761342` |
| 9 | `analyze/llm_client.py` + `prompt_builder.py` + `response_parser.py` | ✅ готово | `c4b70f0` |
| 10 | `deliver/card_generator.py` + тесты | ✅ готово | `504e6db` |
| 11 | `deliver/telegram_bot.py` | ✅ готово | `bf66bad` |
| 12 | `pipeline/orchestrator.py` | ✅ готово | `c0f8b49` |
| 13 | `pipeline/watcher.py` | ✅ готово | `d96b8da` |
| 14 | `cli/main.py` + `__main__.py` | ✅ готово | (prev) |
| 15 | `tests/test_integration.py` | ✅ готово | (prev) |
| +  | `bulk/name_extractor.py` | ✅ готово | текущий |

### Доп. модуль: bulk/name_extractor.py

**Что делает:**
- Находит имена собеседников в транскриптах для контактов без `display_name`
- Ищет в обоих спикерах (первые 10 сегментов), т.к. роли [me]/[s2] часто перепутаны
- 12 regex-паттернов приветствий/представлений
- Исключает имена владельца (Сергей, Серёжа, Серёж, Серёга, Медведев)
- Confidence: medium (1 звонок) / high (2+ звонков с тем же именем)
- Не перезаписывает контакты с `name_confirmed=1`

**CLI:**
```
python -m callprofiler extract-names --user serhio
python -m callprofiler extract-names --user serhio --dry-run
```

**Новые поля contacts:**
`guessed_name`, `guessed_company`, `guess_source`, `guess_call_id`,
`guess_confidence`, `name_confirmed`

**Миграция:** `Repository._migrate()` — auto ALTER TABLE для старых БД без новых колонок.

### Новый системный промпт: analyze_v001.txt (30+ полей анализа)

**Комплексный анализ звонков через LLM:**

| Раздел | Поля |
|--------|------|
| **Основное** | summary, priority, risk_score, category, sentiment, initiative |
| **Действия** | action_items[] {who, what, deadline} |
| **Обещания** | promises[] {who, what, deadline, vague} |
| **Данные** | mentioned_people, companies, amounts, dates, addresses |
| **Контакт** | contact_name_guess, company_guess, role_guess |
| **Честность** | bullshit_index {score, vagueness, defensiveness, contradictions, evidence} |
| **Динамика** | power_dynamics, emotional_tone_owner/other |
| **Флаги** | urgent, conflict, money_discussed, deadline_mentioned, legal_risk, lie_suspected |

**Ключевые правила:**
- Роли [Me]/[S2] часто перепутаны → определять по контексту
- Сергей/Медведев ВСЕГДА владелец, даже если [S2]
- bullshit_index: 0=честный, 100=пиздёж (vagueness, defensiveness, contradictions)
- Extractить ВСЕ упомянутые: имена, компании, суммы, даты, адреса
- Если непонятно → null, не выдумывать
- ТОЛЬКО JSON, без markdown, без пояснений

**Хранение:** Все 30+ полей сохраняются в `Analysis.raw_response` (JSON)

### Изменения: LLM клиент (Ollama → llama.cpp)

**Вместо Ollama теперь используется llama.cpp (llama-server):**
- **Endpoint:** POST `http://127.0.0.1:8080/v1/chat/completions` (OpenAI API совместимый)
- **Класс:** `LLMClient` (обратная совместимость: `OllamaClient = LLMClient`)
- **Параметры запроса:** `messages`, `temperature`, `max_tokens` (нет `model` — загружено на сервере)
- **Зависимости:** только `requests` (без openai SDK)
- **Запуск:** `llama-server -api` (обычно на порту 8080)

### Новый модуль: bulk/enricher.py (массовый LLM-анализ)

**Функция `bulk_enrich(user_id, db_path, limit=0)`:**
- Обрабатывает все звонки **БЕЗ** analysis
- Форматирует транскрипт + метаданные (phone, name, datetime)
- Отправляет на LLM через новый OpenAI-совместимый API
- Распарсивает JSON из ответа LLM (обработка markdown)
- Сохраняет Analysis + Promises в БД
- Логирует прогресс, время обработки, ETA
- Graceful Ctrl+C (завершить текущий файл, не начинать новый)
- `limit=0` = обрабатывать все файлы

**CLI:**
```bash
python -m callprofiler bulk-enrich --user serhio
python -m callprofiler bulk-enrich --user serhio --limit 100
```

### Новый модуль: bulk/loader.py (массовая загрузка транскриптов)

**Функция `bulk_load(txt_folder, user_id, db_path)`:**
- Рекурсивный поиск .txt файлов в папке
- Парсинг имён файлов → CallMetadata (phone, datetime, name)
- MD5-дедупликация по хешу содержимого
- Разбор [me]: / [s2]: маркеров в сегменты:
  - [me]: → speaker='OWNER' (владелец)
  - [s2]: → speaker='OTHER' (собеседник)
- Создание контактов и звонков (status='done')
- Индексация в FTS5
- Логирование каждые 100 файлов
- Graceful обработка ошибок (skip + continue)

**Возвращает статистику:**
```python
{
    'loaded': количество загруженных файлов,
    'skipped': дубликаты (по MD5),
    'errors': ошибки парсинга/БД,
    'unique_contacts': уникальные контакты,
}
```

**CLI:**
```bash
python -m callprofiler bulk-load /path/to/transcripts --user serhio
```

**Тесты:** 7 новых тестов для `_parse_segments()`
- Простые/сложные сегменты, whitespace, timing, edge cases

### Рефакторинг: filename_parser.py (5 форматов)

**Новые форматы (вместо BCR, скобочного, ACR):**

| Формат | Пример | Парсинг |
|--------|--------|---------|
| 1 | `007496451-07-97(0074964510797)_20240925154220` | номер+дубль+дата |
| 2 | `8(495)197-87-11(84951978711)_20240502164535` | 8(код)номер+дубль+дата |
| 3 | `8496451-07-97(84964510797)_20240502170140` | 8номер+дубль+дата |
| 4 | `Иванов(0079161234567)_20260328143022` | имя+номер+дата |
|   | `Вызов@Ира(007925291-85-95)_20170828123145` | с префиксом Вызов@ |
|   | `name(900)_20231009112764` | с коротким номером |
| 5 | `Варлакаув Хрюн 2009_09_03 21_05_57` | имя+дата (без номера) |

**Нормализация телефонов:**
- `007...` → `+7...` (международный 007=+7)
- `8` + 11 цифр → `+7...` (русский формат)
- `00...` (не 007) → `+...` (другие международные)
- 3-4 цифры → как есть (сервисные номера: 900, 112, 0511)
- Убирает: скобки, дефисы, пробелы

**Тесты:** 40 новых (8 normalize_phone + 32 parse_filename)
- Все 5 форматов
- Edge cases (невалидная дата, пусто, неизвестные форматы)
- Пути (Unix/Windows)
- 80 тестов сквозь проект — все зелёные

**BREAKING:** Старые BCR/скобочный/ACR форматы больше не поддерживаются.

---

## Детали шага 5: audio/normalizer.py

### Что реализовано
- `normalize(src, dst, *, loudnorm, sample_rate, channels)` — конвертация в WAV 16kHz mono
- **Двухпроходная EBU R128 LUFS-нормализация** (loudnorm=True по умолчанию)
  - Целевой уровень: -16 LUFS / True Peak -1.5 dBFS
  - Fallback к простой конвертации если ffmpeg-анализ не удался
- `get_duration_sec(wav_path)` — длительность через ffprobe
- Проверка ffmpeg/ffprobe при импорте модуля
- Защита от битых файлов (минимальный размер 1024 байт)
- Логирование через `logging.getLogger(__name__)`

---

## CONSTITUTION.md — Конституция проекта (MERGE-BLOCKING)

**Создан полный документ архитектурных принципов:**

- **Статья 1-3**: назначение (локальная мультипользовательская система), фундаментальные принципы (вертикальные срезы, работающий код > архитектуре, только измеренные проблемы)
- **Статья 4-5**: запрещённые компоненты (Docker, Redis, WhisperX, ECAPA на текущей фазе) и зафиксированный стек
- **Статья 6-8**: изоляция данных по `user_id`, дедупликация MD5, статусы звонков, структура хранения
- **Статья 9-10**: 6-шаговый pipeline, GPU-дисциплина (Whisper+pyannote вместе, LLM отдельно), caller cards для Android overlay
- **Статья 11-13**: Telegram-бот (один на всех, различает по chat_id), версионирование промптов, миграция из batch_asr.py с обязательными хаками (torch.load, use_auth_token=)
- **Статья 14-18**: правила разработки, фазы (0-5), триггеры пересмотра архитектуры (измеренные пороги), антипаттерны

**Статус:** Любой PR, противоречащий CONSTITUTION.md, не мержится без изменения самой Конституции (требует замер + решение).

---

## Детали шага 6: transcribe/whisper_runner.py

### Что реализовано
- **Класс `WhisperRunner`** с методами:
  - `__init__(config: Config)` — инициализация с конфигурацией
  - `load()` — загрузка faster-whisper large-v3 с выбором device (cuda/cpu) и compute_type (float16/int8)
  - `transcribe(wav_path: str) -> list[Segment]` — транскрибирование с конвертацией float сек → int мс
  - `unload()` — выгрузка модели + `gc.collect()` + `torch.cuda.empty_cache()`
- Параметры транскрибирования:
  - Язык: русский (`whisper_language` из config)
  - VAD-фильтр: пропуск молчания, min_silence_duration_ms=400
  - Beam search: beam_size из config (обычно 5)
  - Условный текст и коррекция артефактов (compression_ratio, no_speech_threshold)
- Логирование через `logging` (device, статус загрузки, кол-во сегментов)
- Типизация: `list[Segment]` вместо `list[dict]`
- Обработка пустых сегментов (пропускаются автоматически)
- Защита от повторной загрузки и вызова до load()

### Ключевые отличия от batch_asr.py
| Аспект | batch_asr.py | WhisperRunner |
|--------|--------------|---------------|
| Структура | функции | класс с состоянием |
| Возвращаемый тип | `list[dict]` | `list[Segment]` |
| Время | float секунды | int миллисекунды |
| Выгрузка | ручная | метод `unload()` |
| Логирование | print() | logger |
| Конфигурация | константы | Config объект |

### Почему LUFS-нормализация
Телефонные звонки имеют разный уровень записи:
- AGC на телефоне может сильно занижать/завышать сигнал
- Whisper при слишком тихом сигнале пропускает сегменты или галлюцинирует
- Цель -16 LUFS — стандарт EBU R128 для речи (та же норма, что у подкастов)
- Двухпроходный режим точнее одного прохода: сначала анализируем, затем корректируем

### Источники решений
- EBU R128 loudness recommendation
- ffmpeg `loudnorm` filter documentation
- Статья Habr #932762 (основные практики нормализации аудио для ASR)

---

## Известные ограничения и технические долги

- `configs/base.yaml` содержит `hf_token: "TOKEN"` — перед продакшн-запуском
  заменить на реальный токен HuggingFace
- `data_dir` в конфиге указывает на `D:\\calls\\data` — пути Windows,
  на Linux нужно переопределить
- `tests/` пока содержат только `test_filename_parser.py` и `test_repository.py`;
  тест для `normalizer.py` (с mock ffmpeg) — технический долг

---

---

## Детали шага 7: diarize/pyannote_runner.py + role_assigner.py

### PyannoteRunner — инкапсуляция диаризации

**Методы класса:**
- `__init__(config: Config)` — инициализация
- `load(ref_audio_path: str)` — загрузка pyannote (embedding + pipeline) + построение reference embedding
- `diarize(wav_path: str) -> list[dict]` — диаризация с маппингом OWNER/OTHER по cosine similarity
- `unload()` — выгрузка моделей + GPU cleanup

**Ключевая логика (из batch_asr.py без изменений):**
1. Запустить pyannote pipeline: `min_speakers=2, max_speakers=2`
2. Собрать сегменты по label, отфильтровать < 400мс
3. Для каждого label вычислить embedding (конкатенация его аудиосегментов)
4. Найти label с max cosine similarity к ref_embedding → это OWNER
5. Остальные → OTHER
6. Конвертировать: float сек → int мс, вернуть sorted list

**Параметры pyannote из CONSTITUTION.md Статья 13.1:**
- `use_auth_token=` (не `token=`) для pyannote 3.3.2
- Embedding model: "pyannote/embedding"
- Diarization pipeline: "pyannote/speaker-diarization-3.1"

### role_assigner.assign_speakers() — сопоставление ролей

**Функция:**
```python
def assign_speakers(
    segments: list[Segment],  # from Whisper (speaker='UNKNOWN')
    diarization: list[dict]   # from PyannoteRunner
) -> list[Segment]            # with assigned speakers
```

**Алгоритм:**
1. Для каждого Segment (start_ms, end_ms) найти диаризационный интервал с max overlap
2. Если overlap > 0 → скопировать speaker из диаризации
3. Если overlap = 0 → взять ближайший по времени интервал
4. Вернуть новый list[Segment] с назначенными ролями

**Ключевая функция:**
```python
overlap = max(0.0, min(seg_end, dia_end) - max(seg_start, dia_start))
```

### Отличия от batch_asr.py

| Аспект | batch_asr.py | PyannoteRunner |
|--------|--------------|---|
| Структура | функции (load_pyannote, diarize, get_embedding) | класс с state |
| Reference embedding | построен в load_pyannote | построен в load() |
| Возврат diarize() | `{"s": float, "e": float, "speaker": str}` | `{"start_ms": int, "end_ms": int, "speaker": str}` |
| Логирование | print() | logger |
| Выгрузка | ручная del | метод unload() |
| assign_speakers | функция, работает с dict | функция, работает с Segment |

---

---

## Детали шага 8: ingest/ingester.py

### Класс Ingester — приём файлов в очередь

**Методы:**
- `__init__(repo: Repository, config: Config)` — инициализация
- `ingest_file(user_id: str, filepath: str) -> int | None` — главный метод

**Workflow ingest_file():**
```python
1. Проверить что файл существует (FileNotFoundError)
2. Парсить имя файла → CallMetadata
3. Вычислить MD5 оригинала (дедупликация)
4. Проверить repo.call_exists(user_id, md5)
   → если есть: вернуть None (дубликат)
5. repo.get_or_create_contact(user_id, phone_e164, display_name)
6. Скопировать оригинал в data/users/{user_id}/audio/originals/
   - Конфликты имён: добавить MD5 префикс
7. repo.create_call(user_id, contact_id, direction, call_datetime,
                     source_filename, source_md5, audio_path)
   - Status = 'new' (готов к обработке)
8. Вернуть call_id (или None если дубликат)
```

**Внутренние методы:**
- `_compute_md5(filepath: Path) -> str` — буферизованное вычисление MD5
- `_copy_original(user_id, src_path, file_md5) -> str` — копирование с обработкой конфликтов

### Изоляция по user_id (CONSTITUTION.md Статья 2.5)

Все операции фильтруются по user_id:
- Путь хранения: `data/users/{user_id}/audio/originals/`
- Контакт создаётся для пары (user_id, phone_e164)
- Call привязан к user_id в БД
- Один номер у двух пользователей → два разных контакта

### Дедупликация

```python
# 1. Вычислить MD5 оригинального файла
file_md5 = hashlib.md5(file_contents).hexdigest()

# 2. Проверить repo.call_exists(user_id, md5)
#    (у пользователя уже есть этот файл)
if repo.call_exists(user_id, file_md5):
    return None  # Дубликат
```

### Обработка конфликтов имён

```python
# Если файл data/users/{user_id}/audio/originals/{name} существует:
# 1. Проверить MD5 нового файла vs существующего
# 2. Если MD5 совпадают → это один файл, переиспользовать путь
# 3. Если разные → переименовать: {stem}_{md5[:8]}{suffix}
```

### Логирование (CONSTITUTION.md Статья 14.3)

```python
logger.info("Зарегистрирован call_id=%d для %s (user_id=%s)", ...)
logger.info("Дубликат: %s (MD5=..., user_id=...)", ...)
logger.debug("contact_id=%d для phone=%s", ...)
logger.error("Ошибка при ...: %s", exc)
```

---

## Итоги сессии (2026-03-30)

### Реализовано
- **ШАГ 5**: audio/normalizer.py (205 строк)
  - Двухпроходная EBU R128 LUFS-нормализация
  - Fallback к raw-конвертации при сбое анализа

- **ШАГ 6**: transcribe/whisper_runner.py (189 строк)
  - WhisperRunner с управлением GPU-памятью
  - Конвертация float сек → int мс

- **ШАГ 7**: diarize/pyannote_runner.py (339 строк) + role_assigner.py (106 строк)
  - PyannoteRunner с reference embedding
  - Cosine similarity маппинг (OWNER/OTHER)
  - assign_speakers() для сопоставления ролей

- **ШАГ 8**: ingest/ingester.py (230 строк)
  - Приём файлов с MD5 дедупликацией
  - Копирование в data/users/{user_id}/audio/originals/
  - Запись в БД (status='new')

### Всего кода добавлено
- **4 модуля**: 969 строк кода
- **2 документа обновлены**: CONTINUITY.md, CHANGELOG.md
- **4 коммита**: от c761342 до 5dbe6a7

### Архитектурные решения
✅ CONSTITUTION.md соблюдена (18 статей)
✅ GPU-дисциплина: Whisper+pyannote вместе, LLM отдельно
✅ Изоляция по user_id во всех операциях
✅ Логирование через logger (не print)
✅ Полная типизация с TYPE_CHECKING

### Технические долги (минимальны)
- ⚪ Тесты для normalizer.py, whisper_runner.py, pyannote_runner.py (mock ffmpeg)
- ⚪ Интеграционный тест сквозного pipeline
- ⚪ Обработка edge cases (корруптированные файлы, сетевые ошибки)

---

## Детали шага 9: analyze/llm_client.py + prompt_builder.py + response_parser.py

### OllamaClient — HTTP клиент для локального LLM

**Методы класса:**
- `__init__(base_url: str, model: str, timeout: int = 300)` — инициализация с проверкой подключения
- `generate(prompt: str, stream: bool = False) -> str` — POST /api/generate с temperature=0.3
- `list_models() -> list[str]` — получить доступные модели

**Ключевые особенности:**
- Проверка подключения к Ollama при инициализации (GET /api/tags)
- Поддержка streaming режима для больших ответов
- Temperature 0.3 для консистентного JSON (не галлюцинаций)
- Timeout 300сек для больших моделей (qwen2.5:14b)
- Полная обработка ошибок (ConnectionError, Timeout, RequestException)

### PromptBuilder — построение промптов с подстановкой

**Методы класса:**
- `__init__(prompts_dir: str)` — инициализация с проверкой директории
- `build(transcript_text, metadata, previous_summaries=None, version="v001") -> str` — главный метод

**Workflow build():**
1. Загрузить шаблон из `configs/prompts/analyze_{version}.txt`
2. Извлечь метаданные (contact_name, phone, call_datetime, direction)
3. Форматировать datetime в DD.MM.YYYY HH:MM
4. Извлечь длительность из временных меток [MM:SS] в стенограмме
5. Построить контекст из последних 3 анализов (max 100 символов каждый)
6. Подставить все переменные в шаблон

**Поддерживаемые переменные в шаблоне:**
- `{contact_name}` — имя контакта
- `{phone}` — номер телефона (E.164)
- `{call_datetime}` — дата/время (DD.MM.YYYY HH:MM)
- `{direction}` — IN/OUT/UNKNOWN
- `{duration}` — "Х минут Y секунд" или "неизвестна"
- `{context_block}` — контекст из предыдущих анализов
- `{transcript}` — полная стенограмма с ролями и временами

### parse_llm_response() — парсинг ответов LLM

**Стратегия 3-уровневого fallback:**

1. **Попытка 1: Прямое парсинг JSON**
   - Вызывает `_try_parse_json(raw.strip())`
   - Логирует ошибку при сбое

2. **Попытка 2: Извлечь JSON из markdown-обёртки**
   - `_extract_json_from_markdown(raw)` ищет:
     - ` ```json\n...\n``` ` или ` ```\n...\n``` `
   - Использует regex с `re.DOTALL` для многострочного поиска
   - Вызывает `_try_parse_json()` для распарсенного JSON

3. **Попытка 3: Очистить JSON**
   - `_clean_json(raw)` находит первый `{` и последний `}`
   - Извлекает substring и пытается распарсить
   - Защита от синтаксических ошибок

4. **Fallback на дефолты**
   - Если всё неудачно: `_default_analysis(raw_response=raw)`
   - Возвращает Analysis с нейтральными значениями (priority=50, risk_score=50)
   - Сохраняет raw_response для отладки

**Вспомогательные функции:**
- `_get_int(data, key, default, min_val, max_val)` — безопасное получение int с валидацией диапазона
- `_get_str(data, key, default)` — строка с fallback
- `_get_list(data, key, default)` — список с проверкой типа
- `_get_dict(data, key, default)` — dict с проверкой типа

### configs/prompts/analyze_v001.txt

**Шаблон JSON с инструкциями LLM:**
```
Возвращаемый JSON содержит:
- priority (0-100): насколько важен звонок
- risk_score (0-100): уровень риска/проблемности
- summary (2-4 предложения): суть разговора
- action_items (массив): что нужно сделать
- promises (массив объектов с who/what/due): обещания
- flags (объект: urgent, follow_up_needed, conflict_detected)
- key_topics (массив): ключевые темы разговора
```

**Подстановка переменных:**
- Метаданные звонка (контакт, дата, направление, длительность)
- Контекст из предыдущих анализов
- Полная стенограмма с ролями

### Архитектурные решения STEP 9

✅ **Graceful degradation**: парсинг падает → Returns Analysis с дефолтами + raw_response для отладки
✅ **Markdown-friendly**: поддержка ```json ... ``` (обычная ошибка LLM)
✅ **Markdown-clean**: избегание избыточных проверок (```, ```json, пробелы)
✅ **Трехуровневая стратегия**: от простого к сложному (попытки 1-3 + дефолты)
✅ **Типизация с TYPE_CHECKING**: полная аннотация типов без лишних import
✅ **Logging через logger**: все ошибки и debug информация через logging module
✅ **Версионирование промптов**: поддержка analyze_v001.txt, analyze_v002.txt и т.д.

### Тестирование STEP 9

✅ **Все 40 unit-тестов пройдены** (40/40 passed в 0.31s)
✅ **Lint analysis пройдена** (flake8 и ruff clean)
✅ **Синтаксис проверен** (python -m py_compile)

---

## Детали шага 14: cli/main.py + __main__.py

### CLI — точка входа `python -m callprofiler`

**Команды:**

| Команда | Описание |
|---------|----------|
| `watch` | Запустить FileWatcher.run_loop() — watchdog + автообработка |
| `process <file> --user ID` | Зарегистрировать и обработать один файл |
| `reprocess` | Повторить все звонки с ошибками |
| `add-user ID --incoming --ref-audio --sync-dir [--display-name --telegram-chat-id]` | Добавить пользователя |
| `digest <user> [--days N]` | Топ-10 звонков по priority за N дней |
| `status` | Статистика очереди: статусы, pending, errors |

**Флаги:**
- `--config PATH` — путь к base.yaml (по умолчанию `configs/base.yaml`)
- `--verbose / -v` — DEBUG-логирование

**Ключевые особенности:**
- `_setup_logging()` — консоль + файл (из config.log_file)
- `_load_config_and_repo()` — загрузить конфиг, создать БД, вернуть (cfg, repo)
- Все импорты тяжёлых модулей — внутри функций (ленивая загрузка)
- Graceful KeyboardInterrupt → sys.exit(0)
- `digest` и `status` печатают в stdout без лог-файла

---

## Детали шага 13: pipeline/watcher.py

### FileWatcher — мониторинг папок пользователей

**Методы класса:**
- `__init__(config, repo, ingester, orchestrator)` — инициализация
- `scan_all_users() -> list[int]` — однократное сканирование всех пользователей
- `run_loop()` — бесконечный цикл: scan → process_batch → retry_errors → sleep

**Поток scan_all_users():**
1. Получить всех пользователей из БД
2. Для каждого: обойти incoming_dir рекурсивно (os.walk)
3. Фильтровать по аудио-расширениям: .mp3, .m4a, .wav, .ogg, .opus, .flac, .aac, .wma
4. Проверить file_settle_sec (файл не записывается)
5. Передать в ingester.ingest_file() → call_id (или None если дубликат)

**Ключевые особенности:**
- Рекурсивный обход подпапок (os.walk)
- file_settle_sec: проверка mtime чтобы не хватать незаписанный файл
- Graceful degradation: ошибка одного файла → лог → продолжить
- KeyboardInterrupt → чистый выход из run_loop()
- Дубликаты (call_id=None) пропускаются молча

---

## Детали шага 12: pipeline/orchestrator.py

### Orchestrator — главный оркестратор pipeline

**Методы класса:**
- `__init__(config, repo, telegram=None)` — инициализация всех компонентов
- `process_call(call_id) -> bool` — полная обработка одного звонка
- `process_batch(call_ids)` — batch-обработка с GPU-оптимизацией
- `process_pending()` — обработать все звонки со статусом 'new'
- `retry_errors()` — повторить звонки со статусом 'error' (retry_count < max)

**Поток process_call():**
1. Normalize — ffmpeg → WAV 16kHz mono + LUFS нормализация
2. Transcribe — загрузить Whisper → транскрибировать → выгрузить
3. Diarize — загрузить pyannote → диаризация с ref embedding → assign speakers → выгрузить
4. Analyze — построить промпт → отправить в Ollama → распарсить JSON → сохранить
5. Deliver — обновить caller card + отправить Telegram саммари

**Поток process_batch() (GPU-оптимизация, CONSTITUTION.md Ст. 9.2):**
1. Normalize все файлы
2. Загрузить Whisper → транскрибировать ВСЕ → выгрузить
3. Для каждого файла: загрузить pyannote → diarize → выгрузить
4. Для каждого: LLM analyze (Ollama сам управляет моделью)
5. Для каждого: deliver (карточка + Telegram)

**Ключевые особенности:**
- При ошибке на любом шаге: логирование + update_call_status('error') → не роняет pipeline
- Все статусы в БД: normalizing → transcribing → diarizing → analyzing → delivering → done
- Async Telegram через asyncio.get_event_loop() / new_event_loop()
- Контекст из последних 5 анализов для промпта
- Graceful degradation: нет ref_audio → пропуск диаризации

---

## Детали шага 11: deliver/telegram_bot.py

### TelegramNotifier — Telegram-бот для уведомлений и команд

**Методы класса:**
- `__init__(token, repo)` — инициализация с токеном и репозиторием
- `send_summary(user_id, call_id)` — отправить саммари с кнопками [OK]/[Неточно]
- `handle_feedback()` — обработать нажатие кнопки обратной связи
- Команды: `cmd_digest [N]`, `cmd_search текст`, `cmd_contact +7...`, `cmd_promises`, `cmd_status`
- `run()` — запустить polling в отдельном потоке

**Ключевые особенности:**
- Один бот на всех пользователей (различает по `chat_id`)
- Лениво загружает `python-telegram-bot` (не требуется для импорта)
- Все данные фильтруются по `user_id` (CONSTITUTION.md Статья 2.5)
- HTML-форматирование сообщений
- Inline кнопки для обратной связи

**Команды (CONSTITUTION.md Статья 11.3):**
- `/digest [N]` — топ звонков по priority за N дней
- `/search текст` — FTS5 поиск по транскриптам
- `/contact +7...` — карточка контакта (имя, звонки, риск, саммари)
- `/promises` — открытые обещания
- `/status` — состояние очереди (ожидают, ошибки)

---

## Детали шага 10: deliver/card_generator.py

### CardGenerator — caller cards для Android overlay

**Методы класса:**
- `__init__(repo: Repository)` — инициализация с репозиторием
- `generate_card(user_id, contact_id) -> str` — собрать карточку ≤ 500 символов
- `write_card(user_id, contact_id, sync_dir)` — записать {phone_e164}.txt
- `update_all_cards(user_id)` — пересоздать карточки для всех контактов

**Формат карточки (CONSTITUTION.md Статья 10.2):**
```
{display_name}
Последний: {дата} | Звонков: {count} | Risk: {risk_score}
─────────────────────────
{summary последнего звонка}
─────────────────────────
Обещания: {открытые promises, макс 3}
Actions: {action items, макс 3}
```

**Поток данных:**
1. `get_contact()` → display_name, phone_e164
2. `get_call_count_for_contact()` → кол-во звонков
3. `get_recent_analyses(limit=1)` → последний анализ (summary, risk_score, action_items)
4. `get_contact_promises()` → открытые обещания (filter status='open')
5. Сборка карточки → обрезка до 500 символов

**Дополнения в Repository:**
- `get_all_contacts_for_user(user_id)` — для `update_all_cards`
- `get_call_count_for_contact(user_id, contact_id)` — COUNT(*) звонков

**Тесты (12 тест-кейсов):**
- Базовая карточка (имя, звонки, risk, саммари, обещания, actions)
- Карточка без анализа, без обещаний, без actions
- Несуществующий контакт → пустая строка
- Обрезка до 500 символов при длинном содержимом
- Запись файла {phone}.txt в sync_dir
- Пропуск контакта без phone_e164
- Создание несуществующего sync_dir
- update_all_cards для множества контактов
- Правильный подсчёт множества звонков
- Изоляция карточек по user_id

---

## Сессия 2026-04-10: Phonebook name priority fix

### Исправление: имя из телефонной книги не обновлялось в БД

**Проблема:** `get_or_create_contact()` возвращал `contact_id` без обновления `display_name`
если контакт уже существовал.

**Правило:** Имя в имени файла = имя из телефонной книги Android = АБСОЛЮТНЫЙ ПРИОРИТЕТ.

**Исправлено** в `repository.py`:
- При каждом вызове `get_or_create_contact()` с `display_name≠None` → UPDATE + `name_confirmed=1`
- При создании нового контакта → INSERT с `name_confirmed=1` если есть имя

**Схема приоритетов:**
- `display_name` + `name_confirmed=1` = из телефонной книги (WINNER всегда)
- `guessed_name` = из транскрипта (name_extractor, только если display_name пустой)

**Тесты: 3 новых в test_repository.py, итого 90 pass**

---

## Сессия 2026-04-09: Bug fixes, JSON parsing, оптимизация enricher

### Выполненные работы (6 коммитов):

#### 1. **SQL binding fix** (369935e)
- **Проблема:** enricher.py WHERE c.user_id = ? без параметров
- **Решение:** добавлена (user_id,) в execute()
- **Статус:** ✅ Все 87 тестов pass

#### 2. **FOREIGN KEY constraint fix** (bef94e9)
- **Проблема:** promises требует contact_id NOT NULL, но calls.contact_id может быть NULL
- **Решение:** 
  - schema.sql: contact_id в promises → nullable
  - repository.save_promises(): пропускаем если contact_id = NULL
  - enricher.py: лучший error handling для batch writes
- **Статус:** ✅ Все 87 тестов pass

#### 3. **Оптимизация bulk_enrich** (6034fc0)
- **5 оптимизаций:**
  1. **Сжатие транскрипта** — убрать сегменты < 3 символов (except "да"/"ну"/"угу")
  2. **max_tokens: 1024** (было 2048, JSON редко > 600 токенов)
  3. **Батчевая запись в БД** — новый Repository.save_batch() для одной транзакции
  4. **Пропуск коротких звонков** — transcript < 50 символов → stub, без LLM
  5. **Логирование** — per-file timing, ~tok/s, ETA
- **Статус:** ✅ Все 87 тестов pass

#### 4. **Robust JSON parsing** (668e44c)
- **Новые уровни спасения обрезанного JSON:**
  1. Markdown extraction (```json ... ```)
  2. Text bounds extraction ({...})
  3. **_repair_json()** — auto-close truncated structures
  4. **Regex fallback** — извлечение ключевых полей если JSON совсем сломан
- **Type coercion:** "75" → 75, list из string → [string]
- **Дефолты:** summary='', risk_score=0 (более мягкие чем раньше)
- **Статус:** ✅ Все 87 тестов pass

#### 5. **LLM client improvements** (668e44c)
- **max_tokens:** 2048 → 1500 (достаточно для полного JSON)
- **timeout:** 300s → 180s (лучше для длинных звонков)
- **Error handling:** generate() возвращает None вместо exception
- **Статус:** ✅ Совместимо со всеми модулями

#### 6. **Syntax error fix** (8cd8d5c)
- **Проблема:** unmatched ')' в response_parser.py line 138
- **Решение:** endswith(('}',)) ) → endswith(('}',))
- **Статус:** ✅ Все 87 тестов pass

### Упрощение промпта (analyze_v001.txt)
- **Было:** 30+ полей в огромной структуре
- **Стало:** компактная структура с 15 обязательными полями:
  - Основное: summary, category, priority, risk_score, sentiment
  - Действия: action_items[], promises[]
  - Данные: people, companies, amounts
  - Оценка: contact_name_guess, bs_score, bs_evidence
  - Флаги: {urgent, conflict, money, legal_risk}

### Готовность к production
- ✅ SQL binding: исправлены все параметризованные запросы
- ✅ FK constraints: обработана NULL-безопасность
- ✅ JSON парсинг: 4-уровневая защита от обрезанного JSON
- ✅ LLM интеграция: graceful degradation на ошибках
- ✅ Оптимизация: транскрипты сжимаются, батчи в БД, пропуск пустых

### Оставшиеся задачи (на следующую сессию)
- Тестирование на реальных звонках > 10 мин
- Мониторинг GPU memory при длинных батчах
- (опционально) Интеграция с Android overlay-окном

---

## Как подхватить работу

```bash
git checkout claude/clone-callprofiler-repo-hL5dQ
git pull origin claude/clone-callprofiler-repo-hL5dQ

# Следующий шаг:
# ШАГ 15: Интеграционный тест (ручной прогон)
# python -m callprofiler add-user serhio --incoming D:\calls\audio \
#   --ref-audio C:\pro\mbot\ref\manager.wav --sync-dir D:\calls\sync\serhio\cards
# python -m callprofiler process "D:\calls\audio\test.mp3" --user serhio
# python -m callprofiler status
# python -m callprofiler watch
```
