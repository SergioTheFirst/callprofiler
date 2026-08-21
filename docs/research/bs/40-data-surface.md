# 40 — Data surface: реконструкция по коду (единственная эмпирика на этой машине)

> Статус: round 1, 2026-08-22. Все факты — из кода репозитория на HEAD `4006414`, проверены лично
> (отчёты субагентов перепроверены grep/sed; расхождения исправлены). Ни одного факта «по памяти».
> Формат: `path:line — факт`. Пути относительно `src/callprofiler/`, если не указано иное.

## 0. Карта потока (как есть)

```
transcripts(speaker OWNER/OTHER/UNKNOWN, start_ms,end_ms,text)
   │  calls.role_fragile = 1 если UNKNOWN-доля > 0.3   (diarize/role_assigner.py:12-23)
   ▼
analyze/prompt_builder + prompt_budget.clip_transcript_for_llm   (head ⅓ + middle + tail ¼ от max_chars)
   ▼
configs/prompts/analyze_v001.txt  →  Qwen3.5-9B (json)   → analyses.raw_response (schema_version='v2')
   │   два НЕЗАВИСИМЫХ «BS»-канала в одном ответе:
   │   (a) bs_score 0-100 + bs_evidence[]  — per-call оценка самой LLM
   │   (b) structured_facts[] {fact_type ∈ promise|contradiction|emotion_spike|vagueness|blame_shift|claim,
   │        entity_key, value, quote, polarity, intensity, confidence}  — БЕЗ поля «кто сказал»
   ▼
(a) aggregate/summary_builder._compute_weighted_bs_score → contact_summaries.avg_bs_score (half-life 90d)
    bulk/enricher.py:105-131 + cli/commands/query.py:480 — bs_evidence[] → events(event_type='contradiction',
    who='UNKNOWN', confidence=0.8, entity_id=NULL)
(b) graph/builder.GraphBuilder.update_from_call → graph/validator.FactValidator → graph/repository.insert_fact_event
    → events(event_type: promise|contradiction как есть; emotion_spike|vagueness|blame_shift|claim → 'fact';
             who='UNKNOWN' всегда; fact_type-колонка НЕ заполняется; fact_id=sha256(fact_type|entity_id|quote)[:16])
   ▼
graph/aggregator.EntityMetricsAggregator → entity_metrics (counts по event_type; bs_index = v1_linear)
   ▼
graph/calibration.BSCalibrator → bs_thresholds (p25/p50/p75/p90 распределения bs_index) → label
   ▼
insight/admiralty.source_grade(bs_label, kept_ratio, kept_n) → A–F
   ├─ deliver/card_generator._grade_line → карточка (≤512 байт)
   ├─ dashboard/db_reader.get_person_dossier → indices.bs_index, admiralty (через entity_contact_map, top-confidence)
   └─ biography/psychology_profiler._extract_patterns → паттерны promise_breaker/… (пороги 0.4/0.2/0.2/0.15/0.2)
```

## 1. Промпт (`configs/prompts/analyze_v001.txt`)

- `:1-5` — роли: `[Me]` = владелец Сергей Медведев, `[S2]` = собеседник; «Роли могут быть перепутаны —
  определяй по смыслу»; «"Сергей"/"Серёж"/"Медведев" = ВСЕГДА [Me]».
- `:25-26` — `"bs_score": 0-100`, `"bs_evidence": ["примеры уклончивости/лжи, или пусто []"]`.
- `:68` — правило шкалы: `bs_score: 0=честный конкретный разговор, 100=сплошной пиздёж и уклонения`.
  Это единственное «определение» BS в системе; «уклончивость» и «ложь» склеены в одну шкалу.
- `:53-64` — `structured_facts[]`: `fact_type: "promise|contradiction|emotion_spike|vagueness|blame_shift|claim"`,
  `entity_key`, `value`, `quote`, `start_ms: null`, `end_ms: null`, `polarity: -1|0|1`, `intensity 0..1`,
  `confidence 0..1`. **Поля «кто говорит» (who/speaker) нет.**
