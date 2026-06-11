# Dashboard Person Dossier — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** «Нажал на имя — знаешь о человеке всё»: единая вкладка «Личности» в дашборде с полным фактологическим досье (risk, BS-index, trust, архетип, паттерны, факты-цитаты, обещания, связи, динамика) — без ручных шагов после прогона.

**Architecture:** Доктрина дашборда (юзер, 2026-06-11): ровно 2 функции — (1) ход обработки, (2) психологический портрет личностей. Паттерн прежний: CLI/пайплайн ПИШЕТ, дашборд = чистый read (query_only). Три id-пространства (contact / graph entity / архетип) сшиваются персистной перестраиваемой `entity_contact_map`; досье собирает `get_person_dossier()` из всех слоёв guarded (слой пуст → секция пустая, не 500). Главный реюз: `PsychologyProfiler` (готовые patterns/temporal/social/evolution/top_facts) подключается к дашборду с `include_llm=False`.

**Tech Stack:** FastAPI + SSE (есть), vanilla JS + ECharts (есть), sqlite3 (no ORM), numpy-only insight. Без новых зависимостей.

**Тиры исполнения:** Ф0=T2 (watcher), Ф1=T2 (SQL write-path + security-reviewer), Ф2=T2 (контракт ридера), Ф3=T1 (дашборд JS), Ф4=T2 (LLM/persist). Все тесты офлайн (synth + fixtures поверх schema.sql).

---

## Контекст для исполнителя (что уже есть — НЕ переделывать)

| Слой | Кто пишет | Когда заполняется |
|---|---|---|
| `analyses` (risk_score), `contact_summaries` (global_risk, avg_bs_score, promises/debts/facts), `promises` | watch-пайплайн | автоматически в прогоне |
| `entities/relations/events` (факты-цитаты), `entity_metrics` (bs_index, trust_score, volatility, conflict_count) | orchestrator.py:833 + enricher.py:504 (`enable_graph_update=True` по умолчанию, config.py:85) | автоматически в прогоне |
| `contact_features`, `contact_archetypes` (label, membership, distinctive_dims, pca_x/y) | CLI `features-build` + `archetypes-fit` | **только вручную** ← причина пустой вкладки |
| `entity_profiles` (psychology payload: temperament/motivation), `bio_behavior_patterns`, `bio_contradictions` | биография/психология-пассы (biography/repo.py:804,859; graph/repository.py:602) | только вручную |
| `PsychologyProfiler.build_profile()` | ничего не персистит, считает live (SQL+python, LLM только для interpretation) | по вызову |

Дашборд уже имеет: вкладки overview/calls/search/entities/insight/system; `/api/characters`, `/api/character/{entity_id}` (модалка, app.js:541), `/api/contact/{contact_id}`, 5×`/api/insight/*`. Дыры: `get_character_profile` → `temporal: None`, `network: None` (заглушки db_reader.py:319-320); архетипы не присоединены к персоне; contact↔entity связь = равенство имени (db_reader.py:354-364, 478-487); факты-цитаты (events) в досье не выводятся.

---

## Фаза 0 — авто-питание insight (убирает «Нет модели архетипов»)

### Task 0.1: Debounced auto-fit в watcher

**Files:**
- Modify: `src/callprofiler/config.py` (PipelineConfig или FeaturesConfig — по месту флагов)
- Modify: `configs/base.yaml` (секция pipeline) или `configs/features.yaml`
- Modify: `src/callprofiler/pipeline/watcher.py` (`run_loop`)
- Test: `tests/test_watcher_autofit.py`

Поля конфига (⚠ урок bugs.md 2026-06-06: поле объявить в датаклассе И прочитать в `load_config` И положить в yaml — все три места, иначе тихий дефолт):

```python
insight_autofit: bool = True
insight_autofit_min_new: int = 25      # минимум новых терминальных звонков
insight_autofit_min_interval_sec: int = 1800  # не чаще раза в 30 мин
```

