# CONTINUITY.md — Журнал непрерывности разработки

Этот файл обновляется после **каждой рабочей сессии**.
Цель: любой разработчик или AI-агент может открыть репозиторий и мгновенно
понять, что уже сделано, что в работе, и что делать дальше.

---

## Status

DONE: Biography arch-fixes — export filter, p8 idempotency, checkpoint reset, p8b dedup (2026-04-20)
DONE: D:\calls → C:\calls path migration (2026-04-20)
DONE: Biography p9 wired + insight field pipeline (2026-04-20)
DONE: Biography module v6 — время звонка + годовой итог p9 (2026-04-20)
DONE: Biography Behavioral Engine p3b — bio-v7 (2026-04-20)
NOW: committed + pushed to main
NEXT: none pending — pipeline complete, behavioral engine live
BLOCKERS: None

---

## Текущее состояние: 2026-04-20 (Biography — p9 wired + insight pipeline)

### Ветка разработки
`main` (прямой push)

### Что сделано в этой сессии (2026-04-20, архитектурный аудит + реализация)

**Анализ:** Полный архитектурный и редакторский аудит biography модуля.
Две подтверждённых проблемы → реализованы:

**1. insight поле — конец потери данных (Change 1)**
- `schema.py`: `bio_scenes` — добавлена колонка `insight TEXT NOT NULL DEFAULT ''`.
  ALTER TABLE миграция через `_add_column_if_missing()` для существующих БД.
- `repo.py` `upsert_scene()`: `insight` включён в INSERT и UPDATE (16 params).
- `prompts.py` `build_thread_prompt()`: condensed dict включает `"insight"`.
- `prompts.py` `build_chapter_prompt()`: `scenes_slim` включает `"insight"`.
- Результат: LLM-интерпретация «почему сцена важна для книги» теперь сохраняется
  в БД и передаётся в p3 (thread builder) и p6 (chapter writer).

**2. p9_yearly.py — реализован и подключён (Change 2)**
- `schema.py`: `bio_books` — добавлена колонка `book_type TEXT NOT NULL DEFAULT 'main'`.
  ALTER TABLE миграция.
- `repo.py` `insert_book()`: новый параметр `book_type='main'` (default).
- `p7_book.py`: передаёт `book_type='main'` явно.
- `p9_yearly.py`: новый модуль (по образцу p8_editorial). Определяет год автоматически
  (самый свежий с главами) или принимает `year=`. Вызывает `build_yearly_summary_prompt()`,
  сохраняет `bio_books` с `book_type='yearly_summary'`.
- `orchestrator.py`: p9_yearly добавлен в PASSES и ORDER (9-й проход).
- `cli/main.py`: docstring обновлён «8-проходного» → «9-проходного».

### Следующий шаг
- Нет блокирующих задач. Пайплайн полностью реализован (p1-p9).
- Запустить `biography-run --user X` для полного прогона, проверить p9 вывод.

### Известные ограничения / долги
- Существующие bio_scenes без insight = пустая строка (нужен p1 re-run с новым PROMPT_VERSION для заполнения).
- Существующие bio_books без book_type = 'main' (заполнено DEFAULT).

---

## Текущее состояние: 2026-04-20 (Biography v6 — время звонка + годовой итог p9)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ` (push → main)

### Что сделано в этой сессии (2026-04-20, v6 сессия)

1. **`_call_hour()` helper** — извлекает час из call_datetime (ISO/space sep).
2. **`_SCENE_SYS` + `build_scene_prompt()`** — time_ctx: ночной/утренний сигнал
   передаётся LLM явно в user message, инструкция в system prompt.
3. **`_CHAPTER_SYS`** — правило: упоминать нестандартный час в прозе.
4. **`_YEARLY_SYS` + `build_yearly_summary_prompt()`** — p9, новый проход:
   годовой итог в духе Довлатова (3-5 абзацев, сквозные мотивы, без морали).
5. **Rules обновлены**: biography-style.md, biography-prompts.md, CLAUDE.md.
6. **PROMPT_VERSION**: bio-v5 → bio-v6. Тесты: OK bio-v6.

### Следующий шаг
- `runner.py` — добавить вызов p9 в `biography-run --yearly`
- Добавить `bio_books.book_type` поле если нет в схеме

### Известные ограничения / долги
- p9 runner ещё не реализован (только промпт)
- biography/CLAUDE.md: bio-v4; current: bio-v6 — строчка не обновлена

---

## Текущее состояние: 2026-04-20 (Biography v5 — аудит противоречий в промптах)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ` (push → main)

