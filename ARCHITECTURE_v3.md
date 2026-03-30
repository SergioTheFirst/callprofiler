# CallProfiler — Архитектура v3

## Общая схема

```
┌─────────────────────────────────────────────────────────────┐
│                    ТЕЛЕФОН (Android)                         │
│                                                             │
│  ACR/BCR ──записывает──► FolderSync ──SFTP──► ПК           │
│                                                             │
│  FolderSync ◄──SFTP── ПК (sync/cards/)                     │
│                                                             │
│  MacroDroid: входящий звонок → читает {phone}.txt → overlay │
│                                                             │
│  Telegram: получает саммари, дайджесты, ответы на /search   │
└─────────────────────────────────────────────────────────────┘
            ▲               │
            │               ▼
┌─────────────────────────────────────────────────────────────┐
│                         ПК (Windows)                        │
│                                                             │
│  ┌─────────┐  ┌───────────┐  ┌─────────┐  ┌─────────────┐ │
│  │ Watcher │→│  Pipeline  │→│ SQLite  │→│ Delivery     │ │
│  │(watchdog)│ │            │  │  + FTS5  │  │             │ │
│  └─────────┘  │ 1.Ingest   │  └─────────┘  │ • Telegram  │ │
│               │ 2.Normalize │               │ • Cards gen │ │
│               │ 3.Transcribe│               └─────────────┘ │
│               │ 4.Diarize   │                               │
│               │ 5.Analyze   │                               │
│               └───────────┘                                │
│                    │                                        │
│              ┌─────┴──────┐                                 │
│              │   Models    │                                │
│              │ Whisper(GPU)│                                │
│              │Pyannote(GPU)│                                │
│              │ Ollama(GPU) │                                │
│              └────────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

## Модель данных

```sql
CREATE TABLE users (
    id            TEXT PRIMARY KEY,        -- 'serhio', 'manager2'
    display_name  TEXT NOT NULL,
    telegram_chat_id TEXT,                 -- для отправки саммари
    incoming_dir  TEXT NOT NULL,           -- путь к incoming/
    sync_dir      TEXT NOT NULL,           -- путь к sync/cards/
    ref_audio     TEXT NOT NULL,           -- путь к эталону голоса
    filename_pattern TEXT DEFAULT 'auto',  -- формат имён файлов
    timezone      TEXT DEFAULT 'Europe/Moscow',
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE contacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL REFERENCES users(id),
    phone_e164    TEXT NOT NULL,           -- +79161234567
    display_name  TEXT,
    category      TEXT,                    -- 'Поставщик', 'Клиент', ...
    notes         TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, phone_e164)
);

CREATE TABLE calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL REFERENCES users(id),
    contact_id    INTEGER REFERENCES contacts(id),
    direction     TEXT CHECK(direction IN ('IN','OUT','UNKNOWN')),
    call_datetime TEXT,                    -- ISO 8601
    duration_sec  INTEGER,
    source_filename TEXT NOT NULL,
    source_md5    TEXT NOT NULL,
    audio_path    TEXT,                    -- путь к оригиналу
    norm_path     TEXT,                    -- путь к WAV 16kHz
    status        TEXT DEFAULT 'new'
                  CHECK(status IN ('new','transcribing','diarizing',
                                   'analyzing','done','error')),
    error_message TEXT,
    retry_count   INTEGER DEFAULT 0,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, source_md5)
);

CREATE TABLE transcripts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id       INTEGER NOT NULL REFERENCES calls(id),
    segment_index INTEGER NOT NULL,
    speaker       TEXT CHECK(speaker IN ('OWNER','OTHER','UNKNOWN')),
    start_ms      INTEGER NOT NULL,
    end_ms        INTEGER NOT NULL,
    text          TEXT NOT NULL
);