- [ ] **Step 1: тест (RED).** В `tests/test_watcher_autofit.py` — watcher с mock `_run_insight_fit`: (a) после цикла, где терминализовалось ≥ min_new звонков и интервал прошёл → вызван 1 раз; (b) меньше порога → не вызван; (c) `insight_autofit=False` → не вызван; (d) исключение внутри fit → лог, цикл НЕ падает (паттерн pipeline.md Fallback).

```python
def test_autofit_triggers_after_threshold(watcher_factory):
    w = watcher_factory(autofit=True, min_new=2, min_interval=0)
    w._new_terminal_since_fit = 2
    with mock.patch.object(w, "_run_insight_fit") as m:
        w._maybe_autofit()
    assert m.call_count == 1

def test_autofit_swallows_errors(watcher_factory, caplog):
    w = watcher_factory(autofit=True, min_new=0, min_interval=0)
    with mock.patch.object(w, "_run_insight_fit", side_effect=RuntimeError("boom")):
        w._maybe_autofit()   # не должен поднять
    assert "autofit" in caplog.text.lower()
```

- [ ] **Step 2: прогнать тест — FAIL** (`pytest tests/test_watcher_autofit.py -q`, нет `_maybe_autofit`).
- [ ] **Step 3: реализация.** В `run_loop` после `process_pending()` инкрементить счётчик терминализованных за цикл; `_maybe_autofit()`: гейт флаг → порог → интервал → `_run_insight_fit()` = lazy import `insight.cli_ops` и последовательно `features-build` + `archetypes-fit` + (Ф1) `build_entity_contact_map` для каждого user из БД, в try/except non-fatal. Numpy-only — GPU не трогает, можно в любой фазе.
- [ ] **Step 4: тесты PASS** + `pytest tests/ -q` без регрессий.
- [ ] **Step 5: память (pipeline.md — пункт цикла №7 autofit) → commit `feat(insight): autofit в watcher — архетипы без ручных шагов` → push.**

---

## Фаза 1 — связка contact ↔ entity (фундамент досье)

### Task 1.1: Таблица `entity_contact_map` + builder

**Files:**
- Modify: `src/callprofiler/insight/repository.py` (`apply_insight_schema` + `_MIGRATIONS`)
- Create: `src/callprofiler/insight/person_link.py`
- Modify: `src/callprofiler/insight/cli_ops.py` (вызов в конце archetypes-fit)
- Modify: `src/callprofiler/graph/replay.py` (rebuild map после replay — map derived, как graph из events)
- Modify: `src/callprofiler/cli/main.py` + `cli/commands/insight.py` (команда `person-link --user X [--dry-run]`)
- Test: `tests/insight/test_person_link.py`

DDL (идемпотентно, в apply_insight_schema):

```sql
CREATE TABLE IF NOT EXISTS entity_contact_map (
    user_id    TEXT    NOT NULL,
    entity_id  INTEGER NOT NULL,
    contact_id INTEGER NOT NULL,
    method     TEXT    NOT NULL CHECK (method IN ('name','cooccur')),
    confidence REAL    NOT NULL,
    built_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, entity_id, contact_id)
);
```

Алгоритм `build_entity_contact_map(conn, user_id) -> dict` (DELETE по user_id + полный rebuild — derived-данные, как graph; идемпотентно):

1. **name-match** (confidence 0.95, любой entity_type): нормализация `lower → ё→е → collapse spaces`; матч canonical_name ИЛИ alias == display_name ИЛИ guessed_name контакта.
2. **cooccur** (только PERSON, confidence `0.6 + 0.3*share`): `n_ec` = COUNT(DISTINCT e.call_id) событий entity в звонках контакта; share = n_ec / n_e_total; линк если `share >= 0.6 AND n_ec >= 3`. Owner-entity исключить (entity_metrics owner / canonical = владелец из llm.md — «Сергей… Медведев» всегда owner).
3. НИКАКОГО слияния contacts/entities (Prohibited: auto-merge) — только мягкие ссылки, перестраиваемые.