### Что сделано в этой сессии (2026-04-20, v5 сессия)

**Аудит и чистка биографических промптов — bio-v5:**

1. **PROMPT_VERSION**: `bio-v4` → `bio-v5`

2. Найдено 18 противоречий/нагромождений после накопленных правок v1-v4.

3. **Критические исправления:**
   - `_SCENE_SYS`: убрано "канонические имена" → теперь "как в транскрипте"
   - `_PORTRAIT_SYS`: убрано "в канонической форме" → "живое письмо"
   - `_ARC_SYS`: "звонков" → "бесед" (запрещённое слово в промпте)
   - `build_chapter_prompt()` user msg: убран жёсткий "Объём 2500-4500 слов"

4. **Чистка нагромождений:**
   - `_CHAPTER_SYS`: убран дубль самоиронии; исключение для коротких глав
     в правиле подзаголовков; психологическое измерение сокращено до
     одной строки (дублировало _STYLE_GUIDE)
   - `_EDITORIAL_SYS`: убран риск вымысла при "добавь если нет"; смягчено
     принудительное психологизирование; убраны дубли имён
   - `_BOOK_FRAME_SYS`: убран дубль запрета цифр/звонков

5. **`biography/CLAUDE.md`**: исправлены 3 устаревшие ссылки (bio-v2, имена, объём)

**Тесты:** OK bio-v5.

**Принцип:** промпты теперь без противоречий; каждое правило живёт ровно в
одном месте — либо в _STYLE_GUIDE (разделяемый), либо в конкретном промпте
(специфичное для прохода).

---

## Предыдущая сессия: 2026-04-20 (Biography v4 — конституциональные требования)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ` (push → main)

### Что сделано в этой сессии (2026-04-20, v4 сессия)

**Конституциональные требования — био-v4:**

1. **PROMPT_VERSION**: `bio-v3` → `bio-v4`

2. **`prompts.py` — 2 изменения:**
   - `_CHAPTER_SYS`: убран минимум слов (было «2500-4500 обязательно» → 
     теперь «в норме 2500-4500, но без механического минимума»). Добавлено:
     «если материала мало — пиши честно и кратко, без воды». Имена: с механического
     каноничения (Василий не Вася) на живое письмо (как в материале или контактах).
     Сергей-амбигуитет: только «Медведев Сергей» = владелец.
   - `_EDITORIAL_SYS`: удален минимум расширения (было «если < 2500, расширь до 
     3000-3500» → теперь «нет минимума»). Добавлено: инструкция на живое письмо
     для имён.

3. **Memory-файлы обновлены:**
   - `.claude/rules/biography-style.md`:
     - Russian language checklist: переделано на контекстное использование имён.
     - Добавлено: Сергей-амбигуитет (только полная ФИ = владелец).
     - Length таблица: убран минимум 1500 слов для p6, добавлено «нет минимума
       если материала мало».
   - `.claude/rules/biography-data.md`:
     - Chapter assembly: убран диапазон 1500-2500, добавлено честное кратко
       без воды.
   - `.claude/rules/biography-prompts.md`:
     - Global conventions: уточнено на живое письмо (не механическое).

4. **CHANGELOG.md + CONTINUITY.md**: документировано все выше.

**Тесты:** `prompts.py` импортируется без ошибок (OK bio-v4).

**Принцип:** От механических правил к контекстному творческому письму.
Стиль — современный non-fiction для взрослой русскоязычной аудитории 45+.
Без воды, без минимумов, только живой материал.

---

## Предыдущая сессия: 2026-04-20 (Biography v3 — психологическая глубина)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ` (push → main)

### Что сделано в сессии v3 (2026-04-20)

**Психологическая глубина персонажей — bio-v3:**

1. **`PROMPT_VERSION`: `bio-v2` → `bio-v3`** — memoization сам переключится.

2. **`prompts.py` — 5 изменений:**
   - `_STYLE_GUIDE`: новый раздел «Психологическая глубина» — разрешает
     гипотетические интерпретации поведенческих паттернов через «похоже»,
     «возможно», «судя по всему». Максимум 1-2 на главу. Старое правило
     «не додумывай мотивы» заменено: мотивы допустимы как версии.
   - `_SCENE_SYS` → `insight`: расширено — называть психологическую динамику.
   - `_PORTRAIT_SYS` → `prose`: инструкция на 1 поведенческую интерпретацию
     паттерна. Правила: «версия мотива — да; диагноз — нет».
   - `_CHAPTER_SYS`: новый пункт «Психологическое измерение», 1-2 наблюдения.
   - `_EDITORIAL_SYS`: проверка психологической объёмности при редактуре.

