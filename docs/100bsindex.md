# 100bsindex — BS-v2 (индекс наблюдаемых расхождений + уверенность): план прямого исполнения

Версия: `100bsindex / 2026-08-22`, база: `main@11fe81e` (серия sintezdiharea T-06…T-25 завершена,
миграции 1…11 применены, `PROMPT_VERSION_ANALYZE='v002'`, suite 1590 passed). Источник и авторитет —
`docs/GPT90-execution-plan.md` (далее **GPT90**). Этот документ = GPT90, сведённый с реальным состоянием
репозитория: каждая задача имеет проверенные `path:line`-якоря, точные имена файлов/тестов/констант и не
оставляет выбора исполнителю. Где GPT90 расходится с кодом — расхождение перечислено в §0.1 с доказательством;
принципиальных изменений формул/схемы/версий нет, кроме трёх, доказанных дважды (§0.1 п.1–3).

Тир workstream: **T3** (новые таблицы/миграция, replay/удаление производных строк, терминальные семантики).
Тир каждого slice указан в задаче; исполнение — по Model Routing v2 (CLAUDE.md).

## 0. Решение одним абзацем (= GPT90 §0)

CallProfiler вводит всегда видимую пару:

```text
BS 0…100 = индекс наблюдаемых расхождений
confidence 1…100 = сила, качество, согласие и устойчивость основания этого BS
```

BS не вероятность лжи и не типология человека. Канон хранится на контакте `(user_id, contact_id)` и работает
после первого безымянного звонка. Существующие `entity_metrics.bs_index/bs_formula_version`, `bs_thresholds`,
Admiralty, patterns, `contact_summaries.avg_bs_score`, `promise_outcomes` сохраняются и получают versioned
projection. Baseline `v2_roc_observed_1 / c1_effective_evidence_1` не использует owner labels, `fact_feedback`,
реальную БД, бокс или user-percentiles. Phase B refinements default-off; Phase C только доказывает, что они
не портят baseline. Это исполняет memory-правило `research-build-on-existing`: развитие существующих механизмов,
new-user case первым, без зависимости от adjudication.

### 0.1 Верифицированные расхождения GPT90 ↔ код (каждое проверено дважды: grep + чтение)

| # | GPT90 говорит | Код (`main@11fe81e`) | Решение в этом плане |
|---|---|---|---|
| 1 | «Следующая central migration — **11**, применённые 1…10» (§6, R-01) | `db/migrations.py:326` `Migration(11, "calls_asr_coverage")` уже применена; CONTINUITY «Миграции 10–11»; `docs/ops/box-canary-checklist.md` ждёт `PRAGMA user_version → 11` | Миграция BS-v2 = **12** (`_m012_bs_v2`). Все «M11» GPT90 читать как **M12**. Применённые 1…11 не править (checksum-mismatch = fail-loud) |
| 2 | Phase A держит `PROMPT_VERSION=v001`; `analyze_v002.txt` создаётся только в R-46; флаги `analysis_prompt_active=v001|v002`; §14.8 «PROMPT_VERSION remains v001» | `analyze/service.py:35` `PROMPT_VERSION_ANALYZE = "v002"`; `configs/prompts/analyze_v002.txt` существует (T-14: `{{owner_name}}`, envelope `<данные>`, `promises[].vague`, `who: Me|S2`, `bs_evidence: [str]`, structured_facts БЕЗ `who`) | Phase A держит **v002** неизменным. Кандидат Phase B = **`analyze_v003.txt`** (`structured_facts.who`, typed `bs_evidence`, `promises[].due`). Флаги: `analysis_prompt_active=v002|v003` (default v002), `analysis_prompt_candidate=none|v003`. Кэш-namespace v002/v003 (`llm_cache.make_key` уже включает `prompt_version`, `analyze/llm_client.py:200`) |
| 3 | `bs_legacy_snapshots`: `BEFORE UPDATE`/`BEFORE DELETE` triggers `RAISE(ABORT,'immutable legacy snapshot')` (§6) | T-06 `Repository.purge_user` (`db/repository.py:736-790`) делает `DELETE FROM {tbl} WHERE user_id=?` для **каждой** таблицы с `user_id` по introspection; `tests/test_cleanup.py::test_purge_user_introspection_classifies_all_tables` собирает полную схему. Безусловный DELETE-trigger → `cleanup.py purge-user --apply` падает на первом же контакте со снапшотом = сломан privacy-контракт T-06 (Hard Constraint: пути удаления данных) | Immutability сохраняется, но DELETE-trigger **условный**: M12 добавляет `users.purge_started_at TEXT`; `purge_user` первым оператором транзакции ставит `UPDATE users SET purge_started_at=datetime('now') WHERE user_id=?`; trigger `WHEN NOT EXISTS (SELECT 1 FROM users WHERE user_id=OLD.user_id AND purge_started_at IS NOT NULL)` → RAISE. Вне purge — неизменяемо; внутри purge — удаляется; rollback purge снимает флаг вместе со всем |
| 4 | R-05 «live currently skips verbatim», «replay удаляет speaker markers» | T-15: `graph/builder.py:107-119` сам грузит транскрипт **без role-маркеров** (`"\n".join(text)`) → verbatim-гейт работает, но `FactValidator` speaker всегда `unknown` (`graph/validator.py:158-177` ищет `[me]/[s2]`); `graph/replay.py:126-128` и `cli/commands/graph.py:35-37` делают `seg.text` на `dict` (`Repository.get_transcript` → `list[dict]`, `db/repository.py:878-889`) → `AttributeError` проглочен → `transcript_text=None`. Два формата уже есть: `pipeline/orchestrator.py:85 _format_transcript(list[Segment])` и `bulk/enricher.py:168 _format_transcript(list[dict])` | R-05 остаётся; «почему» исправлено: единый role-tagged formatter заменяет ОБА `_format_transcript` и bare-load builder'а |
| 5 | R-31 «current card direct write violates artifact atomicity» | `deliver/card_generator.py:333` и `aggregate/summary_builder.py:309` уже `atomic_write_text` (T-08). Реальные дефекты: `dashboard/tools.py:296` `CardGenerator(repo, self.config).write_all_cards()` — конструктор принимает ОДИН аргумент (`card_generator.py:109`), метода `write_all_cards` у CardGenerator нет (есть `update_all_cards`, :349) → кнопка «rebuild cards» дашборда падает; `summary_builder.generate_card_text` режет `text[:400]+"..."` символами, не байтами (:281-283); два рендерера; строки `bs:` нет ни в одном | R-31 остаётся; «почему» = дубль рендереров + сломанный dashboard-вызов + небайтовая обрезка |
| 6 | R-30 «Не ждать T-19: минимальный typed renderer реализуется этим slice» | T-19 сделан: `insight/risk_calibration.py:100 risk_band`, `:129 risk_emoji`, `RISK_POLICY_VERSION='risk-v1'`; карточка и дашборд уже на нём | R-30 реализует typed renderer, строку `risk:` берёт из `risk_band/risk_emoji`, не дублирует |
| 7 | Ссылки на `30-signal-audit.md`, `synth-package/README.md`, `docs/research/bs-v2/…`, claims C-21…C-46 | Существуют: `docs/research/bs/{00,10,20,40,60,70,90,99}*.md`, `claims-ledger.md` (C-01…C-20), `box-package/`. Нет: `30-signal-audit.md` (аналог — `40-data-surface.md`), `bs-v2/`, C-21+ | Карта сигналов = `docs/research/bs/40-data-surface.md`. `docs/research/bs-v2/` создаётся задачами R-37/R-48. Claims C-21…C-46 переносятся в ledger задачей R-41 (текст GPT90 §18 как есть); до этого аргументация задач опирается на S-ID (§2.1) и `path:line` |
| 8 | Имена тестов `tests/test_pipeline.py`, `tests/test_bulk_enricher.py`, `tests/test_dashboard_db_reader.py`, `tests/test_features_config.py`, `tests/test_docs_contracts.py`, `tests/test_release_manifest.py`, `tests/test_bs_*.py`, `tests/insight/test_bs_synth_*.py` | Не существуют | Создаются новыми файлами ровно под этими именами (кроме: досье → существующий `tests/test_dashboard_dossier.py`). Существующие и расширяемые: `test_db_migrations.py`, `test_tenant_ownership.py`, `test_graph_replay.py`, `test_graph.py`, `test_card_generator.py`, `test_summary_builder.py`, `test_digest.py`, `test_psychology_profiler.py`, `test_watcher_autofit.py`, `test_prompt_builder.py`, `test_canary.py`, `tests/insight/test_promise_outcomes.py`, `tests/insight/test_admiralty.py` |
| 9 | — (не упомянуто) | `apply_graph_schema(conn)` вызывается ВНУТРИ `uow_for` (`pipeline/orchestrator.py:1089-1091`, `bulk/enricher.py:273-275`); `insight/repository.py::apply_insight_schema` делает безусловный `conn.commit()` (:262) | Добавлено к R-12/R-21/R-22: schema-preflight до `BEGIN`, никакого `apply_*_schema` внутри UoW |
| 10 | — | `analyses.schema_version` default: m002 (`migrations.py:100`) = `'v2'`, `apply_graph_schema` (`graph/repository.py:47`) = `'v1'` — три DDL-владельца расходятся; `save_analysis` пишет значение явно (`repository.py:963`) | R-01 fresh `schema.sql` объявляет `schema_version TEXT DEFAULT 'v1'` (legacy-семантика, как graph DDL); m002 не трогать; writer всегда явный |
| 11 | — | `bs_evidence[]` материализуется в `events(event_type='contradiction', who='UNKNOWN', confidence=0.8, entity_id=NULL, fact_id=NULL)` ТОЛЬКО bulk-путём (`bulk/enricher.py:105-131`) и `backfill-events` (`cli/commands/query.py:~480`); live `orchestrator` events из анализа не пишет вообще | Эти строки = `producer='legacy'` (M12-правило `fact_id IS NULL`) → никогда не C-eligible (§3.2: `bs_evidence` — только M-support). R-22 НЕ начинает писать их в live; C считается только по `producer='graph_v2' AND fact_type='contradiction' AND who='OTHER'` |
| 12 | R-02: `get_entity/get_entity_metrics` | Подтверждено (`graph/repository.py:286,495`); дополнительно unscoped: `graph/aggregator.py:100 full_recalc_from_events(entity_id)`, `biography/data_extractor.py:191 get_behavioral_patterns(entity_id, conn)`, `dashboard/db_reader.py` вызовы метрик через `entity_id` без user в части SELECT | Все четыре — в R-02 callsite inventory |
| 13 | R-36 «summary/card advice» | `card_generator` v2 advice-строки НЕ имеет (`test_generate_card_no_advice_line` закрепляет); advice живёт в `summary_builder._generate_advice` (:510-531, «Надёжный партнёр» при risk<30 ∧ bs<30), `contact_summaries.advice`, `summary_builder.generate_card_text` (:276), Telegram `cmd_contact` (:483-484 «Звонков:», «BS: avg_bs_score») | R-36 правит именно эти четыре места; `card_generator` advice не возвращает |
| 14 | graph-health | `cli/commands/graph.py:362-440` check 4 требует `bs_thresholds` | Не трогать: это гейт biography, не BS-v2. R-44 пишет версионированные строки — гейт остаётся совместим |

Всё остальное в GPT90 (формулы §3–5, таблицы §6, порядок §7, версии §8, UI §9, ADEMP §10, задачи, риски,
traceability) подтверждено кодом и перенесено без изменений смысла.

## 1. Концепция и границы (= GPT90 §1, без изменений)

### 1.1 Что измеряется
- слово ↔ последующий сохранённый status/сообщение об обязательстве;
- слово ↔ слово (`contradiction`);
- конкретика ↔ обещание (`promises[].vague`, подтверждённое текстом обещания);
- поддержанная transcript evidence самооценка `bs_score` как weakest fallback.

Общие `vagueness`/`blame_shift`/`emotion_spike`/bare `claim` — materialized (Phase A чинит их запись),
сохраняются в patterns/context, direct BS weight = 0 (`claim` — opportunity denominator).

### 1.2 Что не измеряется
Ложь, безразличие к истине, ошибка, незнание, забывание, вежливое уклонение, рациональная смена позиции,
ASR-artifact. UI не пишет «лжёт», «честный», «ненадёжная личность», диагноз. `BS=0` = «пригодных расхождений
не обнаружено». `BS=100` на первом звонке при `C≤5` = одно сильное, но слабодоказанное наблюдение.
Основание: DePaulo <https://doi.org/10.1037/0033-2909.129.1.74>, Hauch
<https://doi.org/10.1177/1088868314556539>, Luke <https://doi.org/10.1177/1745691619838258>, UNIDECOR
<https://aclanthology.org/2023.wassa-1.5/>.

## 2. Источники данных — текущий контракт (проверено по `db/schema.sql`, `db/migrations.py`, DDL graph/insight)

| Источник | Поля (как есть) | Роль baseline |
|---|---|---|
| `analyses` | `raw_response, canonical_json (m002), schema_version (m002, default-drift §0.1 п.10), parse_status, risk_score, call_type, prompt_version, created_at` | JSON source + parse quality; risk/call_type только context |
| v2 JSON (`analyze_v002.txt`) | `structured_facts[].fact_type/entity_key/value/quote/confidence/polarity/intensity` (без `who`), `bs_score`, `bs_evidence: [str]`, `promises[].who(Me|S2)/what/vague` (без `due`) | C/P/V/D, supported M; confidence/polarity/intensity direct weight 0 |
| `transcripts` | `call_id,start_ms,end_ms,text,speaker ∈ OWNER|OTHER|UNKNOWN` | who, UNKNOWN share, quote match |
| `calls` | `user_id,contact_id (NULL возможен),call_datetime,created_at,role_fragile,call_type,duration_sec,source_md5 (UNIQUE per user, m007),asr_coverage (m011)` | ownership/as-of/role quality; duration weight 0 |
| `promises` | `promise_id,user_id,contact_id,call_id,who,what,due,status (no CHECK),created_at` + M12 `vague,source_quote,quote_match,status_updated_at,status_method` | promise opportunity; system status fallback только с provenance/date |
| `events` | `id,user_id,contact_id,call_id,event_type CHECK(promise,debt,contradiction,risk,task,fact,smalltalk),who CHECK(OWNER,OTHER,UNKNOWN),payload,source_quote,confidence,deadline,status CHECK(open,fulfilled,broken,expired,resolved)` + m003 `entity_id,fact_id,fact_type,quote,start_ms,end_ms,polarity,intensity` + M12 provenance | grounded fact/opportunity; producer-safe replay |
| `promise_outcomes` (`insight/repository.py:217`) | `user_id,promise_key,contact_id,call_id,side CHECK(owner,contact),what,due,status CHECK(kept,late,broken,unknown),evidence_call_id,evidence_date,evidence_quote,days_late,method CHECK(det,llm),confidence,llm_prompt_hash,llm_result,prompt_version,computed_at` | strongest B; unknown = missing |
| `contact_features` | `contact_id,user_id,feature_set,feature_name,value,support_n,tier` | raw audit/context; все direct weights 0 |
| `contact_summaries` | `contact_id PK,user_id,total_calls,last_call_date,global_risk,avg_bs_score,…,advice` | legacy LLM-self diagnostic; `avg_bs_score` не перезаписывать |
| `entity_metrics` | `entity_id PK,user_id,total_calls,total_promises,fulfilled_promises,broken_promises,overdue_promises,contradictions,vagueness_count,blame_shift_count,emotional_spikes,avg_risk,bs_index,bs_formula_version,emotional_pattern,last_interaction` | existing graph projection; counters repaired |
| `bs_thresholds` | `id,user_id,reliable_max,noisy_max,risky_max,unreliable_max,entity_count,std_dev,created_at` | Phase B relative label only |
| `risk_thresholds` (T-19) | p50/p85 | no BS role |
| `deep_facts` | `user_id,item_key,call_id,contact_id,type,who CHECK(OWNER,OTHER),what,quote,prompt_version` | weight 0; Phase B opportunity candidate |
| `mention_edges` | `user_id,src_contact_id,dst_contact_id,mention_count` | weight 0 |
| `entity_contact_map` | `user_id,entity_id,contact_id,method CHECK(name,cooccur),confidence` PK(user,entity,contact) | projection routing (§7) |
| Admiralty/patterns | `insight/admiralty.py`, `biography/psychology_profiler.py:219`, `biography/data_extractor.py:191` | consumers, не evidence |

Подтверждённые дефекты, которые Phase A обязана исправить (все перепроверены по коду):

1. `graph/repository.py:379-415 upsert_fact` схлопывает тип в `event_type` (CHECK), **не пишет `fact_type`**, пишет `who='UNKNOWN'` литералом.
2. `graph/repository.py:503-511 count_facts_by_type` и `graph/aggregator.py:39-51,100-115` группируют только `event_type`; ждут невозможных `broken_promise/fulfilled_promise/vagueness/…` → v1 реально `∈[0,20]`.
3. `graph/builder.py:107-119` грузит bare-транскрипт (speaker всегда `unknown`); `graph/replay.py:126-128`, `cli/commands/graph.py:35-37` — `seg.text` на `dict` → None; результат `validation["speaker"]` не используется (:205-221).
4. `graph/builder.py:88-96` SELECT без `canonical_json` (комментарий :121 обещает обратное); `fact_key=f"{fact_type}|{entity_id}|{quote}"` (:217) зависит от transient `entity_id`, без `user_id/call_id/who`.
5. `graph/replay.py:66-70` `SELECT id FROM calls … AND id IN` — PK называется `call_id` (`schema.sql:29`).
6. Промпт `Me|S2`; `db/repository.py:1144-1186 save_promises` пишет `who` как есть и **теряет `vague`**; `insight/promise_outcomes.py:87 _side` понимает только `OWNER|OTHER` → live-обещания никогда не входят в outcomes.
7. `response_parser._check_parse_completeness` (:138-152) проверяет только `priority,risk_score,summary,call_type`; `summary_builder._compute_weighted_bs_score` (:379-420) при parse error кладёт 0 в среднее.
8. Entity/map после первого звонка не гарантированы: `ingest/ingester.py:119-124` создаёт контакт с `phone_e164=NULL` на КАЖДЫЙ безномерной звонок (`get_or_create_contact` ищет `phone_e164 = ?` с NULL → никогда не находит, `repository.py:155-158`); `bulk/loader.py:186-196` оставляет `contact_id=NULL`.
9. (новое) `apply_graph_schema` внутри UoW (`orchestrator.py:1091`, `enricher.py:274`); `apply_insight_schema` коммитит сам (`insight/repository.py:262`).
10. (новое) `dashboard/tools.py:296` — несуществующая сигнатура/метод CardGenerator.
11. (новое) `dashboard/static/app.js:1090-1096 bsClass` читает `thr.green_max/yellow_max`, а `bs_thresholds` имеет `reliable_max/noisy_max/…` → калиброванная ветка мертва.

Полная карта потока: `docs/research/bs/40-data-surface.md` §0.

### 2.1 Реестр оснований (S-ID) — те же, что GPT90 §2.1, с актуальными якорями

