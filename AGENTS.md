# AGENTS.md — Руководство для AI-агентов

Этот файл — **точка входа для любого AI-агента**, работающего с репозиторием
CallProfiler (Claude Code, Cursor, Codex, любые другие). Он не заменяет
`CONSTITUTION.md`, `CLAUDE.md`, `CHANGELOG.md` и `CONTINUITY.md`, а
связывает их в рабочий процесс.

> **TL;DR для агента:**
> 1. Прочитай `CONTINUITY.md` (где мы остановились) и последние 50 строк `CHANGELOG.md`.
> 2. Сверься с `CONSTITUTION.md` — это merge-blocking правила.
> 3. Сделай задачу в маленьком вертикальном срезе, не ломая GPU-дисциплину и изоляцию по `user_id`.
> 4. Прогоняй `pytest` после каждого нетривиального изменения.
> 5. Перед завершением сессии обнови `CHANGELOG.md` + `CONTINUITY.md` и сделай коммит.

---

## 1. Что это за проект

CallProfiler — локальная мультипользовательская система пост-обработки
записей телефонных разговоров:

```
аудиофайл → normalize → whisper → pyannote → LLM → SQLite → Telegram / caller card
```

Целевая машина: Windows 11 + RTX 3060 12GB + системный Python 3.10+ (без venv).
Никаких облаков, Docker, Redis, PostgreSQL (см. `CONSTITUTION.md` Статья 4).

---

## 2. Структура репозитория

```
callprofiler/
├── AGENTS.md                ← этот файл (руководство для AI)
├── CLAUDE.md                ← исходный план разработки (15 шагов)
├── CONSTITUTION.md          ← merge-blocking правила (18 статей)
├── CHANGELOG.md             ← журнал изменений (Keep a Changelog)
├── CONTINUITY.md            ← журнал непрерывности (где мы остановились)
├── README.md                ← обычный README для людей
├── configs/
│   ├── base.yaml            ← основной конфиг (data_dir, модели, ffmpeg)
│   └── prompts/
│       └── analyze_v001.txt ← системный промпт LLM (версионируется)
├── src/callprofiler/
│   ├── config.py            ← dataclass Config + load_config()
│   ├── models.py            ← CallMetadata, Segment, Analysis
│   ├── audio/normalizer.py        ← ffmpeg + LUFS нормализация
│   ├── transcribe/whisper_runner.py ← faster-whisper large-v3 (GPU)
│   ├── diarize/
│   │   ├── pyannote_runner.py     ← pyannote 3.3.2 + ref embedding (GPU)
│   │   └── role_assigner.py       ← overlap-mapping сегмент→спикер
│   ├── analyze/
│   │   ├── llm_client.py          ← HTTP клиент llama.cpp (OpenAI API)
│   │   ├── prompt_builder.py      ← подстановка в analyze_vNNN.txt
│   │   └── response_parser.py     ← 4-уровневый robust JSON parser
│   ├── bulk/
│   │   ├── enricher.py            ← массовый LLM-анализ (bulk-enrich)
│   │   ├── loader.py              ← импорт готовых транскриптов (bulk-load)
│   │   └── name_extractor.py      ← угадывание имён из транскриптов
│   ├── db/
│   │   ├── schema.sql             ← CREATE TABLE IF NOT EXISTS
│   │   └── repository.py          ← sqlite3 напрямую, без ORM
│   ├── deliver/
│   │   ├── card_generator.py      ← caller cards ({phone}.txt для Android)
│   │   └── telegram_bot.py        ← уведомления + команды /digest /search ...
│   ├── ingest/
│   │   ├── filename_parser.py     ← 5 форматов имён файлов → CallMetadata
│   │   └── ingester.py            ← MD5 дедупликация + регистрация в БД
│   ├── pipeline/
│   │   ├── orchestrator.py        ← главный pipeline (process_call / process_batch)
│   │   └── watcher.py             ← сканирование incoming_dir + автообработка
│   └── cli/main.py                ← точка входа `python -m callprofiler`
├── tests/                   ← pytest (90 тестов, все зелёные)
└── .claude/
    └── skills/              ← доменные skills для AI-агентов
        ├── filename-parser/
        └── journal-keeper/
```

---

## 3. Обязательный рабочий процесс агента

Любая сессия AI-агента над этим репозиторием **должна**:

### 3.1. Старт сессии — чтение журналов

Прежде чем писать код или предлагать план:

1. Прочитать **`CONTINUITY.md`** — текущее состояние, на чём остановились,
   известные технические долги. Это твой briefing.
2. Прочитать последние 50-100 строк **`CHANGELOG.md`** — что было сделано
   за последние сессии, какие баги только что исправлены.