- `:77-90` — правила: quote «дословная цитата из разговора, >=5 символов», «Факты с confidence<0.6 — не
  записывать», polarity/intensity. **Определений vagueness / blame_shift / emotion_spike / contradiction
  НЕТ** — модель интерпретирует имена типов сама.
- `promises[].vague: true|false` (`:18`) — отдельный флаг «размытого» обещания, в граф не идёт.
- `bulk/enricher.py:411-419` — в промпт подмешивается метрика мата: «Учти при оценке bs_score и call_type»
  (мат как сигнал BS — неверифицированная посылка).
- Клип входа: `analyze/prompt_budget.py:17-40` — `clip_transcript_for_llm(transcript, max_chars)`:
  `head = max_chars//3`, `tail = max_chars//4`, `middle = остаток` из центра; маркеры
  `... [середина разговора] ...`. Т.е. для длинных звонков LLM видит ~3 фрагмента; «противоречие»
  внутри одного звонка между невидимыми частями недоступно по построению.

## 2. Парсер (`analyze/response_parser.py`)

- `:40` — `parse_status ∈ {parsed_ok, parsed_partial, parse_failed, output_truncated, unknown}`.
- `:121` — обязательные для `parsed_ok`: `{"priority","risk_score","summary","call_type"}` — структура
  `structured_facts` в критерий полноты НЕ входит.
- `:306-345` — отсутствующие поля заполняются дефолтами (`_get_int/_get_str/_get_list/_get_dict`) —
  tolerant-repair; `llm.md`: усечение `finish_reason='length'` не кэшируется (T-13), но обрубок
  возвращается вызывающему и может быть сохранён.

## 3. Builder + validator (`graph/builder.py`, `graph/validator.py`, `graph/config.py`)

- `graph/config.py:3-14` — `MIN_FACT_CONFIDENCE=0.6`, `MIN_QUOTE_LENGTH=5`, `RELATION_DECAY_DAYS=180`,
  `FACT_ID_ALGORITHM="sha256"`, `FACT_ID_LENGTH=16`, `BS_FORMULA_VERSION="v1_linear"`.
- `graph/validator.py:22-23` — `MIN_QUOTE_LEN=8`, `MIN_MATCH_RATIO=0.72`; `:149` — `SequenceMatcher(None,
  quote_lower, window).ratio()` по скользящему окну транскрипта; `:97-99` — **если `transcript_text is None`
  — проверка дословности пропускается** (warning).
- `graph/builder.py:191` — `self._validator.validate(fact, transcript_text)`; `:203-204` —
  `fact_type = fact.get("fact_type","fact")`, `fact_key = f"{fact_type}|{entity_id}|{quote}"`; `:214` —
  `event_type=fact_type` передаётся в репозиторий.
- **Кто передаёт транскрипт:** `graph/replay.py:134` и `cli/commands/graph.py:53` — ДА
  (`transcript_text=…`); **`pipeline/orchestrator.py:994`, `bulk/enricher.py:276`, `db/uow.py:8` — НЕТ**
  (`update_from_call(call_id)`). ⇒ в боевом пути (watch / bulk-enrich) дословность цитат НЕ проверяется;
  проверяется только при `graph-replay`/`graph-backfill`.
- `graph/repository.py:395-415` — `insert_fact_event`: `allowed = {promise, debt, contradiction, risk, task,
  fact, smalltalk}`; `db_event_type = event_type if in allowed else "fact"` (docstring `:399`:
  «emotion_spike, vagueness, blame_shift, claim → 'fact'»); `INSERT OR IGNORE INTO events (user_id,
  contact_id, call_id, event_type, who, payload, source_quote, confidence, status, entity_id, fact_id, quote,
  start_ms, end_ms, polarity, intensity) VALUES (…, 'UNKNOWN', …, 'open', …)`.
  **`who` захардкожен `'UNKNOWN'`; колонка `fact_type` (объявлена `:62`) не записывается.**