| ID | Основание |
|---|---|
| S-CODE-01 | `graph/repository.py:379-415,503-511`, `graph/aggregator.py:39-51,100-115`: потеря type/who, structural-zero counters |
| S-CODE-02 | `graph/replay.py:54-135`, `graph/builder.py:88-135,217`, `cli/commands/graph.py:13-60`: PK, canonical_json, transcript/provenance |
| S-CODE-03 | `db/schema.sql`, `db/migrations.py` (latest **11**), `graph/repository.py:_GRAPH_DDL`, `insight/repository.py:_SCHEMA/_MIGRATIONS`: три DDL-владельца; tenant rules m009 |
| S-CODE-04 | `insight/promise_outcomes.py`: `_WINDOW_DAYS=120`, `_LATE_GRACE_DAYS=2`, `_side`, `contact_reliability` `n<3→None` (:376-386) |
| S-CODE-05 | `insight/features/*.py`, `feature_store.py`: raw feature definitions; `specificity.py:19 compute_specificity(segments, reference_now)` |
| S-CODE-06 | `deliver/card_generator.py`, `aggregate/summary_builder.py`, `deliver/digest.py`, `deliver/telegram_bot.py:416-495`, `insight/admiralty.py`, `biography/psychology_profiler.py:219-262`, `biography/data_extractor.py:191-250`, `dashboard/{db_reader.py,labels_ru.py,static/app.js,tools.py}` |
| S-CONST | `CONSTITUTION.md`, T-03/T-04/T-05/T-06/T-08/T-15/T-16/T-19/T-23/T-24, replay invariant `.claude/rules/graph.md` |
| S-DEC | DePaulo/Hauch/Luke/UNIDECOR (§1.2) |
| S-PROM | Charness–Dufwenberg <https://doi.org/10.1111/j.1468-0262.2006.00719.x>, Vanberg <https://doi.org/10.3982/ECTA7673> |
| S-PRAG | Hyland/Clayman/SIGDIAL (`docs/research/bs/20-first-principles.md`) |
| S-ROC | Edwards & Barron <https://doi.org/10.1006/obhd.1994.1087> |
| S-LLM | Xiong et al. (ICLR 2024, §4.3) |
| S-PHIA | UK PHIA <https://www.gov.uk/government/publications/explaining-uncertainty-in-uk-intelligence-assessment> |
| S-SIM | Morris <https://doi.org/10.1002/sim.8086>, Sargent <https://doi.org/10.1057/jos.2012.20>, Hubert–Arabie <https://doi.org/10.1007/BF01908075> |

## 3. Preprocessing и defaults (= GPT90 §3, без изменений; дополнены якоря)

### 3.1 Дата и свежесть
Core functions принимают `as_of_date`; `datetime.now()`/`date.today()` запрещены в `insight/bs_*.py`
(существующий антипаттерн — `summary_builder._compute_weighted_bs_score:384 now=datetime.now()`; в v2 не
повторять). **Contact-local watermark:** explicit CLI `--as-of` приоритетнее; иначе
`resolve_contact_bs_as_of(user_id, contact_id, explicit)` = max persisted domain date строк данного
`(user_id,contact_id)`: `calls.call_datetime`, `promise_outcomes.evidence_date`, `promises.status_updated_at`,
затем `calls.created_at`. Live вызывает resolver после регистрации текущего звонка. Строки с
`source_date > as_of_date` исключаются ДО decay. Для остальных:

```text
r(age_days) = 2 ** (-max(age_days, 0) / 180)
```
180 = `graph/config.py RELATION_DECAY_DAYS` и Admiralty window (`db_reader.py:1090 '-180 days'`).

### 3.2 Provenance и дедуп
```text
normalize_text = NFKC → lowercase → ё→е → collapse whitespace → trim outer punctuation
normalized_entity_key = normalize(entity_type|canonical normalized_key)
fact_id = sha256(user_id|call_id|normalized_entity_key|fact_type|who|normalize_text(quote))[:16]
```
Fact без entity association → sentinel `__contact__` вместо NULL. Два разных entity key с одной цитатой —
разные facts.

Score-eligible fact: `who='OTHER'`, `len(quote.strip()) ≥ 8` code points, `quote_match ≥ 0.72`
(`graph/validator.py:23 MIN_MATCH_RATIO`), `confidence ≥ 0.6` (`graph/config.py MIN_FACT_CONFIDENCE`). После
гейта численное LLM-confidence — ни вес, ни credit. UNKNOWN контакту не присваивается. M12 маркирует
существующие строки `fact_id IS NOT NULL` → `graph_v1`, остальные → `legacy` (включая bs_evidence-события
bulk/backfill, §0.1 п.11); новый builder пишет `graph_v2`. Full replay заменяет только `graph_v1|graph_v2`.
Promise dedup — `(user_id,contact_id,promise_key)`; один source call ≤ одного nonbehavior confidence-credit.

Один grounding contract для fact, promise, M-support: raw candidate span после `strip` ≥8 code points;
`FactValidator._find_best_match` rolling ratio ≥0.72; найденный span после последнего `[s2]` до следующего
маркера → `OTHER`. `UNKNOWN`, `[me]`, transcript-less rows не score-eligible, но dated attempt сохраняется для
confidence denominator. `valid OTHER promise` = canonical `side=OTHER`, boolean `vague` присутствует, quote
проходит contract. Quote выбирается детерминированно: сначала grounded `structured_fact.fact_type=promise` с
`normalize_text(value)==normalize_text(what)`, иначе best rolling window для `what`; ties — earliest offset.
Найденный raw window → `promises.source_quote`, ratio → `quote_match`; unmatched promise сохраняется, но не
входит в P. M available только при structurally valid `bs_score` и ≥1 OTHER support: grounded `bs_evidence`
string, либо grounded structured fact `contradiction|vagueness|blame_shift|emotion_spike`, либо grounded promise
`vague=true`; bare `claim` и конкретное обещание M не поддерживают. v002 `bs_evidence` — строки без type/confidence
→ только span/role gates; один support, не score-сигнал.

### 3.3 Missing/zero
- Empty denominator → component missing, не 0.
- Валидное `vague=false`, kept/fulfilled, отсутствие discrepancy при opportunity → 0.
- `unknown/open`, invalid parse, ungrounded quote → missing.
- Ни одного component → `BS=0.0`, `confidence=1`, `no_evidence=true`.
- User-z-score никогда не baseline input. Raw feature missing → neutral context, direct weight 0.

## 4. Формула BS `v2_roc_observed_1` (= GPT90 §4, дословно)

### 4.1 Behavior `B`
Только обязательства контакта (`side='contact'`); `promise_outcomes` приоритетнее явного status.
```text
y(kept|fulfilled) = 0
y(broken)         = 1
y(late,d)         = 1 - 2 ** (-max(d or 3, 3) / 14)
g(det|explicit)   = 1
g(llm+grounded)   = 1/2
g(llm ungrounded) = 0
B = sum(r_i*g_i*y_i) / sum(r_i*g_i)
```
Source table: `promise_outcomes.status kept/late/broken` → выше; `unknown` missing. Timestamped system
`promises.status fulfilled→0, broken→1` (только при `status_updated_at IS NOT NULL AND status_method IN
('det','system','llm')`); `open` missing. `events.status resolved|expired` — missing без canonical outcome row.
LLM numeric `confidence` не меняет `g`. `3/14` — versioned continuity constants (`_LATE_GRACE_DAYS=2`,
фразы «неделя/две недели» в `contact_reliability`); `7/14/28` — offline sensitivity.

### 4.2 Grounded language `L`
Для call `j`: `c_j∈{0,1}` — валидное OTHER-contradiction (`producer='graph_v2'`, `fact_type='contradiction'`,
`who='OTHER'`, gates §3.2); opportunity `oC_j∈{0,1}` — валидный OTHER `claim|contradiction`. Promises: dedup
по `(call_id, normalize_text(what))`, `p_j = vague_valid_promises_j / all_valid_OTHER_promises_j`.
```text
C = sum(r_j*c_j) / sum(r_j*oC_j)
P = sum(r_j*p_j) / sum(r_j) over calls with >=1 valid OTHER promise
L = (3*aC*C + 1*aP*P) / (3*aC + 1*aP)
```
`a*=1` при nonempty denominator. `(3,1)/4` — two-rank ROC `contradiction > promise-local vagueness`. General
`vagueness/blame_shift/claim/emotion_spike`, hedge/specificity/formality/request_balance/tempo/emotion
palette/accommodation — materialized, direct weight 0.

### 4.3 Model self-score `M`
```text
M = sum(r_i * bs_score_i/100) / sum(r_i)
```
Available только при structurally valid `bs_score` и ≥1 grounded support (§3.2). Unsupported → missing.

### 4.4 Aggregation
```text
z = 11*aB + 5*aL + 2*aM
BS = 0.0                                      if z == 0
BS = round_half_up(100*(11*aB*B+5*aL*L+2*aM*M)/z, 1) otherwise
```
Weights `(11,5,2)/18` — ROC для порядка `behavior > grounded language > model self-score`. Available weights
перенормируются; missing behavior ≠ kept. Golden: `B=.50,L=.80,M=.90 → 62.8`; `B=missing,L=.9375,M=.80 → 89.8`;
all missing → `0.0, no_evidence=true`.

## 5. Confidence `c1_effective_evidence_1` (= GPT90 §5, дословно)

### 5.1 Typed evidence clusters
Candidate credit = tuple `(family,source_call_id,source_date,value,potential,qualified,P_i,R_i,V_i,tie_key)`;
`source_date<=as_of` иначе unavailable.

| class | potential / qualified | source date | `P_i` | `R_i` | `V_i` |
|---|---:|---:|---:|---:|---:|
| B deterministic outcome | `1 / 1` iff complete | `evidence_date` | 1 iff status/call/date valid | evidence-call `min(1-UNKNOWN_share, .7 if fragile)` | exact persisted transcript quote→1, else 0 |
| B grounded LLM outcome | `1/2 / 1/2` iff complete+grounded | `evidence_date` | 1 iff canonical status/prompt/call/date valid | evidence-call rule | recomputed quote match |
| B system status fallback | `1 / 1` iff timestamped | `status_updated_at` | 1 iff enum/writer/date valid | source-call rule if present, else 1 | auditable transition→1 |
| L source call | `5/11`; qualified `5/11` iff valid grounded C/P | call date | relevant fields valid→1 | source-call rule | min quote match among used C/P rows |
| M source call | `2/11`; qualified `2/11` iff valid score+support | call date | structurally valid→1 | source-call rule | max grounded-support quote match |

`parse_failed|output_truncated` → L potential `5/11`, qualified 0; `parsed_partial` пригоден лишь когда
используемые поля полны. Rejected quote / role→UNKNOWN / subthreshold confidence / ungrounded LLM outcome —
potential attempt + `rejection_reason`, qualified 0. Parsed call без BS opportunities → potential 0. Missing
outcome date → row исключается из N/E целиком, считается в `details.undated_excluded`; promise creation date
никогда не заменяет outcome date.

```text
q_x    = (P_x*R_x*V_x) ** (1/3)
N_call = max(r*p_L, r*p_M)
E_call = max(r*qualified_L*q_L, r*qualified_M*q_M)
N = sum_behavior(r_i*potential_i) + sum_source_calls(N_call)
E = sum_behavior(r_i*qualified_i*q_i) + sum_source_calls(E_call)
coverage = N/(N+3)
```
`3` = `contact_reliability` публикуется при `n>=3` (S-CODE-04). Sensitivity `K∈{2,3,5}`; смена K = новая
confidence version. Rejected L + qualified M → `N=5/11, E=2/11`.

### 5.2 Quality
```text
Q = E/N if N>0 else 0
```
`0.7 = 1-0.3` (`diarize/role_assigner.py UNKNOWN_SHARE_THRESHOLD=0.3`). `coverage*Q = E/(N+3)`. Clean→rejected
сохраняет N, уменьшает E; новый rejected attempt увеличивает N при прежнем E. Уверенная OWNER↔OTHER перестановка
без UNKNOWN — residual risk.

### 5.3 Agreement и stability
```text
A = 1-abs(B-L)   if aB and aL   else 0
S = 1-abs(BS_raw_early-BS_raw_late)
```
Флаги `aB/aL/aM` — availability, не truthiness. M в A не участвует. Split по clusters после future-filter;
ключ сортировки `(source_date, family_rank, stable_ref)`: behavior `family_rank=0, stable_ref=promise_key`
(UTF-8 bytes), call-level L/M `family_rank=1, stable_ref=source_call_id` (int); даты — canonical UTC ISO-8601.
Нечётный n → extra cluster в позднюю половину; unrounded `BS_raw`. S доступна только при `E≥2` в каждой половине;
иначе 0.

### 5.4 Итог и anchors
```text
C = clamp(round_half_up(1 + 99*coverage*Q*(1+A+S)/3), 1, 100)
```
Anchors: 30 — предварительное (agreeing B/L при Q=1,S=0 → display C30 при `E=2.28`, raw при `E=2.35135`; stable
one-line физически с E≥4 → C39); 60 — устойчивое (Q=A=S=1 → display 60 при `E=4.333…`; stable one-line →
C60 при `E=23.4`, raw `25.2857`); 90 — сильное (Q=A=S=1 → `E=25.2857…`).

| Clean `N=E` | C при A=0 | C при A=1 | S |
|---:|---:|---:|---|
| 0 | 1 | 1 | 0 |
| 1 | 9 | 18 | 0 |
| 3 | 18 | 34 | 0 |
| 10 | 52 | 77 | 1 |
| 100 | 65 | 97 | 1 |

| raw n | B-only | L-only (`5/11`) | M-only (`2/11`) |
|---:|---:|---:|---:|
| 0 | 1 | 1 | 1 |
| 1 | 9 | 5 | 3 |
| 3 | 18 | 11 | 6 |
| 10 | 52 | 41 | 13 |
| 100 | 65 | 63 | 58 |

Первый звонок без будущего outcome: max nonbehavior `E=5/11`, A=S=0 → **C≤5**. BS любой 0…100 показывается.
Duration, empty calls, post-gate LLM confidence credit не дают. Формула monotone по E при fixed Q/A/S.
`contact_age_estimates.confidence` задаёт продуктовый контракт `1…100` (малое = слабое основание);
`insufficient_evidence` T-15/T-23 отображается как `C<30 → мало данных`; пара BS/C остаётся видимой.

## 6. Схема БД и миграция старых значений — **M12** (`Migration(12, "bs_v2", _m012_bs_v2)`)

Одна запись в `db/migrations.py::ALL_MIGRATIONS`, синхронный `db/schema.sql`, синхронные
`graph/repository.py::_GRAPH_DDL` и `insight/repository.py::_SCHEMA` (для таблиц, которые они создают). 1…11 не
редактировать. `PRAGMA user_version` после применения = 12 (обновить `docs/ops/box-canary-checklist.md` §1 в R-42).

```sql
CREATE TABLE IF NOT EXISTS contact_bs_metrics (
  user_id TEXT NOT NULL,
  contact_id INTEGER NOT NULL,
  bs_index REAL NOT NULL CHECK(bs_index BETWEEN 0 AND 100),
  bs_confidence INTEGER NOT NULL CHECK(bs_confidence BETWEEN 1 AND 100),
  bs_formula_version TEXT NOT NULL,
  confidence_formula_version TEXT NOT NULL,
  behavior_score REAL CHECK(behavior_score BETWEEN 0 AND 1),
  linguistic_score REAL CHECK(linguistic_score BETWEEN 0 AND 1),
  model_score REAL CHECK(model_score BETWEEN 0 AND 1),
  potential_mass REAL NOT NULL CHECK(potential_mass >= 0),
  qualified_mass REAL NOT NULL CHECK(qualified_mass >= 0 AND qualified_mass <= potential_mass),
  quality_score REAL NOT NULL CHECK(quality_score BETWEEN 0 AND 1),
  agreement_score REAL NOT NULL CHECK(agreement_score BETWEEN 0 AND 1),
  stability_score REAL NOT NULL CHECK(stability_score BETWEEN 0 AND 1),
  no_evidence INTEGER NOT NULL CHECK(no_evidence IN (0,1)),
  details_json TEXT NOT NULL DEFAULT '{}',
  source_signature TEXT NOT NULL,
  callset_signature TEXT NOT NULL,
  computed_as_of TEXT NOT NULL,
  computed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, contact_id, bs_formula_version, confidence_formula_version),
  FOREIGN KEY(user_id, contact_id) REFERENCES contacts(user_id, contact_id)
);
CREATE INDEX IF NOT EXISTS idx_cbm_user_contact ON contact_bs_metrics(user_id, contact_id);

CREATE TABLE IF NOT EXISTS bs_legacy_snapshots (
  user_id TEXT NOT NULL,
  subject_kind TEXT NOT NULL CHECK(subject_kind IN ('entity','contact_fallback')),
  subject_key TEXT NOT NULL,
  contact_id INTEGER,
  bs_index REAL NOT NULL CHECK(bs_index BETWEEN 0 AND 100),
  bs_formula_version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, subject_kind, subject_key),
  CHECK(subject_kind='entity' OR contact_id IS NOT NULL),
  FOREIGN KEY(user_id, contact_id) REFERENCES contacts(user_id, contact_id)
);

CREATE TABLE IF NOT EXISTS relation_evidence (
  user_id TEXT NOT NULL,
  evidence_key TEXT NOT NULL,
  source_call_id INTEGER NOT NULL,
  raw_src_type TEXT NOT NULL,
  raw_src_key TEXT NOT NULL,
  raw_dst_type TEXT NOT NULL,
  raw_dst_key TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  source_date TEXT NOT NULL,
  producer TEXT NOT NULL CHECK(producer IN ('graph_v1','graph_v2')),
  PRIMARY KEY(user_id,evidence_key),
  FOREIGN KEY(source_call_id) REFERENCES calls(call_id)
);
CREATE INDEX IF NOT EXISTS idx_relev_key ON relation_evidence(user_id,raw_src_type,raw_src_key,raw_dst_type,raw_dst_key,relation_type);
CREATE INDEX IF NOT EXISTS idx_relev_call ON relation_evidence(user_id,source_call_id);
```

`details_json` frozen как `bs-details-1`; unavailable component → JSON `null`, наблюдённый ноль → `0.0`:
```json
{"schema":"bs-details-1","as_of":"YYYY-MM-DD",
 "components":{"behavior":null,"contradiction":null,"promise_vague":null,"language":null,"model":null},
 "available":{"behavior":false,"contradiction":false,"promise_vague":false,"language":false,"model":false},
 "confidence":{"potential_mass":0.0,"qualified_mass":0.0,"quality":0.0,"agreement":0.0,"stability":0.0,
               "k":3,"undated_excluded":0,"rejection_reasons":[]},
 "evidence_refs":[]}
```
`rejection_reasons`/`evidence_refs` — sorted stable ids (`B:promise_key`, `L:fact_id`, `M:call_id`).
`source_signature` = lowercase SHA-256 compact UTF-8 sorted-key JSON `bs-input-1` (user/contact/as_of, обе версии,
ordered preprocessed source rows); исключает `computed_at`, transient entity ids, UI-флаги.
`callset_signature` = SHA-256 compact sorted `bs-callset-1` tuples `(source_md5, domain_date)` всех same-contact
calls, видимых на `computed_as_of`, включая звонки без/с failed analysis. Reader пересчитывает read-only;
неравенство → `stale=true`; статусные переходы сами по себе stale не создают и не снимают.