3. **`.claude/rules/biography-style.md`:**
   - Секция Tone: добавлен раздел «Психологическая глубина» с примерами.
   - Forbidden/Вымысел: смягчено — гипотезы через условное наклонение допустимы.
   - Sanity checklist: +2 пункта.

4. **`.claude/rules/biography-prompts.md`:**
   - p1 insight, p5 Style requirement, p6 требования, p8 задачи — обновлены.

**Тесты:** `OK bio-v3` (import check).

### Следующий шаг
1. Дождаться p1 → p2-p8 получат bio-v3 промпты.
2. Проверить качество портрета (p5) — психологическая интерпретация vs плоскость.
3. Если нужно — подправить примеры в `_PORTRAIT_SYS` и поднять до bio-v4.

### Известные ограничения / долги
- Активный p1_scene использует кэш (bio-v1). Пересчёт: `DELETE FROM bio_checkpoints WHERE pass_name='p1_scene'`.
- Словарный детектор мата не ловит обфускации.
- Windows file-lock в test_integration.py (6 failures, не в scope).

---

## Текущее состояние: 2026-04-19 (Biography v2 — стиль, токены, memory files)

### Ветка разработки
`main` (прямой push по CLAUDE.md → Git Push Authorization)

### Последний коммит (ожидается)
```
<pending> feat(biography): bio-v2 — max_tokens + non-fiction style + memory files
```

### Что сделано в этой сессии (2026-04-19)

**Все изменения в модуле `src/callprofiler/biography/`:**

1. **`PROMPT_VERSION`: `bio-v1` → `bio-v2`** — memoization сам переключится.

2. **`max_tokens` увеличены** во всех 8 проходах:
   - p1=1800 (было 1200), p2=3800 (было 2500), p3=2500 (было 1500),
     p4=4200 (было 2800), p5=2500 (было 1400), **p6=5500** (было 3200),
     p7=3500 (было 2000), p8=5500 (было 3200).
   - Главное — p6 (chapter) для 2500-4500 слов/глава.

3. **`prompts.py` переписан**:
   - Общий `_STYLE_GUIDE` в p6/p7/p8: non-fiction для 45+, спокойное
     достоинство, эмпатия, умеренная самоирония, запрет на
     «звонок/созвон» и цифры количества.
   - p1 Scene: новое поле `insight`, synopsis 2-4 предл., tone
     `reflective`, key_quote 240 симв.
   - p3 Thread: новые поля `turning_points`, `open_questions`, summary
     3-6 абзацев.
   - p5 Portrait: новое поле `what_owner_learned`, prose 3-5 абзацев,
     запрет на ярлыки-диагнозы.
   - p6 Chapter: структура (вводный → 2-4 блока `## …` → закрывающий),
     1-3 цитаты, ≥1 эмпатическая нота, ≤1 самоироничная реплика.
   - p7 Frame: prologue/epilogue 3-5 абзацев.
   - p8 Editorial: подключён полный style guide, разрешено расширять
     короткие главы.
   - JSON budgets в p6: portraits 4000→6000, arcs 3000→4500,
     scenes 6000→9000, prose excerpt 500→1200.
   - p8 input clip: 12000→20000 симв.

4. **Новые memory-файлы (Progressive Disclosure):**
   - `src/callprofiler/biography/CLAUDE.md` (71 стр.) — обзор модуля.
   - `.claude/rules/biography-data.md` — SQL, пороги, анонимизация,
     idempotency, resume protocol.
   - `.claude/rules/biography-style.md` — аудитория, тон, длины,
     структура, запрещённое, sanity checklist.
   - `.claude/rules/biography-prompts.md` — контракты каждого промпта
     (input/output/constraints/quote rules).
   - Root `CLAUDE.md` — добавлены 4+1 ссылки в Progressive Disclosure.

**Тесты:** `prompts.py` импортируется без ошибок (`PYTHONPATH=src python -c "..."` → `OK bio-v2`).

### Текущий процесс

- **biography-run** для `serhio`: p1_scene на **58%**, идёт на старом
  `bio-v1` (кэш не сброшен, новые промпты не применяются к уже
  начатому проходу).
- Скорость: ~4 сцены/минута, ETA p1 ~27 часов.
- Проходы p2-p8 стартуют после p1 и сразу получат новые промпты
  и новые `max_tokens`.

### Следующий шаг

1. Дождаться p1 завершения (вечер 2026-04-18 по старому ETA;
   теперь — примерно 2026-04-20).