- [ ] **Step 1: тест (RED).** Fixture: schema.sql + apply_graph_schema + apply_insight_schema во временной БД; вставить 2 контакта, 3 entity, events. Кейсы: name-match по алиасу; cooccur ≥0.6/≥3 линкует, 0.5 — нет; повторный build → row count тот же (идемпотентность); `WHERE user_id` изоляция (чужой user не линкуется); owner не линкуется.
- [ ] **Step 2: FAIL** → **Step 3: реализация** → **Step 4: PASS + полный suite.**
- [ ] **Step 5: security-reviewer (SQL write-path) → самопересчёт ключевой метрики теста (урок decisions.md 2026-06-06) → память (insight.md: схема map) → commit → push.**

---

## Фаза 2 — досье-агрегатор (read-only)

### Task 2.1: `PsychologyProfiler.build_profile(..., include_llm: bool = True)`

**Files:** Modify: `src/callprofiler/biography/psychology_profiler.py`; Test: дополнить его тесты.

- [ ] Тест: `include_llm=False` → LLM-клиент НЕ вызывается (mock assert_not_called), `interpretation is None`, структурные части полны. RED → минимальный дифф (обход LLM-ветки) → GREEN → commit.
  Зачем: на боксе llama-server может быть ЖИВ — без флага клик в дашборде повиснет до 120s timeout.

### Task 2.2: `get_person_dossier(contact_id, user_id)` + `/api/person/{contact_id}`

**Files:**
- Modify: `src/callprofiler/dashboard/db_reader.py` (новый метод; `temporal:None`/`network:None` дыры закрываются ЗДЕСЬ — старый `get_character_profile` не ломать, модалка живёт)
- Modify: `src/callprofiler/dashboard/server.py` (`@fa.get("/api/person/{contact_id}")` + `/api/people` — список)
- Test: `tests/test_dashboard_dossier.py`

Контракт JSON (все секции guarded — отсутствие слоя = null/[]):

```python
{
  "contact":   {contact_id, display_name, guessed_name, phone_e164, name_confirmed},
  "indices":   {global_risk, avg_bs_score,            # contact_summaries
                bs_index, trust_score, avg_risk, volatility, conflict_count},  # entity_metrics через map
  "archetype": {label, membership, confidence, distinctive_dims},  # contact_archetypes
  "entity":    {entity_id, canonical_name, aliases, link_method, link_confidence} | None,
  "patterns":  [...],          # PsychologyProfiler(include_llm=False) при наличии entity
  "temporal":  {...},          # оттуда же (calls_per_week, frequency_trend)
  "social":    {...},          # оттуда же + relations top-5 (имя, тип, weight)
  "facts":     [{quote, fact_type, polarity, call_date}],  # events conf>=0.6 ORDER BY intensity DESC LIMIT 5
  "contradictions": [...],     # bio_contradictions если есть
  "promises":  {open: [...]},  # promises по contact_id
  "evolution": [...],          # профайлер (год → avg_risk)
  "interpretation": str|None,  # ИЗ entity_profiles payload (persisted, Ф4) — live-LLM в дашборде ЗАПРЕЩЁН
  "recent_calls": [...]        # как в get_contact_profile
}
```

`/api/people`: список контактов = `get_contacts` + LEFT JOIN map→entity_metrics (bs_index) + contact_archetypes (label) + contact_summaries (global_risk) — колонки списка: имя, архетип, risk, BS, total_calls, last_call_date. Сортировка/поиск на фронте.

- [ ] **Step 1: тесты (RED).** Fixture как в Task 1.1 + contact_archetypes + entity_metrics строки: (a) полное досье — все секции заполнены и согласованы; (b) контакт без entity-линка → indices только contact-слой, patterns/facts пусты, НЕ 500; (c) до archetypes-fit → archetype=None; (d) чужой user_id → None; (e) `/api/people` отдаёт колонки и не падает на пустой БД.
- [ ] **Step 2: FAIL → Step 3: реализация → Step 4: PASS + suite → Step 5: code-reviewer → память → commit → push.**