M12 также (порядок внутри миграции строго такой):

1. `CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_user_contact ON contacts(user_id, contact_id)` — parent key
   для composite FK (PK `contacts.contact_id` одиночный, `schema.sql:14`).
2. `ALTER TABLE users ADD COLUMN purge_started_at TEXT` (§0.1 п.3).
3. Триггеры (стиль m009, `migrations.py:210-285`):
   - `trg_cbm_owner_ins/upd` BEFORE INSERT/UPDATE ON `contact_bs_metrics`: `RAISE(ABORT,'contact owner mismatch')`
     если `NOT EXISTS (SELECT 1 FROM contacts WHERE contact_id=NEW.contact_id AND user_id=NEW.user_id)` —
     работает и при `foreign_keys=OFF`;
   - `trg_bls_owner_ins` BEFORE INSERT ON `bs_legacy_snapshots` WHEN `NEW.contact_id IS NOT NULL`: тот же guard;
   - `trg_bls_immutable_upd` BEFORE UPDATE ON `bs_legacy_snapshots`: `RAISE(ABORT,'immutable legacy snapshot')`;
   - `trg_bls_immutable_del` BEFORE DELETE ON `bs_legacy_snapshots` **WHEN NOT EXISTS (SELECT 1 FROM users WHERE
     user_id=OLD.user_id AND purge_started_at IS NOT NULL)**: `RAISE(ABORT,'immutable legacy snapshot')`;
   - `trg_relev_owner_ins/upd` ON `relation_evidence`: same-owner `source_call_id` (`calls.user_id=NEW.user_id`).
   Единственная допустимая повторная операция над снапшотом — byte-neutral `INSERT OR IGNORE`.
4. `contacts.placeholder_key TEXT` + `CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_placeholder ON
   contacts(user_id, placeholder_key) WHERE placeholder_key IS NOT NULL`. Existing phone-less contacts
   (`phone_e164 IS NULL`, не `self:notes`) получают backfill: lexicographically first linked `calls.source_md5`
   → `md5-<lower>`, при отсутствии звонков → `contact-<contact_id>`. Placeholder никогда не merge'ится.
5. В порядке `(user_id, call_id)` для **всех** `calls.contact_id IS NULL`: `INSERT OR IGNORE` same-owner
   placeholder `md5-<lower source_md5>` → guarded `UPDATE calls SET contact_id=?` → `INSERT OR IGNORE`
   baseline-строка `contact_bs_metrics(v2_roc_observed_1/c1_effective_evidence_1, 0.0/1, no_evidence=1,
   source_signature=sig(empty), callset_signature=…)`. Включая `status='done'`; миграция не ждёт replay; rollback
   транзакции не оставляет orphan contact.
6. `promises`: `vague INTEGER CHECK(vague IN (0,1))`, `source_quote TEXT`, `quote_match REAL CHECK(quote_match
   BETWEEN 0 AND 1)`, `status_updated_at TEXT`, `status_method TEXT NOT NULL DEFAULT 'legacy' CHECK(status_method
   IN ('det','system','llm','legacy'))`.
7. `events`: `normalized_entity_key TEXT`, `quote_match REAL CHECK(quote_match BETWEEN 0 AND 1)`, `quote_verified
   INTEGER NOT NULL DEFAULT 0 CHECK(quote_verified IN (0,1))`, `producer TEXT NOT NULL DEFAULT 'legacy'
   CHECK(producer IN ('legacy','graph_v1','graph_v2'))`; затем `UPDATE events SET producer='graph_v1' WHERE
   fact_id IS NOT NULL` (в текущем коде `fact_id` пишет только `GraphBuilder`; `save_events`/bulk-events его не
   пишут — `repository.py:1204`, `enricher.py:42-131`). m003-колонки `fact_type/quote` переносятся в fresh
   `schema.sql` как есть.
8. `contact_summaries`: `bs_index REAL`, `bs_confidence INTEGER NOT NULL DEFAULT 1 CHECK(bs_confidence BETWEEN 1
   AND 100)`, `bs_formula_version TEXT NOT NULL DEFAULT 'legacy'`, `bs_confidence_version TEXT NOT NULL DEFAULT
   'legacy'`, `bs_as_of TEXT`; `avg_bs_score` — legacy M diagnostic, не перезаписывать.
9. `entity_metrics`: `bs_confidence INTEGER NOT NULL DEFAULT 1 CHECK(… BETWEEN 1 AND 100)`, `bs_confidence_version
   TEXT NOT NULL DEFAULT 'legacy'`, `bs_components_json TEXT NOT NULL DEFAULT '{}'`, `bs_source_signature TEXT NOT
   NULL DEFAULT ''`, `bs_as_of TEXT`, `bs_projection_status TEXT NOT NULL DEFAULT 'legacy' CHECK(… IN
   ('contact','unmapped','ambiguous','legacy'))`.
10. `bs_thresholds`: `bs_formula_version TEXT NOT NULL DEFAULT 'legacy'`, `policy_version TEXT NOT NULL DEFAULT
    'legacy'`.
11. `graph_replay_runs`: `run_signature TEXT`, `as_of TEXT`, `CREATE UNIQUE INDEX IF NOT EXISTS
    idx_replay_runs_sig ON graph_replay_runs(user_id, run_signature) WHERE run_signature IS NOT NULL`.
12. `relations`: `producer TEXT NOT NULL DEFAULT 'graph_v1' CHECK(producer IN ('graph_v1','graph_v2'))`,
    `source_signature TEXT NOT NULL DEFAULT ''`.
13. `relation_evidence` materialization из валидных stored v2 `analyses.raw_response.relations` в порядке
    `(call_id, array_index)`; `evidence_key = sha256(compact json [user_id, source_md5, relation_array_index,
    raw_src_type, raw_src_key, raw_dst_type, raw_dst_key, relation_type])`; invalid rows — в migration report
    (`log.warning` + счётчик), модель не вызывается.
14. Snapshot до первой v2 projection: `INSERT OR IGNORE INTO bs_legacy_snapshots` для каждого `entity_metrics`
    (`subject_kind='entity'`, `subject_key=entity_type|normalized_key`, `payload_json`=вся строка) и для каждого
    `contact_summaries` с `avg_bs_score` (`subject_kind='contact_fallback'`, `subject_key=str(contact_id)`,
    `bs_index=avg_bs_score`).
15. Guarded ALTER для graph/insight-таблиц, которых ещё нет (паттерн m004: `table_exists` → skip, не except).
16. Fresh `schema.sql` включает колонки m002/m003/m004 (`analyses.schema_version TEXT DEFAULT 'v1'`,
    `canonical_json TEXT DEFAULT ''`; `events.entity_id…intensity`; `entities.archived/merged_into_id/is_owner`)
    и все M12-колонки; `_GRAPH_DDL` и `insight/repository.py::_SCHEMA` создают тот же контракт независимо от
    порядка `init_db/apply_graph_schema/apply_insight_schema`.

Три имени: `v1_legacy_snapshot` (byte-exact historical), `v1_linear_repaired_1` (старый алгоритм на починенных
counters), `v2_roc_observed_1` (baseline). `bs-recompute --user USER --as-of DATE` строит versioned canonical rows,
затем projections. UI до backfill — legacy number + `C=1, мало данных`; first-contact initializer всегда создаёт
`0/1`. DDL целиком и type/default matrix фиксируются R-01.

## 7. Recompute, replay и GPU (= GPT90 §7; якоря актуализированы)

```text
stored analyses/events/promises/outcomes/features/transcripts
  → assemble_contact_bs_inputs(user, contact, as_of)          # insight/bs_snapshot.py + bs_inputs.py
  → compute_bs_v2(inputs) + compute_bs_confidence(inputs)     # insight/bs_index.py
  → UPSERT contact_bs_metrics + contact_summaries projection   # insight/bs_recompute.py
  → entity_contact_map projection → entity_metrics
```

Contact — единственный канон. После user-scoped map rebuild (`insight/person_link.py::build_entity_contact_map`):
`COUNT(DISTINCT contact_id)=1` → exact pair/version/signature, status `contact`; `=0` → `v1_linear_repaired_1`,
`C=1`, `unmapped`; `>1` → тот же compatibility score, `C=1`, `ambiguous` («лучший» контакт не выбирается).
Unique→ambiguous очищает contact projection. Numeric id equality нигде.

Compatibility scorer = точное продолжение `graph/aggregator.py:213-245 _bs_v1_linear` на починенных counters:
```text
safe_p = max(total_promises, 1); safe_c = max(total_calls, 1)
v1_raw = .40*(broken_promises/safe_p) + .20*min(contradictions/safe_c,1) + .15*min(vagueness_count/safe_c,1)
       + .15*min(blame_shift_count/safe_c,1) + .10*min(emotional_spikes/safe_c,1)
v1_linear_repaired_1 = min(100*v1_raw, 100)     # float, без нового rounding
```
`total_calls` = `COUNT(DISTINCT events.call_id)` по entity (v1-семантика). Golden: all 0→`0.0`; broken 1/promise
1/call 1→`40.0`; по одному каждого из пяти при denominators 1→`100.0`; broken=2/promises=1→`80.0`;
contradictions=2/call=1→`20.0`. `fulfilled_promises` сохраняется, в формулу не входит.

Единственный mutating facade (после R-20): `recompute_contact_bs_and_projections(conn, user_id, contact_id, as_of,
uow)` = R-18 canonical → R-19 summary → R-20 все uniquely mapped entity projections. Live/bulk/outcome
hook/autofit/replay не вызывают шаги по отдельности. Outcome counters: map rebuild → R-09 → facade.

- **Contact association:** `Repository.register_call_with_baseline(...)` (R-21) вызывается `ingest/ingester.py`
  и `bulk/loader.py`; один `uow_for(repo._get_conn())`; phone → `get_or_create_contact` по `(user_id,phone_e164)`;
  NULL phone → contact с `placeholder_key='md5-'+source_md5.lower()` (поиск только по `(user_id,placeholder_key)`);
  `create_call` + `INSERT OR IGNORE` baseline `0/1`. Card artifact key — canonical phone либо
  `unknown-<placeholder_key>`. Analysis success обогащает строку синхронно до delivery; analysis/scorer failure
  оставляет 0/1 (или прежнее), `calls.status='error'` через `Orchestrator._fail` (stage-qualified), transport
  запрещён; R-31 публикует только local minimal card.
- **Full `graph-replay --apply`:** только весь user scope; repair call_id → canonical payload → role-tagged
  transcript → удалить user rows `producer IN ('graph_v1','graph_v2')` → strict builder → map rebuild → R-09 →
  contact BS → summary → entity projection. Один UoW/SAVEPOINT. Schema helpers (`apply_graph_schema`,
  `apply_insight_schema`, `apply_risk_schema`, `apply_tiers_schema`) выполняются и коммитятся ДО `BEGIN` отдельной
  транзакцией; внутри UoW не вызываются. Pre-state hashes после успешного preflight. Любое исключение →
  rollback до pre-run hash. `--limit` — только preview на `:memory:` backup из query-only source с обязательным
  ROLLBACK; `--limit --apply` — config error до открытия БД (`cli/commands/graph.py:188`).
- **Protected set:** entity ids из `producer='legacy'` rows, `entity_profiles`, обе FK `entity_merges_log`
  (`canonical_id/duplicate_id`), обе стороны `entities.merged_into_id`; transitive closure. Byte-for-byte
  сохранение; builder переиспользует stable `(user,type,normalized_key)` без UPDATE core. Archived raw key →
  same-user acyclic `merged_into_id` chain → terminal canonical; cycle/cross-owner/missing terminal/duplicate
  protected key → fail до mutation. Run signature = hash(user, contact-as_of-map, ordered source signatures,
  formula versions) → UPSERT byte-neutral.
- **`resolve_contact_bs_as_of`** — один, для live/bulk/replay/autofit; значение вычисляется раз до scorer/UoW.
  `graph_replay_runs.as_of` = explicit либо max карты (audit only).
- **Relation decay без wall clock:** builder материализует каждую `raw_response.relations` строку один раз в
  `relation_evidence`; retry заменяет только graph_v2 ledger rows этого звонка, собирает old∪new keys,
  пересчитывает projection из ledger. `source_date=calls.call_datetime`, fallback `calls.created_at`. Anchor
  `t*=max(source_date)` ключа (explicit replay date → future rows исключены). После merge routing:
  `weight=math.fsum(conf_i*2**(-days(t*-source_date_i)/180))` по sorted `(source_date,source_md5,
  relation_array_index)`; `confidence=weight/math.fsum(decay_i)`; `call_count=COUNT(DISTINCT source_md5)`;
  `first/last_seen_call_id` — calls у min/max tuple; `created_at/updated_at` — first/anchor persisted datetimes.
  Equal-confidence age0/180 → weight `1.5`. Это заменяет `graph/repository.py:321 upsert_relation_with_decay`
  (wall-clock).
- `archetypes-fit/features-build` (`insight/cli_ops.py:42,75`): после persist `contact_features` вызывают facade
  для affected contacts. Watcher autofit (`pipeline/watcher.py:317`) — то же; first-call live path от autofit не
  зависит.
- `promise-outcomes`: synchronous `use_llm=False` refresh (R-23) возвращает changed keys/contacts; pipeline зовёт
  facade раз. Ошибка = обычная observable call error.
- CPU/SQLite only: BS-v2 не импортирует torch/pyannote/LLM. `_unload_models()` (T-12) не меняется. Phase B вводит
  stdlib cross-process exclusive lock `<data_dir>/locks/gpu-phase.lock` (`ops/gpu_lock.py`): watcher/orchestrator
  держит от первого ASR/pyannote load через unload до конца LLM-фазы; canary берёт nonblocking, fail-closed до
  `LLMClient.ensure_ready`.

## 8. Versioning (= GPT90 §8 с поправкой §0.1 п.2)

- `bs_formula_version='v2_roc_observed_1'`; `confidence_formula_version='c1_effective_evidence_1'`;
  `policy_version='bs_ui_fixed_1'`.
- `bs_read_version='baseline|legacy'` (`configs/features.yaml` + `config.py::FeaturesConfig`); R-17 добавляет
  safe default `legacy`, R-42 атомарно меняет на `baseline`. Flip = только reader route, 0 DB writes.
- Единственный `BSView(score, confidence, score_version, confidence_version, source ∈ canonical|legacy_snapshot|
  avg|zero, computed_as_of, stale)` (`insight/bs_policy.py`). Legacy route читает immutable snapshot / unchanged
  `avg_bs_score`; baseline — exact pair, затем те же read-only fallbacks. `legacy_snapshot|avg` → C1 + marker
  `предыдущий расчёт`; zero → 0/C1 + `нет пригодных данных`; canonical stale → `последний звонок не учтён`.
  Card/dossier/list/digest/Telegram/Admiralty/advice принимают только этот тип. Offline test доказывает
  `legacy→baseline→legacy→baseline` byte-equivalence.
- Formula change = новая versioned row + recompute; старые не перезаписываются.
- **`PROMPT_VERSION_ANALYZE='v002'` не меняется в Phase A.** `analyze_v003.txt` создаётся только в R-46, default-off;
  cache namespace через существующий `prompt_version` в `llm_cache.make_key`. Включение — после R-49.

## 9. UI contract (= GPT90 §9; якоря существующих поверхностей добавлены)

Канонический `bs_index` — half-up, один десятичный знак. `BS_display=0` только если stored `bs_index==0.0`; иначе
`BS_display=max(1, round_half_up(bs_index, 0))`. Bands/Admiralty/advice сравнивают integer. `0→0, 0.1→1, 0.4→1,
0.5→1, 50.4→50→C, 50.5→51→D`. `bs_confidence` integer, не округляется повторно.

### 9.1 Card ≤512 UTF-8 bytes (`deliver/card_generator.py`, `MAX_CARD_BYTES=512`)
Full и minimal card всегда содержат mandatory строку:
```text
bs: 52/100 · увер. 12/100 · мало данных
```
`мало данных` при C<30. Typed renderer (`deliver/card_render.py`, R-30) выбрасывает optional строки по фиксированному
приоритету, но никогда эту; считает UTF-8 bytes (`_truncate_bytes` :74-83 — паттерн). Суффиксы после `мало данных`
в порядке: legacy `· предыдущий расчёт`; zero `· нет пригодных данных`; stale canonical `· последний звонок не
учтён`. `grade:` остаётся (`_grade_line` :161-210 → R-29), `risk:` — `risk_band/risk_emoji` (T-19).
Publish — `artifacts.atomic_write_text` (уже). Штамп свежести — последняя строка (`_finalize_card` :225).

### 9.2 Admiralty (`insight/admiralty.py`)
Info digit (замена `info_grade(avg_confidence)`):
```text
C >= 90 → 2 «основание сильное» · C >= 60 → 3 «основание устойчивое» · C >= 30 → 4 «основание предварительное» · C < 30 → 6 «основание недостаточно»
```
`source!=canonical` или `stale=true` → F6 принудительно; stored pair видна рядом с marker. Letter: C<30→F; иначе
BS_display ≤25→B, ≤50→C, ≤75→D, >75→E. A = low BS (≤25) + `kept_ratio≥.8` + resolved `n≥5` (`_KEPT_RATIO_MIN`,
`_KEPT_N_MIN` — уже в admiralty.py) + C≥90. `SOURCE_PHRASES` заменяются точно:

| Letter | Exact phrase |
|---|---|
| A | `сохранённые обязательства выполнялись; расхождений мало` |
| B | `наблюдаемых расхождений мало` |
| C | `есть отдельные наблюдаемые расхождения` |
| D | `наблюдаемые расхождения повторялись` |
| E | `наблюдаемых расхождений много` |
| F | `основание недостаточно; индекс предварительный` |

Запрещены как свойства человека: `надёжен|ненадёжен|держит слово|не держит слово|честный|лжец` (текущие
`SOURCE_PHRASES` A/B/E и `contact_reliability` фразы «держит слово» — удаляются).

### 9.3 Dossier, digest, Telegram, advice, patterns
- Dossier (`dashboard/db_reader.py::get_person_dossier`, `app.js::renderDossier` :1149-1156): tiles `BS 52/100`,
  `Уверенность 12/100`, mandatory marker, tooltip §1.2, component/evidence drilldown без диагнозов и counters.
- People list (`get_people` :553, `app.js` :978-979): `BS 52 · C12` из `BSView` + marker.
- Digest/Telegram shared line (`deliver/bs_line.py`): `BS 52/100; увер. 12/100 — мало данных.`; legacy
  `Предыдущий расчёт.`, zero `Нет пригодных данных.`, stale `Последний звонок не учтён.`; ≤300 chars, без
  n/count/duration. Telegram `cmd_contact` (:483-484) — строки `Звонков:` и `BS: {avg_bs_score}` удаляются.