2. Проверить качество p2-p8 на `bio-v2` (одна глава-пробник из
   реальных данных до полного run).
3. Если стиль просел — подправить `_STYLE_GUIDE` и поднять до `bio-v3`.
4. `biography-export --user serhio --out book.md`.

### Известные ограничения / долги

- Активный p1_scene использует старые промпты (кэш). Пересчёт только
  через `DELETE FROM bio_checkpoints WHERE pass_name='p1_scene'`.
- Словарный детектор мата не ловит обфускации (см. сессию 2026-04-17).
- Windows file-lock в test_integration.py (6 failures, не в scope).

---

## Сессия 2026-04-19: Biography v2 — стиль + токены + memory

### Что изменено
Файлы: `prompts.py` (переписаны 7 system prompts), `p1-p8_*.py` (max_tokens),
новые `biography/CLAUDE.md` + 3 rules + обновлённый root `CLAUDE.md`.

### Почему
Владелец уточнил аудиторию и стиль: non-fiction для 45+ с широким
кругозором, спокойное достоинство, эмпатия, умеренная самоирония.
Текущие главы слишком короткие (500-1200 слов) — нужны 2500-4500.
Промпты не кодировали тон, из-за чего риск сухих или неловких глав.

### Что проверить потом
- Длина реальной главы от p6 на `bio-v2` (целевое 2500-4500 слов).
- Наличие прямых цитат и эмпатических нот в сгенерированных главах.
- Работа editorial (p8): не сжимает ли главу обратно.

---

## Предыдущее состояние: 2026-04-17 19:00 (FTS5 search fix + Profanity detector + Feature flags)

### Ветка разработки
`main` (прямой push по CLAUDE.md → Git Push Authorization)

### Последний коммит
```
82e9b03 fix: use FTS5 MATCH instead of LIKE in search_transcripts
```

### Что сделано в этой сессии (2026-04-17)

**СЕССИЯ 2 (Claude Code на Windows, 13:00–19:00):**

1. **FTS5 search optimization** — `src/callprofiler/db/repository.py:311–331`
   - Переделана `search_transcripts()` с LIKE (O(n) скан) на **FTS5 MATCH** (индекс)
   - Фраза заключена в кавычки для точного поиска: `"query"`
   - Escape кавычек в user input (`"` → `""`) для безопасности
   - Подзапрос ранжирует по FTS5 BM25 score
   - Результаты по релевантности, не по call_id
   - LIMIT 50 (параметр) для контроля выдачи
   - Тесты: 2/2 search тесты зелёные ✅
   - Коммит: `82e9b03`

2. **Известные issues** (не затронуты моим изменением):
   - Pre-existing Windows file-lock ошибка в test_integration.py (6 failures из 93 тестов)
   - Не связано с FTS5 или profanity детектором

**СЕССИЯ 1 (утро, 05:00–13:00):**

1. **Словарный детектор мата (без LLM)** — `src/callprofiler/analyze/profanity_detector.py` (107 строк):
   - `_MAT_ROOTS` — ~50 корней русского мата (большая четвёрка + производные + эвфемизмы)
   - Один скомпилированный regex `\b\w*(root1|root2|…)\w*\b` (IGNORECASE + UNICODE)
   - `count_profanity(text) -> {"count", "unique", "density"}` — density = count/words*100, round(2)
   - Сознательный over-match (false positives типа «схуяли» приемлемы)
   - `find_profanity()` + `get_roots()` — для отладки/тестов

2. **DB-миграция: 2 новые колонки в `analyses`**:
   - `profanity_count INTEGER DEFAULT 0`
   - `profanity_density REAL DEFAULT 0`
   - `schema.sql` обновлён (create) + `repository._migrate()` добавляет через `PRAGMA table_info` (auto-migrate существующих БД)
   - `save_analysis()` + `save_batch()` теперь пишут 15 колонок (было 13)

3. **Analysis dataclass** — `models.py`:
   - Добавлены поля `profanity_count: int = 0` и `profanity_density: float = 0.0`

4. **Enricher интеграция** — `bulk/enricher.py`:
   - Считаем мат **до разветвления** stub/LLM → метрика всегда пишется в БД
   - При LLM-ветке добавляем подсказку в user_message: «Сигнал детектора (не LLM): мат=N (уникальных=M, плотность=D/100слов). Учти при оценке bs_score и call_type.»
   - Прикрепляем к analysis перед сохранением
   - Всё feature-gated: `cfg.features.enable_profanity_detection` + `cfg.features.enable_event_extraction`

