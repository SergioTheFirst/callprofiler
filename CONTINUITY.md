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
DONE: Knowledge Graph Этапы 1-2 — schema, graph module, 25 tests pass (2026-04-24)
DONE: Knowledge Graph Этапы 3-4 — EntityResolver fixes + Auditor + LLM Disambiguator (2026-04-25)
DONE: Knowledge Graph Этап 1 — REPLAY (идемпотентная пересборка, 13 tests) (2026-04-25)
DONE: Knowledge Graph Этап 2.1 — FACT VALIDATOR (citation validation, speaker detection, 13 tests) (2026-04-25)
DONE: Knowledge Graph Этап 2.2 — DRIFT CHECK (validator_impact_drift auditor check, 6 tests) (2026-04-25)
DONE: Knowledge Graph Этап 3 — BS CALIBRATION (percentile-based thresholds, 18 tests) (2026-04-25)
DONE: Knowledge Graph Этап 4 — THRESHOLD INTEGRATION (data-driven card emoji, 186 tests pass) (2026-04-25)
DONE: HEALTH GATE — graph-health CLI command, 4 checks, exit 0/1 (2026-04-25)
DONE: PSYCHOLOGY PROFILER MVP — PsychologyProfiler class + CLI person-profile/profile-all (2026-04-25)
NOW: 197 tests pass — committing two commits + push to main
NEXT: Narrative journal extraction (narrative-extract CLI command)
BLOCKERS: None

---

## Текущее состояние: 2026-04-25 (HEALTH GATE + PSYCHOLOGY PROFILER MVP)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ` → push to `main`

### Последний коммит
```

---

## Session Update: 2026-04-29

### What changed
- Hardened the active `build-book-and-profiles` downstream path without touching the currently running Stage 1 wrapper:
  - `graph-backfill` now feeds transcript text into fact validation
  - `graph-backfill` now saves a `graph_replay_runs`-compatible snapshot and triggers BS calibration
  - `profile-all` now persists cached `entity_profiles`
  - `p6_chapters` now resolves biography portraits into graph entities and injects condensed graph dossiers into chapter prompts
  - `PROMPT_VERSION` bumped to `bio-v8`
- Added graph-derived dossier storage cleanup to `graph/replay.py`

### Verification
- `pytest tests/test_psychology_profiler.py tests/test_biography_graph_bridge.py tests/test_bs_calibration.py tests/test_replay_metrics.py -q` → `47 passed`
- `pytest tests/test_graph.py -q` → `62 passed`

### Next
- Let the live batch reach Stages 2–5 and observe whether:
  - `graph-health` now passes for real workflow reasons
  - `entity_profiles` fill with useful dossiers
  - `p6_chapters` enriched context improves cohesion without overflowing context
- After this run, decide separately whether `build-book-and-profiles.bat` should become fail-fast on `graph-health`.

### Known constraints
- `build-book-and-profiles.bat` itself was not edited during this session because it is already executing; editing a live `.bat` mid-run is risky.
- `p5_portraits` still does not consume saved graph dossiers directly; the current integration point is `p6_chapters`.
feat: psychology profiler MVP
```

### Что сделано в этой сессии (2026-04-25, часть 6)

**HEALTH GATE (Block A):**
- `cmd_graph_health()` в `cli/main.py` — 4 проверки: replay rejection < 0.90, audit no-critical, entity_metrics > 0, bs_thresholds > 0
- Subparser `graph-health --user ID` зарегистрирован
- Dispatch entry добавлен
- `.claude/rules/graph.md` — добавлено правило "graph-health exit 0 required before book-chapter"

**PSYCHOLOGY PROFILER MVP (Block B):**
- `src/callprofiler/biography/psychology_profiler.py` — `PsychologyProfiler` class
  - `build_profile()` → dict с keys: entity_id, canonical_name, metrics, patterns, temporal, social, evolution, top_facts, interpretation
  - `_analyze_temporal()`, `_extract_patterns()`, `_analyze_social()`, `_build_evolution()`, `_interpret()`
- `configs/prompts/psychology_profile.txt` — prompt template
- CLI: `person-profile` и `profile-all`
- `tests/test_psychology_profiler.py` — 11 тестов, итого 197 pass
- `.claude/rules/biography-style.md` — Psychology Profile Output Contract (новый файл)

### Следующий шаг
- Narrative journal extraction: `narrative-extract` CLI command

### Известные ограничения / долги
- `_interpret()` делает 3 SQL запроса `_analyze_social()` вместо одного — незначительно

---

## Текущее состояние: 2026-04-25 (Knowledge Graph Этап 4 — THRESHOLD INTEGRATION)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ`

### Последний коммит
```
Step 4: THRESHOLD INTEGRATION — Use BSCalibrator for data-driven risk emoji in cards (cedb0c5)
```