- Advice (`summary_builder._generate_advice` :510-531): `C<30 → Оценка предварительная`; иначе `BS_display=0 →
  Расхождений в пригодных данных не обнаружено`; `1≤BS_display≤50 → Наблюдались отдельные расхождения`;
  `BS_display>50 → Проверяй сроки и конкретику`; соединение только `; `, ≤300 символов. Удалить «Надёжный
  партнёр» (:529), «Осторожно: размытые обещания» (:518 — заменяется таблицей).
- Patterns (`psychology_profiler._extract_patterns` :219-262, `data_extractor.get_behavioral_patterns`, `labels_ru.py
  PATTERN_NAME/SEVERITY`): ключи сохраняются, labels → наблюдения: `promise_breaker → обещания не выполнены`,
  `contradictory → позиции расходились`, `vague_communicator → ответы были неконкретны`, `blame_shifter →
  переносил ответственность`, `emotionally_volatile → были эмоциональные всплески; на BS не влияет`, `reliable →
  наблюдаемых расхождений мало` только при C≥30, `SEVERITY.positive → положительное наблюдение`. Risk fallback
  `db_reader.py:296` `{"low":"Надёжный"}` → `сохранённый риск низкий|средний|высокий`. `contact_reliability`
  фразы → `исходы обязательств: выполнены/были просрочены/не выполнены/пока неизвестны`. Snapshot-тесты всего
  payload: regex `над[её]ж|ненад[её]ж|эмоционально\s+неустойчив|лжец|честн` → 0 совпадений.

## 10. Offline validation и acceptance mathematics (= GPT90 §10, frozen ADEMP; перенесено без изменений)

Synth latent `theta` — заложенная склонность к **наблюдаемым расхождениям**, не ложь; задаётся до и независимо от
scorer; generator не импортирует production scorer и не открывает SQLite/configured paths. Спецификация-зеркало —
`docs/research/bs-v2/synth-package/README.md` (создаёт R-37, байт-смысловая копия этого §10, не источник
параметров).

### 10.1 Frozen generator `bs_synth_dgp_2`
Ровно 100 seed'ов `seed_i=20260822+i`, `i=0…99`; 400 contacts `k=0…399`; master timeline 100 source calls
`j=0…99`. Байтовый контракт:
```text
utf8(x) = x encoded as UTF-8, no BOM/newline
perm_digest(seed,k) = SHA256(utf8("perm|{seed}|{k}"))
order = integers 0..399 sorted by (perm_digest(seed,k), k)
theta[order[rank]] = (rank+0.5)/400
digest(seed,k,call_key,tag) = SHA256(utf8("{seed}|{k}|{call_key}|{tag}"))
U(...) = uint64_be(digest(...)[0:8]) / 2**64
Bernoulli(p,...) = 1[U(...) < clamp(p,0,1)]
Normal(stem) = sqrt(-2*ln(max(U(tag=stem+":a"),2**-64))) * cos(2*pi*U(tag=stem+":b"))
```
`call_key` — `contact`, `s000…s099`, `e000…e099`; seed/contact без padding. Исчерпывающий tag registry (новый tag
= новая DGP version):

| call_key | tags |
|---|---|
| `contact` | `genre`, `affect` |
| every `sNNN` | `promise_opportunity`, `outcome_available`, `outcome_broken`, `outcome_late`, `late_days`, `outcome_method`, `claim_opportunity`, `contradiction`, `promise_vague`, `model_available`, `model_score:a`, `model_score:b`, `general_vagueness`, `blame_shift`, `specificity:a`, `specificity:b`, `emotion_spike`, `quality`, `shared_lm`, `role_swap`, `mnar:behavior`, `mnar:contradiction`, `mnar:vague_promise`, `mnar:model` |
| every materialized `eNNN` | `quality`, `role_swap` |

`as_of=2025-12-31`; `d_j = as_of - 2*(99-j) days`. Promise с available outcome получает resolver-only call `eNNN`
(`evidence_call_id="eNNN"`, date `d_j+30`, transcript); не входит в exposure `n`, не создаёт L/M opportunity,
виден только при date≤as_of (последние 15 source calls без будущего outcome). View `n∈{1,3,10,100}` = nested suffix
`s(100-n)…s099`; `n=0` пуст; n=1 никогда не видит будущий outcome.

Quotes: `alphahex(bytes)` — nibble `0…f` → `a…p`; quote = `цитата-` + первые 20 букв
`alphahex(SHA256(utf8("quote|{seed}|{contact}|{call_key}|{channel}")))` (без digit/date/money/time). Clean
role-tagged transcript содержит строку дословно → match `1.0`. Rejected quote: stored quote сохраняется,
transcript звонка заменяется на `[s2] жжжжжжжжжжжж`; generator пишет expected rejection; R-37 integration test
проверяет production matcher `<0.72`.

| Channel | Exact clean DGP |
|---|---|
| Promise opportunity | `O_B~Bernoulli(.35)`; один OTHER promise + promise-local opportunity |
| Outcome availability | if `O_B`, `O_out~Bernoulli(.70)`; иначе `unknown`; resolved row только с due `eNNN` |
| Outcome severity | `p_broken=.03+.67*theta`; если не broken, `p_late=.05+.30*theta`, иначе kept; late days `[3,7,14,28][floor(4*U)]`; method det if `U<.75` else grounded llm |
| Claim/contradiction | `O_C~Bernoulli(.70)`; contradiction `~Bernoulli(.02+.76*theta)` |
| Promise vagueness | if `O_B`, `vague~Bernoulli(.06+.62*theta)` |
| Model self-score | available iff `U<.88`; `M=clamp(.08+.82*theta+.14*Normal("model_score"),0,1)` + один supporting quote |
| Genre/style controls | contact `G~Bernoulli(.5)` независимо от theta; general vagueness `Bernoulli(.10+.50*G)`, blame shift `Bernoulli(.03+.30*G)`, specificity target `x=clamp(80-45*G+8*Normal("specificity"),0,100)`, stored `q=round_half_up(x,0)` через token construction ниже |
| Affect/context | `H~Bernoulli(.5)`; emotion spike `Bernoulli(.05+.35*H)`; zero-weight sentinels hedge/directive/question/lexical/formality/request_balance/accommodation = `.15+.50G/.20/.20/.50/.50/.50/.50`, tempo `120+20H`, risk `20+50H`, call_type `business` iff G else `personal`, один deep fact и один mention edge на контакт |

Raw record encoding: каждый structured fact = `{"fact_type":type,"who":"S2","confidence":.8,"polarity":0,
"intensity":.5,"quote":quote,"value":quote}` (поле `who` принимает только v003-парсер; v002-путь R-16 читает speaker
из transcript grounding); claim opportunity → ровно один `claim` или `contradiction`; promise opportunity →
`fact_type="promise"` + `promises[{who:"S2",what:quote,vague:<draw>}]`; general V/blame/emotion — свои typed
facts; available M → `bs_score=round_half_up(100*M,1)` + один `bs_evidence` string = OTHER quote; absent M →
null/[]; `risk_score=20+50H`; остальные обязательные v002-поля — sentinels. JSON compact UTF-8, sorted keys.

Specificity token corpus: ровно 100 whitespace-токенов OTHER-сегмента; `z` — число distinct zero-hit quote-токенов;
`q=round_half_up(x,0)`; append `floor(q/3)` копий `15:30-руб` (numeric+time+money = 3 hits); remainder 1 → `7`,
remainder 2 → `7руб`; остаток `100-z-floor(q/3)-I(q mod 3>0)` → `слово`. Role markers вне текста сегмента.
Production `compute_specificity` возвращает ровно `q` (включая 0 и 100); generator assert'ит token count 100, hit
count q, `Feature.value=q`.

Clean: valid parse, OTHER role, `unknown_share=0`, `role_fragile=false`, match 1. Default: call-local
`U(tag="quality")`: parser/resolver invalid if `U<.12`; attribution → UNKNOWN share `.5`/fragile if `U<.15`;
transcript mutation rejects all quotes if `U<.10` (nested common-mode shock). Attempted channel сохраняет potential;
parse/UNKNOWN/bad quote → qualified=0. Evidence-call quality → B; source-call quality → L/M.

Hostile paired strata (те же draws): 1 `clean` (quality probabilities 0); 2 `default` (`.12/.15/.10`); 3
`severe_detectable` (`.35/.45/.45`); 4 `shared_LM` (`shared_lm<.30` → contradiction/vague/M mean на `1-theta`);
5 `adversarial_M` (`.08+.82*(1-theta)+.05*Normal`); 6 `MNAR` (`p_drop=.05+.45*theta` по `mnar:*`, missing, не
rejected); 7 `genre_only`; 8 `undetectable_role_swap` (`role_swap<.30`, `unknown_share=0`); 9 `specificity_null`
(target `80-45*G`, Normal=0); 10 `specificity_signal` (`clamp(80-45*G-40*theta*O_B+8*Normal,0,100)`; slope 20/60,
divisor 2/8 — OAT, never selected).

Sensitivity OAT на **default, n=100**: каждая Bernoulli `p` → `clamp(p±.05)`; отдельно late half-life `7,28`,
recency `90,360`, K `2,5` против `14/180/3`. Без joint shifts. Всё публикуется, ничего не выбирается.

### 10.2 Estimands, tie rules, gates
- Deterministic expectation grid `theta=t/100`, `t=0…100`, clean n=100, exact visible resolver calls/recency,
  ratio-of-expected, uniform four-point late mean, expected C/P, unclipped M mean, unrounded формула → Kendall
  tau-b = `1.0` ровно.
- Primary stochastic recovery: **default, n=100, 400 contacts** на seed; tau-b между unrounded BS и theta; across
  100 seeds median ≥`.60`, nearest-rank p05 (sorted value #5) ≥`.50`. Clean n=100, mixed `n_k=[1,3,10,100][k mod 4]`
  и все clean/default n=1/3/10/100 — обязательные диагностики без sparse gate. Pilot dgp1 (mixed `.5219/.4847`,
  default `.4797/.4477`; n=100 clean `.8299/.8089`, default `.8168/.7923`) — provenance, не acceptance
  (`docs/research/bs/99-rounds.md`). Spearman diagnostic; ARI только для 4×4 predeclared quartiles.
- Paired clean→severe confidence: contact `k` → suffix `n_k`; per seed `median_contact(C_clean-C_severe)>0`; ties
  и отрицательные = failures; PASS при ≥63/100 (one-sided exact `Binomial(100,.5)` tail <.01). Clean panels:
  `median(C_n1)<median(C_n3)<median(C_n10)<median(C_n100)` для 100/100 seeds.
- ROC vs rank-sum на clean n=100: `RS=(3*aB*B+2*aL*L+1*aM*M)/(3*aB+2*aL+1*aM)`; loss 1 (opposite strict), 1/2 (one
  tie), 0 (match); both-tie excluded; pooled rate ≤`.10`; per-seed median/p95 и `.05/.15` публикуются.

Обязательные CI properties (R-39): (1) BS `[0,100]`, C `[1,100]`, round-half-up deterministic; (2) permutation
invariant; duplicate same-call nonbehavior facts не меняют score/C; (3) empty calls/duration/post-gate LLM
confidence не меняют C; `.59→.61` меняет eligibility, `.60…1.00` — нет; (4) new clean evidence не снижает C при
fixed A/S; clean→rejected не повышает C; (5) controlled degradation не повышает C; severe-noise median C < clean
(sign test p<.01); (6) same inputs+as_of → same details/signature; replay growth 0; (7) all-missing → `0/1`; first
valid call visible; (8) expectation grid tau=1; primary gates `.60/.50`; (9) discordance ≤10%; (10) two-user
identical quote: zero collisions/leaks. `100×400` и gates выбраны до pilot.

## 11. Фаза A — baseline (все задачи `unconditional`, offline, ≤1 рабочего дня каждая)

Ни одна задача A не зависит от реальной БД, бокса, owner feedback, `fact_feedback`, Phase B/C. Каждый slice: один
проверяемый результат, один primary test, полный suite зелёный (`python -m pytest -q`, `ruff check --select
F821,E9,F7,F63,F82 src tests`), память → commit → push (CLAUDE.md). Порядок исполнения — §16. Шаблон полей задач
— GPT90.

### R-01 — Additive schema M12
- **Результат:** fresh и upgraded DB дают один BS-v2 schema contract; `PRAGMA user_version=12`.
- **Файлы:** `src/callprofiler/db/migrations.py` (`_m012_bs_v2`, `Migration(12,"bs_v2",…)`), `src/callprofiler/db/
  schema.sql`, `src/callprofiler/graph/repository.py::_GRAPH_DDL`, `src/callprofiler/insight/repository.py::_SCHEMA`,
  `src/callprofiler/db/repository.py::purge_user` (первый оператор: `UPDATE users SET purge_started_at=datetime('now')
  WHERE user_id=?`; `CHILD_RULES` не меняются — все новые таблицы имеют `user_id`).
- **Как:** ровно §6 п.1–16 в указанном порядке через `_add_columns_if_missing`/`table_exists` (`migrations.py:47,124`);
  `executescript` для DDL/триггеров; placeholder/NULL-call backfill и snapshot — обычными параметризованными
  statement'ами внутри той же migration-транзакции (`apply_migrations` уже оборачивает и откатывает,
  `test_failed_migration_rolls_back_and_does_not_advance_user_version`).
- **Почему:** S-CODE-03/S-CONST; §0.1 п.1/3/10.
- **Данные:** synthetic old-schema SQLite (`tests/test_db_migrations.py` legacy-fixtures :187-220 как образец) +
  fresh `schema.sql`; фикстура с контактом без phone, звонком с `contact_id=NULL`, `entity_metrics`-строкой,
  `contact_summaries.avg_bs_score>0`, v2 `raw_response.relations` (valid + invalid), снапшотом и второй user.
- **Тир:** T2.
- **Зависимости:** нет.
- **Тест:** `tests/test_db_migrations.py::test_migration_12_bs_v2_full_contract`.
- **Критерий:** `init_db→apply_graph_schema→apply_insight_schema`, `apply_graph_schema→init_db→apply_insight_schema`
  и fresh дают identical `sqlite_master` dump (нормализованный whitespace); journal ids 1…12; повторный прогон — 0
  DDL; cross-owner insert/update в `contact_bs_metrics`/`bs_legacy_snapshots`/`relation_evidence` → abort; snapshot
  UPDATE всегда abort; snapshot DELETE abort при `purge_started_at IS NULL` и проходит после `UPDATE users SET
  purge_started_at`; `purge_user(apply=True)` на user со снапшотом завершается без исключения и
  `test_purge_user_introspection_classifies_all_tables` зелёный; `INSERT OR IGNORE` снапшота byte-exact; `fact_id!=NULL`
  → graph_v1, остальные legacy; v1 payload snapshot exact; две строки одной BS-version с разными confidence-version
  сосуществуют; NULL-contact done-call → same-owner `md5-<source_md5>` contact + одна `0/1` строка без replay;
  relation ledger exact ordered, invalid relation в отчёте; injected failure → pre-state exact.
- **Rollback:** readers legacy; additive columns/tables не удалять.

### R-02 — Tenant-scoped graph identity API
- **Результат:** каждый identity-based read требует `user_id`.
- **Файлы:** `graph/repository.py::get_entity(:286)/get_entity_metrics(:495)` → `(self, entity_id, user_id)`;
  `graph/aggregator.py::full_recalc_from_events(:100)` → `(entity_id, user_id)`; `biography/data_extractor.py::
  get_behavioral_patterns(:191)` → `(entity_id, user_id, conn)`; все callsites (`cli/commands/graph.py`,
  `dashboard/db_reader.py`, `biography/psychology_profiler.py`, `graph/resolver.py::_fetch_metrics(:158)`).
- **Как:** SQL только `WHERE user_id=? AND id=?`; без compatibility default; inventory-тест по образцу
  `tests/test_tenant_ownership.py::test_inventory_no_public_mutator_with_bare_tenant_id` (:48-67) распространяется
  на `GraphRepository` и `EntityMetricsAggregator`.
- **Тир:** T2. **Зависимости:** R-01.
- **Тест:** `tests/test_tenant_ownership.py::test_graph_repository_identity_reads_require_user` (`@pytest.mark.tenant`).
- **Критерий:** wrong-user reads = None/0; вызов без `user_id` → `TypeError`; inventory violations == [].
- **Rollback:** v2 consumers off; tightening остаётся.

### R-03 — Replay PK blocker
- **Файлы:** `graph/replay.py:61-72`.
- **Как:** `SELECT call_id FROM calls WHERE user_id=? AND call_id IN (SELECT DISTINCT call_id FROM analyses WHERE
  schema_version='v2')` — `calls.id` нигде; комментарий :55-60 о correlated subquery сохранить (analyses без user_id).
- **Тир:** T2. **Зависимости:** R-01.
- **Тест:** `tests/test_graph_replay.py::test_replay_runs_against_calls_call_id`.
- **Критерий:** нет `OperationalError`; rows второго user unchanged exactly (существующие тесты :58-217 зелёные).

### R-04 — Canonical analysis payload reader
- **Файлы:** новый `src/callprofiler/analyze/payload_reader.py` (`load_analysis_payload(conn, call_id) ->
  (dict|None, reason ∈ canonical|raw|invalid)`), `graph/builder.py:88-135`, `graph/replay.py:117-121`.
- **Как:** SELECT включает `a.canonical_json`; parse canonical nonempty object first, raw fallback; replay
  preliminary validation (`json.loads(raw_response_str)`) заменяется тем же helper. `canonical_json` пишет
  `response_parser.py:383` / `repository.save_analysis:957-963` — не менять.
- **Тир:** T1. **Зависимости:** R-03.
- **Тест:** `tests/test_graph.py::test_builder_prefers_canonical_json_and_falls_back_raw`.
- **Критерий:** 3 fixtures → canonical/raw/invalid; invalid → 0 facts, `False`.

### R-05 — Shared role-tagged transcript path
- **Файлы:** новый `src/callprofiler/analyze/transcript_format.py::format_role_tagged(segments: Iterable[dict|Segment])
  -> str` (`[me] text\n[s2] text\n[?] text`, ordered by `start_ms`; `OWNER→[me]`, `OTHER→[s2]`, иначе `[?]`);
  заменяет `pipeline/orchestrator.py:85 _format_transcript`, `bulk/enricher.py:168 _format_transcript`, bare-load в
  `graph/builder.py:107-119` (builder грузит `transcripts` сам через helper, если `transcript_text is None`),
  `graph/replay.py:123-131`, `cli/commands/graph.py:33-39` (`seg.text`→dict-доступ через helper).
- **Почему:** §0.1 п.4; `FactValidator._detect_speaker_context` требует маркеры.
- **Тир:** T2. **Зависимости:** R-04.
- **Тест:** `tests/test_bs_event_provenance.py::test_all_builder_paths_use_same_role_tagged_transcript`.
- **Критерий:** captured `transcript_text` SHA-256 одинаков в live (`_analyze_call`)/bulk (`_update_graph`)/replay/
  backfill; `None` count = 0 для calls с segments; существующий `tests/test_graph_builder_transcript_gate.py` зелёный.