- `db/schema.sql:115-117` — CHECK `event_type IN ('promise','debt','contradiction','risk','task','fact',
  'smalltalk')`; `who IN ('OWNER','OTHER','UNKNOWN')`.
- Owner: `graph/repository.py:680` — `COALESCE(e.is_owner,0)=0` при выборке для калибровки; `entities.is_owner`
  (`:123-135`).

## 4. Агрегатор (`graph/aggregator.py`) — формула и её фактические входы

- `graph/repository.py:503-511` — `count_facts_by_type`: `SELECT event_type, COUNT(*) … GROUP BY event_type`.
- `graph/aggregator.py:44-51` и `:114-120` — `total_promises=counts["promise"]`,
  `broken=counts["broken_promise"]`, `fulfilled=counts["fulfilled_promise"]`,
  `contradictions=counts["contradiction"]`, `vagueness=counts["vagueness"]`,
  `blame_shifts=counts["blame_shift"]`, `emotional_spikes=counts["emotion_spike"]`.
- `graph/aggregator.py:210-243` — `_bs_v1_linear`: `safe_p=max(total_promises,1)`, `safe_c=max(total_calls,1)`;
  `broken_ratio=broken/safe_p`; `*_dens=min(x/safe_c,1)`; `bs_raw = 0.40·broken_ratio + 0.20·contradiction_dens
  + 0.15·vagueness_dens + 0.15·blame_dens + 0.10·emotional_dens`; `return min(bs_raw·100, 100)`.
- **Факт (проверено grep по всему `src/`):** строки `"broken_promise"`/`"fulfilled_promise"` как
  `event_type` НЕ производятся ни одним модулем (встречаются только в aggregator как ключи чтения и в
  `entity_metrics` как имена колонок). CHECK-констрейнт их и не допускает. ⇒ `broken ≡ 0`, `fulfilled ≡ 0`.
- **Факт:** `vagueness`, `blame_shift`, `emotion_spike` никогда не являются значениями `event_type`
  (схлопнуты в `'fact'`, §3). ⇒ `vagueness ≡ blame_shifts ≡ emotional_spikes ≡ 0`.
- **Следствие:** в проде `bs_index = 20 · min(contradictions/total_calls, 1)`, диапазон **[0, 20]**,
  где `contradictions` = события `event_type='contradiction'` с `entity_id` (из `structured_facts`
  c `fact_type='contradiction'`; `bs_evidence`-события enricher имеют `entity_id=NULL` и не считаются —
  `aggregator.py:100-105` `WHERE entity_id=? AND user_id=?`).
- `total_calls` = `COUNT(DISTINCT call_id) FROM events WHERE entity_id=?` (`:100-105`) — число звонков, где
  у сущности есть ХОТЬ ОДНО событие, не число звонков с контактом.
- `entity_metrics` колонки (`graph/repository.py:155-173`): `entity_id, user_id, total_calls, total_promises,
  fulfilled_promises, broken_promises, overdue_promises, contradictions, vagueness_count, blame_shift_count,
  emotional_spikes, avg_risk, bs_index, bs_formula_version, emotional_pattern, last_interaction, updated_at`.
  Никакой давности/окна: счётчики накопительные за всю историю.
- Тесты: `tests/test_graph.py:380-399` вызывают `_bs_v1_linear(...)` с рукописными счётчиками
  (`vagueness=5, blame_shifts=5, …`) — формула проверена на входах, которых боевой путь не порождает.

## 5. Калибратор (`graph/calibration.py`)

- `:35-49` — `analyze(user_id, min_calls=3, min_promises=1)` → `get_bs_scores_filtered` (total_calls≥3,
  total_promises≥1, не owner, не archived); `:61-78` — `p25/p50/p75/p90` → `reliable_max/noisy_max/
  risky_max/unreliable_max`; `:23-31` — `LABEL_MAP` reliable🟢 noisy🟡 risky🔴 unreliable🔴 critical⚫
  uncalibrated⚪. Чисто ранговая: 25% сущностей ВСЕГДА «reliable», 10% ВСЕГДА «critical», независимо от
  абсолютных значений; при массе нулей (§4) перцентили вырождаются (p25=p50=0 → «noisy» начинается с 0).
