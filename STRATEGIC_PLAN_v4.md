# CallProfiler — Обновлённый стратегический план v4

## Статус проекта (апрель 2026)

**Что работает:**
- Pipeline: ingest → normalize → transcribe → diarize → LLM analyze
- БД SQLite с FTS5, мультипользовательская модель
- filename_parser для всех 5 форматов
- bulk-load: 18 000 .txt файлов загружены в БД
- bulk-enrich: LLM-анализ запущен (llama-server + Qwen3.5-9B)
- extract-names: regex-извлечение имён собеседников
- card_generator: генерация .txt карточек для overlay

**Что не работает / требует доработки:**
- JSON от LLM иногда обрезается → response_parser нуждается в robust починке
- Нет contact_summary (агрегированная карточка контакта)
- Нет глобального risk_score по контакту
- Нет фильтрации коротких/бессмысленных звонков
- Карточка overlay — plain text, не структурированная

---

## Критика документа LCIS

| Идея LCIS | Вердикт | Обоснование |
|-----------|---------|-------------|
| Event Store | ❌ Отвергнуто | SQLite с tables = event store без overengineering |
| NeMo telephonic | ❌ Отвергнуто | pyannote работает, менять без замера ошибки нельзя |
| LLM Role Correction | ❌ Отложено | Удваивает время обработки. Внедрять после замера влияния ошибок ролей на качество анализа |
| Precomputed HUD | ✅ Принято | Уже реализовано, улучшить формат |
| Фильтрация коротких/small-talk | ✅ Принято | Добавить call_type в analyses |
| Глобальный risk_score | ✅ Принято | Weighted average по контакту |
| contact_summary materialized | ✅ Принято | Пересчитывать после каждого звонка |
| USB-буфер в роутере | ❌ Отвергнуто | FolderSync достаточен |
| Zero False Merge | ⏸ Отложено | После обработки 18K файлов |
| Векторный поиск | ⏸ Отложено | FTS5 покрывает 90% |

---

## Принятые улучшения из LCIS

### 1. Структурированная карточка overlay

Текущий plain text заменить на структурированный формат:

```
header: Иван Иванов — Прораб
risk: 87 🔴
hook: Просрочил смету на 9 дней. Обещал вчера отправить.
bullet1: Долг 47 000 ₽ (срок 28.03)
bullet2: Противоречие: вчера «уже оплатил», сегодня «ещё не перевёл»
bullet3: Спроси про сына (поступает в институт)
advice: Говори первым. Не давай новых сроков без подтверждения.
```

Максимум 512 байт. MacroDroid парсит построчно по ключам.

### 2. contact_summary (materialized aggregate)

Новая таблица:

```sql
CREATE TABLE contact_summaries (
    contact_id    INTEGER PRIMARY KEY REFERENCES contacts(id),
    user_id       TEXT NOT NULL,
    total_calls   INTEGER DEFAULT 0,
    last_call_date TEXT,
    global_risk   INTEGER DEFAULT 0,       -- weighted avg risk_score
    avg_bs_score  INTEGER DEFAULT 0,       -- weighted avg bs_score
    top_hook      TEXT,                     -- главная фраза для карточки
    open_promises TEXT,                     -- JSON: незакрытые обещания
    open_debts    TEXT,                     -- JSON: долги
    personal_facts TEXT,                    -- JSON: small-talk факты
    contact_role  TEXT,                     -- "Прораб", "Поставщик"
    call_types    TEXT,                     -- JSON: {"business": 12, "smalltalk": 3, "short": 5}
    advice        TEXT,                     -- рекомендация по общению
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Пересчитывается после каждого обработанного звонка с этим контактом.

### 3. Классификация звонков

Добавить в analyses:

```sql
ALTER TABLE analyses ADD COLUMN call_type TEXT
    CHECK(call_type IN ('business','smalltalk','short','spam','personal','unknown'))
    DEFAULT 'unknown';
```

Правила:
- `short`: текст < 50 символов → пропустить LLM, автозаполнение
- `smalltalk`: LLM определяет (confidence > 0.8) → вес 0.1 в агрегатах
- `spam`: повторные короткие с неизвестных номеров → вес 0 в агрегатах
- `business`/`personal`: основной контент, полный вес

### 4. Генерация hook-фразы

LLM при анализе каждого звонка дополнительно генерирует `hook` — одну фразу, которая будет отображаться при следующем входящем звонке от этого контакта.

Добавить в промпт:
```
"hook": "одна фраза-напоминание для следующего звонка с этим человеком"
```

При генерации карточки: hook берётся из последнего бизнес-звонка, а не из small-talk.

---

## Обновлённые фазы

### ФАЗА 1.5 — Завершение массовой обработки (текущая, 1-2 недели)

1. **Починить response_parser** — robust JSON parsing с починкой обрезанных ответов
2. **Прогнать bulk-enrich на всех 18 000 файлах** — запустить и оставить на несколько дней
3. **Добавить call_type** — автоклассификация short/smalltalk/business
4. **Добавить hook в промпт LLM**

### ФАЗА 2 — Агрегация и карточки (1-2 недели после Фазы 1.5)

1. **Создать contact_summaries** — materialized aggregate
2. **Создать summary_builder.py** — пересчёт contact_summary после каждого звонка
3. **Обновить card_generator.py** — структурированный формат (header/risk/hook/bullets/advice)
4. **Пересчитать карточки для всех контактов** — bulk-rebuild-cards

### ФАЗА 3 — Telegram-бот и стабилизация (2-3 недели)

1. **Telegram-бот** — /digest, /search, /contact, /promises
2. **Утренний дайджест** — топ-N по priority + просроченные обещания
3. **Обратная связь** — кнопки [OK]/[Неточно]
4. **Второй пользователь** — проверка изоляции
5. **Автозапуск** — Task Scheduler при старте Windows

### ФАЗА 4 — Веб-интерфейс (2-3 недели)

1. **FastAPI + Jinja2** — таблица звонков, карточка контакта, аудиоплеер
2. **REST API** — /calls, /contacts, /search
3. **Дашборд** — топ контактов по risk, bs_score, активности

### ФАЗА 5 — Продвинутое (по замерам)

| Триггер | Действие |
|---------|----------|
| Ошибка ролей > 15% | LLM Role Correction (двухэтапная из LCIS) |
| FTS5 не хватает | Векторный поиск |
| Контакт меняет номер > 5% случаев | Zero False Merge (phones + contact_links) |
| pyannote DER > 25% | Попробовать NeMo telephonic |

---

## Текущий приоритет

```
СЕЙЧАС: починить parser → дообработать 18 000 файлов → contact_summaries → карточки
ПОТОМ:  Telegram-бот → веб-интерфейс
КОГДА-НИБУДЬ: LLM role correction, векторный поиск, NeMo
```

Порядок не меняется пока нет измеренной проблемы.