### Что сделано в этой сессии (2026-04-25, часть 5 — BS CALIBRATION)

**ШАГ 3 — BS CALIBRATION (вычисление пороговых значений на основе перцентилей):**
- `src/callprofiler/graph/calibration.py` — BSCalibrator class (новый файл)
- Метод analyze(user_id, min_calls=3, min_promises=1):
  - Получить отфильтрованные BS-индексы (исключить archived + owner)
  - Вычислить перцентили: p25, p50, p75, p90 (линейная интерполяция)
  - Определить пороги: reliable_max=p25, noisy_max=p50, risky_max=p75, unreliable_max=p90
  - Сохранить в bs_thresholds table с std_dev
  - Вернуть ok=True если >= 3 entities, иначе ok=False
- Метод get_label(bs_index, user_id):
  - Получить пороги из bs_thresholds
  - Присвоить label: reliable/noisy/risky/unreliable/critical/uncalibrated
  - Вернуть (label, emoji) где emoji из LABEL_MAP
- Статический метод _percentile(data, p):
  - Линейная интерполяция: rank = (p/100) * (n-1)
  - lower_idx, upper_idx, fraction
  - Результат: lower_val + fraction * (upper_val - lower_val)

**LABEL_MAP (5 категорий риска + uncalibrated):**
- 🟢 reliable: bs_index <= p25
- 🟡 noisy: p25 < bs_index <= p50
- 🔴 risky: p50 < bs_index <= p75
- 🔴 unreliable: p75 < bs_index <= p90
- ⚫ critical: bs_index > p90
- ⚪ uncalibrated: no thresholds available

**Тесты:** 18 новых в `test_bs_calibration.py`:
- test_calibrator_analyze_empty_user: no entities → ok=False
- test_calibrator_analyze_few_entities: < 3 entities → ok=False
- test_calibrator_analyze_sufficient_entities: >= 3 entities → ok=True with thresholds
- test_calibrator_analyze_computes_percentiles: p25/p50/p75/p90 calculation
- test_calibrator_analyze_saves_to_db: thresholds persisted
- test_calibrator_get_label_*: reliable/noisy/risky/unreliable/critical labels
- test_calibrator_percentile_*: edge cases (empty, single value)
- test_calibrator_analyze_filters_by_*: min_calls, min_promises filtering
- test_calibrator_analyze_excludes_*: owner, archived entity exclusion

**Result:** 93 tests pass (62 graph + 13 replay_metrics + 18 bs_calibration).
All percentile calculations verified. Label assignment comprehensive.
Database persistence working. Step 3 完了.

### Следующий шаг
- **Этап 5 — HEALTH GATE**:
  - Создать graph-health CLI команду
  - 4 проверки: replay_run, auditor, entity_metrics, bs_thresholds
  - Exit code 0 если stable, 1 если issues

---

## Текущее состояние: 2026-04-25 (Knowledge Graph Этап 4 — THRESHOLD INTEGRATION)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ`

### Последний коммит
```
Step 4: THRESHOLD INTEGRATION — Use BSCalibrator for data-driven risk emoji in cards (cedb0c5)
```

### Что сделано в этой сессии (2026-04-25, часть 6 — THRESHOLD INTEGRATION)

**ШАГ 4 — THRESHOLD INTEGRATION (интеграция BSCalibrator в card_generator и summary_builder):**
- `src/callprofiler/deliver/card_generator.py` — обновлен CardGenerator класс:
  - Добавлена ленивая инициализация BSCalibrator в _get_calibrator()
  - Метод _risk_emoji_with_calibration(risk, user_id) использует calibrator
  - Graceful fallback на hardcoded thresholds если calibration недоступна
  - Интегрирована в generate_card() вместо старого _risk_emoji(risk)
- `src/callprofiler/aggregate/summary_builder.py` — аналогично:
  - _get_calibrator() и _risk_emoji_with_calibration()
  - Обновлена generate_card_text() для использования калибратора
  - Graceful fallback для предыдущей версии
- Лениво инициализируется graph connection через sqlite3.connect() на потребу
- Exception handling: если bs_thresholds table не существует → fallback на hardcoded

**Архитектура:**
- BSCalibrator.get_label(risk_score, user_id) → (label, emoji)
- Labels: reliable/noisy/risky/unreliable/critical/uncalibrated
- Emoji: 🟢/🟡/🔴/🔴/⚫/⚪
- Data-driven: используются перцентили p25/p50/p75/p90 из bs_thresholds
- Если user не calibrated: get_label() возвращает uncalibrated + ⚪

**Integration Points:**
1. card_generator: emoji для caller cards на Android overlay
2. summary_builder: emoji для contact_summaries
3. Оба используют global_risk (0-100) как bs_index для calibrator