- `bs_thresholds` (`graph/repository.py:207-218`): `reliable_max, noisy_max, risky_max, unreliable_max,
  entity_count, std_dev`. Gate `graph-health` требует наличия строки.

## 6. Replay / health / audit (`graph/replay.py`)

- `:61-81` — обнуляет graph-колонки events (v2) и таблицы `entity_profiles, entity_metrics, relations,
  entities`; `:116-142` — `update_from_call(call_id, transcript_text=…)`; `:160-172` — пересчёт
  метрик; `:198-215` — `GraphAuditor` + `replay_runs`; `:220-234` — assert `facts_inserted>0` при
  calls>0, `rejection_rate<0.90`, `orphan_events==0`, `owner_contamination==0`; `:236-246` — warnings при
  rejection_rate>0.60 / <0.05; `:248-263` — пересборка `entity_contact_map`, `mention_edges`.
- Инвариант `graph.md`: `entity_metrics = PURE FUNCTION(events+calls+analyses)` (`aggregator.py:88-92`).

## 7. Презентация

- `insight/admiralty.py:12-31` — `SOURCE_PHRASES` A «надёжен, слово держит» / B «обычно надёжен» /
  C «сигнал шумный» / D «бывали срывы» / E «ненадёжен» / F «данных мало»; `INFO_PHRASES` 2/3/4/6;
  `_KEPT_RATIO_MIN=0.8`, `_KEPT_N_MIN=5`, `_INFO_HIGH=0.8`, `_INFO_MID=0.6`; `:34-46` —
  `source_grade`: reliable→A (если kept_ratio≥0.8 ∧ kept_n≥5) иначе B; noisy→C; risky→D;
  unreliable|critical→E; иначе F; `:49-57` — `info_grade(avg_confidence)`: ≥0.8→2, ≥0.6→3, иначе 4,
  None→6 (avg_confidence = среднее LLM-`confidence` событий — самооценка модели, §9).
- `deliver/card_generator.py:1-27,109,117-122,150-161,179-199` — формат MacroDroid v2 ≤512 байт:
  `header / risk: {global_risk} {emoji} / due: / grade: {src}{info} — {phrase} / call: / bullet×3 / hook /
  обновлено`; `_truncate_bytes` резервирует штамп; риск-эмодзи по `risk_thresholds` (p50/p85) с fallback
  30/70 (`insight/risk_calibration.py`). В карточке BS присутствует ТОЛЬКО через `grade:`-строку.
- `dashboard/db_reader.py:603-630,1024-1062,1121-1130` — досье: `entity_contact_map` top-confidence →
  `entity_metrics.bs_index` → `indices.bs_index`; `BSCalibrator.get_label` → `bs_label` → `admiralty`.
  Дашборд LLM не зовёт. `static/app.js` — числовых порогов по `bs_` не найдено (раскраска по label).
- `insight/tension.py:17-48` — 5 правил «напряжений» по z (Z_HIGH=1, Z_LOW=−1), правило 4: «конкретен
  (`spec_water>1`), но обещания держит редко (`prom_keep_rate_other<−1`)» — единственное место, где
  specificity (B2) сведена с promise-keeping.
- `biography/psychology_profiler.py:244-266` — паттерны: `_add(name, ratio, threshold)`: severity `high`
  если ratio≥1.5·threshold иначе `medium`; `promise_breaker` broken/total_promises ≥0.4;
  `contradictory` contradictions/total_calls ≥0.2; `vague_communicator` ≥0.2; `blame_shifter` ≥0.15;
  `emotionally_volatile` ≥0.2; `reliable` если broken==0 ∧ total_promises≥3 (→ при `broken≡0` любой
  контакт с ≥3 обещаниями помечается «надёжный»); `high_risk` avg_risk≥70.