### R-06 — Complete fact provenance row
- **Файлы:** `graph/validator.py` (возвращает `match_ratio`), `graph/builder.py:193-245`, `graph/repository.py::
  upsert_fact(:379-415)`, `graph/config.py` (`MIN_QUOTE_LENGTH=8` — было 5; `BS_FORMULA_VERSION` не трогать).
- **Как:** builder использует `validation["speaker"]` (`me→OWNER`, `s2→OTHER`, иначе `UNKNOWN`); `upsert_fact`
  пишет `fact_type, who, normalized_entity_key, quote_match, quote_verified=1, producer='graph_v2'`;
  `event_type=COALESCE(allowed fact type,'fact')` (CHECK `schema.sql:117-119`); `fact_id` по §3.2 (entity sentinel
  `__contact__`); partial unique `idx_events_factid` остаётся.
- **Тир:** T2. **Зависимости:** R-01/R-02/R-05.
- **Тест:** `tests/test_bs_event_provenance.py::test_fact_row_persists_type_who_match_and_stable_key`.
- **Критерий:** exact row `fact_type='vagueness', who='OTHER', quote_match=1.0, quote_verified=1,
  producer='graph_v2'`; ids stable при реаллокации `entities.id`; distinct по call/user; ratio<.72 → 0 inserts;
  7-символьная цитата → reject; `tests/test_graph.py::test_builder_filters_short_quote_facts` обновлён на 8.

### R-07 — Coalesced structured counters
- **Файлы:** `graph/repository.py::count_facts_by_type(:503)`, `graph/aggregator.py::_recalc_one(:39)`,
  `full_recalc_from_events(:93-115)`.
- **Как:** `GROUP BY COALESCE(fact_type, event_type)`; в BS-facing counters (`contradictions, vagueness_count,
  blame_shift_count`) — только `who='OTHER'`; `emotional_spikes` — context (все who); `claim` — только opportunity
  (новый ключ в возвращаемом dict, в `entity_metrics` не пишется).
- **Тир:** T2. **Зависимости:** R-06.
- **Тест:** `tests/test_graph.py::test_fact_counters_use_coalesced_fact_type`.
- **Критерий:** по одной строке promise/contradiction/emotion/vagueness/blame/claim + legacy `fact_type NULL,
  event_type='contradiction'` → каждый count == 1, legacy contradiction остаётся 1; OWNER/UNKNOWN numerators 0.

### R-08 — Promise role and vague contract
- **Файлы:** `db/repository.py::save_promises(:1144-1186)` и `save_batch`, `insight/promise_outcomes.py::_side(:87)`,
  `graph/validator.py` (reuse matcher), `analyze/response_parser.py` (`promises[].vague` bool сохраняется, regex-путь
  :322-340 тоже), `deliver/digest.py::_side(:79)`, `bulk/enricher.py:57-66` (та же функция нормализации).
- **Как:** `analyze/roles.py::canonical_who(raw) -> 'OWNER'|'OTHER'|'UNKNOWN'` (`Me|me→OWNER`, `S2|s2→OTHER`,
  уже канонические — как есть, прочее UNKNOWN); `save_promises` пишет `who=canonical_who(...)`, `vague` (0/1/NULL),
  `source_quote`, `quote_match` по §3.2 (сигнатура получает `transcript_text: str | None`); T-16 dedup
  `(user_id,call_id,who,what)` сохраняется (по canonical who); unmatched остаётся, не P-eligible; будущий system
  status writer ставит `status_updated_at,status_method`; промпт не меняется.
- **Тир:** T2. **Зависимости:** R-01/R-05.
- **Тест:** `tests/insight/test_promise_outcomes.py::test_live_me_s2_promises_preserve_vague_and_enter_outcomes`.
- **Критерий:** S2 grounded row → `who='OTHER'`, exact vague, earliest tied window, match ≥.72; Me/wrong-role/
  unmatched/missing-vague → opportunities 0, rows persist; 7 chars rejected; full и regex-парсер согласны; cross-user
  rows 0; существующие `test_det_*`, `test_unknown_speaker_ignored` зелёные.

### R-09 — Outcome provenance and counter projection
- **Файлы:** `graph/repository.py` (новый `promise_outcome_counts(user_id, entity_id) -> dict`), `graph/aggregator.py`,
  `insight/promise_outcomes.py` (query helper).
- **Как:** dedup `(user_id,contact_id,promise_key)` до map-join; prefer `promise_outcomes` (требуются persisted
  `evidence_call_id/evidence_date/evidence_quote` для det/LLM — writer :295-301 уже пишет); fallback — только
  timestamped system status (`promises.status_updated_at IS NOT NULL`); contact side only; kept→fulfilled,
  broken→broken, late→fulfilled+overdue, unknown/undated→ни то ни другое; join через user-scoped
  `entity_contact_map`; `entity_metrics.fulfilled/broken/overdue_promises` пишутся отсюда (аггрегатор больше не ждёт
  `broken_promise`-событий).
- **Тир:** T2. **Зависимости:** R-07/R-08.
- **Тест:** `tests/test_graph.py::test_promise_outcomes_feed_existing_promise_counters`.
- **Критерий:** fixture → fulfilled=2, broken=1, overdue=1, total unique=4; второй прогон идентичен.

### R-10 — Producer-safe replay preservation set
- **Файлы:** `graph/replay.py:75-81` (DELETE only `producer IN ('graph_v1','graph_v2')` в events; `entities` —
  только unprotected), `graph/repository.py`, `graph/resolver.py` (terminal canonical через `merged_into_id`),
  `cli/commands/graph.py::cmd_entity_unmerge(:295)`.
- **Как:** §7 protected set/closure; никогда не blank/delete `legacy`; builder не UPDATE'ит protected core; archived
  raw key → acyclic same-user chain; cycle/cross-owner/missing terminal/duplicate key → fail до mutation под
  `foreign_keys=ON`.
- **Тир:** T2. **Зависимости:** R-03/R-06/R-09.
- **Тест:** `tests/test_graph_replay.py::test_replay_replaces_only_graph_producer_without_row_growth`.
- **Критерий:** две замены — graph row count/hash identical; legacy event, merge-component entities, profiles,
  merge-log byte snapshots identical; facts archived duplicate → terminal canonical 100%; unmerge в rolled-back clone
  видит reversible snapshot; каждый cycle/cross-owner/ambiguous fixture падает с pre-hash exact; other user identical.

### R-11 — Replay target-plan semantics
- **Файлы:** `graph/replay.py`, `graph/builder.py`, `graph/repository.py::upsert_relation_with_decay(:321)` →
  ledger-based projection, новый `src/callprofiler/insight/bs_recompute.py` (только `resolve_contact_bs_as_of`),
  `cli/commands/graph.py::cmd_graph_replay(:188)`, `cli/main.py` (argparse `--apply`), `cli/utils.py`.
- **Как:** `--apply` парсится; `--limit --apply` → config error до `load_config_and_repo`; preview: source
  `ConnectionFactory.reader()` (query_only, `db/connection.py:59-70`) → `sqlite3.Connection.backup` в `:memory:` →
  compatibility DDL + SAVEPOINT + ROLLBACK только на клоне; build target plan до mutation; contact-local as-of map
  один раз; relation upsert → per-call ledger replacement + §7 projection; `processed` увеличивается только на True.
- **Тир:** T2. **Зависимости:** R-10.
- **Тест:** `tests/test_graph_replay.py::test_replay_control_path_is_atomic_and_limit_safe`.
- **Критерий:** `--limit 2` при one invalid → processed=1; pre-M12 `sqlite_master`, journal, data, DB/FS hashes
  before=after; `--limit 2 --apply` exits до открытия БД; explicit/derived as_of maps повторяются под двумя wall
  clocks; новый звонок A меняет строки B 0; оба порядка live == replay hashes; age0/180 → weight 1.5;
  retry/changed analysis → один evidence key set, пересчёт old∪new; reversal builder order → 0 byte diff.

### R-12 — Strict atomic full-user replay
- **Файлы:** `graph/replay.py`, `graph/builder.py` (`strict=True` поднимает per-fact ошибки вместо `log.exception`
  :84-86,158,188,238), `graph/aggregator.py:31-36` (strict), `graph/repository.py`, `insight/person_link.py`,
  `insight/mentions.py`, `insight/repository.py::apply_insight_schema` (параметр `commit: bool=True`), `db/uow.py`.
- **Как:** preflight (`apply_graph_schema`, `apply_insight_schema`, `apply_risk_schema`, `apply_tiers_schema`)
  выполняется и коммитится ДО `BEGIN`; внутри UoW helpers получают `ensure_schema=False, commit=False`
  (`commit_unless_uow` везде, голых `conn.commit()` в `replay.py:73,81`, `person_link`, `mentions`,
  `save_replay_run` — нет); capture pre-state после preflight; один outer `uow_for`: target → R-10 replacement → all
  calls → derived graph → map → mentions → audit/replay-run → invariant checks → commit; replay-run UPSERT по
  signature. Protected rows не входят в delete/update.
- **Тир:** T3. **Зависимости:** R-04/R-10/R-11.
- **Тест:** `tests/test_graph_replay.py::test_full_replay_failure_is_atomic`.
- **Критерий:** preflight failure → graph/data 0 изменений; faults после call3/map/mentions/replay-run → byte-equal
  pre/post hashes graph/map/mentions/replay-run; success → graph_v1=0, expected graph_v2 hash; два success runs —
  same counts/signatures, row growth 0 включая `graph_replay_runs`; protected и second-user snapshots exact.

### R-13 — Pure BS function
- **Файлы:** новый `src/callprofiler/insight/bs_index.py` (dataclasses/constants; `BS_FORMULA_VERSION_V2=
  'v2_roc_observed_1'`, weights как `Fraction(11,18)` etc., `round_half_up` через `decimal.ROUND_HALF_UP`).
- **Как:** `compute_bs_v2(B: float|None, L_C: float|None, L_P: float|None, M: float|None) -> BSResult(value,
  components, version, no_evidence)`; никаких clock/DB/config.
- **Тир:** T2. **Зависимости:** R-01 (по порядку), функционально независима.
- **Тест:** `tests/test_bs_v2_formula.py::test_v2_roc_observed_exact_examples`.
- **Критерий:** `62.8`, `89.8`, `0.0`; 10 000 generated vectors bounded/deterministic.

### R-14 — Pure confidence function
- **Файлы:** `insight/bs_index.py` (`compute_bs_confidence(clusters, as_of, k=3) -> ConfidenceResult`).
- **Как:** §5 exact: typed clusters, potential N, qualified/geomean E, Q=E/N, A (B vs L), chronological split с
  ключом §5.3, call-level `max` отдельно для N и E, clamp 1…100, undated → `N=E=0` + `undated_excluded`, явные
  availability flags.
- **Тир:** T2. **Зависимости:** R-13.
- **Тест:** `tests/test_bs_v2_confidence.py::test_c1_exact_curve_and_quality_gates`.
- **Критерий:** clean A0 `1/9/18/52/65`, A1 `1/18/34/77/97`; raw-n таблица §5.4; all-missing C1; first-call L
  ceiling C5; future excluded; clean→rejected не повышает; available zero ≠ missing; rejected-L+qualified-M →
  `N=5/11,E=2/11`; undated → только audit counter.

### R-15 — Raw contact evidence snapshot
- **Файлы:** новый `src/callprofiler/insight/bs_snapshot.py::snapshot_contact_evidence(conn, user_id, contact_id,
  as_of) -> dict` (read-only), `db/repository.py`, `graph/repository.py`.
- **Как:** exact queries: `analyses` (через `calls.user_id`), `calls`, `transcripts`, `promises` (+M12 поля),
  `events` (`producer`, `fact_type`, `who`, `quote_match`), `promise_outcomes`, `contact_features`, `deep_facts`,
  `mention_edges`; каждый join связывает user ids; `source_date<=as_of`; missing/provenance сохраняются;
  deterministic order `(source_date, table_rank, pk)`. C-candidates: только `producer='graph_v2' AND
  fact_type='contradiction' AND who='OTHER'`; `producer='legacy'` contradiction-события (bs_evidence bulk-пути)
  попадают в snapshot как `legacy_context`, не как C.
- **Тир:** T2. **Зависимости:** R-01/R-06/R-08/R-09.
- **Тест:** `tests/test_bs_v2_inputs.py::test_raw_contact_evidence_snapshot_is_complete_and_scoped`.
- **Критерий:** golden ordered JSON exact; 0 future rows; other-user fields 0; каждый запрос содержит user predicate
  (assert по `sqlite3.set_trace_callback`).

### R-16 — Pure contact input assembler
- **Файлы:** новый `src/callprofiler/insight/bs_inputs.py::assemble_contact_bs_inputs(snapshot) -> BSInputs`.
- **Как:** snapshot → B/L/M opportunities + potential/qualified clusters §3–5; outcome/promise dedup; один §3.2
  grounding gate для facts/promises/v002 `bs_evidence`; call-level P; M support только из enumerated типов/спанов;
  continuous UNKNOWN share; rejected attempts с reason; все weight-0 сигналы — в typed context; без SQL/clock/config.
- **Тир:** T2. **Зависимости:** R-13/R-14/R-15.
- **Тест:** `tests/test_bs_v2_inputs.py::test_contact_input_vector_from_all_existing_signals`.
- **Критерий:** golden typed JSON exact; empty/duration/post-gate confidence → hash неизменен; `.59→.61` меняет
  eligibility, `.60…1.00` нет; future excluded; undated outcome → `N=E=0` + один audit count; 7/8 chars, `.71/.72`,
  me/s2/UNKNOWN, bare-claim boundaries exact; v002 `bs_evidence` поддерживает только M; general V/D/style weight 0.

### R-17 — Phase-A baseline/legacy reader router
- **Файлы:** новый `src/callprofiler/insight/bs_policy.py` (`BSView`, `read_bs_view(conn, user_id, contact_id,
  config) -> BSView`), `src/callprofiler/config.py::FeaturesConfig.bs_read_version: str = "legacy"` (+ `load_config`
  чтение, валидация enum → `ConfigError`), `configs/features.yaml` (`bs_read_version: legacy` с комментарием),
  readers (`db/repository.py`, `graph/repository.py`).
- **Как:** baseline читает exact pair `(v2_roc_observed_1, c1_effective_evidence_1)`, затем §8 zero-write fallbacks;
  legacy читает stable-key snapshot, иначе `avg_bs_score`; canonical сравнивает stored/current `bs-callset-1` →
  `stale`; flips read-only.
- **Тир:** T2. **Зависимости:** R-01/R-13/R-14.
- **Тест:** `tests/test_bs_policy.py::test_phase_a_router_round_trip_preserves_legacy_and_baseline_bytes`.
- **Критерий:** `legacy→baseline→legacy→baseline` byte-equal; stable key переживает id realloc; flips = 0 writes;
  выбор только по полной паре версий; legacy-only/no-value под baseline → `legacy_snapshot|avg` C1
  `предыдущий расчёт` / zero C1 `нет пригодных данных` без INSERT; failed call → только `stale=true`; successful
  recompute снимает stale; 100% downstream fixtures используют один тип.

### R-18 — Canonical contact recompute
- **Файлы:** `insight/bs_recompute.py::recompute_contact_canonical(conn, user_id, contact_id, as_of) -> Signature`,
  `insight/repository.py` (UPSERT).
- **Как:** snapshot → assemble → pure compute → canonical JSON sorted → `source_signature`; UoW UPSERT
  `contact_bs_metrics` по `(user, contact, both versions)` + текущий `callset_signature`; без projections; при
  равной signature — 0 UPDATE (`computed_at` не меняется).
- **Тир:** T2. **Зависимости:** R-16/R-17.
- **Тест:** `tests/test_bs_recompute.py::test_contact_canonical_row_and_projections_are_idempotent`.
- **Критерий:** ровно 1 строка версии; contradiction fixture BS>0; второй run — 0 rows/`computed_at` изменений;
  `bs-details-1` null-vs-zero exact; signature не зависит от UI/read flags, меняется от source/version.

### R-19 — Contact-summary compatibility projection
- **Файлы:** `aggregate/summary_builder.py::rebuild_contact(:98)` (читает projection, не считает), `insight/
  bs_recompute.py`.
- **Как:** после R-18 success — user/contact UPSERT `contact_summaries.bs_index/bs_confidence/bs_formula_version/
  bs_confidence_version/bs_as_of`; signature skip; `avg_bs_score` и `_compute_weighted_bs_score` не трогаются;
  router решает, что рендерить.
- **Тир:** T2. **Зависимости:** R-18.
- **Тест:** `tests/test_bs_recompute.py::test_contact_summary_projection_preserves_legacy_average`.
- **Критерий:** pair/version exact; `avg_bs_score` byte-identical; injected failure откатывает только projection.

### R-20 — Deterministic entity compatibility projection
- **Файлы:** `insight/bs_recompute.py` (`recompute_contact_bs_and_projections` facade + `v1_linear_repaired_1`),
  `graph/repository.py::upsert_entity_metrics(:443)` (новые колонки), `insight/person_link.py`.
- **Как:** §7 states; unique → canonical copy (`bs_index/bs_confidence/versions/components/signature/as_of/
  status='contact'`); 0/>1 → compatibility score, C1, `unmapped|ambiguous`; unique→ambiguous очищает v2 payload;
  ids не сравниваются численно; оба aggregator-пути (`_recalc_one`, `full_recalc_from_events`) зовут одну функцию
  `_bs_v1_linear`.
- **Тир:** T2. **Зависимости:** R-02/R-07/R-09/R-18.
- **Тест:** `tests/test_bs_recompute.py::test_entity_projection_requires_unique_tenant_map`.
- **Критерий:** §7 statuses; goldens `0/40/80/100/20`; оба пути — identical unrounded floats; facade order
  canonical→summary→entity ровно раз; 1→1 и 2→1 signatures exact; ambiguous копирует 0 contact rows; id permutation
  → 0 payload byte changes.

### R-21 — First-call identity/materialization gate
- **Файлы:** `db/repository.py::register_call_with_baseline(user_id, *, phone_e164, display_name, direction,
  call_datetime, source_filename, source_md5, audio_path, call_type) -> (contact_id, call_id, created: bool)`;
  `ingest/ingester.py:117-160` (вызов после `_copy_original`; раздельные `get_or_create_contact`/`create_call`
  удаляются); `bulk/loader.py:185-206` (после parse/MD5, до `save_transcripts`); `pipeline/orchestrator.py::
  _analyze_call(:1058-1098)` (после UoW анализа — facade R-20 синхронно, ДО `_deliver_call`; `apply_graph_schema`
  вынесен из UoW в `Orchestrator.__init__`-preflight); `graph/repository.py` relation decay (ledger);
  `insight/bs_recompute.py`.
- **Как:** один `uow_for`: phone → `(user_id,phone_e164)`; NULL phone → `placeholder_key`; `create_call`; `INSERT OR
  IGNORE` baseline 0/1; ошибка любого шага → 0 новых contact/call/metric rows; existing NULL-contact call
  связывается в том же UoW; retry/dedup (`idx_calls_user_md5`) возвращает ту же тройку. `resolve_contact_bs_as_of`
  один раз; analysis/parse failure оставляет 0/1 (или прежнее) — `_fail` ставит `error`, transport подавлен до
  R-31; scorer exception → `_fail(stage='bs')`, прежняя canonical row не тронута → R-17 `stale=true`.