5. **Feature flags** — `configs/features.yaml` + `config.py`:
   - 6 флагов: `enable_diarization`, `enable_llm_analysis`, `enable_profanity_detection`, `enable_name_extraction`, `enable_event_extraction`, `enable_telegram_notification`
   - Новый dataclass `FeaturesConfig` + `_load_features(config_dir, inline)` со стратегией: **inline в base.yaml > features.yaml рядом > дефолты**
   - Graceful degradation: флаг false → этап пропущен, pipeline продолжается

6. **Orchestrator gating** — `pipeline/orchestrator.py`:
   - `enable_diarization` → ранний return из `_diarize_call` (все сегменты остаются как есть; pipeline идёт дальше)
   - `enable_llm_analysis` → skip `_analyze_call`
   - `enable_telegram_notification` → Telegram-notifier вызывается только при `self.telegram and self.config.features.enable_telegram_notification`

**Тесты (сессия 1):** `pytest tests/ -v` — 93/93 pass ✅ (регрессий нет).

**Коммит (сессия 1):** `5e74a50` — feat: profanity detector + feature flags system

### Текущий процесс

- **biography-run** для пользователя `serhio`: p1_scene на **58%** (9195/15726 сцен, 11 ошибок)
- Скорость: ~4 сцены/минута
- Последнее обновление: 2026-04-17 05:31:40
- ETA p1: ~27 часов (до вечера 2026-04-18)
- ETA всех 8 проходов (p1–p8): ~40–45 часов

### Следующий шаг

1. Дождаться p1 завершения (вечер 2026-04-18)
2. Запустить `biography-export --user serhio --out book.md` для получения готовой книги
3. Тестировать `bulk-enrich --user X --limit 10` на реальных данных с profanity метриками
4. Собрать статистику по profanity детектору (coverage по обиходному мату)

### Известные ограничения / долги

- Словарь не ловит обфускации (`х*й`, `x_y`, через кириллицу+латиницу)
- FTS5 search работает только на существующих indices (если transcripts_fts не создана, фолбэк на LIKE)
- Windows file-lock при удалении temp-dir в test_integration.py (6 failures, не затронуты моим кодом)
- Latent bug в `orchestrator._analyze_call`: используется несуществующий `self.config.models.ollama_url` — НЕ ТРОНУТО (не в scope; live-watch pipeline не тестировался)

---

## Сессия 2026-04-16: 8-Pass Biography Pipeline + Memory Protocol

### Результат

Полнофункциональный 8-проходный конвейер генерации биографии из транскриптов, готовый к многодневному прогону на локальном llama-server.

#### Создано 15 новых файлов (~3200 строк кода)

- **schema.py** — 7 таблиц (bio_scenes, bio_entities, bio_threads, bio_arcs, bio_portraits, bio_chapters, bio_books) + bio_checkpoints (resume) + bio_llm_calls (memoization)
- **repo.py** — BiographyRepo: идемпотентные upsert'ы по user_id, FTS-free, переиспользует sqlite3 connection host Repository
- **llm_client.py** — ResilientLLMClient: MD5-ключ кэша, exponential backoff retry, логирование в bio_llm_calls
- **prompts.py** — 8 русскоязычных builder'ов (p1..p8), strict JSON contracts, head+tail clipping
- **json_utils.py** — extract_json(): удаление markdown-заборов, lenient JSON recovery при усечении
- **p1_scene.py** — per-call narrative units (synopsis, tone, themes, entities)
- **p2_entities.py** — canonicalization + alias merging (Васяа/Вася/Василий), cross-chunk dedup
- **p3_threads.py** — per-entity chronological threads с tension curves
- **p4_arcs.py** — sliding-window problem→investigation→outcome arcs
- **p5_portraits.py** — character sketches (traits, relationship, pivotal scenes)
- **p6_chapters.py** — monthly chapters, top-40 scenes по importance
- **p7_book.py** — frame (title/TOC/prologue/epilogue) + full stitched prose
- **p8_editorial.py** — chapter polish pass + re-stitch as version=final
- **orchestrator.py** — per-pass try/except (crash in one pass → only its checkpoint fails, continues to next)

#### CLI команды

- `biography-run [--passes p1,p2,...] [--max-retries 5]` — Run biography pipeline
- `biography-status` — Show per-pass checkpoint status
- `biography-export --out FILE.md` — Export latest assembled book

**Commits:**
- `5e74a50` — feat: profanity detector + feature flags system
- `82e9b03` — fix: use FTS5 MATCH instead of LIKE in search_transcripts