- `aggregate/summary_builder.py:378-420` — `avg_bs_score` = взвешенное среднее per-call `bs_score`
  (half-life 90 дней, `2**(-days/90)`); `:509-530` — `_generate_advice`: `bs_score>60` → совет,
  `risk<30 ∧ bs_score<30` → «стандартный». Это ВТОРОЙ BS, не связанный с `bs_index`.

## 8. Поведенческие исходы (`insight/promise_outcomes.py`) — единственный верифицируемый сигнал

- `:44,48,51-53` — `_WINDOW_DAYS=120`, `_LATE_GRACE_DAYS=2`, `_KEPT_RATIO_HIGH=0.8`, `_KEPT_RATIO_MID=0.5`,
  `_MIN_RELIABILITY_N=3`; `:56-60` — `_RE_DONE`/`_RE_FAIL` (ё-нормализация, см. decisions.md);
  `:383-398` — `contact_reliability` только `side='contact'`, `kept_ratio = kept/(kept+late+broken)`,
  n<3 → None; фразы «держит слово» / «через раз» / «чаще не выполняет».
- Источник обещаний: UNION `promises` + `events(promise|debt)`; `who='UNKNOWN'` — пропуск. Разрешение
  исхода — det-regex по будущим сегментам ТОЙ ЖЕ стороны у того же contact_id (+LLM только `--llm`,
  мемоизация). `promise_outcomes(user_id, promise_key PK, …, status kept|late|broken|unknown, days_late,
  quote, confidence)`.
- Это единственный сигнал, у которого есть **внешний критерий** (исход), а не самооценка LLM.

## 9. Существующие «уверенности» в системе

| Где | Что | Семантика | Внешний критерий |
|---|---|---|---|
| `structured_facts[].confidence` | 0..1 от LLM, гейт 0.6 | самооценка модели | нет |
| `events.confidence` → `admiralty.info_grade` | среднее по событиям → 2/3/4 | то же, агрегат | нет |
| `analyses.feedback` (`db/schema.sql:70`) | `ok`/`inaccurate` per-call, кнопки `feedback_{call_id}_{ok|inaccurate}` (`deliver/telegram_bot.py:181-234`) | владелец о РЕЗЮМЕ звонка | да, но про summary, не про факты |
| `fact_feedback(user_id,item_kind∈promise|event|deep_fact,item_key,verdict∈confirmed|rejected)` | `fv|event|{id}|c|r` (`telegram_bot.py:560-561`) | владелец о КОНКРЕТНОМ обещании/факте; rejected нигде не рендерится | да — лучший из имеющихся weak labels |
| `promise_outcomes.status` | kept/late/broken/unknown | поведение | да (det, с шумом regex) |
| `contact_age_estimates.confidence` (`insight/repository.py:75` CHECK 1..100) | классы точности 3>2>1>0; +10 за независимое согласие, cap 95; конфликт min+10; LLM −15/cap 50 | экспертные правила, не калиброваны | нет (план §15 vozrast.md) |
| `contact_age_style.confidence` (`:97-98`, level 1..5) | `conf=100/(1+exp(−x))`, `x=1.5·(ln ESS−ln 10)+1.0·(agreement−0.5)+0.8·marker−1.2·conflict` (`age_style/confidence.py:442-495`) | «expert, not trained» | нет |
| `age_fusion.fuse_age` (`fuse-v1`) | 5 правил, +5/−10, cap 95/70/50 | правила | нет |
| `calls.role_fragile` | UNKNOWN-доля >0.3 | качество ролей | косвенный |
| `admiralty.source_grade` A–F | по bs_label + kept_ratio | ранг | частично (kept) |

Общее у всех: ни одна не проверялась reliability-диаграммой; ни у одной нет `formula_version`, кроме
age (`FUSION_VERSION`, `TABLE_VERSION`); единственная с CHECK 1..100 — age.

## 10. Что ещё есть рядом (используемо для нового дизайна)

