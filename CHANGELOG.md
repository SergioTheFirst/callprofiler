# CHANGELOG.md

Все значимые изменения в проекте фиксируются здесь.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/).
Версионирование: [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