- **Тир:** T2. **Зависимости:** R-05/R-11/R-18/R-19/R-20.
- **Тест:** `tests/test_pipeline.py::test_first_call_has_both_indices_before_delivery`.
- **Критерий:** 10/10 кейсов (normal contradiction, short, parse_failed, LLM raises, no analysis, scorer raises,
  role_fragile, preexisting `contact_id=NULL`, phone-less new/existing, retry) — pair до любого delivery;
  formerly-null call → один same-owner placeholder; contradiction BS>0; injected failure после каждого DB statement →
  0 partial rows; scorer-after-initializer failure → тот же contact/row/artifact + 0/1 + observable error; ingester
  и bulk зовут helper ровно раз, split writers 0; transport calls 0 до typed pair/error; оба порядка обработки и
  replay → identical logical BS/relation hashes; interleaved A не меняет B; model calls 0.

### R-22 — Bulk/backfill convergence
- **Файлы:** `bulk/enricher.py::_update_graph(:262)` и `_flush_batch`, `cli/commands/graph.py::cmd_graph_backfill(:13)`,
  `insight/bs_recompute.py`.
- **Как:** после каждого успешного graph update — facade R-20 раз с тем же role transcript/as_of; `apply_graph_schema`
  вне UoW; bs_evidence-события bulk-пути (`_extract_events_from_analysis:105-131`) остаются `producer='legacy'` и
  не влияют на C; live их не начинает писать.
- **Тир:** T2. **Зависимости:** R-05/R-18/R-19/R-20/R-21.
- **Тест:** `tests/test_bulk_enricher.py::test_bulk_and_backfill_match_live_bs_signature`.
- **Критерий:** live/bulk/backfill pair/components/signature byte-equal; invalid payload → 0 canonical changes;
  model calls 0; `tests/test_bulk_enrich_readiness.py` зелёный.

### R-23 — Scoped deterministic outcome refresh
- **Файлы:** `insight/promise_outcomes.py` (новый `refresh_outcomes_scoped(conn, user_id, *, contact_id=None,
  call_id=None) -> list[tuple[promise_key, contact_id]]`; `run_promise_outcomes` не меняется).
- **Как:** `use_llm=False`; только unresolved OTHER promises данного user/contact; `_WINDOW_DAYS=120`,
  `_LATE_GRACE_DAYS=2` те же; persist `evidence_call_id/evidence_date/evidence_quote/method='det'`; sorted changed
  keys/contacts; все записи через `commit_unless_uow`; идемпотентно.
- **Тир:** T2. **Зависимости:** R-08/R-09.
- **Тест:** `tests/insight/test_promise_outcomes.py::test_incremental_outcome_refresh_returns_affected_contacts`.
- **Критерий:** unknown→kept/broken один раз; exact evidence fields; sorted один affected contact; LLM calls 0;
  второй run → пусто, 0 rows changed.

### R-24 — Synchronous outcome recompute hook
- **Файлы:** `pipeline/orchestrator.py` (`process_call` между `save_transcripts`/`set_role_fragile` (:255) и
  ветвлением `enable_llm_analysis` (:277); `process_batch` после `_unload_models()` (:474) и ДО Фазы 3 (:484)),
  `insight/promise_outcomes.py`, `graph/aggregator.py`, `insight/bs_recompute.py`, `db/uow.py`.
- **Как:** синхронный CPU UoW: R-23 → dedup affected contacts → R-09 counters для mapped entities → R-20 facade;
  commit только после projections. Exception → rollback outcome+counters+canon+projections, `_fail(stage=
  'outcomes')` вне failed savepoint, delivery подавлена; success передаёт affected typed pairs в terminal local-card
  publication (R-31) даже при `enable_llm_analysis=false`; retry видит unresolved source и сходится.
- **Тир:** T2. **Зависимости:** R-09/R-20/R-21/R-23.
- **Тест:** `tests/test_pipeline.py::test_outcome_hook_recomputes_once_and_records_failure`.
- **Критерий:** facade count на affected contact = 1; counter/contact/entity projection меняются; faults после
  outcome и после entity → все derived/outcome hashes pre-state; retry resolves → expected signature; rerun = 0
  writes; LLM-disabled путь эмитит typed pair и делает 0 `LLMClient` calls; статус/ошибка видимы; GPU calls 0;
  other user unchanged; `tests/test_stage1_transcribe_only.py`, `test_orchestrator_*` зелёные.

### R-25 — Graph-replay BS projection order
- **Файлы:** `graph/replay.py` (Step 9 :248-262 → внутри R-12 UoW: `entity_contact_map` → R-09 counters → repaired v1
  для каждой entity → R-20 facade для affected contacts → mention edges → metrics/audit → replay-run),
  `graph/repository.py`, `insight/person_link.py`, `insight/mentions.py`, `insight/bs_recompute.py`.
- **Тир:** T2. **Зависимости:** R-09/R-12/R-18/R-19/R-20.
- **Тест:** `tests/test_graph_replay.py::test_replay_recomputes_contact_then_mapped_entity_same_signature`.
- **Критерий:** counters/canon/projections совпадают до/после replay; два runs identical; fault после final entity
  projection → graph/map/counters/canon/projections к pre-run hashes; unique/ambiguous/unmapped exact; row growth 0;
  source/legacy hashes unchanged.

### R-26 — Feature/autofit recompute parity
- **Файлы:** `insight/cli_ops.py::run_features_build(:42)/run_archetypes_fit(:75)`, `cli/commands/insight.py`,
  `pipeline/watcher.py::_run_insight_fit(:317)`.
- **Как:** после persist raw `contact_features` собрать affected `(user,contact)` → facade R-20 с stored as_of;
  first-call path не ждёт порога `insight_autofit_min_new`; никаких LLM/GPU импортов.
- **Тир:** T2. **Зависимости:** R-18/R-19/R-20.
- **Тест:** `tests/test_watcher_autofit.py::test_autofit_and_archetypes_fit_call_pure_bs_recompute`.
- **Критерий:** каждый affected contact — ровно один вызов; below-threshold first-call pair существует; mocked
  LLM/GPU = 0; существующие 8 тестов файла зелёные.

### R-27 — Atomic v1→v2 recompute command
- **Файлы:** новый `src/callprofiler/cli/commands/bs.py::cmd_bs_recompute`, `cli/main.py` registry (`"bs-recompute":
  ("callprofiler.cli.commands.bs", "cmd_bs_recompute")`), `insight/bs_recompute.py`.
- **Как:** `bs-recompute --user USER [--as-of YYYY-MM-DD] [--dry-run]`; dry-run default: counts/deltas/versions;
  apply — один user, батчи по 200 контактов, resume по `source_signature`; без `--all`; projections только после
  canonical success; exit codes по T-22 (`cli/utils.py`).
- **Тир:** T2. **Зависимости:** R-17…R-20/R-25.
- **Тест:** `tests/test_bs_recompute_cli.py::test_v1_to_v2_backfill_is_atomic_and_idempotent`.
- **Критерий:** dry-run = 0 rows; apply конвертирует 100% eligible; ineligible остаются legacy+C1; rerun = 0;
  mid-batch failure → последний полный батч resumable, half-projection нет.

### R-28 — Absolute baseline label policy
- **Файлы:** `insight/bs_policy.py` (`bs_display(bs_index) -> int`, `bs_band(display) -> 'B'|'C'|'D'|'E'`,
  `low_data(c) -> bool`, `POLICY_VERSION='bs_ui_fixed_1'`), `graph/calibration.py::BSCalibrator.get_label` (reader
  фильтрует `bs_formula_version/policy_version`), `graph/repository.py::get_latest_bs_thresholds(:595)`.
- **Как:** §9 zero-preserving rule; bands ≤25/≤50/≤75/>75; low-data C<30; percentiles — только `relative_context`
  при explicit флаге и matching version (Phase B). `graph-health` check 4 (`cli/commands/graph.py:53-59`) не меняется.
- **Тир:** T1. **Зависимости:** R-13/R-14/R-17.
- **Тест:** `tests/test_bs_policy.py::test_baseline_labels_do_not_require_threshold_rows`.
- **Критерий:** `0/0.1/0.4/0.5 → 0/1/1/1`; 25/50/75/76 → B/C/D/E при C≥30; `50.4→50/C`, `50.5→51/D`; C=29 →
  low-data/F; произвольные threshold rows меняют результат 0 раз; `tests/test_bs_calibration.py` зелёный.

### R-29 — Admiralty v2 mapping
- **Файлы:** `insight/admiralty.py` (`source_grade(view: BSView, kept_ratio, kept_n) -> str`, `info_grade(c: int)
  -> str`, новые `SOURCE_PHRASES`/`INFO_PHRASES` §9.2; удалить `_INFO_HIGH/_INFO_MID`), `dashboard/labels_ru.py`,
  callsites `deliver/card_generator.py::_grade_line(:161-210)`, `dashboard/db_reader.py:1074-1102` (убрать SELECT
  `AVG(confidence) FROM events` и `BSCalibrator`).
- **Как:** letter из `BS_display`; digit 2/3/4/6 по C; A = ≤25 + kept_ratio≥.8 + n≥5 + C≥90; noncanonical/stale →
  F6; consume только `BSView`.
- **Тир:** T1. **Зависимости:** R-20/R-28.
- **Тест:** `tests/insight/test_admiralty.py::test_admiralty_v2_observational_mapping` (существующие
  `test_source_grade/test_info_grade/test_grade_line_format` переписываются под новые сигнатуры/фразы).
- **Критерий:** C 29/30/60/90 → 6/4/3/2; ровно шесть фраз §9.2; изменение `events.confidence` не меняет grade; A
  требует все условия; legacy/avg/zero/stale → F6 + marker + видимая пара; forbidden regex отсутствует.

### R-30 — Pure caller-card renderer
- **Файлы:** новый `src/callprofiler/deliver/card_render.py::render_card(lines: CardInput) -> str` (typed dataclass:
  header, risk_band, bs_view, grade, due, call_time, bullets, hook, now); `deliver/card_generator.py::generate_card
  (:232-305)` и `aggregate/summary_builder.py::generate_card_text(:201-284)` — оба становятся адаптерами к нему
  (второй формат исчезает; `text[:400]` удаляется).
- **Как:** mandatory `bs:` строка сразу после `risk:`; optional строки выбрасываются по фиксированному приоритету
  (hook → bullet3 → bullet2 → call → due → bullet1), `grade:` и штамп свежести — mandatory; измерение UTF-8 bytes;
  `BS_display` по §9 один раз; `risk:` из `risk_band/risk_emoji`; `grade:` из R-29.
- **Тир:** T1. **Зависимости:** R-19/R-21/R-29.
- **Тест:** `tests/test_card_generator.py::test_typed_card_always_keeps_pair_within_512_bytes`.
- **Критерий:** 100% fixtures обоих публичных callables содержат regex `bs: \d{1,3}/100 .* \d{1,3}/100`; 511/512/513
  UTF-8 кейсы ≤512, без partial UTF-8/line; full/minimal/error snapshots без trait/counters; canonical/legacy/avg/
  zero/stale markers exact; null-phone artifact label stable; `test_generate_card_no_advice_line`,
  `test_generate_card_freshness_stamp_last_line`, `test_generate_card_max_bytes` зелёные.

### R-31 — Atomic caller-card publication
- **Файлы:** `deliver/card_generator.py::write_card(:306)/update_all_cards(:349)/_remove_legacy_cards(:337)`,
  `aggregate/summary_builder.py::write_card(:286)/write_all_cards(:314)` (делегируют в CardGenerator),
  `src/callprofiler/artifacts.py`, `pipeline/orchestrator.py::_deliver_call(:1106-1145)`, `dashboard/tools.py::
  _rebuild_cards_sync(:281-300)` (→ `CardGenerator(repo).update_all_cards(self.user_id)`), `cli/commands/contacts.py::
  cmd_rebuild_cards(:37)`, `cli/commands/query.py::cmd_rebuild_cards(:104)`.
- **Как:** один terminal adapter `publish_card(user_id, contact_id, view: BSView, *, error: bool)`; ключ = canonical
  phone либо `unknown-<placeholder_key>`; рендер R-30; `atomic_write_text`; error path публикует local minimal card и
  подавляет Telegram. Cleanup сохраняет `^\d+$` и `^unknown-md5-[0-9a-f]{32}$`, удаляет только явный legacy phone
  alias после успешной публикации канонического файла.
- **Тир:** T1. **Зависимости:** R-30.
- **Тест:** `tests/test_card_generator.py::test_card_publish_is_atomic`.
- **Критерий:** inventory: за каждым публичным card writer — shared publisher, прямых `write_text` 0; success — exact
  new bytes; каждый injected failure — exact old bytes; `.part` не виден; все 10 R-21 кейсов публикуют ≤512-байтную
  карточку с парой; placeholder → update-all/оба CLI/dashboard → ровно один `unknown-md5-*`; unrelated file жив;
  wrong dashboard ctor/method calls 0; R-24 LLM-disabled republishes pair с 0 LLM calls; Telegram error sends 0;
  `test_card_write_is_atomic_old_card_survives_crash` зелёный.

### R-32 — Dossier canonical pair
- **Файлы:** `dashboard/models.py` (`bs_index/avg_bs_score` → `bs: BSViewModel`), `dashboard/db_reader.py::get_people
  (:553-700)/get_person_dossier(:698-1105)/get_all_characters(:266-310)/get_character_profile(:348)`,
  `dashboard/static/app.js` (:978-979, :1090-1096 `bsClass`, :1149-1156, :1597, :798), `dashboard/labels_ru.py`.
- **Как:** только `BSView` через R-17 (без прямого `em.bs_index`/`avg_bs_score` fallback); два tiles + marker +
  tooltip §1.2 + components; `bsClass` по `BS_display` bands (threshold column names чинить только для optional
  context R-44); `{"low":"Надёжный"}` → `сохранённый риск низкий`; 0 writes/LLM.
- **Тир:** T1. **Зависимости:** R-17/R-18/R-28.
- **Тест:** `tests/test_dashboard_dossier.py::test_dossier_and_list_use_canonical_bs_pair`.
- **Критерий:** list/dossier canonical/legacy_snapshot/avg/zero/stale values, versions, markers == R-17 view; stale
  high-C содержит `последний звонок не учтён`; other-user fields 0; tooltip `не детектор лжи`; full payload без
  counts/duration и forbidden regex; существующие dossier-тесты зелёные.

### R-33 — Shared compact delivery line
- **Файлы:** новый `src/callprofiler/deliver/bs_line.py::bs_line(view: BSView) -> str`, `deliver/digest.py::
  _format_item(:238)`, `deliver/telegram_bot.py::cmd_contact(:416-495)`.
- **Как:** §9.3 line/suffixes; без counts/duration; digest item — cap 300 после сохранения mandatory line;
  Telegram `cmd_contact` удаляет `📞 Звонков:` и `BS: {avg_bs_score}`, вставляет `bs_line`.
- **Тир:** T1. **Зависимости:** R-18/R-19.
- **Тест:** `tests/test_digest.py::test_shared_bs_line_under_300_chars_without_counts`.
- **Критерий:** digest/Telegram snapshot equality; каждый item ≤300; regex `n=|звонков|мин\.|фактов|обещаний:`
  и trait phrases отсутствуют; оба числа присутствуют; все четыре source + stale рендерят marker без fallback SQL;
  `test_digest_item_truncated_to_300_chars` зелёный.

### R-34 — Observable promise-outcome wording
- **Файлы:** `insight/promise_outcomes.py::contact_reliability(:376-400)`, `deliver/digest.py::_reliability_note
  (:226)`, `dashboard/static/app.js:1368` (заголовок секции → `Исходы обязательств`).
- **Как:** numeric summary сохраняется; `phrase` → `исходы обязательств: выполнены|были просрочены|не выполнены|пока
  неизвестны` по доминирующему статусу; никогда `надёжен|надёжность|держит слово`; без n/count/days в тексте.
- **Тир:** T1. **Зависимости:** R-09/R-33.
- **Тест:** `tests/insight/test_promise_outcomes.py::test_reliability_wording_is_observational`
  (`test_reliability_phrase_thresholds` переписывается на новые фразы).
- **Критерий:** exact phrase snapshot per status; forbidden regex 0.

### R-35 — Observable psychology patterns
- **Файлы:** `biography/psychology_profiler.py::_extract_patterns(:219-262)`, `biography/data_extractor.py::
  get_behavioral_patterns(:191-250)`, `dashboard/labels_ru.py` (`PATTERN_NAME`, `SEVERITY.positive`),
  `dashboard/db_reader.py::_build_character_label(:288-300)`; snapshot-тесты card/dossier/biography.
- **Как:** repaired counters/projection; labels §9.3; `reliable` — только `C≥30` (по `entity_metrics.bs_confidence`
  projection), label `наблюдаемых расхождений мало`; `emotionally_volatile` → `были эмоциональные всплески; на BS не
  влияет`; `SEVERITY.positive` → `положительное наблюдение`; risk fallback → `сохранённый риск низкий|средний|высокий`.
- **Тир:** T2. **Зависимости:** R-07/R-09/R-20/R-28.
- **Тест:** `tests/test_psychology_profiler.py::test_bs_patterns_are_observational`
  (`test_reliable_detected_when_no_broken` обновляется: без C≥30 — паттерна нет).
- **Критерий:** no-evidence → без reliability trait; emotion-only → BS 0; snapshots без `reliable`-trait rendering;
  stem regex `над[её]ж|ненад[её]ж|эмоционально\s+неустойчив|лжец|честн` → 0 user-visible совпадений
  (`tests/test_dashboard_labels_ru.py` обновлён).

### R-36 — Observable summary advice
- **Файлы:** `aggregate/summary_builder.py::_generate_advice(:510-531)` → `_generate_advice(view: BSView,
  debts_json)`, `rebuild_contact(:152)`; `deliver/card_generator.py` advice НЕ возвращается.
- **Как:** stale → `Последний звонок не учтён` без grade/advice; noncanonical → §8 marker; иначе таблица §9.3;
  `Говори первым` (risk≥70) и `Начни с долга` остаются (не BS); `Надёжный партнёр`, `Осторожно: размытые обещания`
  удалены; ≤300, counter-free.
- **Тир:** T1. **Зависимости:** R-19/R-28/R-30.
- **Тест:** `tests/test_summary_builder.py::test_bs_advice_uses_observational_decision_table`.
- **Критерий:** exact table outputs для BS0/0.1/0.4/0.5/50.4/50.5, C29/30, каждого source; stale high-C содержит
  `Последний звонок не учтён`, F6, без unmarked recommendation; ≤300; forbidden regex 0.

### R-37 — Independent latent BS synth
- **Файлы:** новый `src/callprofiler/insight/synth/bs_profiles.py` (generator `bs_synth_dgp_2`), loader в
  `insight/synth/corpus.py` (`SyntheticCorpus` паттерн: только `:memory:`/tmp, отказ на configured path), spec
  `docs/research/bs-v2/synth-package/README.md` (зеркало §10).