3. При архитектурных решениях — открыть **`CONSTITUTION.md`** и найти
   релевантную статью (1–18). Если твоё решение противоречит Конституции —
   это бракует PR, нужно либо менять решение, либо менять Конституцию
   с измеренным обоснованием.

### 3.2. Во время работы

- **Вертикальные срезы, а не горизонтальные слои** (CONSTITUTION 2.1).
  Не надо рефакторить «всю БД» одним PR.
- **Изоляция `user_id` во всех запросах к БД** (CONSTITUTION 2.5).
  Запрос без `WHERE user_id = ?` к таблицам `contacts/calls/analyses/promises` — баг.
- **GPU-дисциплина** (CONSTITUTION 2.4):
  Whisper + pyannote держатся в VRAM вместе; перед LLM-запросами обе выгружаются.
  Не загружай три GPU-модели одновременно.
- **Ошибки не проглатываются** (CONSTITUTION 6.4).
  Каждый шаг pipeline в try/except → `update_call_status('error', error_message)` →
  продолжить со следующим файлом. `except: pass` запрещён.
- **Оригиналы аудио неприкосновенны** (CONSTITUTION 6.1).
- **Дедупликация по MD5** (CONSTITUTION 6.2).

### 3.3. Финал сессии — запись в журналы

Перед `git commit` ОБЯЗАТЕЛЬНО:

1. Добавить запись в **`CHANGELOG.md`** в секцию `[Unreleased]` или
   `[YYYY-MM-DD]`, указав: что сделано, почему, какие тесты изменились.
2. Обновить **`CONTINUITY.md`** — где остановились, что дальше, новые
   известные ограничения.
3. Сверить изменения с `CONSTITUTION.md` (нет ли нарушений).
4. Запустить тесты.
5. Сделать коммит на ветке `claude/clone-callprofiler-repo-hL5dQ`.

> Этот процесс существует потому, что контекст AI-сессии стирается.
> Журналы — единственный способ преемственности между сессиями
> (принцип «Obsidian-like memory», обозначенный владельцем).

---

## 4. Ключевые команды

### 4.1. Разработка

```bash
# Установка зависимостей (целевая машина — Windows, системный Python)
pip install -e . --break-system-packages

# Запуск всех тестов (должно быть 90 pass)
pytest tests/ -v

# Запуск одного теста
pytest tests/test_repository.py::test_phonebook_name_overwrites_guessed_name -v

# Линт (если настроен ruff)
ruff check src/ tests/
```

### 4.2. CLI приложения

```bash
# Добавить пользователя
python -m callprofiler add-user serhio \
    --display-name "Сергей" \
    --incoming "D:\calls\audio" \
    --ref-audio "C:\pro\mbot\ref\manager.wav" \
    --sync-dir "D:\calls\sync\serhio\cards"

# Обработать один файл
python -m callprofiler process "D:\calls\audio\test.mp3" --user serhio

# Запустить watchdog (основной режим)
python -m callprofiler watch

# Массовые операции
python -m callprofiler bulk-load /path/to/transcripts --user serhio
python -m callprofiler bulk-enrich --user serhio [--limit N]
python -m callprofiler extract-names --user serhio [--dry-run]

# Отладка
python -m callprofiler status
python -m callprofiler reprocess
python -m callprofiler digest serhio --days 7
```

### 4.3. Ветка разработки

Все изменения — на ветке `claude/clone-callprofiler-repo-hL5dQ`.
Не пушить в другие ветки без явного указания владельца.

---

## 5. Стек и жёсткие зависимости (не менять без CONSTITUTION-ревизии)

| Слой         | Решение                              | Обоснование                  |
|--------------|--------------------------------------|------------------------------|
| ASR          | `faster-whisper` large-v3            | Лучшее качество русского     |
| Диаризация   | `pyannote.audio` 3.3.2 + ref embed   | Работает, замерено           |
| LLM          | `llama.cpp` (OpenAI API совместимый) | Локальность, контроль памяти |
| БД           | `sqlite3` + FTS5 (без ORM)           | Один ПК, простота            |
| Telegram     | `python-telegram-bot`                | Стандарт                     |
| GPU          | torch 2.6.0+cu124, RTX 3060 12GB     | Железо пользователя          |

**Обязательные хаки** (иначе не работает, см. CONSTITUTION 13.1):
- `torch.load` monkey-patch (`weights_only=False`)
- `use_auth_token=` (не `token=`) для pyannote 3.3.2
- `HF_TOKEN` из `configs/base.yaml`

---

## 6. Модель данных (краткая карта)

```
users (user_id PK) ──┐
                     │
  contacts (contact_id PK, user_id FK, phone_e164, display_name, guessed_name, name_confirmed)
                     │
  calls (call_id PK, user_id FK, contact_id FK nullable, source_md5 UNIQUE per user, status, direction)
    ├── transcripts (call_id FK, start_ms, end_ms, text, speaker OWNER|OTHER)
    │      └── transcripts_fts (FTS5 virtual table)
    ├── analyses (call_id FK, priority, risk_score, summary, flags JSON, feedback)
    └── promises (call_id FK, contact_id nullable, who, what, due, status)
```

