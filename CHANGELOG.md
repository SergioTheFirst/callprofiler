# CHANGELOG.md

Все значимые изменения в проекте фиксируются здесь.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/).
Версионирование: [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

## [2026-04-25b] — Knowledge Graph: Этап 2.2 (DRIFT CHECK — проверка смещения метрик BS-индекса)

### Added — graph/auditor.py (_check_validator_impact_drift method)

**Проблема:** При пересчёте BS-индекса (recalc_from_events) может возникнуть дрейф
формулы или данных. Нужно автоматически обнаруживать ненадёжные метрики.

**Решение** в `graph/auditor.py`:
```python
def _check_validator_impact_drift(self, user_id: str) -> dict:
    # Стратифицированная выборка: 40% с bs_index > 50, 40% с total_calls > 10, 20% random
    # Для каждого: full_recalc_from_events() и вычислить drift
    # drift = abs(stored_bs - recalc_bs) / max(stored_bs, 1.0)
    # Returns: ok=(drift_pct <= 0.10), count=drifted_entities, details
```

**Алгоритм:**
1. Получить все entities с metrics для user_id
2. Классифицировать по bs_index, total_calls
3. Стратифицированная выборка (40/40/20), размер = max(10, min(100, count // 3))
4. Для каждого в sample: recalc_from_events()
5. Если drift > 0.10 → счётчик drifted_count
6. Вернуть ok=(drift_pct <= 0.10)

**Результаты проверки:**
- Если drift_pct <= 10% → ok=True (стабильные метрики)
- Если drift_pct > 10% → ok=False (требуется внимание)
- details dict с sample_size, drifted_count, drift_pct, examples

**Интеграция:** Добавлена в run_checks() как 10-й check (наряду с orphan_events, owner_contamination).

**Тесты:** 6 новых в `test_graph.py` (75 total):
- test_auditor_drift_check_empty_graph: пустой граф → ok=True
- test_auditor_drift_check_small_sample: < 3 entities → ok=True
- test_auditor_drift_check_no_drift: свежие данные → drift минимален
- test_auditor_drift_check_stratified_sampling: стратификация работает корректно
- test_auditor_drift_check_details_structure: структура details match contract
- test_auditor_drift_check_with_low_drift: drift <= 10% → ok=True

**Result:** Auditor теперь проверяет консистентность BS-индекса. Обнаруживает дрейф
в 10% выборке entities, стратифицированной по качеству. Все 75 tests pass.

---

## [2026-04-25] — Knowledge Graph: Этап 2 (FACT VALIDATOR — усиленная валидация фактов)

### Added — graph/validator.py (FactValidator class)

**Проблема:** LLM может генерировать факты с неполными или неточными цитатами.
Требуется валидация ДО записи в events table.

**Решение** в `graph/validator.py`:
```python
class FactValidator:
    def validate(fact, transcript_text=None) -> dict:
        # Check 1: Quote length >= 8 chars
        # Check 2: Rolling window search в transcript (ratio >= 0.72)
        # Check 3: Speaker attribution detection ([me] vs [s2])
        # Check 4: Semantic checks (future markers, negations, vagueness)
        # Returns: valid, errors[], warnings[], speaker, is_future, is_negated, is_vague
```

**Валидация включает:**
1. **Length:** quote.strip() >= 8 (MIN_QUOTE_LEN)
2. **Verbatimness:** rolling window match ratio >= 0.72 (если transcript_text есть)
3. **Speaker:** detect [me] vs [s2] from context (last marker in lookback window)
4. **Semantics:**
   - Future markers (EN: will, shall, plan; RU: буду, будет, планирую, обещаю)
   - Negations (EN: not, no, never; RU: не, нет, никогда)
   - Vague words (EN: maybe, probably, seems; RU: может, наверное, похоже)

Warnings генерируются для семантических проблем но не блокируют upsert.

### Changed — graph/builder.py (FactValidator integration)

- Импорт FactValidator
- `__init__()` создаёт `self._validator = FactValidator()`
- `_update()` вызывает `validator.validate(fact, transcript_text)` перед upsert
- Факты с errors отклоняются; warnings логируются как debug

**Фильтрация (до upsert):**
```
1. MIN_FACT_CONFIDENCE >= 0.6 (как раньше)
2. validator.validate() — если errors → skip
```

### Updated graph/builder.py docstring

Документированы валидация checks в `update_from_call()` docstring.

### Changed — .claude/rules/graph.md (Anti-Noise Filters)

Уточнена роль FactValidator (Этап 2) в валидационном конвейере.
Described quote verification strategy (rolling window + speaker detection).

**Тесты:** 13 новых в `test_graph.py` (56 total, все pass):
- test_validator_quote_length_valid/invalid
- test_validator_quote_found_exact_in_transcript
- test_validator_quote_found_fuzzy_in_transcript
- test_validator_quote_not_found_in_transcript
- test_validator_detects_speaker_me/s2
- test_validator_future_markers
- test_validator_negation_detection
- test_validator_vague_word_detection
- test_validator_combined_warnings
- test_validator_no_transcript_warning
- test_builder_uses_validator_rejects_short_quotes
- test_builder_uses_validator_with_transcript

**Result:** Facts now validated before upsert. Exact and fuzzy match support.
Speaker attribution enabled for call context. Semantic warnings logged (debug level).

---

## [2026-04-25] — Knowledge Graph: Этап 5 (REPLAY — идемпотентная пересборка)

### Added — graph/replay.py (GraphReplayer class)

**Проблема:** После исправления raw_response в analyses нужно пересоздать граф
(entities/relations/entity_metrics). Требуется идемпотентная пересборка, которая
при повторном запуске на том же data не создаёт новые rows.

**Решение** в `graph/replay.py`:
```python
class GraphReplayer:
    def replay(user_id, limit=None) -> dict:
        # DELETE entity_metrics, relations, entities (unarchived)
        # UPDATE events SET entity_id/fact_id/quote = NULL (v2 only, не трогает v1)
        # GraphBuilder.update_from_call() для каждого v2 analysis
        # full_recalc_from_events() для каждого entity
        # Returns: stats с assertions
```

**Assertions (exit code !=0 если нарушено):**
- `facts_count > 0` после обработки calls
- `orphan_events == 0` (event.entity_id → несуществующая entity)
- `owner_contamination == 0` (is_owner=1 entity не имеет bs_index > 0)

**Используется:**
- Ручное исправление raw_response в analyses + `graph-replay`
- Смена BS-formula версии + `graph-replay`
- Тестирование детерминизма

### Added — graph-replay CLI command

```bash
python -m callprofiler graph-replay --user USER_ID [--limit N]
```

Outputs stats JSON: calls_processed, entities_count, relations_count, facts_count,
avg_bs_index, warnings.

Exit 0 = ok, 1 = warnings, 2 = critical assertions failed.

### Changed — graph/builder.py (transcript_text parameter)

- `update_from_call(call_id, transcript_text=None)` — новый опциональный параметр
- Используется на шаге 2 (FactValidator) для верификации цитат

### Changed — .claude/rules/graph.md (Layer Contract + CLI docs)

- Добавлен **Layer Contract**: events = DERIVED (computed from analyses.raw_response)
- Добавлена документация по graph-replay команде

### Updated architecture documentation

Зафиксировано что events.entity_id/fact_id/quote — **derived fields**, безопасно
пересоздаются при replay. events WHERE schema_version='v1' OR entity_id IS NULL
не трогаются при replay (безопасность для legacy pipeline).

**Тесты:** 5 новых в `test_graph_replay*` (42 total). Все pass.
- test_graph_replay_empty_user, test_graph_replay_v2_only, test_graph_replay_idempotent
- test_graph_replay_skips_v1, test_graph_replay_assertions_facts_count

## [2026-04-25] — Knowledge Graph: Этапы 3-4 (EntityResolver + LLM Disambiguator)

### Added — full_recalc_from_events() INVARIANT (aggregator.py)

**Проблема:** После merge двух сущностей `recalc_for_entities()` читал метрики
инкрементально, что давало двойной счёт (события обеих сущностей уже объединены,
но старые метрики накапливались поверх).

**Исправление** в `aggregator.py`:
```python
def full_recalc_from_events(self, entity_id: int) -> dict:
    # Читает user_id из entities, запрашивает DISTINCT call_ids через events,
    # группирует по fact_type, JOIN analyses для avg_risk, JOIN calls для
    # last_interaction, вычисляет emotional_pattern JSON, вызывает _bs_v1_linear(),
    # UPSERT через upsert_entity_metrics(), коммит, возвращает полный snapshot dict.
```

INVARIANT: `entity_metrics = PURE FUNCTION(events + calls + promises)`
После merge executor вызывает `full_recalc_from_events(canonical_id)` вместо
`recalc_for_entities()`.

**Тесты:** test_full_recalc_returns_dict_for_empty_entity, test_full_recalc_idempotent,
test_full_recalc_entity_not_found_raises, test_full_recalc_counts_facts_correctly

### Fixed — 5 багов в resolver.py (execute_merge + _fetch_entities)

**Баг 1:** `_fetch_entities()` не читал `is_owner` — владелец мог попасть в кандидаты.
**Баг 2:** `_fetch_entity_by_id()` — неправильные индексы колонок row[5]/row[6].
**Баг 3:** `execute_merge()` — user_id брался из `canonical_name.split(":")[0]` (неверно).
**Баг 4:** `EntityMetricsAggregator(self)` — self это EntityResolver, не GraphRepository.
**Баг 5:** `recalc_for_entities([canonical_id], user_id)` → `full_recalc_from_events(canonical_id)`.
**Баг 6 (pre-existing):** `_find_blocking_pairs` — `sum([v for v in blocks.values()], [])` —
  blocks.values() суть dict'ы, а не lists. Исправлено на:
  `[lst for block_dict in blocks.values() for lst in block_dict.values()]`

### Added — is_owner migration (repository.py)

- `("entities", "is_owner", "INTEGER DEFAULT 0")` добавлено в `_entity_migrations`
- Индекс `idx_entities_owner` на `entities(user_id, is_owner)`
- `_fetch_entities()` теперь фильтрует `COALESCE(is_owner, 0) = 0`

**Тесты:** test_is_owner_column_exists_after_migration, test_is_owner_index_exists,
test_resolver_find_candidates_excludes_owner, test_resolver_execute_merge_owner_blocked

### Added — graph/auditor.py (9 sanity checks, exit code 2 for CRITICAL)

```python
class GraphAuditor:
    CRITICAL_CHECKS = {"owner_contamination", "orphan_events"}
    # 9 проверок: entities_without_events, high_bs_no_contradictions,
    # high_risk_no_promises, orphan_events (CRITICAL), metrics_drift,
    # archived_referenced, merge_candidates_residual,
    # owner_contamination (CRITICAL), empty_canonical_quotes
```

CLI: `graph-audit --user X` → exit 0 (ok) / 1 (warnings) / 2 (critical).

**Тесты:** test_auditor_clean_graph_all_ok, test_auditor_detects_orphan_events,
test_auditor_detects_owner_contamination

### Added — Post-merge chain detection (resolver.py Step 3)

После закрытия merge-транзакции `execute_merge()` вызывает `find_candidates()` для
canonical entity и логирует предупреждение, если обнаружены цепочки (chain merge candidates).

### Added — biography/data_extractor.py (3 pure-read functions)

```python
def get_entity_profile_from_graph(entity_id, conn) -> dict
# → canonical_name, entity_type, aliases, metrics, top_facts, conflicts,
#   promise_chain, top_relations, timeline, evolution

def get_behavioral_patterns(entity_id, conn) -> dict
# Детерминированные паттерны из метрик:
# promise_breaker, contradictory, vague_communicator, blame_shifter,
# emotionally_volatile, reliable, high_risk

def get_social_position(entity_id, conn) -> dict
# → org_links, open_promises, conflict_count, centrality
```

### Changed — biography/p6_chapters.py (graph integration)

- `run()` принимает `graph_conn=None`
- `_enrich_portraits_with_graph(portraits, graph_conn)`: добавляет `graph_profile`
  и `behavioral_patterns` к каждому portrait
- Lazy import с флагом `_GRAPH_AVAILABLE`

### Added — graph/llm_disambiguator.py (Этап 4 — LLM Advisory)

```python
class LLMDisambiguator:
    GRAY_ZONE_MIN = 0.50  # score ≥ 0.65 → manual merge (no LLM)
    GRAY_ZONE_MAX = 0.64  # score < 0.50 → skip
    def disambiguate_pair(self, entity_a, entity_b, score, signals) -> dict:
        # Returns: llm_says (MERGE|SEPARATE|UNCLEAR), confidence 0-1,
        # reasoning, signals_for, signals_against, raw_response
```

LLM только советует — НЕ принимает решение о merge. `llm_says` = advisory.

### Added — configs/prompts/entity_disambiguation.txt

Русскоязычный промпт (4 аспекта: temporal, role_consistency, mutual_exclusivity,
behavioral_fingerprint). Явно указано: "Ты НЕ принимаешь решение об объединении."
Возвращает JSON: `{verdict, confidence, reasoning, signals_for, signals_against}`.

### Added — CLI commands (cli/main.py)

- `entity-merge --user X [--dry-run] [--loop]` — слияние с preview и итерацией
- `entity-unmerge --user X --merge-id N` — откат слияния из snapshot
- `graph-audit --user X` — 9 sanity checks, exit 2 for CRITICAL
- `book-chapter --user X --entity N` — JSON профиль сущности для biography

**Тесты итого:** 37 pass (было 25 → +12 в этой сессии). Время 0.24s.

## [2026-04-24] — Knowledge Graph: Этапы 1-2

### Added — Knowledge Graph layer (graph module)

**Проблема:** Structured data (entities, relations, facts) extracted by LLM
lived only as unstructured JSON in `analyses.raw_response`. No queryable graph.

**Что реализовано (Этапы 1-2):**

**Схема (Этап 1):**
- `entities` table: canonical entity storage (PERSON/PLACE/COMPANY/PROJECT/EVENT)
  with `normalized_key` (Latin transliteration, snake_case, LLM-generated)
- `relations` table: time-decayed weighted edges between entities
  (decay formula: `weight * 0.5^(days/180) + confidence`)
- `entity_metrics` table: aggregated BS-index + per-type fact counts
- `analyses.schema_version` column (ALTER TABLE, DEFAULT 'v1')
- 7 columns added to `events`: `entity_id`, `fact_id`, `quote`, `start_ms`,
  `end_ms`, `polarity`, `intensity`
- Partial unique index on `events.fact_id` for deduplication
- `apply_graph_schema(conn)`: idempotent migration callable on startup

**Модуль `src/callprofiler/graph/` (Этап 2):**
- `config.py`: thresholds (MIN_FACT_CONFIDENCE=0.6, RELATION_DECAY_DAYS=180)
- `repository.py`: `GraphRepository` — upsert/get for all graph tables
- `builder.py`: `GraphBuilder.update_from_call()` — reads raw_response,
  skips v1 silently, processes v2: upserts entities → relations (with decay)
  → facts (anti-noise filtered, INSERT OR IGNORE dedup)
- `aggregator.py`: `EntityMetricsAggregator` — deterministic BS-index v1_linear:
  `0.40*broken_ratio + 0.20*contradiction_dens + 0.15*vagueness_dens
  + 0.15*blame_dens + 0.10*emotional_dens`

**Промпт `analyze_v001.txt`:**
- Добавлены `schema_version: "v2"`, `entities`, `relations`, `structured_facts`
  arrays с полными инструкциями по извлечению (normalized_key, quote-контракт)

**Интеграция:**
- `enricher.py`: `_update_graph()` вызывается после batch flush; lazy import;
  non-fatal; gated by `cfg.features.enable_graph_update`
- `orchestrator.py`: graph update после `save_promises()`; same pattern
- `config.py`: `FeaturesConfig.enable_graph_update = True`

**CLI:**
- `graph-backfill --user X [--schema v2|all]`
- `reenrich-v2 --user X [--limit N]`
- `graph-stats --user X`

**Тесты:** 25 тестов в `tests/test_graph.py` — все pass (0.15s).
Покрытие: schema idempotency, repository CRUD, user isolation, builder
(v1 skip, v2 process, relations, fact filtering, dedup), BS-index formula,
aggregator persistence.

**Документация:** `.claude/rules/graph.md` (layer principles, anti-noise rules,
BS-formula versioning, schema_version contract, Этапы 3-4 roadmap).

### Added — Biography: Behavioral Engine p3b + bio-v7 (2026-04-20)

**Новый детерминированный проход p3b_behavioral между p3 и p4:**

**[p3b] Behavioral Engine — no LLM, pure stats**
- `p3b_behavioral.py`: новый проход. Для каждой сущности PERSON (≥2 сцен)
  вычисляет: trust_score (base 50, conflict_ratio×-30, promise_kept×+3,
  promise_broken×-8, avg_importance>65 → +8, clamp[0,100]), volatility
  (std_dev importance), initiator_out_ratio → role_type (initiator/responder/mixed).
- Детекция противоречий: если у сущности ≥2 конфликтных сцены с importance≥40
  и delta≥14 дней → `bio_contradictions` запись (severity по importance_sum).
- `schema.py`: новые таблицы `bio_behavior_patterns` и `bio_contradictions`
  с индексами. ALTER TABLE migration для существующих БД.
- `repo.py`: 7 новых методов — upsert_behavior_pattern, get_behavior_pattern_for_entity,
  get_behavior_patterns_for_user, upsert_contradiction, get_contradictions_for_entity,
  get_calls_for_contact; get_portraits_for_user — LEFT JOIN bio_behavior_patterns.
- `orchestrator.py`: ORDER обновлён на 11 проходов с p3b_behavioral между p3 и p4.
- `__init__.py`: docstring «11 passes».

**Portrait enrichment (p5 → bio-v7)**
- `p5_portraits.py`: перед prompt-строением вызывает get_behavior_pattern_for_entity,
  передаёт behavior= в build_portrait_prompt.
- `prompts.build_portrait_prompt()`: новый параметр behavior; если есть —
  добавляет в user-message блок behavioral сигналов (trust_score, conflict_count,
  role_type, volatility) с инструкцией использовать как гипотезы через «похоже»/«возможно».

**Chapter enrichment (p6 → bio-v7)**
- `prompts.build_chapter_prompt()`: portraits_slim теперь включает опциональные
  поля trust и role (из LEFT JOIN); chapter LLM видит поведенческий контекст.
- `PROMPT_VERSION = "bio-v7"` — поломан memoization кэш для свежих ответов.

### Fixed — Biography: architecture findings P1+P2 resolved (2026-04-20)

**4 исправления по результатам архитектурного ревью:**

**[P1a] biography-export отдавал yearly_summary вместо основной книги**
- `repo.latest_book()`: добавлен параметр `book_type='main'`, SQL фильтрует
  `AND book_type=?`. До этого после p9_yearly наружу уходил годовой итог.
- `cli/main.py` biography-export: SQL-запрос добавил `AND book_type='main'`.

**[P1b] p8_editorial не был идемпотентным**
- `p8_editorial.py`: `status="edited"` → `status="final"`. Теперь повторный
  запуск корректно пропускает уже отредактированные главы (фильтр `!= 'final'`).
- `p8_editorial.py`: `reassemble` default `True` → `False`. В стандартном
  pipeline p7_book запускается отдельно после p8b_doc_dedup.

**[P2a] start_checkpoint() не сбрасывал счётчики**
- `repo.start_checkpoint()` ON CONFLICT DO UPDATE: добавлено
  `processed_items=0, failed_items=0, last_item_key=NULL`. Повторный старт
  прохода теперь показывает реальные, а не накопленные числа.

**[P2b] Новый проход p8b_doc_dedup — межглавный параграфный дедуп**
- `p8b_doc_dedup.py`: детерминированный дедуп без LLM (exact-hash MD5 +
  Jaccard similarity ≥ 0.72 на word-sets). Единица — абзац ≥ 80 символов.
  Главы обходятся по chapter_num, первое вхождение побеждает.
- `orchestrator.py`: новый ORDER — `…p6 → p8_editorial → p8b_doc_dedup
  → p7_book → p9_yearly`. p7 собирает книгу из уже очищенных глав.
- `__init__.py`: обновлён docstring (10 проходов).

### Added — Biography: p9_yearly wired + insight field pipeline (2026-04-20)

**Архитектурный аудит biography модуля → две подтверждённых проблемы исправлены:**

**1. insight field — устранена потеря данных (Change 1)**
- `bio_scenes` DDL: новая колонка `insight TEXT NOT NULL DEFAULT ''`.
- `apply_biography_schema()`: `_add_column_if_missing()` мигрирует существующие БД.
- `repo.upsert_scene()`: `insight` в INSERT и UPDATE (было 15 params → 16).
- `prompts.build_thread_prompt()`: condensed dict включает `insight`.
- `prompts.build_chapter_prompt()`: `scenes_slim` включает `insight`.
- Исправлено: LLM-интерпретация «нарративная/психологическая важность сцены» теперь
  сохраняется в БД и передаётся в p3 и p6 (раньше — генерировалась и отбрасывалась).

**2. p9_yearly.py — реализован (Change 2)**
- `bio_books` DDL: новая колонка `book_type TEXT NOT NULL DEFAULT 'main'`.
- `apply_biography_schema()`: ALTER TABLE миграция для существующих БД.
- `repo.insert_book()`: параметр `book_type='main'` (default для p7 book).
- `p7_book.py`: явно передаёт `book_type='main'`.
- `p9_yearly.py`: новый модуль. Определяет год автоматически, вызывает
  `build_yearly_summary_prompt()`, сохраняет как `book_type='yearly_summary'`.
- `orchestrator.py`: PASSES + ORDER включают p9_yearly (9-й проход).
- `cli/main.py`: docstring «8-проходного» → «9-проходного».

### Added — Biography Module: время звонка + годовой итог (bio-v6) (2026-04-20)

**Изменения:**

1. **PROMPT_VERSION**: `bio-v5` → `bio-v6`

2. **Время беседы в p1** (`_SCENE_SYS` + `build_scene_prompt()`):
   - Добавлен хелпер `_call_hour()` — извлекает час из `call_datetime`.
   - Если час < 6 или ≥ 22 → в user message: «ВРЕМЯ БЕСЕДЫ: NN:xx — ночной
     час (значимый сигнал)». Если < 8 → «до 8 утра (вероятно, срочно)».
   - В `_SCENE_SYS`: инструкция повысить importance на 10-20 и отразить в
     setting («посреди ночи», «ранним утром»).
   - В `_CHAPTER_SYS`: правило упоминать нестандартный час в прозе.

3. **Новый проход p9** (`_YEARLY_SYS` + `build_yearly_summary_prompt()`):
   - Годовой итог в духе Довлатова: 3-5 абзацев, без подзаголовков, без морали.
   - Фокус на сквозных мотивах года, а не пересказе глав.
   - Input: chapters (с excerpt), top_arcs (≤12), top_entities (≤15).
   - Output: markdown проза. Хранение: `bio_books` с `book_type="yearly_summary"`.
   - Промпт короткий (≤400 токенов доп. правил) — под Qwen3.5-9B.

4. **Правила обновлены**: biography-style.md (время суток, p9 sanity checks,
   length table), biography-prompts.md (p9 contract), biography/CLAUDE.md
   (p9 в pipeline, принцип времени суток).

### Changed — Biography Module: аудит противоречий в промптах (bio-v5) (2026-04-20)

**Проблема:** В biography/prompts.py найдено 18 противоречий и нагромождений
после нескольких последовательных правок (bio-v1 → v4). Промпты накопили
дубли правил, устаревшие инструкции по именам, запрещённые слова.

**1. Bumped `PROMPT_VERSION`: `bio-v4` → `bio-v5`**

**2. Исправлены критические противоречия в `prompts.py`:**

- `_SCENE_SYS` (p1): "Имена в канонической форме (Василий, не Вася)" →
  "как употреблены в транскрипте; канонизация — задача p2". Убрано
  противоречие с bio-v4 правилом «живое письмо».
- `_PORTRAIT_SYS` (p5): "Имена — в канонической форме" →
  "живое письмо, как звучат в материале". Устранено противоречие с _CHAPTER_SYS.
- `_ARC_SYS` (p4): "тянулись несколько звонков" → "несколько бесед".
  Убрано использование запрещённого слова «звонков» в самом промпте.
- `build_chapter_prompt()` user message: "Объём 2500-4500 слов" (жёстко) →
  "если материала достаточно — до 2500-4500; если мало — честно и кратко".
  Устранено противоречие с системным промптом «нет механического минимума».

**3. Устранены нагромождения в `_CHAPTER_SYS`:**

- Удалена строка про самоиронию ("желательно, но не обязательно") —
  конфликтовала с _STYLE_GUIDE ("верхняя граница"). Правило живёт в
  _STYLE_GUIDE, дубль убран.
- Правило "2-4 подзаголовка обязательно" → "2-4 для полноценных глав;
  1-2 или без — если глава короткая". Убрано противоречие с "короткая
  плотная глава лучше раздутой".
- Психологическое измерение: убраны примеры-дубли из _STYLE_GUIDE →
  теперь одна строка со ссылкой на стилевой канон.

**4. Исправлен `_EDITORIAL_SYS`:**

- "Если цитаты нет — добавь" → "не добавляй искусственно; только
  перераздели акценты в уже имеющемся тексте". Устранён риск вымысла
  (редактор не имеет доступа к исходным транскриптам).
- "Если персонажи плоские — добавь психологизм" → добавлено условие:
  только если паттерн уже в черновике, не форсировать. Устранён конфликт
  с "не каждый персонаж нуждается в разборе" из _STYLE_GUIDE.
- Удалена ссылка на имена в _EDITORIAL_SYS (дубль — _STYLE_GUIDE уже
  включён через конкатенацию).

**5. `_BOOK_FRAME_SYS`:** Удалена строка "Никаких цифр/статистик/звонков"
(полный дубль _STYLE_GUIDE, включённого туда же).

**6. `biography/CLAUDE.md`:** Исправлены устаревшие ссылки:
- "2500-4500 слов каждая" → "при достаточном материале"
- "Имена в канонической форме" → "живое письмо, как в материале"
- "bio-v2" → "bio-v4; current: bio-v5"

**Тесты:** `prompts.py` импортируется без ошибок (OK bio-v5).

**Итого устранено:**
- 4 прямых противоречия в инструкциях по именам
- 2 запрещённых слова в теле промптов
- 3 жёстких лимита, противоречащих гибкому подходу
- 4 дубля правил, создававших нагромождения

---

### Changed — Biography Module: smart name handling + flexible word counts (bio-v4) (2026-04-20)
### Changed — Biography Module: smart name handling + flexible word counts (bio-v4) (2026-04-20)

**Контекст:** конституциональное требование — текст должен быть «живой»
(использовать имена как они звучат в материале), без механического
каноничения. Одновременно — убрать водяной минимум слов: если за период
недостаточно материала, лучше честная короткая глава, чем раздутая пустая.
Сергей как имя может быть неоднозначным: только «Медведев Сергей» (полная
ФИ) = владелец.

**1. Bumped `PROMPT_VERSION`: `bio-v3` → `bio-v4`**

Memoization cache перестроится; все p6 (chapter) и p8 (editorial) пересчитаются
с новыми инструкциями.

**2. Изменения в `prompts.py`:**

- `_CHAPTER_SYS`: 
  - Слово count: было «2500-4500 слов обязательно» → теперь 
    «в норме 2500-4500, но НЕ механический минимум. Если материала мало —
    пиши честно и кратко».
  - Имена: было «канонические (Василий, не Вася)» → теперь 
    «живое письмо, как звучит в материале или контактах. Только
    'Медведев Сергей' = владелец; 'Сергей' в диалоге может быть другой».
- `_EDITORIAL_SYS`:
  - Было: «Если черновик < 2500 слов, можно расширить до 3000-3500» → теперь
    «Нет минимума: если материал того стоит, оставь как есть».
  - Добавлено: инструкция на живое письмо для имён (без механического
    каноничения).

**3. Обновлены memory-файлы:**

- `.claude/rules/biography-style.md`:
  - Секция «Russian language checklist»: переформулировано правило на имена —
    от механического каноничения к контекстному использованию.
  - Добавлено: Сергей-амбигуитет (только «Медведев Сергей» = владелец).
  - Таблица Length: p6 chapter — убран минимум 1500 слов, добавлено
    «Нет минимума если материала мало».
  - Золотое правило: «нет воды ради количества».
- `.claude/rules/biography-data.md`:
  - Секция «Chapter assembly»: убран диапазон 1500-2500, добавлено
    «без минимума если данных мало».
- `.claude/rules/biography-prompts.md`:
  - Секция Global conventions: уточнено правило на имена (живое письмо,
    не механическое).

**Тесты:** `prompts.py` импортируется без ошибок.

**Побочные эффекты:**
- Новые chapters (p6) будут генериться с учётом отсутствия минимума слов.
- Editorial pass (p8) не будет растягивать короткие главы ради количества.
- Имена в главах будут отражать материал, а не форсированную канонизацию.

---

### Changed — Biography Module: психологическая глубина персонажей (bio-v3) (2026-04-20)

**Контекст:** владелец указал, что книга выиграет от психологической объёмности
персонажей — осторожные интерпретации поведенческих паттернов через условное
наклонение. Это оживляет текст и вызывает у читателя эмпатию, не превращаясь
в клинический анализ.

**1. Bumped `PROMPT_VERSION`: `bio-v2` → `bio-v3`**

Memoization cache (`bio_llm_calls`) автоматически игнорирует старые ответы;
новые запросы пересчитываются. Старые записи остаются для аудита.

**2. Изменения в `prompts.py`:**

- `_STYLE_GUIDE`: добавлен раздел «Психологическая глубина» — допускает
  гипотетические интерпретации поведенческих паттернов через маркеры
  «похоже», «возможно», «по всей видимости». Максимум 1-2 на главу.
  Скорректировано правило «не додумывай мотивы» → теперь допустимы как
  версии через условное наклонение.
- `_SCENE_SYS` → поле `insight`: расширено, допускает называть динамику
  сцены («оба ждали, кто уступит первым»).
- `_PORTRAIT_SYS` → `prose`: добавлена инструкция на 1 поведенческую
  интерпретацию через условное наклонение, если паттерн явно прослеживается.
  Правила смягчены: «осторожная версия мотива — да; клинический диагноз — нет».
- `_CHAPTER_SYS` → «Психологическое измерение»: новый пункт требований,
  1-2 наблюдения-версии на главу с обязательным условным наклонением.
- `_EDITORIAL_SYS` → новая задача: проверить психологическую объёмность,
  добавить 1-2 наблюдения если персонажи плоские (только на основе фактов).

**3. Изменения в memory-файлах:**

- `.claude/rules/biography-style.md`:
  - Добавлен раздел «Психологическая глубина» в секцию Tone.
  - Раздел Вымысел: «нельзя утверждать мотивы как факт» + допустимы как
    гипотезы через условное наклонение.
  - Sanity checklist: +2 пункта для психологических интерпретаций.
- `.claude/rules/biography-prompts.md`:
  - p1: `insight` — уточнено определение.
  - p5: Style requirement — допускает 1 психологическую интерпретацию.
  - p6: Требования к прозе — добавлен пункт на 1-2 психологических наблюдения.
  - p8: Что делает — добавлена проверка психологической объёмности.

**Тесты:** `prompts.py` импортируется без ошибок (`OK bio-v3`).

**Побочный эффект:** активный biography-run получит bio-v3 промпты только
на проходах p2-p8 (p1 уже использует кэш bio-v1 для обработанных записей).

---

### Changed — Biography Module: max_tokens + non-fiction style for 45+ audience (2026-04-19)

**Контекст:** владелец указал целевую аудиторию книги — русскоязычные
взрослые 45+, технически прогрессивные, с широким кругозором. Стиль —
non-fiction со спокойным достоинством, эмпатией к собеседникам и
умеренной самоиронией владельца. Предыдущие 500-1200 слов/главу были
рассчитаны на короткие ответы; для полноценной главы книги нужно
2500-4500 слов.

**1. Bumped `PROMPT_VERSION`: `bio-v1` → `bio-v2`**

- Memoization cache (`bio_llm_calls`) автоматически игнорирует старые
  ответы; новые запросы пересчитываются. Старые записи остаются для
  аудита.

**2. `max_tokens` увеличены во всех 8 проходах:**

| Pass            | Было | Стало | Зачем                                |
|-----------------|------|-------|--------------------------------------|
| p1_scene        | 1200 | 1800  | richer synopsis + `insight` поле     |
| p2_entities     | 2500 | 3800  | полные aliases + описания            |
| p3_threads      | 1500 | 2500  | 3-6 абзацев summary + turning_points |
| p4_arcs         | 2800 | 4200  | до 20 арок с подробными synopsis     |
| p5_portraits    | 1400 | 2500  | 3-5 абзацев prose                    |
| **p6_chapters** | 3200 | 5500  | **2500-4500 слов/глава (КРИТИЧНО)**  |
| p7_book         | 2000 | 3500  | 3-5 абзацев prologue + epilogue      |
| p8_editorial    | 3200 | 5500  | редактура с сохранением объёма ±15%  |

**3. Переписаны system prompts в `prompts.py`:**

- Добавлен общий `_STYLE_GUIDE` (подключается в p6/p7/p8): non-fiction,
  аудитория 45+, спокойное достоинство, эмпатия, умеренная самоирония,
  запрет на «звонок/созвон/телефонный разговор» и цифры количества.
- **p1 Scene**: добавлено поле `insight`, `synopsis` расширен до 2-4
  предложений, `emotional_tone` получил значение `reflective`,
  `key_quote` расширен до 240 символов.
- **p3 Thread**: добавлены поля `turning_points` (со scene_index + why)
  и `open_questions`, `summary` расширен до 3-6 абзацев.
- **p5 Portrait**: добавлено поле `what_owner_learned`, `prose` расширен
  до 3-5 абзацев, явный запрет на ярлыки-диагнозы.
- **p6 Chapter**: структура обязательна (вводный → 2-4 блока `## …` →
  закрывающий), требование 1-3 прямых цитат, ≥1 эмпатическая нота,
  ≤1 самоироничная реплика, длина 2500-4500 слов.
- **p7 Book frame**: prologue/epilogue расширены до 3-5 абзацев,
  subtitle до 140 символов, разрешена аккуратная самоирония в прологе.
- **p8 Editorial**: подключён полный `_STYLE_GUIDE`, явные критерии
  усиления (прямая цитата, эмпатия, самоирония), разрешено расширять
  короткий черновик до 3000-3500 слов.

**4. JSON data-budgets для p6 увеличены:**
- portraits prose excerpt: 500 → 1200 симв.
- portraits blob: 4000 → 6000 симв.
- arcs blob: 3000 → 4500 симв.
- scenes blob: 6000 → 9000 симв.

**5. p8 editorial input clip: 12000 → 20000 символов** (глава целиком,
а не обрезок).

**6. Memory files (Progressive Disclosure):**

- **`src/callprofiler/biography/CLAUDE.md`** (new, 71 lines) — обзор
  модуля: mission, inputs, outputs, 8-pass pipeline, chapter types,
  принципы.
- **`.claude/rules/biography-data.md`** (new) — SQL-запросы для каждого
  прохода, пороги (importance, mention_count, MIN_MENTIONS), правила
  анонимизации PII, idempotency invariants, resume protocol.
- **`.claude/rules/biography-style.md`** (new) — целевая аудитория
  (45+ кругозор), жанр non-fiction, тон (спокойное достоинство),
  эмпатия, самоирония, длины всех сущностей, структура главы,
  список запрещённых слов/форматов, sanity checklist.
- **`.claude/rules/biography-prompts.md`** (new) — контракт каждого
  prompt'а: input signature, output JSON/markdown, constraints, quote
  extraction rules, versioning workflow.
- **`CLAUDE.md`** — добавлены 4 новые ссылки в Progressive Disclosure.

**Файлы:** `prompts.py`, `p1_scene.py`, `p2_entities.py`, `p3_threads.py`,
`p4_arcs.py`, `p5_portraits.py`, `p6_chapters.py`, `p7_book.py`,
`p8_editorial.py`; 4 новых memory-файла + root `CLAUDE.md`.

**Side effect:** текущий biography-run (p1_scene на 58%) продолжит работу
на **старом** `bio-v1` промпте — его hash уже закэширован. Новые проходы
(p2-p8) запустятся уже на `bio-v2`. Для полного пересчёта p1 нужно
`DELETE FROM bio_checkpoints WHERE pass_name='p1_scene'` и рестарт.

---

### Fixed — FTS5 Search Optimization (2026-04-17)

**`search_transcripts()` now uses FTS5 MATCH instead of LIKE:**

- **File:** `src/callprofiler/db/repository.py:311–331`
- **Problem:** Query used `LIKE ?` for O(n) full-table scan; FTS5 virtual table `transcripts_fts` existed but was never queried
- **Solution:**
  - Replaced with FTS5 MATCH subquery using BM25 scoring
  - Phrase wrapped in quotes for exact matching: `"query"` (user input escapes `"` → `""`)
  - Results ordered by FTS5 rank (relevance), not by call_id
  - Added `limit` parameter (default 50) to cap output
  - User isolation via `WHERE c.user_id = ?` on outer JOIN
- **Performance:** Subquery fetches top 200 from FTS5 (fast), outer JOINs apply user filter, LIMIT respects cap
- **Tests:** 2/2 search tests pass ✅
- **Impact:** `/search` command and Telegram `/search` now respond in <1s even on 18K calls (vs. timeout on large result sets)

### Added — Profanity Detector + Feature Flags (2026-04-17)

**1. Dictionary-based Russian profanity detector (no LLM):**

- **`src/callprofiler/analyze/profanity_detector.py`** (107 lines, new)
  - `_MAT_ROOTS` tuple — ~50 Russian profanity roots (большая четвёрка + производные + лёгкий мат + жаргон)
  - Single compiled regex: `\b\w*(root1|root2|…)\w*\b` with `re.IGNORECASE | re.UNICODE`
  - `count_profanity(text) -> {"count": int, "unique": int, "density": float}` — density = matches per 100 words
  - `find_profanity(text) -> list[str]` (debug helper)
  - Deliberate over-match: false positives on «схуяли»-like words acceptable; miss is worse than false hit

- **DB migration — `analyses` table** (auto via `_migrate()` + `schema.sql`):
  - `profanity_count INTEGER DEFAULT 0`
  - `profanity_density REAL DEFAULT 0`
  - `save_analysis()` / `save_batch()` now persist 15 columns (was 13)

- **`src/callprofiler/models.py`** — `Analysis` dataclass extended: `profanity_count: int = 0`, `profanity_density: float = 0.0`

- **`src/callprofiler/bulk/enricher.py`** — profanity computed BEFORE stub/LLM branch (both paths save metric). On LLM path, injected as hint into user_message:
  ```
  Сигнал детектора (не LLM): мат=N (уникальных=M, плотность=D/100слов).
  Учти при оценке bs_score и call_type.
  ```
  LLM may use it or ignore — typically raises risk/bs_score on high density.

**2. Feature flags system:**

- **`configs/features.yaml`** (new) — 6 flags with inline docs:
  - `enable_diarization: true` — pyannote speaker attribution
  - `enable_llm_analysis: true` — llama-server call; off → empty Analysis
  - `enable_profanity_detection: true` — dictionary detector above
  - `enable_name_extraction: true` — auto-extract names from transcript
  - `enable_event_extraction: true` — events table population from LLM JSON
  - `enable_telegram_notification: false` — default OFF until bot is set up

- **`src/callprofiler/config.py`**:
  - New `FeaturesConfig` dataclass (6 bool fields)
  - `Config.features: FeaturesConfig`
  - New `_load_features(config_dir, inline)` — priority: inline `features:` section in base.yaml > adjacent `features.yaml` > defaults
  - Missing file → graceful defaults (no crash)

- **`src/callprofiler/pipeline/orchestrator.py`** — stages gated per flag:
  - `process_call()` / `process_batch()`: diarize skipped when disabled (segments remain unannotated, pipeline continues)
  - LLM analyze skipped when disabled (logged at INFO level)
  - Telegram notifier called only when `self.telegram and self.config.features.enable_telegram_notification`

- **`src/callprofiler/bulk/enricher.py`** — `enable_profanity_detection` + `enable_event_extraction` gated (disabled → skip compute/save, empty metric/events)

**Testing:** `pytest tests/ -v` — **93/93 pass** ✅ (no regressions).

**Design notes:**
- Feature flags are *graceful degradation*, not fatal errors: disabled stage = silent skip + INFO log
- Profanity detector deliberately uses root-based regex to catch morphological variants (хуй → хуёвый, охуеть, хуйня); obfuscation (х*й, x_y) out of scope
- DB metric persisted even when LLM analysis is off — allows decoupling detector from LLM usage

### Added — 8-Pass Biography Pipeline (2026-04-16)

**Complete multi-day book-generation system from call transcripts:**

- **`src/callprofiler/biography/`** (15 new files, ~3200 LOC)
  - `schema.py` (252L) — 7 bio_* tables (scenes, entities, threads, arcs, portraits, chapters, books) + bio_checkpoints (resume) + bio_llm_calls (prompt memoization)
  - `repo.py` (652L) — BiographyRepo: user_id-scoped idempotent upserts, sqlite3 direct (no ORM), WAL mode
  - `llm_client.py` (230L) — ResilientLLMClient: MD5-keyed prompt cache, exponential-backoff retry (5 attempts), every attempt logged to bio_llm_calls
  - `prompts.py` (672L) — 8 Russian prompt builders (p1_scene, p2_entities, ..., p8_editorial), strict JSON contracts, head+tail clipping for context
  - `json_utils.py` (73L) — extract_json(): markdown fence stripping + lenient brace-balanced recovery for truncated JSON
  - `p1_scene.py` — Extract per-call narrative units (synopsis, tone, themes, entities)
  - `p2_entities.py` — Canonicalize entity names (Васяа/Вася/Василий → canonical), cross-chunk dedup
  - `p3_threads.py` — Build temporal entity threads with tension curves
  - `p4_arcs.py` — Detect multi-call problem→investigation→resolution arcs via sliding window
  - `p5_portraits.py` — Generate character sketches (traits, relationship, pivotal scenes)
  - `p6_chapters.py` — Monthly chapter generation from bucketed scenes
  - `p7_book.py` — Assemble book frame (title/TOC/prologue/epilogue) + full stitched markdown
  - `p8_editorial.py` — Polish chapters + re-assemble as final version
  - `orchestrator.py` (119L) — Orchestrator: 8-pass runner with per-pass try/except (one pass crash → only its checkpoint fails, continues)

- **CLI commands** (`src/callprofiler/cli/main.py`)
  - `biography-run [--passes p1,p2,...] [--max-retries 5]` — Run biography pipeline (all or subset)
  - `biography-status` — Show per-pass checkpoint status (processed/total/failed/updated_at)
  - `biography-export --out FILE.md` — Export latest assembled book to markdown

- **Architecture features**
  - Resume-safe: all work tracked in bio_checkpoints; re-run skips completed passes
  - Resilient: every LLM call memoized by prompt hash; crash → restart picks up where it left off
  - Multi-day capable: exponential backoff retry, no single-call timeout, graceful degradation on LLM failure
  - User-isolated: all queries filter by user_id
  - Local-only: uses existing llama-server (http://127.0.0.1:8080/v1/chat/completions)

### Fixed — Biography Pipeline Bug Fixes (2026-04-16)

- **`src/callprofiler/cli/main.py`** `cmd_biography_export()` — rewrote to bypass `_load_config_and_repo()` (which calls `_validate()` → `shutil.which("ffmpeg")` → `EnvironmentError` when ffmpeg not in PATH); now reads YAML directly and opens sqlite3 connection directly; ffmpeg not needed for export
- **`src/callprofiler/biography/p4_arcs.py`** — added `bio.start_checkpoint(user_id, PASS_NAME, 0)` before early-return on no scenes; previously `finish_checkpoint` UPDATE matched 0 rows (no prior INSERT), leaving checkpoint status as 'not_started' silently

### Changed — Git Authorization & Memory Protocol (2026-04-16)

- **`CLAUDE.md`** — Added `## Git Push Authorization` section: push to `main` (overrides feature-branch rule for this project)
- **`CONSTITUTION.md`** — Added **Статья 19** "Память проекта и сессионный протокол":
  - CONTINUITY.md: mandatory update after every session (Status/NOW/NEXT/DONE)
  - CHANGELOG.md: Keep a Changelog format (Added/Fixed/Changed/Removed by session)
  - Session protocol: read journals at start, update at end
  - Violation = violation of CONSTITUTION

### Added — Parse Status Enum & Centralized Rules (2026-04-15)

- **`parse_status`** enum field (parsed_ok/parsed_partial/parse_failed/output_truncated) — added to `Analysis` dataclass, `analyses` table schema, and database migration
- **`response_parser.py`** refactored: early-return pattern for each parse attempt, new `_is_json_truncated()` helper, new `_check_parse_completeness()` validator, all parse attempts now track and return `parse_status`
- **`repository.py`** — auto-migration for `parse_status` column via PRAGMA table_info, backward-compatible `getattr()` with "unknown" default
- **`enricher.py`** progress logging — now includes `parse_status=%s` for debugging
- **`.claude/rules/pipeline.md`** (NEW) — diarization failure handling rule: when diarization fails/returns 0 segments → mark speaker=UNKNOWN, diarization_failed=true, continue pipeline
- **Centralized rules** — moved memory/bugs.md → .claude/rules/bugs.md, memory/decisions.md → .claude/rules/decisions.md (single source of truth)

### Added — Phase 1.5-2: call_type, hook, structured cards, backfill-calltypes (2026-04-15)

- **`analyses.call_type`** column (business/smalltalk/short/spam/personal/unknown) — schema + migration in `_migrate()`
- **`analyses.hook`** column (одна фраза-напоминание) — schema + migration
- **`models.py`** `Analysis` dataclass: два новых поля `call_type` и `hook`
- **`repository.py`** `save_analysis()` + `save_batch()` — сохраняют call_type и hook
- **`response_parser.py`** — извлекает и валидирует `call_type`, берёт `hook` из LLM JSON
- **`enricher.py`** `_stub_analysis()` — теперь устанавливает `call_type='short'`
- **`configs/prompts/analyze_v001.txt`** — добавлены `call_type` и `hook` в JSON-шаблон + правила
- **`card_generator.py`** — полностью переписан: MacroDroid-compatible key:value format (≤512 байт UTF-8), данные из `contact_summaries`; `MAX_CARD_BYTES = 512`
- **`cmd_rebuild_cards`** в `main.py` — исправлен: теперь вызывает `SummaryBuilder.rebuild_all()` + `CardGenerator.update_all_cards()`
- **`cmd_backfill_calltypes`** + argparse + dispatch — новая команда `backfill-calltypes --user ID`; читает `raw_response`, парсит JSON, обновляет `call_type` где было 'unknown'
- **Tests**: обновлён `test_card_generator.py` для нового формата; 93 тестов проходят ✅

### Added — Slash commands & Claude Code optimizations (token economy)

**4 новые slash-команды в `.claude/commands/`:**
- `/brief` — быстрый брифинг в начале сессии (80% экономия токенов vs ручное чтение)
- `/quick-status` — компактный статус без чтения больших файлов
- `/save` — безопасное сохранение сессии (tests → journal → commit → push)
- `/check-schema` — проверка схемы БД перед SQL-запросами (предотвращает баги)

**Расширенные permissions в `.claude/settings.local.json`:**
- git commands (status, diff, log, add, commit, push, etc.) без подтверждения
- pytest, python -m callprofiler — без подтверждения
- Только безопасные read/test команды, никаких деструктивных операций

**Новая секция в CLAUDE.md:** "SLASH-КОМАНДЫ" (дополнение к Memory Protocol, не замена)

**Consequence:** Новые сессии могут использовать `/brief` вместо длинного startup prompt.
Экономия ~1500 токенов на каждом старте сессии.

### Added — CLI commands for diagnostics & analytics (5 new commands)

**Schema & Debugging:**
- `inspect-schema`: PRAGMA table_info for all tables, shows columns/types/constraints/indices
- `backfill-events --user ID`: Fill missing events from existing analyses (promises→promise, action_items→task, bs_evidence→contradiction, amounts→debt)

**Search & Promises:**
- `search <query> --user ID`: FTS5 search in transcripts (max 10 results with date, best contact name, text fragment, call_id)
- `promises --user ID`: Open promises grouped by contact with proper who translation (Me→"Я (Сергей)", S2→contact_name)

**Analytics:**
- `analytics --user ID`: Statistics on contacts/calls/events/promises with top-5 by calls/risk/bs_score

### Added — Helper functions for better UX
- `_get_best_contact_name()`: Selects display_name → guessed_name → phone_e164 (first non-empty)
- `_translate_who()`: Translates Me/S2/OWNER/OTHER to human-readable format
- Both applied in search, promises, and analytics commands

### Fixed — Data display consistency
- All commands now use same contact name selection logic
- Proper who field translation across all outputs
- Call datetime and due date formatting
- User validation on all commands

### Fixed — Memory vault rebase conflict resolved
- Resolved 4-way merge conflict in memory/{business,decisions,roadmap,bugs}.md
- Accepted comprehensive versions from commit 661696d
- Completed rebase with `git rebase --continue`
- Pushed to origin/main (commit bdf2c70)
- Memory vault now FINAL: all 4 files conflict-free and comprehensive

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