- **Как:** полный frozen hash-RNG, seed/grid, channel-probabilities, hostile strata, tag registry (closed; unknown tag
  → `ValueError`); latent first; resolver-only `eNNN`; expectation grid; 100×400; smoke на seed 20260822 той же
  DGP/half-up; без `random.Random`/banker's rounding; без sqlite/config import в генераторе.
- **Тир:** T2. **Зависимости:** R-13/R-14/R-16.
- **Тест:** `tests/insight/test_bs_synth_generator.py::test_bs_synth_is_independent_deterministic_and_db_safe`.
- **Критерий:** same seed → byte-identical; ровно 100 seeds/400 contacts/100-call timeline; nested 0/1/3/10/100;
  каждый resolved outcome имеет due `eNNN` call/date/transcript, first-call — нет; каждый raw fact проходит
  `FactValidator`/R-16 grounding when clean; specificity corpus → exact q через production `compute_specificity`;
  registry rejects unknown tag; grid независим от scorer; все strata; smoke делит константы/hash draws; configured
  production path raises до open.

### R-38 — Preregistered synth evaluator
- **Файлы:** `src/callprofiler/insight/synth/bs_evaluate.py`, `tests/insight/test_bs_synth_recovery.py`.
- **Как:** R-37 fixtures → R-16 → scorer; primary default/n100 tau-b с tie rule и nearest-rank #5; clean/mixed и все n
  panels отдельно; fixed-denominator sign test (ties=failures); optional pre-binned ARI; rank-sum comparator и §10.2
  half-loss; seed/scenario counts; все OAT варианты; report byte-identical для тех же seeds.
- **Тир:** T2. **Зависимости:** R-16/R-37.
- **Тест:** `tests/insight/test_bs_synth_recovery.py::test_bs_synth_recovery_and_noise_gates` (маркер `slow`;
  в CI обязателен).
- **Критерий:** grid tau-b=1; default/n100 median≥.60/p05≥.50; все диагностики present; clean median C строго
  n1<n3<n10<n100 для 100/100; clean→severe positives ≥63/100; discordance формула exact, rate ≤10%; OAT manifest
  exact.

### R-39 — Global formula invariant suite
- **Файлы:** `tests/test_bs_v2_properties.py` (stdlib `random` с фиксированным seed; Hypothesis НЕ добавляется — не в
  `pyproject.toml`).
- **Как:** missing/permutation/duplicate/noise/as_of генераторы; ROC vs rank-sum; мутации empty calls/duration/LLM
  confidence (`.60…1.00` invariant, gate crossing separately); 10 000 vectors.
- **Тир:** T2. **Зависимости:** R-13/R-14/R-37/R-38.
- **Тест:** `tests/test_bs_v2_properties.py::test_bs_v2_global_invariants`.
- **Критерий:** 0 failures по десяти свойствам §10; discordant ≤10%; без network/model calls.

### R-40 — Tenant ownership closure
- **Файлы:** `tests/test_tenant_ownership.py` (inventory над `insight/bs_*.py`, `bs_policy`, `bs_recompute`,
  `bs_snapshot`, `card_render`, `bs_line`, `admiralty`, R-06/R-15/R-18…R-36 callsites).
- **Как:** enumerate canonical/snapshot/mutator/projection/surface functions; user argument обязателен; equal-user
  joins; same quote/contact logical keys у двух users; DB trigger negative cases.
- **Тир:** T2. **Зависимости:** R-02/R-06/R-15/R-18/R-20/R-21…R-36.
- **Тест:** `tests/test_tenant_ownership.py::test_bs_v2_inventory_is_tenant_scoped` (`@pytest.mark.tenant`).
- **Критерий:** wrong-owner reads → none; mutators affect 0; same quote → две tenant rows; surfaces leak 0 fields.

### R-41 — Contracts and layer maps
- **Файлы:** `.claude/rules/{graph,insight,db,dashboard,decisions,bugs}.md`, `docs/research/bs/claims-ledger.md`
  (C-21…C-46 из GPT90 §18 — перенос как есть, статус `план`), `docs/research/bs/40-data-surface.md` (ссылка на
  этот план).
- **Как:** версии, canonical/snapshot schema, формулы, replay order, projection ambiguity, UI semantics, legacy
  router; bugs.md п.1 «BS-index v1_linear» → RESOLVED со ссылкой на R-06/R-07/R-09; decisions.md абзац «BS-v2
  (100bsindex) принят владельцем 2026-08-22, supersedes вердикт ОТЛОЖЕНО по 90-execution-plan»; memory
  `research-build-on-existing` не противоречит (развитие, new-user first) — обновить строку «BS-research shelved».
- **Тир:** T0. **Зависимости:** R-01…R-40.
- **Тест:** `tests/test_docs_contracts.py::test_bs_v2_plan_and_maps_reference_current_versions`.
- **Критерий:** grep находит score/confidence/router versions в пяти картах; уравнения/статусы exact; ни одна карта
  не утверждает «BS≤20» как ожидаемое после rollout.

### R-42 — Atomic Phase-A activation and closeout
- **Файлы:** `src/callprofiler/config.py` (`bs_read_version` default → `"baseline"`), `configs/features.yaml`,
  `docs/sintezdiharea.md` (§7 новая задача **T-26 — BS-v2 observed discrepancy + evidence confidence**, namespace
  `BSV2-R-01…R-52`; §9 dependency graph), `docs/ops/box-canary-checklist.md` (§1 `user_version → 12`, новый §:
  `bs-recompute --dry-run` → apply → `graph-replay --apply` → сверка карточек), `CHANGELOG.md`, `CONTINUITY.md`.
- **Как:** §14 acceptance при static default `legacy` и explicit `baseline` route; только после PASS — оба default'а
  `baseline`; один release-commit (config + memory); неполная половина = тест красный.
- **Тир:** T2. **Зависимости:** R-01…R-41; §14 п.2…10 на explicit baseline.
- **Тест:** `tests/test_docs_contracts.py::test_bs_v2_phase_a_release_state_is_atomic`.
- **Критерий:** missing config → exact Phase-A pair; legacy explicit route byte-round-trips с 0 writes;
  upgraded legacy-only contact под default рендерит legacy number+C1 без backfill writes; sintezdiharea содержит
  T-26; CHANGELOG одна release-строка; CONTINUITY exact versions/tests и один real next step; любой незакрытый gate
  оставляет defaults legacy.

## 12. Фаза B — optional accumulated-data refinements (= GPT90 §12; промпт-кандидат = **v003**)

Новые boolean флаги default false; enum defaults `baseline|none|v002`; reader default — Phase A versions. Existing
pipeline flags не меняются. Ни owner labels, ни real-DB thresholds не prerequisite.

События: `E-B0` — §14 Phase A green; `E-B1` — explicit `bs_refinement=contextual`; `E-B2` — R-45 candidate
falsifier green; `E-B3` — `analysis_prompt_candidate=v003` при `analysis_prompt_active=v002`.

### R-43 — Refinement/version routing
- **Файлы:** `configs/features.yaml`, `src/callprofiler/config.py::FeaturesConfig`, `insight/bs_policy.py` registry.
- **Как:** validated enums `bs_refinement=baseline|contextual|style` (baseline), `bs_candidate=none|style` (none),
  `analysis_prompt_candidate=none|v003` (none), `analysis_prompt_active=v002|v003` (v002). Contextual display —
  только R-44 PASS + флаг; style/active-v003 — только при matching R-52 PASS manifest; candidate routes shadow-only;
  selected formula/policy в row/signature; unknown value → `ConfigError` (T-01 preflight).
- **Тир:** T1. **Зависимости:** R-42.
- **Тест:** `tests/test_features_config.py::test_bs_refinements_default_to_baseline`.
- **Критерий:** missing config → Phase-A versions/v002, no candidate; invalid → config error; style/active-v003 без
  PASS manifest fail-closed; candidate change → отдельная shadow signature, 0 active rows.
- **Условие:** `if E-B0 → implement; else baseline`. **Rollback:** `bs_refinement: baseline`.

### R-44 — Versioned contextual percentiles
- **Файлы:** `graph/calibration.py::BSCalibrator.analyze(:35)/get_label(:101)`, `graph/repository.py::
  get_latest_bs_thresholds(:595)` (`WHERE bs_formula_version=? AND policy_version=? ORDER BY created_at DESC, id
  DESC`), `dashboard/db_reader.py:1050-1056`, `dashboard/static/app.js::bsClass(:1090)` (column names
  `reliable_max/noisy_max/risky_max/unreliable_max`).
- **Как:** p25/p50/p75/p90 только при explicit флаге и `entity_count≥3`; label `относительно ваших контактов`;
  никогда не кормит score/C/Admiralty baseline.
- **Тир:** T1. **Зависимости:** R-28/R-32/R-43.
- **Тест:** `tests/test_bs_policy.py::test_contextual_thresholds_never_change_numeric_baseline`.
- **Критерий:** флаг меняет только relative label; score/C/letter byte-equal; <3 — без context, оба индекса
  видимы; `graph-health` check 4 зелёный при версионированных строках.
- **Условие:** `if E-B1 → relative label; else none`.

### R-45 — Within-contact promise-specificity candidate
- **Файлы:** `insight/bs_index.py`, `insight/bs_inputs.py`, `insight/features/specificity.py::compute_specificity`
  (reuse, не переопределять), synth/property tests.
- **Как:** candidate `v2_roc_observed_style_1`; `compute_specificity` на stored `speaker=OTHER` сегментах каждого
  звонка (UNKNOWN исключён), raw 0…100 принимается, если функция вернула Feature хотя бы от одного токена (zero hits
  = наблюдённый 0); recency-weighted `sp=mean(specificity | ≥1 valid OTHER promise)`, `sn=mean(specificity | no
  valid OTHER promise)`; available при обеих непустых группах и total calls≥2; `S_gap=clamp((sn-sp)/100,0,1)`;
  `L_base=(3*aC*C+aP*P)/(3*aC+aP)`; style только при существующем L_base и S available/positive:
  `L_style=1-(1-L_base)*(1-S_gap/4)`, иначе `L_base`. Outer 11/5/2 unchanged. `S_gap` score-only: 0 confidence
  mass; `c1_effective_evidence_1` считает N/E/A/S из baseline B и grounded C/P (+M где §5 позволяет), никогда из
  `L_style`; contact только со specificity → C=1.
- **Тир:** T2. **Зависимости:** R-26/R-38/R-43.
- **Тест:** `tests/test_bs_v2_refinements.py::test_style_candidate_adds_rank_value_without_genre_false_positive`.
- **Критерий:** goldens `C1/P0/S-missing→L=.75`, `L_base=.75/S=.25→L_style=.765625`, only-S`.4→L missing`; only-S
  → `N=E=0,C=1`; добавление/удаление S не меняет confidence details; baseline byte-identical при S missing/0;
  `specificity_null` → `S_gap=0`; genre-only seeds: nearest-rank p95 `|mean(delta|G=1)-mean(delta|G=0)|` ≤2.0
  displayed points; `specificity_signal`: отчёт slopes 20/40/60 и divisors 2/4/8 без selection; canonical
  slope40/divisor4 default/n100 tau median≥.60/p05≥.50 и улучшает tau над baseline в ≥63/100 seeds (ties =
  failures). Fail → E-B2 FAIL/baseline.
- **Условие:** `if E-B0 AND bs_candidate=style → build+gate; PASS → E-B2 + shadow candidate; FAIL → baseline`.

### R-46 — Prompt v003 candidate and cache namespace
- **Файлы:** новый `configs/prompts/analyze_v003.txt` (копия v002 + `structured_facts[].who: "Me|S2|UNKNOWN"`,
  `bs_evidence: [{"quote","type","who"}]`, `promises[].due: "YYYY-MM-DD|null"`, quote min 8), `analyze/
  {service.py,prompt_builder.py,response_parser.py,canary.py}`, `bulk/enricher.py`, `pipeline/orchestrator.py`,
  `config.py`.
- **Как:** один resolver `selected_prompt_version(config, *, candidate=False) -> str` → имя файла, `PromptBuilder.
  build(version=…)`, `LLMClient(prompt_version=…)` (cache namespace), парсер (v003 схема требует `who`/quote),
  persisted `analyses.prompt_version`; hardcoded `"v001"` default в `PromptBuilder.build(:69)` и
  `parse_llm_response(:30)` убираются (только явная версия); short/error fallbacks пишут ту же выбранную версию.
  UNKNOWN остаётся score-ineligible, не коэрсится в S2. `analysis_prompt_candidate=v003` потребляется только shadow
  canary; live/bulk — `analysis_prompt_active=v002` до R-52 PASS.
- **Тир:** T2 (PROMPT_VERSION/cache invalidation). **Зависимости:** R-05/R-08/R-43.
- **Тест:** `tests/test_prompt_builder.py::test_analyze_v003_bs_fields_and_cache_namespace`.
- **Критерий:** live/bulk/fallback/canary пишут одну explicit version; v002 default byte-equal; v003 schema
  rejects missing who/quote; v002/v003 cache hashes различаются 100%; candidate flag меняет active prompt/caches 0 раз.
- **Условие:** `if E-B3 → shadow only; activation requires E-C2+E-C4 (R-52)`.
- **Rollback:** `analysis_prompt_candidate=none`, `analysis_prompt_active=v002`.

### R-47 — GPU-safe read-only M4 metrics
- **Файлы:** `analyze/canary.py::run_canary(:78)`, `cli/commands/bulk.py::cmd_canary_analyze(:129)`, `cli/main.py`,
  `cli/utils.py`, новый `src/callprofiler/ops/gpu_lock.py` (`msvcrt.locking` на Windows / `fcntl.flock` иначе;
  файл `<data_dir>/locks/gpu-phase.lock`), `pipeline/orchestrator.py` (lock от первого ASR/pyannote load до конца
  Фазы 3), `pipeline/watcher.py`, report dataclass.
- **Как:** canary читает только config text, nonblocking-acquire ДО открытия БД и `LLMClient`; БД через
  `ConnectionFactory.reader()` (`mode=ro`+`query_only`); никаких `load_config_and_repo`/`init_db`/migrations/mkdir/
  file logging; output parent должен существовать; единственный файл — atomic report; lock в `finally`. Метрики:
  parse/truncated, required-field completeness, quote-match distribution, OTHER/UNKNOWN attribution, promise vague/due
  completeness; fingerprint server/model/prompt; `cache_conn=None`.
- **Тир:** T2. **Зависимости:** R-46.
- **Тест:** `tests/test_canary.py::test_m4_report_contains_bs_grounding_metrics_and_writes_nothing`.
- **Критерий:** contention → explicit busy до client construction, 0 `ensure_ready`/LLM calls; uncontended порядок
  lock→assert ASR/pyannote absent→LLM→unlock; schema report полная; на pre-M12 fixtures `sqlite_master`/migrations/
  DB/WAL/SHM/cache/FS inventory byte-equal кроме report; mkdir/init/schema/write calls 0; оба варианта — same ordered
  call ids; существующие 3 теста `test_canary.py` зелёные.
- **Условие:** `if E-B3 candidate exists → report capability; else skip`.

## 13. Фаза C — box verification only (= GPT90 §13; candidate = `style_1` | `prompt_v003`)

Phase C существует только для named box-requiring Phase-B candidate, прошедшего offline gate. Без candidates
R-48…R-52 = `not-applicable`, box commands = 0. C не валидирует/калибрует baseline. Все операции на verified copy
(`ops/backup.py::create_backup/verify_backup` → temp restore), production БД read-only (`ConnectionFactory.reader`),
`originals`/`in` не затрагиваются (CLAUDE.md: `C:\calls\in` protected).

События: `E-C0(style_1|prompt_v003)` — verified backup in temp path / frozen read-only transcript manifest;
`E-C1(style_1)` — R-48 PASS; `E-C2(prompt_v003)` — R-49 paired M4 **и** semantic synth PASS; `E-C3(style_1)` —
R-50 PASS; `E-C4(candidate)` — R-51 PASS; `E-C5` — R-52 manifest/config committed.

### R-48 — Frozen paired style reference
- **Файлы:** `docs/research/bs-v2/box-package/paired_reference.py`, `schemas/style-paired-reference.schema.json`,
  `checklists/R48-style-reference.md` (паттерн существующего `docs/research/bs/box-package/` — все скрипты `--db`,
  отказ на пути внутри `C:\calls\data`, `--synth` smoke).
- **Как:** только `style_1`; verified backup → temp restore; source hash; baseline и style shadow side-by-side с
  fixed as_of; eligible contacts/missingness/signatures; без go/no-go и tuning.
- **Тир:** T3. **Зависимости:** R-43/R-45; T-20 backup, T-24 harness.
- **Тест:** `docs/research/bs-v2/box-package/tests/test_shadow_report_contract.py::test_report_is_read_only_and_complete`.
- **Критерий:** contact set 100% paired; source hashes unchanged; cross-tenant 0; style rows отдельной версии;
  contextual/prompt создают 0 metric rows; absent style → 0 box commands.
- **Условие:** `if E-B2 AND E-C0(style_1) → report; else not-applicable`.

### R-49 — M4 v002/v003 canary
- **Файлы:** `docs/research/bs-v2/box-package/m4_compare.py`, `box-package/prompt-semantic-corpus.json`, R-47 command.
- **Как:** hash-sort eligible transcript fingerprints, первые 50; каждый дважды в deterministic AB/BA по call hash под
  R-47 lock с exact installed llama-server/model (инвариант 27: модель не меняется); compare parse/truncated, grounded
  quote, role attribution, per-call median latency; без cache/DB write. Bootstrap 10 000:
  `U_boot(b,d)=uint64_be(SHA256(utf8("bootstrap|20260822|{b}|{d}"))[0:8])/2**64`, index `floor(50*U_boot)`; sorted
  #9500 = nearest-rank one-sided 95% upper percentile медианы. В том же zero-write run — frozen 50-case role-tagged
  RU synth cohort через parser→R-16→scorer: 25 positives (10 word↔word contradictions, 15 vague OTHER promises), 25
  negatives (по 5: concrete promise, explicit correction, polite hedge, OWNER-only discrepancy, ASR-near mismatch);
  по 5 lexical variants; corpus SHA и expected C/P type committed до model output; temperature 0; 625 pairs §10
  half-loss; 1 case = `.04`.
- **Тир:** T3. **Зависимости:** R-46/R-47; E-C0 manifest.
- **Тест:** `docs/research/bs-v2/box-package/tests/test_m4_report_contract.py::test_same_calls_and_fingerprints`.
- **Критерий:** same 50 ids/fingerprints; invalid count ≤ baseline+1; grounded и OTHER-attribution counts ≥
  baseline−1; bootstrap upper95 median latency ratio ≤1.00; candidate p95 ≤ baseline p95, оба < 300s timeout
  (`_LLM_TIMEOUT` существующий); paired differences, Wilson intervals, seed в отчёте. Semantic synth: v003
  target-qualified positives ≥ v002−1; unsupported positives среди negatives ≤ v002+1; half-loss ≤ v002+.04;
  median planted positive BS > median negative BS; duplicate run byte-equal. Меньше 50 / hash mismatch / любой fail →
  v002, нет E-C2.