CREATE TABLE analyses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id         INTEGER NOT NULL REFERENCES calls(id),
    priority        INTEGER CHECK(priority BETWEEN 0 AND 100),
    risk_score      INTEGER CHECK(risk_score BETWEEN 0 AND 100),
    summary         TEXT,
    action_items    TEXT,                  -- JSON array
    promises        TEXT,                  -- JSON array
    flags           TEXT,                  -- JSON object
    key_topics      TEXT,                  -- JSON array
    raw_llm         TEXT,                  -- полный ответ LLM
    llm_model       TEXT,
    prompt_version  TEXT,
    feedback        TEXT CHECK(feedback IN ('ok','inaccurate',NULL)),
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE promises (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL REFERENCES users(id),
    contact_id    INTEGER NOT NULL REFERENCES contacts(id),
    call_id       INTEGER NOT NULL REFERENCES calls(id),
    who_promised  TEXT CHECK(who_promised IN ('OWNER','OTHER')),
    promise_text  TEXT NOT NULL,
    due_date      TEXT,                    -- ISO date или NULL
    status        TEXT DEFAULT 'open'
                  CHECK(status IN ('open','fulfilled','broken','expired')),
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Полнотекстовый поиск
CREATE VIRTUAL TABLE transcripts_fts USING fts5(
    text,
    content='transcripts',
    content_rowid='id'
);
```

## GPU Memory Management

```
Шаг 3: Transcribe
  ┌──────────────────────────────┐
  │ faster-whisper large-v3      │
  │ ~3 GB VRAM (float16)        │
  │ Загрузить → транскрибировать │
  │ НЕ выгружать (нужен на ш.4) │ ← оптимизация: Whisper нужен только один раз,
  └──────────────────────────────┘   но pyannote тоже ~1.5GB, они помещаются вместе

Шаг 4: Diarize
  ┌──────────────────────────────┐
  │ pyannote 3.3.2 + embedding   │
  │ ~1.5 GB VRAM                 │
  │ Загружены вместе с Whisper   │ ← batch_asr.py так и делает сейчас
  └──────────────────────────────┘

  После шагов 3-4: выгрузить ОБЕ модели
  gc.collect() + torch.cuda.empty_cache()

Шаг 5: Analyze
  ┌──────────────────────────────┐
  │ Ollama (Qwen 14B Q4)         │
  │ ~10 GB VRAM или RAM          │
  │ Загрузить → analyze → idle   │ ← Ollama сам управляет выгрузкой
  └──────────────────────────────┘
```

**Текущий batch_asr.py** загружает Whisper + pyannote одновременно (~4.5 GB VRAM) и держит их всё время. Это работает. В pipeline нужно добавить выгрузку перед LLM.

## Система Caller Cards (overlay)

### Генерация на ПК

После каждого обработанного звонка `card_generator.py`:

1. Найти контакт по `contact_id` из обработанного звонка.
2. Собрать: последний analysis, открытые promises, количество звонков, средний risk.
3. Сформировать текст ≤ 500 символов.
4. Записать в `sync/{user_id}/cards/{phone_e164}.txt`.

Карточка перезаписывается при каждом новом звонке с этого номера → всегда актуальна.

### Доставка на телефон

FolderSync уже используется для загрузки записей (телефон → ПК). Добавить обратную синхронизацию:

```
ПК: data/users/serhio/sync/cards/  →  Телефон: /sdcard/CallProfiler/cards/
Направление: ПК → Телефон
Интервал: каждые 5 минут (или по событию)
Протокол: SFTP (тот же сервер)
```

### Показ на Android

**MacroDroid** (бесплатный, не требует root):

```
Macro: CallProfiler Overlay
  Trigger: Call Incoming (Any Number)
  Actions:
    1. Set Variable: {phone} = {trigger_number}
    2. Shell Script: echo {phone} | sed 's/^8/+7/' | sed 's/[^+0-9]//g'
       → {phone_clean}
    3. Read File: /sdcard/CallProfiler/cards/{phone_clean}.txt → {card}
    4. If {card} is set:
         Show Popup: {card}
         (Overlay type, position: top, timeout: 20 sec)
```

**Tasker** (альтернатива, платный, мощнее):

```
Profile: Event → Phone Ringing
Task:
  A1. Variable Set: %phone → %CNUM
  A2. Variable Search Replace: %phone, ^8(\d{10})$, +7\1
  A3. Read File: /sdcard/CallProfiler/cards/%phone.txt → %card
  A4. If %card is set
        Flash / AutoNotification: %card
  A5. End If
```

### Ограничения Android 14+

- Overlay permission (`SYSTEM_ALERT_WINDOW`) нужно выдать вручную: Settings → Apps → MacroDroid → Display over other apps.
- Некоторые OEM (Xiaomi, Samsung) убивают фоновые приложения. Решение: добавить MacroDroid в исключения оптимизации батареи.
- Если overlay не работает на конкретной прошивке → fallback: показывать notification вместо overlay. Менее удобно, но работает везде.

## Модуль filename_parser

Парсит имена файлов от различных рекордеров.

Входные форматы (определить в Фазе 0 по реальным файлам):

```
BCR формат:      20260328_143022_OUT_+79161234567_Иванов.mp3
Скобочный:       (28.03.2026 14-30-22) Иванов +79161234567 OUT.m4a
ACR формат:      +79161234567_20260328143022_OUT.wav
Простой:         call_2026-03-28_14-30.mp3
```

Выход:

```python
@dataclass
class CallMetadata:
    phone: str | None        # E.164: +79161234567
    datetime: datetime | None
    direction: str           # IN / OUT / UNKNOWN
    contact_name: str | None
    raw_filename: str
```

Если формат не распознан → `phone=None, direction=UNKNOWN`. Не ронять pipeline из-за непарсящегося имени.

## Telegram-бот

### Один бот, много пользователей

```python
# При получении команды
user = db.get_user_by_chat_id(update.effective_chat.id)
if not user:
    return  # игнорировать незарегистрированных

# Все запросы фильтруются по user.id
calls = db.get_calls(user_id=user.id, limit=10)
```

### Автоматические сообщения

После обработки каждого звонка:

```
📞 Исходящий → Иванов П. (+7916***4567)
28.03.2026 14:30 | 4 мин 12 сек

📋 Обсудили отгрузку труб на апрель.
Иванов подтвердил скидку 12%.
Просит прислать счёт до пятницы.

⚡ Priority: 72 | Risk: 45
📌 Отправить счёт до 04.04
🤝 Иванов обещал: скидка 12% с апреля

[OK] [Неточно]
```

### Команды

| Команда | Действие |
|---------|----------|
| `/digest` | Топ-5 по priority за сегодня |
| `/digest 7` | Дайджест за 7 дней |
| `/search труба` | Полнотекстовый поиск по транскриптам |
| `/contact +7916...` | Карточка контакта: история, promises, risk-тренд |
| `/promises` | Все открытые обещания |
| `/status` | Сколько файлов в очереди, ошибки |

## Pipeline: состояния и обработка ошибок

```
                    ┌──────────────────────┐
                    │       new            │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                ┌───│   transcribing       │───┐
                │   └──────────┬───────────┘   │
                │              │               │
                │   ┌──────────▼───────────┐   │
                ├───│    diarizing         │───┤
                │   └──────────┬───────────┘   │
                │              │               │
                │   ┌──────────▼───────────┐   │
                ├───│    analyzing         │───┤
                │   └──────────┬───────────┘   │
                │              │               │
                │   ┌──────────▼───────────┐   │
   error ◄──────┘   │       done           │   └──────► error
  (retry ≤ 3)       └─────────────────────┘    (retry ≤ 3)
```

- При ошибке: `status='error'`, `error_message=traceback`, `retry_count += 1`.
- Ретрай: раз в час, только если `retry_count < 3`.
- После 3 неудач: файл остаётся в error, уведомление в Telegram.

## Структура проекта

```
callprofiler/
├── pyproject.toml
├── README.md
├── STRATEGIC_PLAN.md
├── ARCHITECTURE.md
├── BENCHMARKS.md
├── configs/
│   ├── base.yaml                 -- пути, параметры
│   ├── models.yaml               -- модели ASR/LLM
│   └── prompts/
│       └── analyze_v001.txt
├── src/
│   └── callprofiler/
│       ├── __init__.py
│       ├── config.py
│       ├── models.py             -- dataclasses: CallMetadata, Analysis, и т.д.
│       ├── db/
│       │   ├── schema.sql
│       │   └── repository.py     -- CRUD, всегда с user_id
│       ├── ingest/
│       │   ├── filename_parser.py
│       │   └── ingester.py       -- приём файла, дедупликация
│       ├── audio/
│       │   └── normalizer.py     -- ffmpeg → WAV (из batch_asr.py: convert_to_wav)
│       ├── transcribe/
│       │   └── whisper_runner.py  -- из batch_asr.py: load_whisper, transcribe
│       ├── diarize/
│       │   ├── pyannote_runner.py -- из batch_asr.py: load_pyannote, diarize
│       │   └── role_assigner.py   -- из batch_asr.py: assign_speakers
│       ├── analyze/
│       │   ├── llm_client.py      -- Ollama HTTP API
│       │   ├── prompt_builder.py  -- сборка промпта с контекстом
│       │   └── response_parser.py -- парсинг JSON от LLM
│       ├── deliver/
│       │   ├── telegram_bot.py
│       │   └── card_generator.py  -- генерация {phone}.txt
│       ├── pipeline/
│       │   ├── orchestrator.py    -- из batch_asr.py: process_file, main
│       │   └── watcher.py        -- watchdog
│       └── cli/
│           ├── main.py           -- точка входа
│           ├── add_user.py
│           └── reprocess.py      -- перезапуск error-файлов
├── tests/
│   ├── test_filename_parser.py
│   ├── test_repository.py
│   └── fixtures/
└── data/                         -- .gitignore
```

## Что НЕ делать

| Не делать | Почему |
|-----------|--------|
| WhisperX word alignment | Для LLM-анализа сегменты faster-whisper достаточны |
| ECAPA-TDNN enrollment | pyannote + ref embedding из batch_asr.py уже работает |
| Gold-set 30 звонков | Обратная связь через Telegram-кнопки практичнее |
| Docker | Один ПК, один процесс |
| Redis/Celery | SQLite-статусы достаточны |
| Neo4j/ChromaDB | Не раньше фазы 5 |
| Своё Android-приложение | MacroDroid + txt файлы решают задачу |
| Schema versioning на JSON | Достаточно prompt_version в analyses |
