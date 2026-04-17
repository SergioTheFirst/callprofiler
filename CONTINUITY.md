# CONTINUITY.md — Журнал непрерывности разработки

Этот файл обновляется после **каждой рабочей сессии**.
Цель: любой разработчик или AI-агент может открыть репозиторий и мгновенно
понять, что уже сделано, что в работе, и что делать дальше.

---

## Status

DONE: Profanity detector + Feature flags (5e74a50) + FTS5 search optimization (82e9b03)  
NOW: idle — biography-run на 58% (p1_scene, ~27 часов осталось)  
NEXT: biography-export после p1-p8; тестирование bulk-enrich на реальных данных  
BLOCKERS: None currently

---

## Текущое состояние: 2026-04-17 19:00 (FTS5 search fix + Profanity detector + Feature flags)

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