- `contact_features` (11+ осей, `Feature(value, support_n, tier)`, веса IMMUNE 1.0 / ROBUST 0.8 /
  AFFECTIVE 0.6 / FRAGILE 0.4, `support_floor=2`, z-score внутри юзера — `insight/feature_store.py`);
  hedge-лексикон `insight/features/linguistic.py:914-917` = {наверное, наверно, возможно, может, кажется,
  вроде, типа, посмотрим, попробую, постараюсь, неуверен, затрудняюсь} (12 слов, без весов, без учёта
  жанра); specificity (`specificity.py`, числа/даты/деньги/время по whitespace-токенам).
- `deep_facts` (M8, `insight/deep_extract.py`): map-reduce по полному транскрипту, гейт quote-substring
  через `textnorm.norm_quote`, `who∈{OWNER,OTHER}` обязателен — т.е. ТАМ атрибуция есть.
- `mention_edges`, `entity_contact_map` (name 0.95 / cooccur), `contact_tiers` (F8), `risk_thresholds`.
- `insight/spotcheck.py` — `spotcheck-sample --n --seed`: стратифицированная markdown-выборка звонков для
  ручной проверки (WER/роли/обещания); **ярлыки обратно в БД не пишет**.
- `insight/synth/corpus.py` — синт заполняет `calls/transcripts/analyses` (`sample_analysis`), **не
  генерирует `structured_facts`/events** (grep пуст) → граф/BS на синте сегодня не воспроизводим без
  расширения генератора.
- Миграции: `db/migrations.py:286-296` — `ALL_MIGRATIONS` id 1..9 (последняя `9 owner_triggers`),
  `Migration(id, name, apply)`, checksum = sha256(исходника `apply`).
- Автофит в watcher (`pipeline/watcher.py:323-339`): `run_features_build → run_archetypes_fit (→ person-link)
  → run_age_estimate(stale_only) → run_style_estimate(stale_only) → recompute_tiers`. Граф (`graph-replay`)
  в автофит НЕ входит; граф обновляется инкрементально на каждый звонок (`orchestrator.py:994`).
- Бэкап (`ops/backup.py`): `backup`/`verify-backup` (quick_check, FK, table_counts, sha256)/`restore`
  (T-20, чистит `-wal/-shm`).

## 11. Сводка дефектов, выявленных реконструкцией (входы в 60-existing-bs-verdict.md)

| # | Дефект | Где | Класс |
|---|---|---|---|
| D1 | 4 из 5 членов BS структурно ≡ 0 (нет производителя `broken_promise`; vagueness/blame/emotion схлопнуты в `'fact'`) | repository.py:399-402, aggregator.py:44-51 | мёртвая формула |
| D2 | `who='UNKNOWN'` для всех structured_facts → нельзя отличить «контакт уклоняется» от «владелец уклоняется» | repository.py:406-415, промпт без who | потеря атрибуции |
| D3 | verbatim-проверка цитат пропускается в боевом пути | orchestrator.py:994, enricher.py:276, uow.py:8 | галлюцинации проходят |
| D4 | Нет определений типов фактов в промпте; «уклончивость/ложь» склеены в `bs_score` | analyze_v001.txt:53-68 | конструкт не определён |
| D5 | Два несвязанных BS (`bs_index` ранговый по графу, `avg_bs_score` самооценка LLM) с разными шкалами | summary_builder.py:378, aggregator.py:210 | двойственность |
| D6 | Ранговая калибровка гарантирует 10% «critical» при любых данных; вырождается на нулях | calibration.py:61-78 | ложная точность |
| D7 | Счётчики без окна давности; `total_calls` = звонки с событиями сущности | aggregator.py:100-105 | смещение |
| D8 | `reliable` при broken==0 ∧ promises≥3 — всегда истинно из-за D1 | psychology_profiler.py:261-263 | ложный позитив |
| D9 | Клип головы/хвоста → внутризвонковые противоречия невидимы | prompt_budget.py:17-40 | слепота |
| D10 | Синт не порождает structured_facts → офлайн-тест формулы невозможен на механизме | synth/corpus.py | тестируемость |
| D11 | Тесты формулы на рукописных входах → «зелёный» при мёртвом проде | tests/test_graph.py:380-399 | ложная верификация |