- **Условие:** `if E-B3 AND R-47 PASS AND E-C0(prompt_v003) → run; else not-applicable`.

### R-50 — Refinement non-degradation report
- **Файлы:** `docs/research/bs-v2/box-package/style_holdout.py`, `schemas/style-holdout.schema.json`.
- **Как:** до просмотра scores freeze `cutoff=max(persisted call date)-120 days`; pre-cutoff scores только по
  ранним строкам; `Y` = mean §4.1 severity post-cutoff `method=det` kept/late/broken в +120d; eligible contact —
  pre-cutoff baseline+candidate opportunity и ≥3 outcomes; hash-sort, первые ровно 20 — confirmatory;
  candidate−baseline Kendall tau-b после всех `2^20` within-contact swaps; one-sided p = `count(delta_perm >=
  delta_obs)/2^20` (ties в numerator); остальные contacts — diagnostic; strata call_type/unknown genre, missingness;
  без fit/tune.
- **Тир:** T3. **Зависимости:** R-45/R-48.
- **Тест:** `docs/research/bs-v2/box-package/tests/test_non_degradation_report.py::test_report_uses_frozen_versions_and_as_of`.
- **Критерий:** до чтения scores: ≥20 eligible contacts, ≥60 future det outcomes, ≥100 confirmatory pairs с
  `Y_i!=Y_j` и хотя бы одним strict method score; E-C3 PASS только при delta>0, exact p<.05, identical coverage, ни
  один genre stratum с ≥5 contacts не меняет знак. Insufficient/fail → style off.
- **Условие:** `if E-B2 AND E-C0(style_1) AND E-C1(style_1) → test; else not-applicable`.

### R-51 — Candidate-specific rollback rehearsal
- **Файлы:** `docs/research/bs-v2/box-package/rollback_candidate.py`, `checklists/R51-candidate-rollback.md`,
  `schemas/candidate-rollback.schema.json`.
- **Как:** config остаётся baseline/v002. Style: temp restore, hash sources, shadow-read style→baseline→style,
  recompute только своих versioned rows. Prompt: `cache_conn=None`, shadow v003→active v002→shadow v003 на тех же
  frozen transcripts, 0 DB/cache writes; recheck semantic-corpus hash и E-C2 fingerprint. Production config не
  редактируется.
- **Тир:** T3. **Зависимости:** style — R-48/R-50 PASS; prompt — R-49 PASS; T-20/T-25.
- **Тест:** `docs/research/bs-v2/box-package/tests/test_bs_rollback_report.py::test_candidate_specific_rehearsal_precedes_activation`.
- **Критерий:** style baseline pair/signature recovered 100%, второй style read byte-equal первому; prompt v002/v003
  fingerprints повторяются с 0 writes; sources exact; cross-tenant/data-loss 0; config baseline/v002; каждая
  applicable ветка эмитит E-C4.
- **Условие:** `if (style_1: E-B2∧E-C1∧E-C3) OR (prompt_v003: E-B3∧E-C2) → rehearse; else not-applicable`.

### R-52 — Atomic candidate decision and activation
- **Файлы:** `docs/research/bs-v2/box-package/release-manifest.json`, `configs/features.yaml`,
  `.claude/rules/decisions.md`.
- **Как:** каждый candidate → exact E-B/E-C reports, fingerprints, version, WHY; после E-C4 PASS style →
  `bs_refinement=style`, prompt → `analysis_prompt_active=v003` + candidate cleared; missing/fail → baseline/v002
  (reason). Manifest+config+decision = один release state.
- **Тир:** T3. **Зависимости:** R-51.
- **Тест:** `tests/test_release_manifest.py::test_candidate_activation_requires_matching_rehearsal`.
- **Критерий:** каждый candidate ровно `enabled(version,rehearsal,report)` или `baseline(reason)`; без rehearsal
  enable невозможен; active config == manifest; Phase-A versions доступны; single-flag rollback → baseline/v002 с 0
  source writes.
- **Условие:** `style_1: E-B2+E-C1+E-C3+E-C4 → activate; prompt_v003: E-B3+E-C2+E-C4 → activate; иначе baseline`.

## 14. Полное acceptance Phase A (= GPT90 §14 с поправками §0.1)

1. R-01…R-42 green; все `unconditional`; каждый slice ≤1 дня.
2. Fresh/upgrade migration parity (user_version 12), `python -m pytest -q` 0 failed, `ruff` гейт зелёный.
3. First-call matrix 10/10 (normal/nonzero, short, parse-failed, no-analysis, LLM/scorer errors, role-fragile,
   null-contact, null-phone, retry): pair + minimal card до delivery; first-call C≤5; retry не дублирует/не
   сбрасывает; placeholder не auto-merge.
4. Card ≤512 UTF-8 bytes; digest item ≤300 chars; no user-visible counts/duration.
5. Golden BS, clean N/E и raw-n таблицы exact; dgp2 expectation/default-n100, sparse diagnostics, confidence/noise
   и property gates §10 green; smoke использует тот же hash registry.
6. Upgrade full replay: graph_v1→graph_v2 once; два runs same details/signature/counts включая replay-run, growth 0;
   protected legacy entity/profile/source и second user byte-identical; pre-M12 preview не меняет схему/файл;
   injected failure → full rollback; process order/wall clock hashes equal.
7. Все новые mutators требуют `user_id`; two-user suite (`-m tenant`) zero leak/collision.
8. BS-v2 initializer/scorer/recompute = 0 model/LLM/GPU calls; существующий **v002** analysis path неизменен, в
   offline-тестах мокается, `PROMPT_VERSION_ANALYZE` остаётся `v002`.
9. Existing mechanisms queryable: stable-key v1 snapshot + round-trip, repaired v1 comparator, `avg_bs_score`,
   threshold rows, Admiralty, patterns, outcomes, explicit entity projection states.
10. UI strings: observed discrepancy + «не детектор лжи»; low confidence marks, never hides.

Failure в любом пункте → его R-задача. Никогда не требование owner labels/real-DB calibration.

## 15. Rollback model (= GPT90 §15)

- `bs_read_version` выбирает immutable legacy snapshot или versioned baseline с 0 writes; Phase-B flags false.
- M12 additive retained; никакого down-migrate/drop.
- Source analyses/transcripts/promises/outcomes immutable; full replay заменяет только `graph_v1|graph_v2` в одном
  user UoW; canonical metrics versioned.
- `bs-recompute --dry-run` default; explicit user/as_of apply.
- v1 payload захватывается `INSERT OR IGNORE` по stable key до первой projection; R-17 доказывает round-trip.
- Prompt v003 — отдельный cache namespace и один флаг; v002 не удаляется.
- Card/dashboard/digest регенерируются из canonical source.
- Cross-tenant/source-hash/replay-growth failure = stop-the-line.

## 16. Место в `docs/sintezdiharea.md` и критический путь

Зарегистрировать successor **T-26 — BS-v2 observed discrepancy + evidence confidence**, namespace `BSV2-R-01…R-52`
(не конфликтует с research R-01…R-03 §8 sintezdiharea). T-19 не переписывать. BS-v2 использует завершённые
T-03 (ownership), T-04 (UoW), T-05 (migrations), T-06 (purge — см. §0.1 п.3), T-08 (atomic artifacts), T-13 (cache
key с prompt_version), T-14 (v002), T-15 (строгий парсер), T-16 (идемпотентность), T-19 (RiskPolicy), T-22 (exit
codes), T-24 (tenant markers). R-03…R-27 — vertical slices T-15/T-16; R-28…R-36 расширяют T-19/T-23; R-37…R-40
пополняют T-24; Phase C входит в T-25 только для named candidate.

```text
R01 → R02/R03 → R04 → R05 → R06 → R07
R01 → R08 → R09; R06/R09 → R10 → R11 → R12
R13 → R14; sources → R15 → R16 → R17 → R18 → R19 → R20
R20 → R21 → R22; R23/R20 → R24; R12/R09/R20 → R25; R20 → R26 → R27
R17/R20 → R28 → R29 → R30 → R31; R32/R33/R34/R35/R36
R16 → R37 → R38 → R39 → R40 → R41 → R42
optional contextual R43→R44; style R43→R45→R48→R50→R51→R52; prompt R43→R46→R47→R49→R51→R52
```

Параллельные группы (независимы по файлам): {R-13,R-14} ∥ {R-02,R-03,R-04}; {R-08} ∥ {R-05,R-06,R-07};
{R-32,R-33,R-34,R-35,R-36} ∥ {R-37,R-38,R-39}. Исполнение каждой группы — режим оркестрации decisions.md
2026-08-22 (Opus implement → Sonnet review → личная верификация diff + full suite перед push); **отчёт агента ≠
доказательство** (CLAUDE.md).

Следующий шаг после этого документа: **Phase A, R-01**.

## 17. Открытые риски (= GPT90 §17 + 3 новых)

| Риск | Почему открыт | Проверка / outcome |
|---|---|---|
| RISK-01 late curve 14 days | continuity, не empirical | R-39 sensitivity 7/14/28 |
| RISK-02 contradiction = rational update | промпт без context taxonomy | synth negative-control; Phase B v003 instruction; never label lie |
| RISK-03 resolver mistakes speech for deed | det/LLM inferred from calls | method/quote в details; LLM half-weight |
| RISK-04 one fact → extreme BS | renormalized missing families | C≤5 one-call; UI wording; never hidden |
| RISK-05 180-day decay | no universal value | 90/180/360 sensitivity; as_of deterministic |
| RISK-06 same-call correlation | many fields one response | max L/M credit/call; duplication property |
| RISK-07 confident role swap invisible | no UNKNOWN marker | explicit residual; synth expects BS loss |
| RISK-08 canonical/projection drift | three read models | R-18 signature, R-19/R-20/R-25 equality |
| RISK-09 card budget | mandatory line + UTF-8 | R-30 boundary matrix; R-31 atomic |
| RISK-10 relative thresholds relabel | stale/version rows | R-28/R-44 invariance |
| RISK-11 prompt v003 harms parse/latency | exact build unknown | R-49 paired M4; fail → v002 |
| RISK-12 synth circular | inverse construction | latent-first R-37 + evaluator R-38 + hostile strata |
| RISK-13 style encodes genre | specificity genre-sensitive | baseline 0; R-45 shadow; R-50 future-det |
| RISK-14 performance on 16k calls | joins may scan | indexes §6/signature/incremental; never baseline gate |
| RISK-15 schema drift central/ad-hoc | три DDL owner'а | R-01 parity + order fixtures |
| RISK-16 low C read as low BS | cognitively confusable | labels with nouns/100 + low-data phrase |
| RISK-17 future leakage | retrospective as_of | pre-decay future exclusion R-15/R-16; R-39 |
| RISK-18 censoring changes composition | rejected evidence | potential N retained; R-38 sign test |
| RISK-19 map ambiguity leaks identity | many-to-many map | R-20 states; id-permutation tests |
| RISK-20 phone-less placeholders fragment | auto-merge worse | one per source_md5, visibly unnamed; explicit future assignment only |
| RISK-21 protected legacy entities accumulate | profiles unreconstructible | replay report count/keys; separate owner-authorized cleanup |
| RISK-22 dgp2 primary ≠ first-call accuracy | sparse Bernoulli noisy | all n panels; first-call promise = pair + C≤5 only |
| RISK-23 GPU lock on Windows/dev | cross-process | R-47 two-process test; fail-closed |
| RISK-24 within-contact specificity useless | null-safe still useless | R-45 gates; R-50; fail → baseline |
| RISK-25 (new) purge-guard flag | `users.purge_started_at` забыт новым deleting-путём | R-01 тест: любой DELETE снапшота вне purge → abort; `test_purge_user_introspection_classifies_all_tables` |
| RISK-26 (new) bs_evidence legacy events в C | bulk/backfill пишут contradiction-события без provenance | R-15 producer filter + тест с legacy contradiction row → C не меняется |
| RISK-27 (new) первичный бокс-прогон после M12 | 16k+ звонков: M12 backfill + `bs-recompute` + `graph-replay --apply` — многочасовые | R-42 расширяет `box-canary-checklist.md`: backup → M12 на копии → время → только потом боевая; `--dry-run` обязателен |

## 18. Traceability matrix (= GPT90 §18; C-21…C-46 переносятся в ledger задачей R-41)

| Claim + source | Спор → решение | Задача | Test | Criterion |
|---|---|---|---|---|
| C-01/C-23, S-DEC/S-CONST | lie/trait vs owner value → observed pair always, disclaimer | R-21/R-30…R-36 | pipeline/full surface snapshots | 10/10 pair; trait regex 0 |
| C-02/C-34, S-CODE-06 | entity/analysis/phone gate vs first call → placeholder initializer | R-01/R-18/R-21 | null-contact/phone/failures | pair+artifact before delivery; C≤5 |
| C-03/C-04/C-27, S-CODE-01 | dead v1 vs repair → counters live, V/D direct 0 | R-06…R-09/R-20/R-35 | fact/outcome/pattern fixtures | repaired counts exact; v1 retained |
| C-05/C-09, S-PROM/S-CODE-04 | outcome ≠ deed → method/date/quote B + late sensitivity | R-08/R-09/R-23/R-39 | outcome provenance/curve | undated absent; 7/14/28 |
| C-06/C-07, S-PRAG/S-CODE-05 | style confound → baseline 0, promise-local P | R-16/R-35/R-45/R-50 | input/style holdout | baseline unchanged; fail→off |
| C-08/C-33, S-ROC | no effect sizes → ROC ranks + loss sensitivity | R-13/R-38/R-39 | golden/sensitivity | equations exact; discord ≤10% |
| C-10, S-ROC | missing as clean → renormalization + low C | R-13/R-14 | missing vectors | all missing 0/1 |
| C-11/C-17, S-LLM | same-response agreement → M weakest | R-14/R-16 | common-mode mutations | post-gate delta 0 |
| C-12/C-13/C-14, S-PHIA | probability/volume confusion → N/E strength | R-14/R-39 | curves/monotonicity | raw-n exact |
| C-15/C-29, S-CODE-02 | marginal Q/future → per-cluster q, future exclusion | R-14…R-16/R-39 | quality/as_of | rejected cannot raise |
| C-16, S-CODE-01 | decay universal? → continuity 180 + sensitivity | R-13/R-39 | decay sensitivity | deterministic |
| C-18, S-PHIA | stability ≠ truth → chronological repeatability | R-14/R-39 | split tie | S=0 until E_half≥2 |
| C-19/C-20/C-30/C-42, S-SIM | circular synth → closed dgp2 | R-37…R-39 | generator/evaluator | grid 1; .60/.50 |
| C-21/C-31, S-CODE-02/S-CONST | partial replay/data loss → protected set, strict UoW | R-03…R-12/R-25 | upgrade/fault/order | growth 0; hashes exact |
| C-22/C-28, S-CODE-03 | flag without history → versioned canon + snapshot/router | R-01/R-17…R-20/R-27 | migration/round-trip/CLI | byte round-trip |
| C-24, S-CODE-06 | remove vs develop consumers → exact projections | R-28…R-36 | policy/snapshots | mechanisms remain |
| C-25/C-32, S-CONST | numeric identity/best-map → triggers, stable key, unique map | R-02/R-06/R-20/R-40 | collision/map/tenant | leaks 0 |
| C-26/C-45, S-CONST | richer LLM vs 12GB order → CPU A + GPU lock B/C | R-21…R-27/R-46…R-49 | mocked models/lock | Phase-A model 0 |
| C-35, S-CONST | generic box flow → typed branches, rehearsal→activation | R-48…R-52 | release audit | pre-rehearsal baseline |
| C-36, S-CODE-02/S-CONST | nested commits vs convergence → one facade/UoW | R-12/R-20…R-26 | faults | every hash rolls back |
| C-37, S-CONST | promised default → legacy-safe slices + atomic release | R-17/R-42 | release-state | incomplete→legacy |
| C-38, S-CONST | rounded zero wording → zero-preserving display | R-28…R-36 | `.1/.4/.5` | number/band/phrase agree |
| C-39/C-40, S-SIM | ties/hidden DGP/box tuning → exact losses, hash DGP | R-37…R-40/R-50 | evaluator/holdout | fixed denominators |
| C-41, S-CONST | timeout vs latency → paired gate + hard stop | R-47/R-49 | same-50 report | upper95 ≤1; <300s |
| C-43, S-CODE-04/S-LLM | per-path grounding → one contract | R-05/R-08/R-16 | boundary matrix | 7/8, .71/.72 exact |
| C-44, S-CODE-06 | duplicate card writers → one renderer/publisher | R-30/R-31 | inventory+bytes | direct writes 0 |
| C-46, S-PRAG | absolute specificity confound → within-contact gap | R-45/R-50 | null/positive+holdout | null loss ≤2 |

## 19. Hostile review disposition (= GPT90 §19) + ревизия этого документа

GPT90 §19 (статистик, deception researcher, архитектор, DB/tenant, адвокат владельца, этика, red team, plan critic,
operations) — принято без изменений. Дополнительная ревизия 100bsindex против кода дала §0.1: 3 принципиальных
правки (migration id, prompt version, purge-совместимый snapshot trigger) и 11 якорных/фактических, все с
`path:line`. Residual RISK-01/02/03/05/07/18/25/26/27 — явные ограничения с offline/versioned falsifiers.

## 20. Definition of Done для программиста

Открыв только этот файл, программист получает: construct (§1), таблицы/колонки как есть (§2), exact
preprocessing/formulas (§3–5), M12 DDL/порядок (§6), materialization/replay/GPU (§7), версии (§8), exact UI (§9),
validation (§10/14), упорядоченные one-day задачи с файлами:строками/алгоритмом/данными/тиром/deps/test/criterion/
условием/rollback (§11–13), интеграцию (§16), риски (§17), traceability (§18).

Механическая проверка плана:
- [x] Phase A R-01…R-42 все `unconditional`, без B/C/box/owner/real-DB зависимости.
- [x] Ни одна задача не начинается с «исследовать»; у каждой ровно один результат и один primary test.
- [x] fact_type/who/outcomes/live verbatim/replay/purge-trigger/dashboard-ctor дефекты имеют Phase-A owners.
- [x] Оба индекса работают при n=0/первом звонке и видимы при низкой уверенности.
- [x] Существующие BS/Admiralty/pattern/outcome/summary механизмы расширены, не заморожены/удалены
  (memory `research-build-on-existing`).
- [x] Версии формул/промпта (v002→v003)/схемы (M12) и миграция старых значений/rollback явны.
- [x] Phase B default baseline; `PROMPT_VERSION_ANALYZE` меняется только там.
- [x] Phase C валидирует только optional refinements; у Phase A нет входящих зависимостей от C.
- [x] Каждая числовая константа — code continuity, ROC-математика, алгебраический вывод или preregistered gate.
- [x] Каждый `path:line` в §0.1/§2/§11 проверен на `main@11fe81e` 2026-08-22 (grep + чтение); при дрейфе строк
  исполнитель ищет по имени символа, не по номеру.