**Приоритет имён контактов** (важнейшая бизнес-логика):
```
МАКСИМАЛЬНЫЙ: display_name (из имени файла = телефонная книга Android)
              + name_confirmed = 1
ВТОРИЧНЫЙ:    guessed_name (авто-извлечение из транскрипта — name_extractor.py)
              записывается только если display_name пустой
```

Подробности — в `CHANGELOG.md` 2026-04-10.

---

## 7. Агенты и skills

CallProfiler — многодоменный проект, где AI-агенту может понадобиться
специализированное знание. Мы оформляем такие знания как **skills**
в каталоге `.claude/skills/`.

### 7.1. Реализованные skills

| Skill             | Что делает                                                            | Где               |
|-------------------|-----------------------------------------------------------------------|-------------------|
| `filename-parser` | Парсинг 5 форматов имён Android-записей → `CallMetadata`              | `.claude/skills/filename-parser/SKILL.md` |
| `journal-keeper`  | Обязательный workflow записи в `CHANGELOG.md` + `CONTINUITY.md`       | `.claude/skills/journal-keeper/SKILL.md` |

### 7.2. Предлагаемые агенты/skills (к созданию по мере нужды)

> Реализуется только при измеренной потребности — принцип CONSTITUTION 2.3.
> Ниже — план команды, а не обязательство.

| Предложение               | Зачем                                                                      | Триггер к созданию                          |
|---------------------------|----------------------------------------------------------------------------|---------------------------------------------|
| `constitution-auditor`    | Проверка PR/кода на нарушение CONSTITUTION (user_id, GPU, форб. стек)      | Чаще 1 раз в неделю нарушение в PR          |
| `llm-json-surgeon`        | Ремонт обрезанного/кривого JSON из LLM (уже есть в `response_parser.py`)   | Новый формат LLM или провал парсинга > 5%   |
| `schema-migrator`         | Шаблоны SQLite миграций (паттерн `Repository._migrate()`)                  | Второй раз при добавлении колонки           |
| `gpu-discipline-checker`  | Верификация load/unload пар моделей и VRAM budget                          | OOM на RTX 3060 в batch pipeline            |
| `bulk-ops-runner`         | Агент-специалист по bulk-enrich / bulk-load / extract-names + ETA/метрики  | Регулярные прогоны на > 1000 файлов          |
| `prompt-version-manager`  | Управление версиями `analyze_vNNN.txt` + A/B-прогоны по feedback'у         | Переход на analyze_v002                     |

### 7.3. Как создать новый skill

1. Создать каталог `.claude/skills/<name>/`.
2. Написать `SKILL.md` с секциями: **Назначение**, **Когда применять**,
   **Инструкции шаг за шагом**, **Анти-паттерны**, **Ссылки на код**.
3. Сослаться на него в секции 7.1 этого файла.
4. Обязательно обновить `CHANGELOG.md` и `CONTINUITY.md`.

Skill должен быть:
- **Узко доменным** (не «как писать на Python»).
- **Self-contained** — при чтении одного файла агент может работать.
- **Привязанным к коду** через ссылки `file:line`.
- **Обновляемым**: если код меняется — SKILL.md тоже.

---

## 8. Анти-паттерны (мгновенный red flag)

- Новый зависимость без записи «замерено — нужно» в `RISKS.md` / `CONTINUITY.md`.
- SQL-запрос к `contacts/calls/analyses/promises` без `WHERE user_id = ?`.
- `except: pass` или `except Exception: pass` без логгера.
- Модификация файла в `audio/originals/`.
- Загрузка Whisper и LLM одновременно в VRAM.
- Новые миграции БД прямым `ALTER TABLE` в обход `Repository._migrate()`.
- Вывод через `print()` вместо `logger` в production-модулях.
- Добавление Docker / Redis / PostgreSQL / LangChain / WhisperX / ECAPA.
- Коммит без обновления `CHANGELOG.md` и `CONTINUITY.md`.
- `git push --force` без явного разрешения владельца.

---

## 9. Полезные ссылки

- Полный план разработки: `CLAUDE.md` (15 шагов)
- Архитектурные правила: `CONSTITUTION.md` (18 статей)
- История изменений: `CHANGELOG.md`
- Текущее состояние: `CONTINUITY.md`
- Прототип, из которого мигрировали: `reference_batch_asr.py`
- Конфиг: `configs/base.yaml`, системные промпты: `configs/prompts/`

---

**Принцип команды:** работающий код важнее идеальной архитектуры, но не
важнее конституции. Конституцию можно менять — но только с замером,
а не «потому что красивее».