---

## Фаза 3 — UI «Личности» (T1, дашборд JS)

### Task 3.1: вкладка + досье-панель

**Files:** Modify: `src/callprofiler/dashboard/templates/index.html`, `static/app.js`, `static/style.css`.

- [ ] Вкладку `entities` переименовать в **«Личности»**; контент: сверху поиск + таблица контактов из `/api/people` (клик строки → досье), ниже секция «Упомянутые персоны» = прежний список characters (entities без contact-линка; их модалка `/api/character/{id}` остаётся).
- [ ] Досье-панель (по `/api/person/{id}`), секции по контракту 2.2: шапка (имя/телефон/архетип-бейдж+membership) → индексы (risk, BS относительно `bs_thresholds` если откалиброваны: 🟢🟡🔴, trust) → черты-фразы (distinctive_dims) → паттерны (severity-цвет) → факты-цитаты с датами → обещания → связи (top-5 relations, клик → досье той персоны) → темпоральное (calls/week, тренд, мини-циркад per-contact — параметризовать `get_insight_circadian` по contact_id) → ЭКГ (reuse `/api/insight/ecg?contact_id=`) → интерпретация (3 абзаца или «недоступно — запусти profile-all»).
- [ ] Клик точки PCA-карты и узла эго-сети → открыть это же досье (закрывает «Ф7 интерактив» из insight.md). Данные клика: contact_id уже есть в insight-выдачах.
- [ ] Домен-правила вывода: фразы вместо сырых чисел где возможно; длительности/каунты звонков юзеру не показывать (CLAUDE.md Domain) — «звонков: N» в служебной таблице списка допустимо, в досье-прозе нет.
- [ ] Визуальная проверка — на боксе (dev-ПК без данных); смоук: эндпоинты на fixture-БД.
- [ ] Память (dashboard-карта) → commit → push.

---

## Фаза 4 — persisted LLM-интерпретация (бокс, LLM-окно)

### Task 4.1: `profile-all --persist`

**Files:** Modify: `src/callprofiler/cli/main.py` (+ команда), `src/callprofiler/graph/repository.py` (merge interpretation в entity_profiles payload, profile_type='psychology'); Test: `tests/test_profile_persist.py` (mock LLM).

- [ ] `profile-all --user X --persist`: для entities с map-линком → `build_profile(include_llm=True)` → interpretation в payload (merge, не затирая temperament/motivation). Гейт: только при доступном llama-server; НЕ во время ASR-фазы (запускается вручную/после прогона — GPU sequential Hard Constraint). Memoization llm_calls — по плану «port biography resilience» (decisions.md), здесь не дублировать.
- [ ] Идемпотентность: повторный run с тем же содержимым не плодит строк (UPSERT по entity_id+profile_type).
- [ ] Тест mock-LLM → RED → код → GREEN → commit → push.

---

## Чеклист на боксе (после merge)

1. `git pull` → перезапуск watch + dashboard.
2. Прогон наполняет graph автоматически; autofit (Ф0) сам строит архетипы+map → вкладка «Личности» живая без ручных команд.
3. Для интерпретаций: `python -m callprofiler profile-all --user me --persist` (llama-server жив, ASR-фаза не идёт).
4. Проверка: клик имени → досье ≤1с; пустые слои не дают 500; `graph-health --user me` exit 0.

## Self-review

- Покрытие запроса: пустая вкладка (Ф0), полный портрет risk+BS+всё-что-есть (Ф2), «нажал имя — знаешь всё» (Ф3), «без лирики» — только факты/цитаты/фразы, био-проза в досье не включается. ✓
- Тип-согласованность: `entity_contact_map` (1.1) = источник для indices/entity (2.2) и `/api/people`; `include_llm` (2.1) используется в 2.2. ✓
- Не трогаем: терминальные статусы, пути удаления, GPU-порядок — T3-гейтов внутри задач нет (кроме соблюдения «LLM не во время ASR» в Ф4, отражено).