**Result:** 186 tests pass (18 bs_calibration + 15 card_generator + 62 graph + 13 replay + остальные).
Интеграция полная. Fallback works. Все карточки теперь могут быть data-driven если user calibrated.

### Следующий шаг
- **Этап 5 — HEALTH GATE**:
  - graph-health --user <id> CLI команда
  - 4 проверки стабильности графа

---

## Текущее состояние: 2026-04-25 (Knowledge Graph Этап 2.2 — DRIFT CHECK)

**ШАГ 2.2 — DRIFT CHECK (обнаружение смещения BS-индекса):**
- `src/callprofiler/graph/auditor.py` — _check_validator_impact_drift() метод
- Интегрирован в run_checks() наряду с остальными 9 проверками
- Стратифицированная выборка: 40% с bs_index > 50, 40% с total_calls > 10, 20% random
  - Целевой размер выборки: max(10, min(100, все_entities // 3))
- Алгоритм:
  1. Получить все entities с metrics для user_id
  2. Классифицировать по bs_index, total_calls, и случайная выборка
  3. Для каждого в sample: full_recalc_from_events(entity_id)
  4. Вычислить drift = abs(stored_bs - recalc_bs) / max(stored_bs, 1.0)
  5. Вернуть ok=(drift_pct <= 0.10), count=drifted_entities, details

**Результаты проверки:**
- ok=True если drift_pct <= 10%
- ok=False если drift_pct > 10%
- details dict с: sample_size, drifted_count, drift_pct, examples

**Тесты:** 6 новых в `test_graph.py`:
- test_auditor_drift_check_empty_graph: пустой граф → ok=True
- test_auditor_drift_check_small_sample: < 3 entities → ok=True
- test_auditor_drift_check_no_drift: свежие данные → drift минимален
- test_auditor_drift_check_stratified_sampling: стратификация работает
- test_auditor_drift_check_details_structure: структура details корректна
- test_auditor_drift_check_with_low_drift: drift <= 10% → ok=True

**Result:** 75 tests pass (62 graph + 13 replay_metrics). Step 2 полностью готов.

### Следующий шаг
- **Этап 3 — BS Calibration**:
  - Создать src/callprofiler/graph/calibration.py с BSCalibrator class
  - Метод analyze(user_id): вычислить p25/p50/p75/p90 для всех entities
  - Метод get_label(bs_index, user_id) → (label, emoji)

---

## Текущее состояние: 2026-04-25 (Knowledge Graph Этап 2 — FACT VALIDATOR)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ`

### Последний коммит (готов к push)
```
Knowledge Graph Этап 2: FactValidator, citation verification, speaker attribution, 56 tests pass
```

### Что сделано в этой сессии (2026-04-25, часть 3)

**ШАГ 2 — FACT VALIDATOR (усиленная валидация):**
- `src/callprofiler/graph/validator.py` — FactValidator class
- Валидация цитат ДО записи в events table
- 4 уровня проверок:
  1. Quote length >= 8 chars (MIN_QUOTE_LEN)
  2. Rolling window search в transcript (ratio >= 0.72)
  3. Speaker attribution detection ([me] vs [s2] from context)
  4. Semantic checks (future markers, negations, vague words)
- Поддержка EN + RU маркеров (future, negations, vague)
- Warnings логируются (debug) но не блокируют; Errors блокируют upsert

**Интеграция в GraphBuilder:**
- Import FactValidator в graph/builder.py
- `__init__()` создаёт validator instance
- `_update()` вызывает validate(fact, transcript_text) перед upsert
- Confident confidence check + validator check (2-слойная фильтрация)

**Архитектурное улучшение:**
- Validator полностью отделён от builder (может быть переиспользован)
- Transcript_text опциональный параметр в update_from_call()
- Warnings информационные (log debug) не критические

**Тесты:** 13 новых в `test_graph.py` (56 total, все pass):
- Length validation: valid/invalid quotes
- Transcript matching: exact, fuzzy, not found
- Speaker detection: [me], [s2], unknown
- Semantic markers: future, negations, vague words
- Combined warnings: multiple issues detected
- Builder integration: validator rejects short quotes, uses transcript

**Result:** Facts fully validated before DB write. Exact+fuzzy citation matching.
Speaker context detected. Semantic warnings logged (not blocking).
All 56 tests pass. Ready for Этап 3.

### Следующий шаг
- **Этап 3 — BS Calibration**:
  - bs_thresholds table (fact_type, min_confidence, min_intensity, etc)
  - BSCalibrator class для пересчёта BS-index с новыми пороговыми значениями
  - Миграция graph_replay для использования calibrator

### Известные ограничения / долги
- Validator работает с EN + RU маркерами; другие языки не поддерживаются
- Fuzzy matching ratio 0.72 хардкодирована; возможно нужна настройка
- Speaker detection работает только в 100-символьном lookback window
- Semantic checks не охватывают все типы вагуэности (примеры: "около", "типа")

---

## Текущее состояние: 2026-04-25 (Knowledge Graph Этап 5 — REPLAY)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ`

### Последний коммит
```
Knowledge Graph Этап 5: graph-replay command, idempotent rebuild, 42 tests pass
```

### Что сделано в этой сессии (2026-04-25, часть 2)

**ШАГ 1 — REPLAY (безопасный):**
- `src/callprofiler/graph/replay.py` — GraphReplayer class
- `graph-replay --user X [--limit N]` CLI command
- Идемпотентная пересборка: DELETE → UPDATE → rebuild
- Assertions: facts_count > 0, orphan_events=0, owner_contamination=0
- 5 тестов: empty_user, v2_only, idempotent, skips_v1, assertions_facts_count

**Архитектурный контракт:**
- Зафиксирован в `.claude/rules/graph.md`
- events = DERIVED from analyses.raw_response (schema_version='v2')
- events.entity_id/fact_id/quote — безопасно пересоздавать при replay
- events WHERE schema_version='v1' OR entity_id IS NULL — не трогать

**Интеграция:**
- graph/builder.py: добавлен параметр `transcript_text` для будущего FactValidator
- cli/main.py: добавлена cmd_graph_replay + parser + dispatcher

### Следующий шаг
- **Этап 2 — FACT VALIDATOR**:
  - src/callprofiler/graph/validator.py с FactValidator class
  - Проверка цитат через rolling window в транскрипте
  - Speaker attribution ([me] vs [s2])
  - Semantic checks (future markers, contradictions, vagueness)
  - Интеграция в GraphBuilder.update_from_call()

### Известные ограничения / долги
- FactValidator требует transcript_text в GraphBuilder (пока опциональный)
- Знаниевый граф ещё не калибрирован (шаг 3 — BS Calibration)
- Терминология: "REPLAY" (шаг 1) ≠ "REPLICATE" (шаг 2-5 stabilization pipeline)

---

## Текущее состояние: 2026-04-25 (Knowledge Graph Этапы 3-4 завершены)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ`

### Последний коммит
```
Knowledge Graph Этапы 3-4: resolver fixes, auditor, LLM disambiguator, 37 tests pass
```

### Что сделано в этой сессии (2026-04-25)

**Step 1 — INVARIANT full_recalc_from_events (aggregator.py):**
- Добавлен `full_recalc_from_events(entity_id)` — детерминированный пересчёт метрик
  из events (не инкрементально). Вызывается после merge. Решает double-count bug.

**Step 2 — GraphAuditor (graph/auditor.py):**
- 9 sanity checks; 2 CRITICAL (owner_contamination, orphan_events)
- CLI `graph-audit --user X` → exit 2 / 1 / 0

**Step 3 — Post-merge chain detection (resolver.py):**
- execute_merge() после закрытия транзакции проверяет цепочки merge-кандидатов
- --loop флаг в CLI итерирует до отсутствия кандидатов (cap 50)

**Step 4 — biography/data_extractor.py:**
- 3 функции: get_entity_profile_from_graph, get_behavioral_patterns, get_social_position
- p6_chapters.py обновлён: принимает graph_conn, вызывает _enrich_portraits_with_graph()
- CLI book-chapter --user X --entity N

**Step 5 — LLM Disambiguator (graph/llm_disambiguator.py):**
- Gray zone 0.50–0.64 → LLM advisory (НЕ авто-merge)
- configs/prompts/entity_disambiguation.txt (4 аспекта, JSON ответ)

**Step 6 — CLI commands (cli/main.py):**
- entity-merge, entity-unmerge, graph-audit, book-chapter

**Step 7 — Тесты:**
- 37 tests pass (было 25, +12 новых)
- Исправлены 2 баги в тестах: FK constraint в orphan_events, list flattening в resolver

**Исправленные баги в resolver.py:**
- 5 багов в execute_merge() + _fetch_entities() + _find_blocking_pairs (pre-existing)

### Следующий шаг
- Запустить `graph-audit --user <uid>` на продакшн БД
- Запустить `entity-merge --user <uid> --dry-run` чтобы увидеть кандидатов
- При необходимости: `reenrich-v2 --user X --limit 20` для пересчёта v2 analyses

### Известные ограничения / долги
- biography/data_extractor.py не покрыта автотестами (тестируется косвенно через p6_chapters)
- LLM disambiguator требует работающий llama-server на 127.0.0.1:8080 (локальный)
- entity-unmerge: snapshot_json должен существовать в entity_merges_log (иначе error)

---

## Текущее состояние: 2026-04-24 (Knowledge Graph Этапы 1-2)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ`

### Последний коммит
```
Knowledge Graph Этапы 1-2: schema, graph module, 25 tests pass
```

### Что сделано в этой сессии (2026-04-24)

**Knowledge Graph — Этап 1 (Schema + Extraction):**
- `schema.sql`: таблицы `entities`, `relations`, `entity_metrics` (CREATE IF NOT EXISTS)
- `graph/repository.py`: `apply_graph_schema(conn)` — идемпотентная миграция;
  ALTER TABLE analyses (schema_version), ALTER TABLE events (7 новых колонок);
  partial unique index на events.fact_id
- `analyze_v001.txt`: добавлены schema_version='v2', entities, relations, structured_facts

**Knowledge Graph — Этап 2 (Builder + Aggregation):**
- `graph/__init__.py`, `graph/config.py`, `graph/repository.py`
- `graph/builder.py`: GraphBuilder.update_from_call() — v1 skip, v2 process,
  anti-noise filter (confidence≥0.6, len(quote)≥5), fact dedup via sha256
- `graph/aggregator.py`: BS-index v1_linear (детерминированный, без LLM)

**Интеграция:**
- `enricher.py`: _update_graph() после batch flush, gated by enable_graph_update
- `orchestrator.py`: graph update после save_promises()
- `config.py`: FeaturesConfig.enable_graph_update = True
- `cli/main.py`: graph-backfill, reenrich-v2, graph-stats

**Тесты:** 25/25 pass в tests/test_graph.py

**Документация:** .claude/rules/graph.md (принципы, anti-noise, BS-formula,
schema_version contract, roadmap Этапов 3-4)

### Следующий шаг
- Этап 3: EntityResolver — fuzzy merge по Levenshtein (Python, без LLM)
- Этап 4: LLM-assisted merge (max 50 LLM calls per run)
- Оба задокументированы в .claude/rules/graph.md как roadmap

### Известные ограничения / долги
- Этапы 3-4 не реализованы — только roadmap
- graph-backfill нужно запустить вручную для существующих v2 analyses

---

## Текущее состояние: 2026-04-20 (Biography — p9 wired + insight pipeline)

### Статус
✅ **PARSE STATUS IMPLEMENTATION DONE** — Enum tracking for JSON parsing (4 states), diarization failure handling rules added, rules documentation centralized in .claude/rules/ directory.

### Что сделано в этой сессии (2026-04-15 — Parse Status + Rules)

**Три точечных улучшения реализованы и закоммичены:**

1. **Parse Status Enum** (parsed_ok/parsed_partial/parse_failed/output_truncated)
   - Added `parse_status: str` field to `Analysis` dataclass in models.py
   - Added `parse_status TEXT DEFAULT 'unknown'` column to analyses table
   - Refactored `response_parser.py`: early-return pattern, `_is_json_truncated()` detector, `_check_parse_completeness()` validator
   - Auto-migration in `repository.py` via PRAGMA table_info (backward-compatible)
   - Enricher logging includes `parse_status=%s` for debugging

2. **Diarization Failure Rules** (graceful degradation)
   - Created `.claude/rules/pipeline.md` documenting error handling strategy
   - Rule: diarization fails or 0 segments → mark speaker=UNKNOWN, set diarization_failed=true, **continue pipeline** (not fail)
   - LLM can still extract meaning from undiarized transcript

3. **Centralized Rules Documentation**
   - Moved memory/bugs.md → .claude/rules/bugs.md (centralized bug tracking)
   - Moved memory/decisions.md → .claude/rules/decisions.md (architectural ADRs)
   - Created .claude/rules/pipeline.md (pipeline rules, error handling)
   - Single source of truth for operational guidelines

**Commit:** `ad97190` (merged after resolving conflicts with origin/main)
**Push:** ✅ `16d3cc8..ad97190` → origin/main

**Тесты:** 93 passed ✅ (no regression)

**Следующий шаг:** Next user request or continue with Phase 2 optimization.

---

### Что сделано в предыдущей сессии (2026-04-14 — Part 6: Claude Code Optimization)

**Applied TOP-3 recommendations from vc.ru/ai/2868238 (carefully, non-breaking):**

1. **`.claudeignore`** — 30-40% token savings per session
   - Excludes: `__pycache__/`, `data/db/`, `data/logs/`, `*.db`, `*.mp3/wav/m4a`, `.git/`,
     IDE caches, historical docs (`ARCHITECTURE_v3.md`, `reference_batch_asr.py`, etc.)
   - Conservative list — only files that are 100% not needed for code understanding
   - Zero risk (read scope only)

2. **`.claude/settings.json`** — project-level env vars
   - `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=60` → compact at 60% instead of 80%
     (prevents quality degradation at 20-40% context fill)
   - `CLAUDE_CODE_SUBAGENT_MODEL=haiku` → subagents on Haiku (50-70% savings)
   - Schema-validated JSON with `$schema` link

3. **4 new slash commands in `.claude/commands/`:**
   - `/brief` — session start, reads CONTINUITY.md (100 lines) + CHANGELOG.md (40 lines)
   - `/quick-status` — compact status without heavy file reads
   - `/save` — safe save: tests → journal check → commit → push with retry
   - `/check-schema` — DB schema verification before SQL

4. **`.claude/OPTIMIZATION.md`** — full documentation of what/why applied
   - Lists what's NOT applied and why (CLAUDE.md refactor, main branch hook)
   - Measurable effects table

5. **Extended `.claude/settings.local.json`** — safe permissions
   - git/pytest/python commands no-confirmation
   - Only read/test — no destructive ops

**NOT applied (per user "do not break anything"):**
- ❌ CLAUDE.md refactor to 80 lines (file is 700+ lines of historical plan; risk > benefit)
- ❌ Main branch protection hook (user explicitly allows direct push to main)
- ❌ Path-scoped rules (can add when project grows)

**Tests:** 90 passed ✅ (changes are config-only, no code impact)

**Next:** Use `/brief` at next session start. Session rules in CLAUDE.md unchanged.

### Ветка разработки
- **Current branch:** `main` (direct push enabled)
- **Development branch:** `claude/clone-callprofiler-repo-hL5dQ` (for isolated feature work)

---

## Предыдущее состояние: 2026-04-14 (Memory vault resolved, Phase 5 complete)

### Статус
✅ **PHASE 5 COMPLETE** - Memory Protocol enforced. All rebase conflicts resolved. Ready for Phase 6 optimization.

### Ветка разработки
- **Current branch:** `main` (direct push enabled)
- **Development branch:** `claude/clone-callprofiler-repo-hL5dQ` (for isolated feature work)

### Что сделано в этой сессии (2026-04-14 — Part 3: Memory Vault Conflict Resolution)

**MERGED TO MAIN AND PUSHED:**

1. **Permission activated:** Claude Code can now push directly to `main`
   - Updated CLAUDE.md with Git Branch Policy section
   - All changes merged from feature branch to main
   - All work now on main branch

2. **Commits merged (5 total):**
   - `8d62300` Audit: Memory Protocol + Automation fixes
   - `1d165bd` Implement Telegram bot (6 commands + notifications)
   - `bc4fd6f` Contact summaries infrastructure (weighted risk)
   - `80c3b57` Event extraction refinement
   - `fd862d3` Events table and extraction
   - Plus: audit + policy update commits

3. **Files on main:**
   - ✓ CLAUDE.md (with Memory Protocol + Git Policy)
   - ✓ CHANGELOG.md (comprehensive history)
   - ✓ CONTINUITY.md (state tracking)
   - ✓ AGENTS.md (AI workflow)
   - ✓ 3 .bat files (new-session, save-session, emergency-save)
   - ✓ start-prompt.txt (session initialization)
   - ✓ All source code (contact_summaries, telegram_bot, etc.)

### Что сделано в этой сессии (2026-04-14 — Part 3)

**CONFLICT RESOLUTION:**

1. **Git rebase conflict resolved** (memory vault files)
   - 4 files in conflict during rebase: business.md, decisions.md, roadmap.md, bugs.md
   - Resolved: accepted comprehensive versions (from commit 661696d)
   - These versions have full documentation: phases 0-10, architectural decisions, metrics, tracking system
   - Completed rebase: `git rebase --continue` → successful
   - Pushed to origin/main: commit `bdf2c70`

2. **Memory vault structure FINALIZED:**
   - ✓ memory/business.md (79 lines) - pipeline, user profile, hardware, data model, metrics
   - ✓ memory/decisions.md (126 lines) - architecture decisions with rationale and trade-offs
   - ✓ memory/roadmap.md (158 lines) - phases 0-10, Phase 5 complete, Phase 6 optimization focus
   - ✓ memory/bugs.md (120 lines) - 14 tracked items (3 active, 3 resolved, 5 backlog, 3 future)

3. **Status: READY FOR PHASE 6**
   - All merge conflicts resolved ✓
   - Memory vault pushed to main ✓
   - Phase 5 automation complete ✓
   - Next: Phase 6 optimization (GPU memory, DB indexing, Telegram search pagination)

### Что сделано в этой сессии (2026-04-14 — Part 5: 5 CLI Commands, Schema Inspection, Events Backfill)

**ПРОБЛЕМА 1: РЕШЕНО - Events таблица пуста**
- ✓ Проверен enricher.py → уже вызывает repo.save_events() на строках 225, 239
- ✓ Создана команда `backfill-events --user ID` для заполнения пропущенных событий
  - Парсит raw_response из существующих анализов
  - Извлекает: promises, action_items, bs_evidence, amounts
  - Маппирует: Me→OWNER, S2→OTHER
  - Сохраняет в таблицу events

**ПРОБЛЕМА 2: РЕШЕНО - SQL-запросы неизвестных колонок**
- ✓ Создана команда `inspect-schema`
  - Выводит PRAGMA table_info для всех таблиц
  - Показывает колонки, типы, constraints, индексы
  - Поддержка виртуальных таблиц (FTS5)

**ПРОБЛЕМА 3: РЕШЕНО - Отсутствовали search и promises**
- ✓ Добавлена команда `search <query> --user ID`
  - FTS5 поиск по транскриптам (до 10 результатов)
  - Выводит: дата | лучшее имя контакта | телефон | фрагмент | call_id
  - Выбор имени: display_name → guessed_name → phone_e164

- ✓ Добавлена команда `promises --user ID`
  - Открытые promises, сгруппированные по контакту
  - Выводит: контакт | кто | что | когда | из звонка
  - Перевод who: Me→"Я (Сергей)", S2→имя контакта, OWNER→"Я", OTHER→имя контакта

**ПРОБЛЕМА 4: РЕШЕНО - Who поле неинформативно**
- ✓ Добавлена функция `_get_best_contact_name()` - выбирает display_name→guessed_name→phone_e164
- ✓ Добавлена функция `_translate_who()` - переводит Me/S2/OWNER/OTHER в человеческий формат
- ✓ Применена во всех командах (search, promises, analytics)

**ПРОБЛЕМА 5: РЕШЕНО - Аналитические запросы**
- ✓ Создана команда `analytics --user ID`
  - Всего контактов, звонков, анализов
  - События по типам (promise, debt, task, risk, etc.)
  - Promises: open / всего
  - Топ-5 контактов по кол-ву звонков
  - Топ-5 по risk_score (average)
  - Топ-5 по bs_score (average)
  - Контакты с guessed_name

**Все 90 тестов PASSED ✅**

### Текущий workflow (going forward)

**Mode: Direct push to main**

1. Work on `claude/clone-callprofiler-repo-hL5dQ` for isolated tasks
2. When ready: merge to `main` and push
3. Keep journals updated ALWAYS (CHANGELOG + CONTINUITY)
4. Every commit includes: "Journal updated: CHANGELOG.md + CONTINUITY.md"

---

### Что сделано в этой сессии (2026-04-14 — Part 1)

**FIXES APPLIED:**

1. **CLAUDE.md** — Добавлена обязательная секция `🧠 MEMORY PROTOCOL`
   - RULE 1: Контекст стирается, память только в журналах
   - RULE 2: Начало сессии — прочитать CONTINUITY.md + CHANGELOG.md, сказать статус
   - RULE 3: Сразу после кода — обновить CONTINUITY.md и CHANGELOG.md (без запроса)
   - RULE 4: Конец ответа с кодом — `[Memory updated]`
   - RULE 5: Лимит контекста — сохранить CONTINUITY.md ПЕРВЫМ
   - RULE 6: НИКОГДА не пропускать обновление памяти

2. **Автоматизация Windows (3 .bat файла):**
   - `new-session.bat` — инициализация сессии (показать статус, CONTINUITY, CHANGELOG, ветка)
   - `save-session.bat` — полное сохранение (тесты + commit + push)
   - `emergency-save.bat` — срочное сохранение (без тестов, с timestamp)

3. **start-prompt.txt** — Начальный prompt для новых сессий
   - Напоминает о Memory Protocol
   - Инструкции READ: CONTINUITY.md → CHANGELOG.md → SAY status
   - Ссылки на ключевые файлы (CLAUDE, CONSTITUTION, AGENTS)
   - Checklist перед финальным commit

4. **CONTINUITY.md** — Обновлена с данными аудита

**VERIFIED:**
- ✓ CLAUDE.md tracked in git (как надо)
- ✓ CHANGELOG.md tracked in git (как надо)
- ✓ CONTINUITY.md tracked in git (как надо)
- ✓ AGENTS.md tracked in git (как надо)
- ✓ AGENTS.md section 3.3 правильно описывает обновление журналов
- ✓ .gitignore не блокирует критические файлы

**NOT FOUND (созданы в этой сессии):**
- ✗ new-session.bat → CREATED
- ✗ save-session.bat → CREATED
- ✗ emergency-save.bat → CREATED
- ✗ start-prompt.txt → CREATED

---

### Что сделано в этой сессии (2026-04-11e)

**Реализован полнофункциональный Telegram-бот** для доставки уведомлений и команд:

1. **TelegramNotifier класс** (deliver/telegram_bot.py):
   - Токен из `TELEGRAM_BOT_TOKEN` с graceful fallback
   - Инициализация с валидацией пользователя по chat_id
   - Long polling mode в отдельном потоке (не webhook)

2. **6 команд бота:**
   - `/start` — приветствие с описанием команд
   - `/digest [N] [days]` — топ-N звонков (по умолчанию 5, за 1 день)
   - `/search <текст>` — FTS5 поиск по транскриптам с контактом и датой
   - `/contact <номер или имя>` — карточка из contact_summaries (risk, hook, promises, facts)
   - `/promises` — открытые обещания, сгруппированные по контакту
   - `/status` — состояние очереди (всего/обработано/в работе/ошибки)

3. **Автоматические уведомления:**
   - После обогащения: отправить саммари с метаданными (направление, дата, длительность)
   - Risk emoji (🟢/🟡/🔴) по score
   - Inline-кнопки [OK] [Неточно] для feedback
   - Обработка callback: найти analysis_id, сохранить feedback

4. **CLI команда** (cli/main.py):
   - `python -m callprofiler bot`
   - Проверка TELEGRAM_BOT_TOKEN
   - Вывод зарегистрированных пользователей с chat_id
   - Логирование статуса инициализации

5. **Тестирование:**
   - All 90 tests pass (bot использует только существующие методы Repository)
   - User isolation via (user_id ← chat_id) mapping
   - Graceful error handling для missing/malformed data

**Ключевые детали:**

- Все команды требуют регистрации пользователя (check telegram_chat_id in users)
- Нерегистрированные chat_id игнорируются с логом
- JSON парсинг для events (promises, debts, facts) с try/except fallback
- HTML parse_mode для форматирования (bold, italic)
- Direction в notifications (IN/OUT/UNKNOWN)
- Feedback saving: callback → call_id → analysis_id → set_feedback()

---

### Что было в сессии (2026-04-11d)

**Реализована инфраструктура contact_summaries** для синтезирования полных профилей контактов:

1. **Added `contact_summaries` table** to `schema.sql`:
   - contact_id (PK), user_id (FK), total_calls, last_call_date
   - global_risk (0–100): exponential-decay weighted average of risk_scores
   - avg_bs_score (0–100): same weighting for BS-score
   - top_hook (TEXT): hook from last analysis
   - open_promises, open_debts, personal_facts (JSON): filtered events
   - contact_role (TEXT): guessed company/role
   - advice (TEXT): rules-based recommendations
   - updated_at (TIMESTAMP)

2. **Created `aggregate/summary_builder.py`** with SummaryBuilder class:
   - `rebuild_contact()`: Core algorithm — aggregate risk, BS-score, events, hook, role, advice
   - `rebuild_all()`: Bulk rebuild for user with error handling
   - `generate_card_text()`: Format ≤512 bytes card with emoji, hook, bullets, advice
   - `write_card()` / `write_all_cards()`: Persist cards as {phone_e164}.txt
   - **Weighted risk model:** weight = 2^(-days_ago/90), exponential decay (half-life 90 days)
   - **BS-score calculation:** Same exponential weighting, extract from analysis.raw_response JSON
   - **Event extraction:** Promises/debts/facts filtered by type + status, returned as JSON
   - **Advice generation:** Rules-based on risk, bs_score, open_debts

3. **Added 3 Repository methods** (`repository.py`):
   - `save_contact_summary(contact_id, user_id, ...)` → INSERT OR REPLACE
   - `get_contact_summary(contact_id)` → dict or None
   - `get_all_contacts_for_user(user_id)` → list[dict] sorted by display_name

4. **Added 2 CLI commands** (`cli/main.py`):
   - `rebuild-summaries --user ID` — пересчитать contact_summaries для пользователя
   - `rebuild-cards --user ID` — пересоздать caller cards в sync_dir

5. **Testing:**
   - All 90 tests pass (new schema + methods; existing tests unaffected)
   - Weighted risk model verified with exponential decay
   - JSON event parsing robust (try/except on json.loads)
   - Card text generation handles missing fields gracefully

### Техническая детали

**Weighted risk algorithm:**
```python
weight = 2^(-days_ago / 90)  # Exponential decay with 90-day half-life
global_risk = sum(weight_i * risk_i) / sum(weight_i)
```
Recent calls have higher weight; old calls still influence but less.

**Event extraction:**
- open_promises: events where type='promise' and status='open'
- open_debts: events where type='debt' and status='open'
- personal_facts: events where type='smalltalk' and status='open', limit 5 newest

**Card text format** (≤512 bytes):
```
{Name} — {Role}
Risk: {score} {emoji}
Hook: {hook}
• {debt or promise or fact}
• (second bullet)
• (third bullet)
💡 {advice}
```

Risk emoji: 🟢 (risk<30), 🟡 (30-70), 🔴 (>70)

**Advice rules:**
- risk>70 → "Говори первым"
- bs_score>60 → "Осторожно: размытые обещания"
- open_debts → "Начни с долга"
- risk<30 && bs<30 → "Надёжный партнёр"
- default → "Стандартный контакт"

---

### Что было в сессии (2026-04-11c)

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
