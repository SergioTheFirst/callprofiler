# BS-v2 — атомарный execution plan

Версия плана: `GPT90 / 2026-08-22`. Тир workstream: **T3**. Реализация начинается с R-01.
Production-код этим исследованием не изменён.

## 0. Решение одним абзацем

CallProfiler вводит всегда видимую пару:

```text
BS 0…100 = индекс наблюдаемых расхождений
confidence 1…100 = сила, качество, согласие и устойчивость основания этого BS
```

BS не является вероятностью лжи или типологией человека. Канон хранится на контакте
`(user_id, contact_id)`, поэтому работает после первого безымянного звонка; existing
`entity_metrics.bs_index`, `bs_formula_version`, `bs_thresholds`, Admiralty, patterns,
`contact_summaries.avg_bs_score` и `promise_outcomes` сохраняются и получают versioned projection.
Baseline `v2_roc_observed_1 / c1_effective_evidence_1` не использует owner labels, `fact_feedback`,
реальную БД, box или user-percentiles. Phase B refinements default-off; Phase C только доказывает,
что они не портят baseline.

## 1. Концепция и границы

### 1.1 Что измеряется

- слово ↔ последующий сохранённый status/сообщение об обязательстве;
- слово ↔ слово (`contradiction`);
- конкретика ↔ обещание (`promises[].vague`, подтверждённое текстом обещания);
- поддержанная transcript evidence самооценка `bs_score` как weakest fallback.

Общие `vagueness` и `blame_shift` не являются расхождением сами по себе: правдивый расплывчатый
ответ и обоснованное возложение ответственности возможны. Поэтому Phase A чинит их materialization
и сохраняет в patterns/context, но их direct BS weight равен 0. То же относится к `emotion_spike` и
обычному `claim` (последний служит opportunity denominator). Это решение развивает старый механизм,
не выдавая стиль за наблюдаемое слово↔дело/слово↔слово.

### 1.2 Что не измеряется

Ложь, безразличие к истине, ошибка, незнание, забывание, вежливое уклонение, рациональная смена
позиции и ASR-artifact не идентифицируются из этих данных. UI не пишет «лжёт», «честный»,
«ненадёжная личность» или диагноз. `BS=0` означает «пригодных расхождений не обнаружено», не
«человек честен». `BS=100` на первом звонке при confidence≤5 остаётся одним сильным, но
слабодоказанным наблюдением.

Основание: C-01/C-23; DePaulo <https://doi.org/10.1037/0033-2909.129.1.74>, Hauch
<https://doi.org/10.1177/1088868314556539>, Luke
<https://doi.org/10.1177/1745691619838258>, UNIDECOR
<https://aclanthology.org/2023.wassa-1.5/>.

## 2. Источники данных — точный current contract

| Источник | Поля | Роль baseline |
|---|---|---|
| `analyses` | `raw_response`, `canonical_json`, `schema_version`, `parse_status`, `risk_score`, `call_type`, `prompt_version`, `created_at` | JSON source + parse quality; risk/call type только context |
| v2 JSON | `structured_facts.fact_type/confidence/polarity/intensity/quote`, `bs_score`, `bs_evidence`, `promises[].who/what/vague` | C/P/V/D, supported M; confidence/polarity/intensity direct weight 0 |
| `transcripts` | `call_id,start_ms,end_ms,text,speaker` | who, UNKNOWN share, quote match |
| `calls` | `user_id,contact_id,call_datetime,created_at,role_fragile,call_type,duration_sec` | ownership/as-of/role quality; duration direct/quality weight 0 |
| `promises` | `user_id,contact_id,call_id,who,what,due,status` + m11 `vague,source_quote,quote_match,status_updated_at,status_method` | promise opportunity; system status fallback только с provenance/date |
| `events` | `event_type,who,status,confidence,deadline,source_quote` + m003 `fact_type,quote,…` + m11 provenance | grounded fact/opportunity; producer-safe replay |
| `promise_outcomes` | `promise_key,side,status,evidence_call_id,evidence_date,evidence_quote,days_late,method,confidence` | strongest B; unknown absent |
| `contact_features` | `feature_name,value,support_n,tier` | raw audit/context; all direct weights 0 in baseline |
| `contact_summaries` | `avg_bs_score` | existing legacy LLM-self diagnostic; не перезаписывать новым BS |
| `entity_metrics` | all counters, `bs_index,bs_formula_version` | existing graph projection; counters repaired |
| `bs_thresholds` | four percentile cutoffs | Phase B relative label only; never numeric baseline |
| `risk_thresholds` | risk percentiles | no BS role |
| `deep_facts` | `type,who,quote,call_id,contact_id,prompt_version` | direct weight 0; Phase B promise opportunity candidate |
| `mention_edges` | contact graph counts | direct/quality weight 0 |
| Admiralty/patterns | letter/digit and rule outputs | consumers, not independent evidence |

Проверенные defects, которые Phase A обязана исправить:

1. `graph/repository.py:399-415` теряет `fact_type`, пишет who UNKNOWN.
2. `graph/repository.py:503-511` группирует только event_type; aggregator ожидает невозможные
   broken/fulfilled event types; v1 реально ≤20.
3. Live/bulk не передают transcript; replay удаляет speaker markers.
4. Builder не SELECT-ит canonical_json; fact_id зависит от transient entity_id.
5. `graph/replay.py:61-72` обращается к `calls.id`, хотя PK `call_id`.
6. Prompt `Me|S2`, а outcome `_side` понимает `OWNER|OTHER`; `promises[].vague` теряется.
7. `parsed_ok` не проверяет BS fields; parse error превращает legacy average в 0.
8. Entity/map не гарантированы после первого звонка.

Полная карта: [`30-signal-audit.md`](30-signal-audit.md). Claims: C-02…C-07/C-21.

### 2.1 Реестр оснований, используемый задачами

| ID | Основание |
|---|---|
| S-CODE-01 | `graph/repository.py:399-415,503-511`, `graph/aggregator.py:44-51`: потеря type/who и structural-zero counters |
| S-CODE-02 | `graph/replay.py:61-72`, builder/replay callsites: неверный PK, transcript/provenance/replay defects |
| S-CODE-03 | `db/schema.sql`, `db/migrations.py`, graph/insight DDL: schema owners, latest migration 10, tenant rules |
| S-CODE-04 | `insight/promise_outcomes.py`: +120-day resolver, statuses/method/date и current `n>=3` reliability gate |
| S-CODE-05 | `insight/features/*.py`, `feature_store.py`: raw feature definitions, UNKNOWN/style confounds |
| S-CODE-06 | card/dashboard/digest/Admiralty/psychology modules, перечисленные в §9 и `30-signal-audit.md` |
| S-CONST | `CONSTITUTION.md`, T-03/T-08/T-15/T-19/T-23 и replay invariant `.claude/rules/graph.md` |
| S-DEC | DePaulo/Hauch/Luke/UNIDECOR из §1.2: linguistic cues не дают lie detector |
| S-PROM | Charness–Dufwenberg и Vanberg из §4.1: promises имеют наблюдаемый action/outcome criterion |
| S-PRAG | Hyland/Clayman/SIGDIAL, ссылки в `20-first-principles.md`: hedging/style зависит от жанра и функции |
| S-ROC | Edwards & Barron, <https://doi.org/10.1006/obhd.1994.1087>: ROC weights кодируют только ordinal rank |
| S-LLM | Xiong et al., ссылка §4.3: verbalized self-confidence модели не calibrated ground truth |
| S-PHIA | UK PHIA, ссылка §5: analytic confidence отделяется от содержания assessment |
| S-SIM | Morris/Sargent/Hubert–Arabie, ссылки §10: ADEMP, verification/validation и ARI scope |

`Почему` каждой R-задачи ссылается одновременно на C-n и один или несколько S-ID; полный
source→dispute→decision→task→test→criterion дан в §18.

## 3. Preprocessing и defaults

### 3.1 Дата и свежесть

Core functions обязаны принимать `as_of_date`; `datetime.now()` запрещён. Для BS это **contact-local
watermark**: explicit CLI `--as-of` имеет приоритет, иначе resolver берёт max persisted domain date
только строк данного `(user_id,contact_id)` — call/evidence/status date, затем persisted `calls.created_at`.
Live вызывает resolver уже после регистрации current call; дата никогда не берётся прямо из порядка
обработки. Новый звонок контакта A поэтому не старит B, out-of-order звонок A не откатывает A, а replay
получает ту же карту contact→as_of. **До decay**
строки с `source_date > as_of_date` исключаются: `max(age,0)` не имеет права превращать будущее в
«свежее». Для оставшихся строк:

```text
r(age_days) = 2 ** (-max(age_days, 0) / 180)
```

180 — existing `RELATION_DECAY_DAYS` и Admiralty window (C-16), не empirical human constant.

### 3.2 Provenance и дедуп

```text
normalize_text = NFKC → lowercase → ё→е → collapse whitespace → trim outer punctuation
normalized_entity_key = normalize(entity_type|canonical normalized_key)
fact_id = sha256(user_id|call_id|normalized_entity_key|fact_type|who|normalize_text(quote))[:16]
```

Если valid fact не имеет entity association, stable sentinel `__contact__` используется вместо NULL;
два разных normalized entity keys с одной цитатой остаются разными facts.

В score входит только fact с `who='OTHER'`, quote length ≥8, `quote_match>=0.72`, fact confidence
existing gate ≥0.6 (`graph/validator.py`, `graph/config.py`). После gate численное LLM-confidence не
является ни весом, ни confidence-credit; переход через gate отдельно меняет eligibility. UNKNOWN не
присваивается контакту. M11 маркирует существующие builder rows с `fact_id IS NOT NULL` как
`graph_v1`, прочие как `legacy`; новый builder пишет `graph_v2`. Full replay заменяет только
`graph_v1|graph_v2`. Promise dedup — `(user_id,contact_id,existing promise_key)`; один source call даёт не более одного
nonbehavior confidence-credit.

Один grounding contract применяется к fact, promise и M-support. Raw candidate span после `strip`
имеет ≥8 Unicode code points; production `FactValidator` rolling match даёт `ratio>=0.72`; найденный
span находится после последнего `[s2]` до следующего role marker, поэтому `OTHER`. `UNKNOWN`, `[me]`
и transcript-less rows не score-eligible, но dated attempt сохраняется для confidence denominator.
Для structured fact дополнительно `confidence>=0.60`. `valid OTHER promise` означает canonical
`side=OTHER`, boolean `vague` присутствует и quote проходит этот contract. Quote выбирается
детерминированно: сначала grounded `structured_fact.fact_type=promise` с совпадающим
`normalize_text(value)==normalize_text(what)`, иначе best rolling window для `what`; ties — earliest
character offset. Именно найденный raw window пишется в `promises.source_quote`, а ratio — в
`quote_match`; unmatched promise сохраняется, но не входит в P. M available только при valid bs_score и
хотя бы одном OTHER support: grounded `bs_evidence` string либо grounded structured fact type
`contradiction|vagueness|blame_shift|emotion_spike`, либо grounded promise с `vague=true`; bare `claim`
и конкретное обещание M не поддерживают. Для v001 `bs_evidence` не имеет type/confidence, поэтому ему
нужны только span/role gates; оно остаётся одним support, а не отдельным score-сигналом.

### 3.3 Missing/zero

- Empty denominator → component missing, не 0.
- Валидное `vague=false`, kept/fulfilled, отсутствие discrepancy при наличии opportunity → 0.
- `unknown/open`, invalid parse, ungrounded quote → missing.
- Ни одного component → `BS=0.0`, `confidence=1`, `no_evidence=true`.
- User-z-score никогда не baseline input. Raw feature missing → neutral context, direct weight 0.

## 4. Формула BS `v2_roc_observed_1`

### 4.1 Behavior `B`

Только обязательства контакта; `promise_outcomes` приоритетнее явного status.

```text
y(kept|fulfilled) = 0
y(broken)         = 1
y(late,d)         = 1 - 2 ** (-max(d or 3, 3) / 14)
g(det|explicit)   = 1
g(llm+grounded)   = 1/2
g(llm ungrounded) = 0
B = sum(r_i*g_i*y_i) / sum(r_i*g_i)
```

Exact source table: `promise_outcomes kept/late/broken` maps above; `unknown` missing. Timestamped
system `promises.status fulfilled→0, broken→1`; `open` missing. Legacy/event `resolved|expired` is
semantically ambiguous and missing unless a canonical outcome row resolves it. Outcome LLM numeric
`confidence` never changes `g`; grounding/date decide eligibility.

2-day grace, two-week phrase и current det/LLM split уже существуют в `promise_outcomes.py`; `3/14`
являются versioned continuity constants. `7/14/28` входят в offline sensitivity. Источник порядка:
Charness & Dufwenberg <https://doi.org/10.1111/j.1468-0262.2006.00719.x>, Vanberg
<https://doi.org/10.3982/ECTA7673>; ограничение — C-05/C-09.

### 4.2 Grounded language `L`

Baseline использует два construct-near сигнала. Для каждого call `j`: `c_j∈{0,1}` — присутствует
валидное OTHER-contradiction; opportunity `oC_j∈{0,1}` — есть валидный OTHER claim/contradiction.
Для promises сначала dedup по `(call_id, normalize_text(what))`, затем
`p_j=vague_valid_promises_j/all_valid_OTHER_promises_j`. Так один LLM response не псевдореплицирует
confidence, но несколько обещаний меняют долю неконкретных обещаний внутри call.

```text
C = sum(r_j*c_j) / sum(r_j*oC_j)
P = sum(r_j*p_j) / sum(r_j) over calls with >=1 valid OTHER promise
L = (3*aC*C + 1*aP*P) / (3*aC + 1*aP)
```

`a*=1` при nonempty opportunity denominator. `(3,1)/4` — two-rank ROC для normative construct order
`contradiction > promise-local vagueness`, а не effect sizes; когда доступен один компонент,
renormalization намеренно убирает внутренний rank. General `vagueness`, `blame_shift`, `claim` и
`emotion_spike` materialized, но direct weight 0. Общие hedge, specificity, formality, request balance,
tempo, emotion palette, accommodation также имеют direct weight 0: литература описывает
style/pragmatics, не discrepancy. Основание C-06…C-08/C-27; ROC:
<https://doi.org/10.1006/obhd.1994.1087>.

### 4.3 Model self-score `M`

```text
M = sum(r_i * bs_score_i/100) / sum(r_i)
```

Звонок available только при structurally valid `bs_score` и хотя бы одном grounded structured
discrepancy или grounded `bs_evidence`. Unsupported score missing. Raw LLM confidence не входит.
Основание C-11; Xiong et al.
<https://proceedings.iclr.cc/paper_files/paper/2024/hash/6733cf15e10e2cd1d59af033c3bb8507-Abstract-Conference.html>.

### 4.4 Aggregation

```text
z = 11*aB + 5*aL + 2*aM
BS = 0.0                                      if z == 0
BS = round_half_up(100*(11*aB*B+5*aL*L+2*aM*M)/z, 1) otherwise
```

Weights `(11,5,2)/18` — ROC для **заданного Goal и construct-nearness order**
`behavior > grounded language > model self-score`, не эмпирические effect sizes. Available
weights перенормируются: missing behavior не считается kept. Golden examples:

- `B=.50,L=.80,M=.90 → BS=62.8`;
- `B=missing,L=.9375,M=.80 → BS=89.8`;
- all missing → `BS=0.0,no_evidence=true`.

## 5. Confidence `c1_effective_evidence_1`

### 5.1 Typed evidence clusters и effective evidence

Каждый candidate credit — tuple
`(family,source_call_id,source_date,value,potential,qualified,P_i,R_i,V_i,tie_key)`. Строка обязана иметь
`source_date<=as_of`; иначе unavailable. Exact class contract:

| class | potential / qualified credit | source date | `P_i` | `R_i` | `V_i` |
|---|---:|---:|---:|---:|---:|
| B deterministic outcome | `1 / 1` iff complete | persisted `evidence_date` | 1 iff resolver status/call/date valid | evidence-call `min(1-UNKNOWN_share,.7 if fragile)` | exact persisted transcript quote→1, else 0 |
| B grounded LLM outcome | `1/2 / 1/2` iff complete+grounded | persisted `evidence_date` | 1 iff canonical status/prompt/call/date valid | evidence-call rule | recomputed quote match |
| B system status fallback | `1 / 1` iff timestamped provenance | `status_updated_at` | 1 iff enum/writer/date valid | source-call rule if present, else 1 | auditable system transition→1 |
| L source call | `5/11`; qualified `5/11` iff valid grounded C/P | call date | relevant fields valid→1, otherwise 0 | source-call rule | minimum quote match among used C/P rows |
| M source call | `2/11`; qualified `2/11` iff valid score+support | call date | score and support structurally valid→1 | source-call rule | maximum grounded-support quote match |

`parse_failed|output_truncated` analysis создаёт L potential attempt `5/11`, но qualified=0;
`parsed_partial` пригоден лишь когда именно используемые поля полны. Rejected quote, role→UNKNOWN,
subthreshold fact confidence и ungrounded LLM outcome сохраняют potential attempt и rejection_reason,
но qualified=0. Успешный parsed call без BS opportunities получает potential=0, поэтому empty calls
не штрафуют и не награждают. Missing outcome date/status-transition date не позволяет вычислить
recency: row полностью исключается из N/E и учитывается только в `details.undated_excluded`; promise
creation date никогда не заменяет outcome date. Dated ungrounded/rejected rows сохраняют potential.
Numeric outcome/LLM confidence после eligibility не меняет credit.

L и M хранятся как два candidate credits до call-level reduction. Для одного source call:

```text
q_x = (P_x*R_x*V_x) ** (1/3)                 # для каждого candidate/behavior cluster
N_call = max(r*p_L, r*p_M)
E_call = max(r*qualified_L*q_L, r*qualified_M*q_M)
```

Это определяет, например, rejected L + qualified M как `N=5/11,E=2/11`; P/R/V разных candidates
не смешиваются в один tuple. Behavior outcomes остаются отдельными dedup clusters.

```text
N = sum_behavior(r_i*potential_i) + sum_source_calls(N_call)
E = sum_behavior(r_i*qualified_i*q_i) + sum_source_calls(E_call)
coverage = N/(N+3)
```

`3` — behavior-equivalent evidence units: существующий `contact_reliability` впервые публикуется при
`n>=3` resolved outcomes (S-CODE-04), поэтому это versioned half-coverage point, а не число классов.
Sensitivity `K∈{2,3,5}` обязателен; смена K требует новой confidence version.

### 5.2 Quality

Для всех potential clusters:

```text
Q = E/N if N>0 else 0
```

`0.7=1-0.3`, где 0.3 — current role-fragile threshold. Pairing не теряется: сначала geomean одного
cluster; `coverage*Q=E/(N+3)`. Clean→rejected сохраняет N и уменьшает E; новый rejected attempt
увеличивает N при прежнем E. Уверенная OWNER↔OTHER перестановка без UNKNOWN наблюдаемо неотличима и
остаётся residual risk; synth не обещает, что C её обнаружит. `confidence` LLM не поднимает P/V.

### 5.3 Agreement и stability

```text
A = 1-abs(B-L)                               if aB and aL
A = 0                                        otherwise

S = 1-abs(BS_raw_early-BS_raw_late)
```

Флаги `aB/aL/aM` проверяют availability, а не truthiness: доступный 0 не равен missing. M никогда не
участвует в agreement: он common-mode с L. Split строится по clusters после future-filter. Полный
ключ сортировки — `(source_date,family_rank,stable_ref)`, где behavior имеет
`family_rank=0, stable_ref=promise_key`, а call-level L/M reduction —
`family_rank=1, stable_ref=source_call_id`; даты — canonical UTC ISO-8601, ids сравниваются как integers,
`promise_key` — как UTF-8 bytes. Эти типы сравниваются только внутри своего `family_rank`, поэтому ключ
тотален и replay-stable. При нечётном n extra cluster идёт
в позднюю половину; используется unrounded `BS_raw`. S доступна только если halves имеют `E>=2`
каждая; иначе 0. B и L — operationally distinct, но не статистически независимы из-за общего
ASR/role path. M не участвует в A. Split-half — repeatability, не truth.

### 5.4 Итог и anchors

```text
C = clamp(round_half_up(1 + 99*coverage*Q*(1+A+S)/3), 1, 100)
```

- 30: предварительное основание; agreeing B/L при Q=1,S=0 начинает display C30 при `E=2.28`
  (raw C30 at E=2.35135). Stable one-line физически становится доступна только при E≥4 и тогда C39.
- 60: устойчивое основание; reference Q=A=S=1 пересекает display 60 при `E=4.333…`; одна очень
  stable one-line начинает display C60 при `E=23.4` (raw C60 at E=25.2857), поэтому label не означает
  «подтверждено двумя».
- 90: сильное основание; reference Q=A=S=1 пересекает display 90 при `E=25.2857…`.

| Clean effective `N=E` | C при A=0 | C при A=1 | Условие S |
|---:|---:|---:|---|
| 0 | 1 | 1 | 0 |
| 1 | 9 | 18 | 0 |
| 3 | 18 | 34 | 0 |
| 10 | 52 | 77 | 1 |
| 100 | 65 | 97 | 1 |

Для свежих raw observations (идеальное Q, chronological split становится доступен только при
`E_half>=2`) method matters:

| raw n | B-only | L-only (`5/11`) | M-only (`2/11`) |
|---:|---:|---:|---:|
| 0 | 1 | 1 | 1 |
| 1 | 9 | 5 | 3 |
| 3 | 18 | 11 | 6 |
| 10 | 52 | 41 | 13 |
| 100 | 65 | 63 | 58 |

На первом звонке без будущего outcome максимум nonbehavior-credit `E=5/11`, A=S=0; при Q=1
получается **C≤5**. Это не мешает показать любой BS 0…100, но честно маркирует single-call basis.

Ни duration, ни empty calls, ни raw LLM confidence после eligibility не дают credit. Формула monotone
по E при fixed Q/A/S; controlled снижение P/R/V при неизменной availability/value не повышает C.
Произвольная censoring/missingness может менять composition и не имеет ложной pointwise-гарантии;
end-to-end noise проверяется агрегатным preregistered synth contrast. Основание C-12…C-18/C-29;
analytic confidence:
<https://www.gov.uk/government/publications/explaining-uncertainty-in-uk-intelligence-assessment>.

`contact_age_estimates.confidence` задаёт общий продуктовый контракт диапазона `1…100`: малое число
означает слабое основание, а не отрицательный вывод. Его конкретная age formula не переиспользуется:
звонки/токены без BS-evidence не должны поднимать BS confidence. Existing
`insufficient_evidence` T-15/T-23 отображается как `C<30 → мало данных`; в отличие от trait quarantine,
сама пара BS/C остаётся видимой по owner veto.

## 6. Схема БД и migration старых значений

Следующая central migration — **11**, одна запись в `db/migrations.py::ALL_MIGRATIONS` и синхронный
`db/schema.sql`. Применённые 1…10 не редактировать.

```sql
CREATE TABLE contact_bs_metrics (
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

CREATE TABLE bs_legacy_snapshots (
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

CREATE TABLE relation_evidence (
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
```

`details_json` schema is frozen as `bs-details-1`; unavailable component is JSON `null`, an observed
zero is `0.0`:

```json
{
  "schema": "bs-details-1",
  "as_of": "YYYY-MM-DD",
  "components": {"behavior": null, "contradiction": null, "promise_vague": null,
                 "language": null, "model": null},
  "available": {"behavior": false, "contradiction": false, "promise_vague": false,
                "language": false, "model": false},
  "confidence": {"potential_mass": 0.0, "qualified_mass": 0.0, "quality": 0.0,
                 "agreement": 0.0, "stability": 0.0, "k": 3,
                 "undated_excluded": 0, "rejection_reasons": []},
  "evidence_refs": []
}
```

`rejection_reasons` and `evidence_refs` are sorted stable identifiers (`B:promise_key`, `L:fact_id`,
`M:call_id`), never display counts/quotes by themselves. `source_signature` is lowercase SHA-256 of
compact UTF-8 sorted-key JSON `bs-input-1` containing user/contact/as_of, both formula versions and the
ordered preprocessed source rows/values; it excludes `computed_at`, transient entity ids, UI policy and
reader flags. Therefore config display flips cause 0 recompute while source/version change cannot collide.
`callset_signature` is a second lowercase SHA-256 over compact sorted `bs-callset-1` tuples
`(source_md5,domain_date)` for every same-contact call visible at `computed_as_of`, including a call with
missing/failed analysis. A successful recompute stores the current value; the routed view recomputes it
read-only. Inequality means the persisted pair predates at least one associated call and sets `stale=true`;
status/pipeline transitions alone cannot create or clear the marker.

M11 также:

- unique parent key `contacts(user_id,contact_id)` и INSERT/UPDATE ownership triggers на
  `contact_bs_metrics`; cross-owner row обязан `RAISE(ABORT,'contact owner mismatch')` даже при
  неверно отключённом FK;
- `bs_legacy_snapshots` получает тот же same-owner INSERT guard для non-NULL `contact_id` и
  `BEFORE UPDATE`/`BEFORE DELETE` triggers с `RAISE(ABORT,'immutable legacy snapshot')`; entity snapshot
  может иметь NULL contact, contact fallback обязан иметь same-owner contact; единственная повторная
  операция — byte-neutral `INSERT OR IGNORE` по stable PK;
- `contacts.placeholder_key TEXT` и unique partial index `(user_id,placeholder_key) WHERE
  placeholder_key IS NOT NULL`; новый phone-less call получает literal `md5-<lower source_md5>`, existing
  phone-less contact backfill — lexicographically first linked source_md5, иначе `contact-<contact_id>`;
  placeholder никогда автоматически не merge'ится и служит local artifact key. Затем M11 в порядке
  `(user_id,call_id)` обрабатывает **все** existing `calls.contact_id IS NULL`: `INSERT OR IGNORE` same-owner
  placeholder `md5-<lower source_md5>`, guarded UPDATE links call, and `INSERT OR IGNORE` seeds its
  `v2_roc_observed_1/c1_effective_evidence_1` BS0/C1 row with callset signature. Это включает status=done;
  migration не ждёт replay/enrichment/owner и rollback транзакции не оставляет orphan contact;
- `promises.vague INTEGER CHECK(vague IN (0,1))`, `source_quote TEXT`,
  `quote_match REAL CHECK(quote_match BETWEEN 0 AND 1)`, `status_updated_at TEXT`,
  `status_method TEXT NOT NULL DEFAULT 'legacy' CHECK(status_method IN ('det','system','llm','legacy'))`;
- carry existing migration-3 `events.fact_type`/`quote` into fresh `schema.sql` unchanged (never edit m003),
  and add `normalized_entity_key TEXT`,
  `quote_match REAL CHECK(quote_match BETWEEN 0 AND 1)`,
  `quote_verified INTEGER NOT NULL DEFAULT 0 CHECK(quote_verified IN (0,1))`,
  `producer TEXT NOT NULL DEFAULT 'legacy' CHECK(producer IN ('legacy','graph_v1','graph_v2'))`;
- `contact_summaries.bs_index REAL`,
  `bs_confidence INTEGER NOT NULL DEFAULT 1 CHECK(bs_confidence BETWEEN 1 AND 100)`,
  `bs_formula_version TEXT NOT NULL DEFAULT 'legacy'`,
  `bs_confidence_version TEXT NOT NULL DEFAULT 'legacy'`, `bs_as_of TEXT`; existing `avg_bs_score`
  остаётся legacy M diagnostic;
- `entity_metrics.bs_confidence INTEGER NOT NULL DEFAULT 1 CHECK(bs_confidence BETWEEN 1 AND 100)`,
  `bs_confidence_version TEXT NOT NULL DEFAULT 'legacy'`, `bs_components_json TEXT NOT NULL DEFAULT '{}'`,
  `bs_source_signature TEXT NOT NULL DEFAULT ''`, `bs_as_of TEXT`,
  `bs_projection_status TEXT NOT NULL DEFAULT 'legacy' CHECK(bs_projection_status IN
  ('contact','unmapped','ambiguous','legacy'))`; existing score/version remain;
- `bs_thresholds.bs_formula_version TEXT NOT NULL DEFAULT 'legacy'`,
  `policy_version TEXT NOT NULL DEFAULT 'legacy'`, чтобы legacy percentiles не применились к v2;
- `graph_replay_runs.run_signature TEXT`, `as_of TEXT` и unique `(user_id,run_signature)`; full replay
  UPSERT'ит deterministic signature вместо append, поэтому второй identical run даёт row growth0;
- `relations.producer TEXT NOT NULL DEFAULT 'graph_v1' CHECK(producer IN ('graph_v1','graph_v2'))` и
  `source_signature TEXT NOT NULL DEFAULT ''`; M11 помечает existing aggregate rows graph_v1.
  `relation_evidence` выше — rebuildable per-call ledger, не новый BS signal: `evidence_key` есть SHA-256
  compact tuple `(user_id,source_md5,relation_array_index,raw endpoint types/keys,relation_type)`. INSERT/
  UPDATE triggers требуют same-owner `source_call_id`; indexes `(user_id,raw_src_type,raw_src_key,
  raw_dst_type,raw_dst_key,relation_type)` и `(user_id,source_call_id)`. Migration детерминированно
  materializes it from valid stored v2 `analyses.raw_response.relations` in call/array order (invalid rows
  counted in migration report, no guess); it does not call a model. Fresh/graph DDL совпадают;
- fresh `schema.sql` наконец включает columns existing migrations 2/3/4; updated
  `graph/repository.py::_GRAPH_DDL` и `insight/repository.py` DDL создают тот же contract независимо
  от порядка `init_db/apply_graph_schema/apply_insight_schema`.

M11 детерминированно выполняет
`UPDATE events SET producer='graph_v1' WHERE fact_id IS NOT NULL` и оставляет `legacy` только при
`fact_id IS NULL`: в current code `fact_id` создаёт именно GraphBuilder, а generic source-event writer
его не пишет. Upgrade fixture фиксирует это допущение; неоднозначная строка остаётся legacy и попадает
в migration report, а не удаляется.

До первой v2 projection scoped backfill `INSERT OR IGNORE` сохраняет v1 entity payload по stable
`entity_type|normalized_key` и contact fallback из неизменяемого `avg_bs_score`. Различаются три
имени: `v1_legacy_snapshot` (точное историческое), `v1_linear_repaired_1` (replay-compatible
сравнительный старый алгоритм на починенных counters) и `v2_roc_observed_1` (baseline). Команда
`bs-recompute --user USER --as-of DATE` строит versioned canonical rows, затем projections. При ошибке
snapshot/v1 остаётся. UI до backfill показывает legacy number + `C=1, мало данных`; first-contact
initializer всегда создаёт baseline `0/1` row. DDL целиком и type/default matrix фиксируются R-01;
никакой implementation choice не оставляется миграции.

## 7. Recompute, replay и GPU

Единая pure pipeline:

```text
stored analyses/events/promises/outcomes/features/transcripts
  → assemble_contact_bs_inputs(user, contact, as_of)
  → compute_bs_v2(inputs) + compute_bs_confidence(inputs)
  → UPSERT contact_bs_metrics + contact_summaries projection
  → entity_contact_map projection → entity_metrics
```

Contact — единственный BS-v2 canon. После user-scoped map rebuild:

- `COUNT(DISTINCT contact_id)=1` → exact contact pair/version/signature, status `contact`;
- `=0` → deterministic `v1_linear_repaired_1`, `C=1`, status `unmapped`;
- `>1` → не выбирать «лучший» contact: тот же compatibility score, `C=1`, status `ambiguous`.

Несколько mapping-method rows к одному contact считаются однозначными; два entity могут безопасно
проецировать один contact. При unique→ambiguous прежняя contact projection очищается. Ни прямого
равенства numeric ids, ни неопределённого entity-only v2 scorer нет.

Compatibility scorer для состояний `unmapped|ambiguous` — не имя без формулы, а точное продолжение
существующего `graph/aggregator.py::_bs_v1_linear` на починенных R-07/R-09 counters:

```text
safe_p = max(total_promises, 1)
safe_c = max(total_calls, 1)
v1_raw = .40*(broken_promises/safe_p)
       + .20*min(contradictions/safe_c, 1)
       + .15*min(vagueness_count/safe_c, 1)
       + .15*min(blame_shift_count/safe_c, 1)
       + .10*min(emotional_spikes/safe_c, 1)
v1_linear_repaired_1 = min(100*v1_raw, 100)       # float, без нового rounding
```

`total_calls` здесь сохраняет v1-семантику `COUNT(DISTINCT events.call_id)`, не все calls контакта;
меняется только происхождение counters: `COALESCE(fact_type,event_type)` и canonical outcomes.
Это только совместимая entity-проекция, не canon и не fallback BS-v2 контакта. Golden vectors:
all counters 0→`0.0`; one broken of one promise with one call→`40.0`; по одному каждому из пяти
numerators при denominators 1→`100.0`; broken=2/promises=1 and all others zero→`80.0`, тогда как
contradictions=2/call=1 остаётся `20.0`. `fulfilled_promises` сохраняется, но в историческую формулу
не добавляется. `v1_legacy_snapshot` — единственный byte-exact historical rollback; repaired
comparator историческим значением не называется.

После R-20 единственная mutating facade называется
`recompute_contact_bs_and_projections(conn,user_id,contact_id,as_of,uow)` и выполняет строго
R-18 canonical → R-19 contact summary → R-20 all uniquely mapped entity projections. Live, bulk,
outcome hook, feature/autofit и replay не вызывают эти три шага по отдельности. Outcome counters
имеют дополнительный порядок: map rebuild → R-09 outcome-counter recompute → эта facade.

- Contact association: до enrichment общий repository API `register_call_with_baseline(...)`, вызываемый
  и `ingest/ingester.py`, и `bulk/loader.py`, одним UoW создаёт/находит normal contact либо, при отсутствии phone,
  отдельный contact с `placeholder_key=md5-<source_md5>`, связывает call и делает `INSERT OR IGNORE`
  baseline `BS0/C1/no_evidence`; повторный call никогда не сбрасывает накопленное. Placeholder не
  auto-merge'ится с именем/другим phone-less call. Card artifact key — canonical phone либо
  `unknown-<placeholder_key>`; NULL phone не отменяет local card. Analysis success обогащает строку синхронно до delivery;
  analysis/scorer failure оставляет 0/1 (или прежнее значение), пишет `calls.status='error'` с
  stage-qualified message и запрещает transport delivery. Terminal adapter R-31 затем атомарно
  публикует local minimal card, но не Telegram; до R-30/R-31 временного direct-write пути нет.
- Full `graph-replay --apply`: только весь user scope; repair call_id → canonical payload → role-tagged
  transcript → удалить user/call rows `producer IN ('graph_v1','graph_v2')` → strict builder → map
  rebuild → R-09 counters → contact BS → summary → entity projection. Весь rebuild одна
  UoW/SAVEPOINT. Schema helpers run and commit once before `BEGIN` and are never called inside;
  this additive schema preflight is a separate migration transaction, and replay pre-state hashes are
  captured only after it succeeds. A replay failure may leave the already-valid schema upgrade, never partial
  graph/data; a preflight failure starts no replay.
  map/mention/repository/aggregator writers use caller-controlled commit/`commit_unless_uow`, so no
  nested `commit()` пробивает outer UoW. Любое per-fact либо
  post-projection exception поднимается и откатывает pre-run hash. `--limit` разрешён только preview
  на `:memory:` backup из query-only source с обязательным ROLLBACK; `--limit --apply` — config error до DB open.
- Replay защищает unrebuildable ownership: seed set содержит entity ids из `producer=legacy` rows,
  `entity_profiles`, обоих FK каждой `entity_merges_log` row и обеих сторон `entities.merged_into_id`;
  protected set — transitive closure этого merge graph. Entity rows, profiles, merge logs и legacy refs
  сохраняются byte-for-byte; builder переиспользует их stable `(user,type,normalized_key)` без UPDATE core.
  Raw key архивированного duplicate всегда проходит same-user acyclic `merged_into_id` chain до terminal
  canonical id, и новые derived facts/relations крепятся только к canonical; cycle, cross-owner, missing
  terminal, duplicate/missing protected stable key fail before mutation. Удаляются лишь unprotected derived
  entities. Replay-run signature — hash user/contact-as_of-map/ordered target source signatures/formula versions;
  identical run UPSERT'ится byte-neutral.
- Один `resolve_contact_bs_as_of(user_id,contact_id,explicit)` используется live/bulk/replay/autofit.
  Он реализует exact contact-local §3.1 contract; значение вычисляется один раз до scorer/UoW и передаётся
  во все BS helpers. Full replay signature включает sorted map `(contact stable key,as_of)`, а scalar
  `graph_replay_runs.as_of` хранит explicit value либо max карты только как audit metadata. Два контакта
  с interleaved dates не влияют на watermarks друг друга.
- Relation decay не делит с BS ложный user-global clock. Builder materializes every stored
  `raw_response.relations` row once into M11 `relation_evidence`; retry replaces only that call's graph_v2
  ledger rows inside the caller UoW, collecting old∪new affected keys, then recomputes each projection from
  its ledger (не O(N) reparse). `source_date=call_datetime`, fallback persisted `calls.created_at`; undated
  impossible rows audit/reject. При explicit replay date future rows
  исключаются; иначе local anchor `t*=max(source_date)` этого relation key. После canonical merge routing:
  `weight=math.fsum(conf_i*2**(-days(t*-source_date_i)/180))` по sorted
  `(source_date,source_md5,relation_array_index)`; `confidence=weight/math.fsum(decay_i)`;
  `call_count=COUNT(DISTINCT source_md5)`. `first_seen_call_id`/`last_seen_call_id` — calls у min/max того
  же tuple; `created_at`/`updated_at` — exact first/anchor persisted datetimes. Projection signature hashes
  sorted ledger inputs and merge routes; equal signature makes 0 UPDATE. A key with no remaining evidence
  deletes only its graph_v2 projection. Live recomputes old∪new keys touched by a call; replay replaces all
  graph_v1/v2 ledger/projections and recomputes all keys. Поэтому algebra
  commutative/order-independent, wall clock отсутствует и две equal-confidence строки age0/180 дают
  weight `1.5`, не `2` и не `1`.
- `archetypes-fit/features-build`: после raw `contact_features` persist вызывает тот же scorer; feature
  weights 0 baseline, но hook гарантирует future version parity.
- Watcher autofit: вызывает scorer, но first-call live path от autofit не зависит.
- `promise-outcomes`: synchronous `use_llm=False` refresh возвращает changed promise keys/contacts;
  pipeline вызывает scorer один раз. Ошибка получает обычный observable call error, не выдуманный
  outbox/derived-job state.
- CPU/SQLite only. Никакого LLM, ASR, pyannote или torch import. Existing `_unload_models()` перед LLM
  не меняется. Phase B вводит stdlib cross-process exclusive lock
  `<data_dir>/locks/gpu-phase.lock`: watcher/orchestrator держит его от первого ASR/pyannote load через
  unload до конца своей LLM phase; standalone canary берёт тот же lock nonblocking и fail-closed до
  `LLMClient.ensure_ready`, если pipeline активен. Metadata не заменяет OS advisory lock.

## 8. Versioning

- `bs_formula_version='v2_roc_observed_1'`.
- `confidence_formula_version='c1_effective_evidence_1'`.
- `policy_version='bs_ui_fixed_1'`.
- `bs_read_version='baseline|legacy'`; R-17 добавляет safe default=`legacy`, а финальный release slice
  R-42 после всех Phase-A gates атомарно меняет static default на `baseline`. Flip меняет
  только reader route, делает 0 DB writes. Единственный `BSView` имеет
  `(score,confidence,score_version,confidence_version,source,computed_as_of,stale)`, где source ровно
  `canonical|legacy_snapshot|avg|zero`. Legacy route читает immutable snapshot/unchanged avg; baseline
  сначала exact pair `(v2_roc_observed_1,c1_effective_evidence_1)`, затем те же read-only fallbacks.
  `legacy_snapshot|avg` всегда дают C1 и mandatory marker `предыдущий расчёт`; zero даёт 0/C1 и
  `нет пригодных данных`. Canonical сравнивает stored/current `bs-callset-1`; mismatch ставит stale и
  mandatory `последний звонок не учтён`, сохраняя persisted pair. Card/dossier/list/digest/Telegram,
  Admiralty и advice принимают только этот typed view — ни одна surface не повторяет fallback SQL. Offline test
  доказывает `legacy→baseline→legacy→baseline` byte-equivalence; confidence-only version bumps
  сосуществуют, потому что обе версии входят в PK/UPSERT/reader key.
- Formula change всегда новая versioned canonical row + recompute; old rows не перезаписываются и не
  silent reinterpretation.
- `PROMPT_VERSION` **не меняется в Phase A**. `analyze_v002.txt` создаётся только R-46 Phase B,
  default-off; cache key/version bump обязателен. Включение возможно лишь после read-only M4 R-49.

## 9. UI contract

Канонический `bs_index` хранится half-up с одним десятичным знаком. Все user-facing поверхности
получают `BS_display=0`, только если stored `bs_index==0.0`; иначе
`BS_display=max(1,round_half_up(bs_index,0))`. Fixed bands, Admiralty letter и advice сравнивают именно
этот integer, поэтому ненулевое наблюдение не превращается в видимое «0/не обнаружено». Например,
`0→0`, `0.1→1`, `0.4→1`, `0.5→1`, `50.4→50→C`, `50.5→51→D`. `bs_confidence` уже integer и не
округляется повторно.

### 9.1 Card ≤512 UTF-8 bytes

Full и minimal card всегда содержат одну mandatory whole line:

```text
bs: 52/100 · увер. 12/100 · мало данных
```

`мало данных` при C<30. Typed renderer выбрасывает optional whole lines, но никогда эту строку;
считает UTF-8 bytes. Для legacy source строка заканчивается `· предыдущий расчёт`, для zero —
`· нет пригодных данных`, для stale canonical — `· последний звонок не учтён`; эти suffix также
mandatory и применяются в указанном порядке после `мало данных`. Existing `grade:` остаётся:

```text
grade: F6 — данных мало, основание недостаточно
```

Card publish — existing `artifacts.atomic_*`, не `Path.write_text`.

### 9.2 Admiralty

Info digit — CP-specific evidence strength, не probability:

```text
C >= 90 → 2 «основание сильное»
C >= 60 → 3 «основание устойчивое»
C >= 30 → 4 «основание предварительное»
C <  30 → 6 «основание недостаточно»
```

`source!=canonical` или `stale=true` принудительно даёт F6 независимо от сохранённых score/C; stored pair
остаётся видим рядом с mandatory source/freshness marker, поэтому старое число не переименовано и не
выглядит актуальным.

Сохранены current digits 2/3/4/6 и anchors Goal. Letter сохраняется: C<30→F; иначе absolute fallback
BS≤25→B, ≤50→C, ≤75→D, >75→E. A сохраняет current extra contract: low BS + kept_ratio≥.8 + resolved
n≥5, но дополнительно C≥90. `bs_thresholds` может показать relative context в Phase B, не меняя
letter/numeric baseline. Exact `SOURCE_PHRASES` запрещают trait language:

| Letter | Exact observable phrase |
|---|---|
| A | `сохранённые обязательства выполнялись; расхождений мало` |
| B | `наблюдаемых расхождений мало` |
| C | `есть отдельные наблюдаемые расхождения` |
| D | `наблюдаемые расхождения повторялись` |
| E | `наблюдаемых расхождений много` |
| F | `основание недостаточно; индекс предварительный` |

Запрещены `надёжен|ненадёжен|держит слово|не держит слово|честный|лжец` как свойства человека.

### 9.3 Dossier, digest, Telegram, advice, patterns

- Dossier: tiles `BS 52/100`, `Уверенность 12/100`; рядом mandatory routed marker; tooltip с §1.2;
  component/evidence drilldown без
  диагнозов, call/fact/outcome counters и duration.
- People list: compact `BS 52 · C12` из `BSView`, с тем же source/freshness marker.
- Digest/Telegram shared line: `BS 52/100; увер. 12/100 — мало данных.`; legacy дополняет
  `Предыдущий расчёт.`, zero — `Нет пригодных данных.`, stale — `Последний звонок не учтён.`;
  ≤300 chars, без n/count/duration.
- Advice decision table: `C<30 → Оценка предварительная`; иначе `BS_display=0 → Расхождений в
  пригодных данных не обнаружено`; `1≤BS_display≤50 → Наблюдались отдельные расхождения`;
  `BS_display>50 → Проверяй сроки и конкретику`. Эти строки могут
  соединяться только через `; ` и остаются ≤300 символов. Удалить `держит слово`/`Надёжный партнёр`;
  удалить вывод «Надёжный партнёр» из low/parse-zero, но не сам advice mechanism.
- Patterns сохраняют keys, меняют labels на observations: `обещания не выполнены`, `позиции
  расходились`, `ответы были неконкретны`, `переносил ответственность`; `emotionally_volatile`
  отображается `были эмоциональные всплески; на BS не влияет`, `reliable` — только
  `наблюдаемых расхождений мало` при C≥30. Risk fallback — `сохранённый риск низкий|средний|высокий`.
  `contact_reliability` отдаёт только
  `исходы обязательств: выполнены/были просрочены/не выполнены/пока неизвестны`, никогда trait.
  No reliable pattern при C<30. Full card/dossier/digest/Telegram snapshots проверяют весь payload,
  а не только новую строку; regex `над[её]ж|ненад[её]ж|эмоционально\s+неустойчив|лжец|честн` даёт 0;
  Telegram `Звонков:` и любые counters запрещены в user-facing ответе.

## 10. Offline validation и acceptance mathematics

Synth latent `theta` означает заложенную склонность к **наблюдаемым расхождениям**, не ложь.
Он задаётся до и независимо от scorer; generator не импортирует production scorer и не открывает
SQLite/configured paths. Это verification реализации и recovery конструкта, не real-world validation.
Ниже — полный frozen ADEMP; [`synth-package/README.md`](synth-package/README.md) обязан быть его
байт-смысловым зеркалом, а не скрытым источником параметров.

### 10.1 Frozen generator

Версия генератора — `bs_synth_dgp_2`. Ровно 100 seed'ов: `seed_i=20260822+i`, `i=0…99`; в каждом
400 contacts `k=0…399` и master timeline из 100 source calls `j=0…99`. Все индексы нулевые. Байтовый
контракт закрыт:

```text
utf8(x) = x encoded as UTF-8, no BOM/newline
perm_digest(seed,k) = SHA256(utf8("perm|{seed}|{k}"))
order = integers 0..399 sorted by (perm_digest(seed,k), k)
theta[order[rank]] = (rank+0.5)/400

digest(seed,k,call_key,tag) = SHA256(utf8("{seed}|{k}|{call_key}|{tag}"))
U(...) = uint64_be(digest(...)[0:8]) / 2**64
Bernoulli(p,...) = 1[U(...) < clamp(p,0,1)]
Normal(stem) = sqrt(-2*ln(max(U(tag=stem+":a"),2**-64)))
               * cos(2*pi*U(tag=stem+":b"))
```

`call_key` — literal `contact`, `s000…s099` либо `e000…e099`; decimal seed/contact в hash input
не padding'уются. Исчерпывающий registry (новый random tag требует новую DGP version):

| call_key | literal tags |
|---|---|
| `contact` | `genre`, `affect` |
| every `sNNN` | `promise_opportunity`, `outcome_available`, `outcome_broken`, `outcome_late`, `late_days`, `outcome_method`, `claim_opportunity`, `contradiction`, `promise_vague`, `model_available`, `model_score:a`, `model_score:b`, `general_vagueness`, `blame_shift`, `specificity:a`, `specificity:b`, `emotion_spike`, `quality`, `shared_lm`, `role_swap`, `mnar:behavior`, `mnar:contradiction`, `mnar:vague_promise`, `mnar:model` |
| every materialized `eNNN` | `quality`, `role_swap` |

`as_of=2025-12-31`. Source date `d_j=as_of-2*(99-j) days`; поэтому все counterfactual exposure
views имеют общий terminal date и не смешивают объём с возрастом. Promise с source `sNNN` и available
outcome получает resolver-only call `eNNN`, `evidence_call_id="eNNN"`, date `d_j+30 days` и transcript.
Этот call не входит в exposure `n`, не создаёт L/M opportunity и видим только если date≤as_of; последние
15 source calls поэтому честно остаются без будущего outcome. View `n∈{1,3,10,100}` берёт nested suffix
`s(100-n)…s099`, только их promises и уже наступившие `eNNN`; `n=0` пуст. View n=1 — буквально свежий
первый звонок и никогда не видит будущий outcome.

Quotes contain no accidental specificity hit. Let `alphahex(bytes)` map each digest nibble `0…f` to
letters `a…p`; the literal quote is `цитата-` plus the first 20 letters of
`alphahex(SHA256(utf8("quote|{seed}|{contact}|{call_key}|{channel}")))`. `call_key` is the declared
`sNNN` or `eNNN`, so every quote is stable, distinct and longer than eight Unicode characters without a
digit/date/money/time token. Clean role-tagged transcript contains that exact string, so recomputed match
is exactly `1.0`. A rejected
quote keeps the stored quote but replaces the call transcript with `[s2] жжжжжжжжжжжж`; the generator
records expected rejection, and the R-37 integration test (not the generator) asserts the production matcher
returns `<0.72`. For every source call:

| Channel | Exact clean/default DGP before quality noise |
|---|---|
| Promise opportunity | `O_B~Bernoulli(.35)`; creates one OTHER promise and promise-local opportunity |
| Outcome availability | if `O_B`, `O_out~Bernoulli(.70)`; otherwise status `unknown`; resolved row appears only with due `eNNN` |
| Outcome severity | `p_broken=.03+.67*theta`; if not broken, conditional `p_late=.05+.30*theta`, else kept; late days are `[3,7,14,28][floor(4*U)]`; method det if `U<.75`, else grounded llm |
| Claim/contradiction | `O_C~Bernoulli(.70)`; if available, contradiction `~Bernoulli(.02+.76*theta)` |
| Promise vagueness | if `O_B`, `vague~Bernoulli(.06+.62*theta)` |
| Model self-score | available iff `U<.88`; `M=clamp(.08+.82*theta+.14*Normal("model_score"),0,1)` and one supporting quote |
| Genre/style controls | contact `G~Bernoulli(.5)` independent of theta; general vagueness `Bernoulli(.10+.50*G)`, blame shift `Bernoulli(.03+.30*G)`, raw target `x=clamp(80-45*G+8*Normal("specificity"),0,100)`, stored specificity is recomputed `q=round_half_up(x,0)` from the exact token construction below |
| Affect/context controls | independent `H~Bernoulli(.5)`; emotion spike `Bernoulli(.05+.35*H)`; zero-weight sentinels are hedge/directive/question/lexical/formality/request_balance/accommodation=`.15+.50G/.20/.20/.50/.50/.50/.50`, tempo=`120+20H`, risk=`20+50H`, call_type=`business` iff G else `personal`, one deep fact and one mention edge per contact |

Raw record encoding is also closed. Every emitted structured fact is exactly
`{"fact_type":type,"who":"S2","confidence":.8,"polarity":0,"intensity":.5,
"quote":quote,"value":quote}`; claim opportunity emits exactly one `claim` or, when its
draw is true, one `contradiction`. Promise opportunity emits one `fact_type="promise"` fact plus one
`promises[{who:"S2",what:quote,vague:<draw>}]`. General V/blame/emotion emit their own typed fact when
drawn. Available M is persisted as `bs_score=round_half_up(100*M,1)` and one `bs_evidence` string equal
to its OTHER quote; absent M stores JSON null/empty evidence. `risk_score=20+50H`; all other required
v001 fields use the fixed sentinels above. JSON is compact UTF-8 with sorted keys; arrays keep call/tag
order. Thus the generator emits inputs, never a precomputed BS-v2 output.

The stored OTHER segment passed to the unchanged `compute_specificity` has exactly 100 whitespace
tokens. Let `z` be its count of distinct zero-hit quote tokens and `q=round_half_up(x,0)`. Append
`floor(q/3)` copies of `15:30-руб` (exactly numeric+time+money = three hits); for remainder 1 append
`7`, for remainder 2 append `7руб`; fill the remaining
`100-z-floor(q/3)-I(q mod 3>0)` positions with `слово`. Role markers are outside segment text.
Therefore the production function returns exactly `q/100*100=q`, including q=0 and q=100, while every
grounding quote remains in the same OTHER span. The generator asserts token count100, hit count q and
recomputed Feature.value=q for every call; arbitrary continuous stored feature values are forbidden.

Clean uses valid parse, OTHER role, `unknown_share=0`, `role_fragile=false` and verbatim match1. Default
uses the same call-local `U(tag="quality")`: parser/resolver invalid if `U<.12`, attribution becomes
detectable UNKNOWN with share`.5`/fragile if `U<.15`, and transcript mutation rejects all call quotes if
`U<.10`. These nested failures deliberately model one common-mode shock. An attempted channel retains its
potential credit; parse/UNKNOWN/bad quote makes qualified=0. Evidence-call quality governs B; source-call
quality governs L/M. Separate algebraic fixtures perturb P/R/V one at a time, so nesting does not masquerade
as three independent votes. Zero-weight context rows remain stored.

Hostile paired strata reuse the exact latent/call/opportunity draws:

1. `clean`: quality probabilities 0;
2. `default`: `.12/.15/.10` as above;
3. `severe_detectable`: the same shared U with parse/UNKNOWN/quote thresholds `.35/.45/.45`;
4. `shared_LM`: when source tag `shared_lm<.30`, contradiction/vague probabilities and M mean use
   `1-theta`; opportunities and B unchanged;
5. `adversarial_M`: every available M uses `.08+.82*(1-theta)+.05*Normal("model_score")`; B/L unchanged;
6. `MNAR`: after generation, each otherwise usable B/C/P/M observation is removed by its declared
   `mnar:*` tag with `p_drop=.05+.45*theta`; it is missing, not a rejected potential attempt;
7. `genre_only`: specificity/general vagueness depend on G exactly as above while outcomes remain
   conditionally independent of G given theta;
8. `undetectable_role_swap`: source/evidence tag `role_swap<.30` swaps OWNER/OTHER while leaving
   `unknown_share=0` and `role_fragile=false`; expected to hurt BS recovery, not necessarily confidence.
9. `specificity_null`: deterministic control replaces per-call target by `80-45*G` (Normal=0),
   with no promise interaction; within-contact promise-minus-nonpromise gap is exactly zero. The separate
   stochastic `genre_only` view retains per-call Normal noise for the finite-sample false-positive gate.
10. `specificity_signal`: only raw specificity target becomes
   `clamp(80-45*G-40*theta*O_B+8*Normal("specificity"),0,100)`, then uses the same integer quantization
   and token materialization; it is a planted positive control for
   R-45, never evidence that real specificity predicts outcomes. Slope40 is a stress magnitude of the same
   order but below the already frozen 45-point genre swing; 20/60 are reported OAT and never selected.

The probabilities are frozen engineering stress parameters chosen to span rare→common,
clean→severe and independent→common-mode regimes; they are not literature effect sizes. Sensitivity is
one-at-a-time on **default,n=100**: for each of the following Bernoulli probability functions, replace its
final realized `p(theta,G,H)` by `clamp(p-.05)` and `clamp(p+.05)` while every other parameter remains
canonical: promise opportunity, outcome availability/broken/late/method, claim opportunity/contradiction,
promise vague, model availability, genre, general vagueness, blame, affect, emotion, shared-LM selector,
MNAR drop, role swap, and each parse/role/quote threshold. Separately run late half-life `7,28`, recency
half-life `90,360` and confidence K `2,5` against canonical `14/180/3`. There are no joint shifts and no
Cartesian products; specificity positive-control slope20/60 and residual divisor2/8 are separate OAT
around canonical40/divisor4 (never selected by result). Hostile strata otherwise
run only canonical parameters. Every result is published, never selected.

### 10.2 Estimands, tie rules и gates

The deterministic expectation grid has `theta=t/100`, `t=0…100`; it uses clean n=100 opportunities,
the exact visible resolver calls/recency weights, ratio-of-expected weighted numerators/denominators,
uniform four-point late mean, expected C/P and unclipped M mean in the unrounded formula. Its required
Kendall tau-b against theta is exactly `1.0`.

Primary stochastic recovery is frozen as **default-quality, n=100, all 400 contacts** for each seed;
the metric is Kendall tau-b between unrounded BS and theta. Across 100 seeds median must be ≥`.60` and
nearest-rank p05 — sorted value number5 — ≥`.50`. Clean n=100, mixed
`n_k=[1,3,10,100][k mod4]`, and each clean/default n=1/3/10/100 nested view are mandatory diagnostics
with ties/coverage reported but no minimum accuracy claim at sparse n. This separation is substantive:
mixed n tau ranks estimators with radically different precision, whereas first-call usefulness is tested
by visibility, bounds and C≤5. A disclosed pre-freeze dgp1 pilot with an explicit but then-unstandardized
tag registry produced mixed clean median/p05 `.5219/.4847`, default `.4797/.4477`, while n=100 produced
clean `.8299/.8089`, default `.8168/.7923`; it falsified the mixed estimand. The `.60/.50` gates, seeds
and contact count were **not** changed after that pilot; dgp2 closes tags/provenance and is frozen before
implementation. These pilot numbers are provenance, not acceptance evidence (`99-rounds.md`, Round5).
Spearman is diagnostic only; ARI is reported only for four predeclared theta quartiles and four score
quartiles. `tau=.60/.50` corresponds to 80%/75% concordant pairs only in the no-tie special case; no
such translation is made when ties exist.

For paired clean→severe confidence, contact k uses its predeclared mixed suffix
`n_k=[1,3,10,100][k mod4]`; one result per seed is
`median_contact(C_clean-C_severe)>0`. Ties and negative differences are failures, never removed;
the fixed denominator remains 100. PASS requires ≥63 positives, whose one-sided exact
`Binomial(100,.5)` tail is <`.01`. Separately, for clean counterfactual panels every seed must have
`median_contact(C_n1)<median_contact(C_n3)<median_contact(C_n10)<median_contact(C_n100)`; pointwise
monotonicity is claimed only for adding qualified evidence at fixed A/S.

ROC-versus-rank-sum ordering sensitivity uses the canonical **clean,n=100** records, unrounded values
and identical availability. Comparator is exactly
`RS=(3*aB*B+2*aL*L+1*aM*M)/(3*aB+2*aL+1*aM)` (0 when denominator0); equal available weights are
diagnostic only. Every unordered pair for which at least one method has a strict order receives loss `1`
for opposite strict orders, `1/2` when one method ties and the other is strict, and `0` for matching strict
orders; both-tie pairs are excluded. Exact rate is
`sum(loss)/count(not-both-tie)`, pooled by summing numerators and denominators over all 100 seeds, and
must be ≤`.10`; per-seed median/p95 plus `.05/.15` sensitivity boundaries are reported.
This is a product decision-loss budget, not an accuracy claim.

Обязательные CI properties:

1. BS `[0,100]`, C `[1,100]`; round-half-up deterministic.
2. Permutation invariant; duplicate same-call nonbehavior facts не меняют score/C.
3. Empty calls/duration и post-gate LLM confidence не меняют C; `.59→.61` отдельно меняет
   eligibility, `.60…1.00` — нет.
4. New comparable clean evidence не снижает C при fixed A/S; clean→rejected при сохранённом potential
   cluster строго не повышает C.
5. Controlled role/quote/parse degradation при fixed availability/value не повышает C; end-to-end
   severe-noise median C ниже paired clean median (one-sided exact sign test p<.01). Confident role swap
   без UNKNOWN проверяет потерю BS recovery, но не обязан менять C.
6. Same inputs+as_of → same details/source_signature; replay row growth 0.
7. All-missing → `0/1`; first valid call visible regardless entity/map/parse outcome.
8. Отдельный deterministic expectation grid: unrounded rank `Kendall tau-b=1`. Frozen primary
   default/n100 DGP: 100 seeds × 400 contacts; median tau-b≥.60 и nearest-rank p05≥.50. Clean/mixed и
   все n=1/3/10/100 panels публикуются без sparse-accuracy gate; clean median confidence строго растёт
   по panels. При отсутствии ties tau=.60 означает 80% concordant pairs; Spearman только diagnostic,
   ARI optional только для заранее заданных quartiles.
9. ROC vs explicit rank-sum на clean/n100: exact tie-aware discordant-pair rate §10.2 ≤10%; 5%/15% sensitivity
   публикуется.
10. Two-user identical quote: zero collisions/leaks.

100×400 и gates были выбраны до pilot; pilot сменил неверный mixed estimand, но не эти числа. 100
independent seeds дают percentile resolution 1%, 400 contacts дают 79,800 пар/seed. Все числа здесь
versioned engineering loss/precision gates, не claims реальной accuracy. K=3, g=1/2 и 25/50/75
проходят declared sensitivity. Simulation method:
Morris <https://doi.org/10.1002/sim.8086>, Sargent <https://doi.org/10.1057/jos.2012.20>, ARI limit
<https://doi.org/10.1007/BF01908075>.

## 11. Фаза A — baseline (все задачи unconditional, offline)

Ни одна задача A не зависит от реальной DB, box, owner feedback, `fact_feedback`, `outcome_feedback`,
Phase B или C. Каждый slice ≤1 рабочего дня и даёт ровно один проверяемый результат.

### R-01 — Additive schema v11

- **Что / результат:** fresh и upgraded DB получают один и тот же BS-v2 schema contract.
- **Файлы/модули:** `src/callprofiler/db/migrations.py::ALL_MIGRATIONS` (id 11),
  `src/callprofiler/db/schema.sql`, `src/callprofiler/graph/repository.py::_GRAPH_DDL`,
  `src/callprofiler/insight/repository.py` schema DDL.
- **Как:** реализовать полный type/default/CHECK/FK/trigger contract §6; unique owner parent key;
  deterministic nullable-phone `placeholder_key`+partial unique index plus exact existing-contact and
  NULL-call linking/BS0-C1 backfill; `graph_v1` backfill and model-free relation-evidence materialization;
  immutable legacy snapshot table; guarded ALTER для graph tables, которых ещё нет;
  sync всех трёх DDL owners; migrations 1…10 не менять.
- **Почему:** C-02/C-22/C-25/C-28/C-31; S-CODE-03/S-CONST: latest migration 10, schema drift и tenant invariant.
- **Данные:** synthetic old-schema SQLite + fresh `schema.sql`; никаких production paths.
- **Тир:** T2 — migration/SQL write path.
- **Зависимости:** existing T-03/T-04/T-05 contracts; R-зависимостей нет.
- **Тест:** `tests/test_db_migrations.py::test_migration_11_bs_v2_full_contract`.
- **Критерий:** `upgrade→graph→insight`, `graph→upgrade→insight` и fresh дают identical schema dump;
  journal ids 1…11; repeat=0 DDL; cross-owner metric/snapshot insert/update abort; snapshot UPDATE/DELETE
  always abort while repeated `INSERT OR IGNORE` is byte-exact; `fact_id!=NULL` becomes graph_v1,
  generic rows legacy; v1 payload snapshot exact; две строки с одной BS-version и разными
  confidence-version сосуществуют, а UPSERT одной меняет 0 bytes другой; existing done NULL-contact call
  becomes same-owner `md5-<source_md5>` contact with one canonical 0/1 row immediately after migration,
  with no replay/enrich; raw v2 fixture creates exact ordered relation ledger and invalid relation is reported;
  injected backfill failure leaves call/contact/metric/relation-ledger pre-state exact.
- **Условие:** `unconditional`.
- **Rollback:** feature flag/readers остаются legacy; additive columns/table не удалять; v1 rows не
  тронуты; новая versioned schema остаётся неактивной.

### R-02 — Tenant-scoped graph identity API

- **Что / результат:** каждый identity-based GraphRepository read требует `user_id` и не возвращает чужую строку.
- **Файлы/модули:** `src/callprofiler/graph/repository.py::get_entity/get_entity_metrics` и callsites.
- **Как:** убрать unscoped signatures; SQL только `WHERE user_id=? AND id=?`; callsites передают owner;
  numeric id без user не имеет compatibility default.
- **Почему:** C-25; S-CODE-01/S-CONST: tenant ownership обязателен до новых projections.
- **Данные:** два user с одинаковыми logical names и colliding fixture ids.
- **Тир:** T2.
- **Зависимости:** R-01.
- **Тест:** `tests/test_tenant_ownership.py::test_graph_repository_identity_reads_require_user`.
- **Критерий:** wrong-user reads=0; вызов без user_id даёт TypeError; 100% callsites проходят inventory.
- **Условие:** `unconditional`.
- **Rollback:** v2 consumers disabled; ownership tightening retained, unsafe API не восстанавливается.

### R-03 — Replay PK blocker

- **Что / результат:** graph replay проходит Step 1 на canonical calls schema.
- **Файлы/модули:** `src/callprofiler/graph/replay.py`.
- **Как:** заменить оба `calls.id` на `calls.call_id`, сохранить `WHERE user_id=?`, выбрать call ids
  через join analyses без unscoped subquery.
- **Почему:** C-21; S-CODE-02/S-CODE-03: `schema.sql:28-48` против `replay.py:61-72`.
- **Данные:** in-memory two-user fixture с v2 analysis.
- **Тир:** T2.
- **Зависимости:** R-01.
- **Тест:** `tests/test_graph_replay.py::test_replay_runs_against_calls_call_id`.
- **Критерий:** no `OperationalError`; rows второго user unchanged exactly.
- **Условие:** `unconditional`.
- **Rollback:** revert query-only patch; DB schema/data не меняются.

### R-04 — Canonical analysis payload reader

- **Что / результат:** live/replay/bulk читают один и тот же validated JSON payload.
- **Файлы/модули:** новый `src/callprofiler/analyze/payload_reader.py`, `graph/builder.py`, `graph/replay.py`.
- **Как:** SELECT `canonical_json`; parse canonical nonempty object first, raw fallback only; expose reason
  `canonical|raw|invalid`; replay preliminary validation вызывает тот же helper.
- **Почему:** C-11/C-21; S-CODE-02: builder comment и SQL расходятся; tolerant raw не должен обойти repair.
- **Данные:** canonical valid/raw broken, canonical empty/raw valid, both invalid fixtures.
- **Тир:** T1.
- **Зависимости:** R-03.
- **Тест:** `tests/test_graph.py::test_builder_prefers_canonical_json_and_falls_back_raw`.
- **Критерий:** 3 fixtures дают sources canonical/raw/invalid; invalid пишет 0 facts and returns False.
- **Условие:** `unconditional`.
- **Rollback:** fallback-only reader; stored analyses untouched.

### R-05 — Shared role-tagged transcript path

- **Что / результат:** каждый GraphBuilder path получает byte-identical role-tagged transcript.
- **Файлы/модули:** новый `analyze/transcript_format.py`, `pipeline/orchestrator.py`,
  `bulk/enricher.py`, `graph/replay.py`, `cli/commands/graph.py`.
- **Как:** один pure formatter `[me] text\n[s2] text\n[?] text` ordered by start_ms; live/bulk fetch
  current segments и передают `transcript_text`; replay перестаёт join bare text.
- **Почему:** C-15/C-21; S-CODE-02/S-CONST: validator требует markers, live currently skips verbatim.
- **Данные:** same segments through four call sites.
- **Тир:** T2 — cross-layer grounding contract.
- **Зависимости:** R-04.
- **Тест:** `tests/test_bs_event_provenance.py::test_all_builder_paths_use_same_role_tagged_transcript`.
- **Критерий:** captured argument SHA-256 одинаков в live/bulk/replay/backfill; transcript None count=0 для
  calls с segments.
- **Условие:** `unconditional`.
- **Rollback:** disable graph consumer, не разрешать ungrounded insert; analyses сохраняются.

### R-06 — Complete fact provenance row

- **Что / результат:** один structured fact materializes с сохранёнными type, speaker, match и stable key.
- **Файлы/модули:** `graph/validator.py`, `graph/builder.py`, `graph/repository.py`, `graph/config.py`.
- **Как:** validator возвращает match ratio; builder использует returned speaker (`me→OWNER`,
  `s2→OTHER`); INSERT пишет `fact_type,normalized_entity_key,quote_match,quote_verified,producer='graph_v2'`;
  fact key по §3 с stable normalized entity key;
  `event_type=COALESCE(allowed fact type,'fact')` остаётся CHECK-compatible.
- **Почему:** C-03/C-07/C-15/C-21/C-25; S-CODE-01/S-CODE-02: mandatory known defect и hash collision.
- **Данные:** exact/loose/rejected quotes, same quote two calls/two users, entity id reallocation.
- **Тир:** T2 — persistence/tenant/replay identity.
- **Зависимости:** R-01/R-02/R-05.
- **Тест:** `tests/test_bs_event_provenance.py::test_fact_row_persists_type_who_match_and_stable_key`.
- **Критерий:** exact row `fact_type='vagueness',who='OTHER',quote_match=1,verified=1`; ids stable across
  entity realloc, distinct across call/user; rejected ratio<.72 inserts 0.
- **Условие:** `unconditional`.
- **Rollback:** reader ignores new provenance; producer rows rebuildable from analyses.

### R-07 — Coalesced structured counters

- **Что / результат:** all existing entity fact counters reflect persisted v2 types.
- **Файлы/модули:** `graph/repository.py::count_facts_by_type`, `graph/aggregator.py`.
- **Как:** group `COALESCE(fact_type,event_type)` under user/entity; only OTHER facts feed BS-facing
  counters; retain emotional counter as context; claims count opportunity only.
- **Почему:** C-03/C-04; S-CODE-01: mandatory `COALESCE(fact_type,event_type)` Goal.
- **Данные:** one row each promise/contradiction/emotion/vagueness/blame/claim plus legacy fact_type NULL.
- **Тир:** T2.
- **Зависимости:** R-06.
- **Тест:** `tests/test_graph.py::test_fact_counters_use_coalesced_fact_type`.
- **Критерий:** expected counts all equal 1; OWNER/UNKNOWN numerator counts 0; legacy contradiction remains 1.
- **Условие:** `unconditional`.
- **Rollback:** v1 grouping behind compatibility version; rows unchanged.

### R-08 — Promise role and vague contract

- **Что / результат:** live prompt promise enters canonical contact promise inventory with vague intact.
- **Файлы/модули:** `src/callprofiler/db/repository.py::save_promises/save_batch`,
  `src/callprofiler/insight/promise_outcomes.py::_side`, `src/callprofiler/graph/validator.py`,
  `src/callprofiler/analyze/response_parser.py`, `src/callprofiler/deliver/digest.py` role helper.
- **Как:** normalize `Me|me→OWNER`, `S2|s2→OTHER`; preserve already canonical; unknown stays UNKNOWN;
  parser preserves required boolean `vague`; apply the exact ordered span/tie/OTHER/8-char/.72 contract §3.2
  to write m11 `vague,source_quote,quote_match`; unmatched rows remain stored but score-ineligible; future
  system status writer sets `status_updated_at,status_method`; no prompt bump.
- **Почему:** C-05/C-07/C-29; S-CODE-04: Me/S2 skipped, vague lost, undated status cannot support recency.
- **Данные:** Me/S2/OWNER/OTHER/garbage promises, exact/loose/tied/wrong-role/7-char quotes, missing vague,
  repair-parser response and both users.
- **Тир:** T2 — SQL write/semantic normalization.
- **Зависимости:** R-01.
- **Тест:** `tests/insight/test_promise_outcomes.py::test_live_me_s2_promises_preserve_vague_and_enter_outcomes`.
- **Критерий:** S2 grounded row is OTHER/contact with exact vague/raw earliest tied window and match≥.72;
  Me/wrong-role/unmatched/missing-vague score opportunities=0 but source rows persist; 7-char rejected;
  full and repair parsers agree; garbage excluded; cross-user rows0.
- **Условие:** `unconditional`.
- **Rollback:** shared reader accepts old+new values; no destructive rewrite required.

### R-09 — Outcome provenance and counter projection

- **Что / результат:** fulfilled/broken/overdue counters derive from canonical outcomes/status without
  impossible event types.
- **Файлы/модули:** `graph/repository.py`, `graph/aggregator.py`, `insight/promise_outcomes.py` query helper.
- **Как:** dedup `(user_id,contact_id,promise_key)` before any map join; prefer `promise_outcomes`; require persisted evidence call/date/quote for
  det/LLM; recover those fields from matched segment during writer; fallback only timestamped system
  status; contact side only; kept→fulfilled, broken→broken, late→fulfilled+overdue, unknown/undated→neither;
  join through user-scoped `entity_contact_map`.
- **Почему:** C-04/C-05/C-29; S-CODE-04: event CHECK forbids derived event types and LLM rows may be undated.
- **Данные:** kept/late/broken/unknown duplicate legacy/outcome fixtures.
- **Тир:** T2 — cross-table derived SQL.
- **Зависимости:** R-07/R-08.
- **Тест:** `tests/test_graph.py::test_promise_outcomes_feed_existing_promise_counters`.
- **Критерий:** fixture totals fulfilled=2, broken=1, overdue=1, total unique=4; second run identical.
- **Условие:** `unconditional`.
- **Rollback:** projection version back to v1; outcomes remain untouched derived data.

### R-10 — Producer-safe replay preservation set

- **Что / результат:** replay replacement plan identifies exactly rebuildable graph rows and preserves every unrebuildable legacy entity/profile byte.
- **Файлы/модули:** `graph/replay.py`, `graph/repository.py`, `graph/resolver.py`,
  `cli/commands/graph.py` unmerge path.
- **Как:** на полном user target delete only selected-call rows with
  `producer IN ('graph_v1','graph_v2')`; never blank/delete `legacy`; compute exact §7 transitive protected
  closure from legacy refs+profiles+`merged_into_id`+both merge-log FKs, preserve entity/profile/log bytes
  and forbid builder UPDATE of protected core. Resolve every raw entity/relation stable key through an
  archived entity's same-owner acyclic `merged_into_id` chain to terminal canonical before any derived
  write. Duplicate/missing protected key, cycle, cross-owner edge or missing terminal fails pre-mutation
  under `foreign_keys=ON`.
- **Почему:** C-21/C-25/C-31; S-CODE-02: default legacy старых facts удваивал бы counters.
- **Данные:** upgraded graph_v1+graph_v2, `legacy/fact_id=NULL/entity_id!=NULL`, protected profile,
  two-level reversible manual merge with archived duplicate raw key, unprotected entity and second user.
- **Тир:** T2 — destructive derived-row path, scoped/rebuildable.
- **Зависимости:** R-03/R-06/R-09.
- **Тест:** `tests/test_graph_replay.py::test_replay_replaces_only_graph_producer_without_row_growth`.
- **Критерий:** two replacements: graph row count/hash identical; legacy event, every merge-component entity,
  profile and merge-log byte snapshots identical; facts mentioning archived duplicate attach terminal canonical
  100% and never archived id; unmerge command succeeds inside rolled-back clone and sees original reversible
  snapshot; unprotected target rebuildable; each cycle/cross-owner/ambiguous-key fixture fails with every
  table pre-hash exact; other user identical.
- **Условие:** `unconditional`.
- **Rollback:** disable replay writer; restore derived rows by rerun old version, never touch source analyses.

### R-11 — Replay target-plan semantics

- **Что / результат:** `--limit`, failed builder, transaction and as-of have deterministic safe meaning.
- **Файлы/модули:** `graph/replay.py`, `graph/builder.py`, `graph/repository.py`, `insight/bs_recompute.py`,
  `cli/commands/graph.py`, `cli/main.py`, `cli/utils.py`.
- **Как:** parse `--apply` and reject `--limit --apply` before repository open; preview branches before
  `load_config_and_repo/init_db`, opens source DB query-only, copies it with SQLite backup API to `:memory:`,
  runs any compatibility DDL and SAVEPOINT+ROLLBACK only on that clone; apply alone may preflight the source.
  Build target plan before mutation; exact §7
  contact-local as-of map once; replace wall-clock relation upsert with per-call idempotent ledger replacement
  and exact per-key commutative §7 projection over sorted stored contributions; processed increments only on True.
- **Почему:** C-21/C-31; S-CODE-02/S-CONST: partial limited rebuild несовместим с user-wide graph tables.
- **Данные:** 5 calls, limit2, one invalid payload, fixed/derived dates, two contacts with interleaved and
  out-of-order dates, one relation with equal confidence at age0/180, pre-M11 DB and two wall clocks.
- **Тир:** T2.
- **Зависимости:** R-10.
- **Тест:** `tests/test_graph_replay.py::test_replay_control_path_is_atomic_and_limit_safe`.
- **Критерий:** `--limit 2` report processed=1 при one invalid; pre-M11 `sqlite_master`, migration journal,
  all data and DB/filesystem hashes before=after; `--limit 2 --apply` exits before DB open; explicit and
  derived contact-as_of maps repeat under two wall clocks; A's new call changes B's BS rows0; both live
  process orders equal replay hashes; relation age0/180 gives exact weight1.5, first/last calls follow the
  frozen stable tuple; retry/changed analysis leaves one evidence key set and recomputes old∪new projections;
  reversing builder order changes relation/evidence bytes0.
- **Условие:** `unconditional`.
- **Rollback:** preview уже rollback-only; source rows never mutate.

### R-12 — Strict atomic full-user replay

- **Что / результат:** full replay либо коммитит весь user graph, либо оставляет exact pre-run snapshot.
- **Файлы/модули:** `src/callprofiler/graph/replay.py`, `graph/builder.py`, `graph/aggregator.py`,
  `graph/repository.py`, `insight/person_link.py`, `insight/mentions.py`, `insight/repository.py`, `db/uow.py`.
- **Как:** `strict=True` поднимает per-fact errors; одна outer UoW: target→R-10 replacement→all calls→
  derived graph→map→mentions→audit/replay-run→invariant checks→commit. Graph/insight schema preflight
  выполняется и коммитится **до** `BEGIN`; внутри UoW helpers получают `ensure_schema=false,commit=false`.
  Capture replay pre-state after successful preflight; preflight failure opens no replay transaction.
  Raw commits replay/map/mentions/save-replay-run заменяются caller-controlled/`commit_unless_uow`;
  builder/aggregator strict path не проглатывает exceptions; protected merge-component
  entity/profile/merge-log/legacy/source rows
  не входят в delete/update. Replay run uses deterministic §7 signature UPSERT, not append.
- **Почему:** C-21/C-31/C-36; S-CODE-02/S-CONST: current builder swallows errors and multi-commit breaks replay invariant.
- **Данные:** five-call upgraded fixture; faults call3, after map, after mentions, after replay-run; second user.
- **Тир:** T3.
- **Зависимости:** R-04/R-10/R-11.
- **Тест:** `tests/test_graph_replay.py::test_full_replay_failure_is_atomic`.
- **Критерий:** preflight failure changes graph/data0; after successful preflight, все four replay failure
  points дают byte-equal pre/post hashes graph/map/mentions/replay-run;
  success leaves graph_v1=0 and expected graph_v2 hash; two success runs same counts/signatures and total
  row growth0 including `graph_replay_runs`; protected legacy event/entity/profile/merge-log and second-user
  snapshots exact; archived-key facts resolve to terminal canonical on both runs.
- **Условие:** `unconditional`.
- **Rollback:** disable apply; rebuildable derived rows only, source hashes immutable.

### R-13 — Pure BS function

- **Что / результат:** one dependency-free function computes exactly §4.
- **Файлы/модули:** new `src/callprofiler/insight/bs_index.py` (dataclasses/constants only).
- **Как:** typed optional B/L/M inputs; ROC helpers as rational integer weights; clamp; decimal
  round-half-up; return value/components/version/no_evidence, no clock/DB/config.
- **Почему:** C-08/C-10/C-16/C-27; S-ROC/S-DEC: chosen D2, ordinal—not empirical—weights.
- **Данные:** literal golden vectors and boundary/property generators.
- **Тир:** T2 — new metric.
- **Зависимости:** R-01 по execution order; pure function persistence-independent.
- **Тест:** `tests/test_bs_v2_formula.py::test_v2_roc_observed_exact_examples`.
- **Критерий:** exact `62.8`, `89.8`, `0.0`; 10,000 generated vectors all bounded/deterministic.
- **Условие:** `unconditional`.
- **Rollback:** `bs_formula_version` routes readers back to v1; pure module has no state.

### R-14 — Pure confidence function

- **Что / результат:** one dependency-free function computes exactly §5 and observable 30/60/90 semantics.
- **Файлы/модули:** `insight/bs_index.py`.
- **Как:** exact tuple §5; potential N, qualified/geometric usable E, Q=E/N, B-vs-L A, deterministic
  chronological split, exact call-level `max` отдельно для L/M N и E, clamp 1…100; undated N=E=0
  with audit counter; explicit availability flags; no clock/DB.
- **Почему:** C-12…C-18/C-29/C-30; S-PHIA/S-CODE-04: evidence strength, not calibrated probability.
- **Данные:** clean/rejected/undated/future/zero-valued component, split tie and first-call fixtures.
- **Тир:** T2.
- **Зависимости:** R-13.
- **Тест:** `tests/test_bs_v2_confidence.py::test_c1_exact_curve_and_quality_gates`.
- **Критерий:** exact clean A0 table `1/9/18/52/65`, A1 table `1/18/34/77/97`; raw-n table §5;
  all-missing C1; first-call L ceiling C5; future excluded; clean→rejected never raises C; available zero
  differs from missing; rejected-L+qualified-M yields exact `N=5/11,E=2/11`; undated increments only
  `details.undated_excluded`.
- **Условие:** `unconditional`.
- **Rollback:** confidence projection defaults 1/legacy; BS remains available.

### R-15 — Raw contact evidence snapshot

- **Что / результат:** один user-scoped SQL snapshot возвращает все raw BS source rows без formula aggregation.
- **Файлы/модули:** новый `src/callprofiler/insight/bs_snapshot.py`, `db/repository.py`, `graph/repository.py`.
- **Как:** exact queries for analyses/calls/transcripts/promises/events/outcomes/features/deep/mentions;
  каждый join связывает user ids; filter `source_date<=as_of`; rows сохраняют missing/provenance, не
  coalesce to zero; deterministic order.
- **Почему:** C-02/C-05…C-07/C-25/C-29; S-CODE-01…S-CODE-05/S-CONST: все §2 signals должны пройти audit один раз.
- **Данные:** exhaustive two-user fixture с каждым сигналом, future/undated/missing twins.
- **Тир:** T2.
- **Зависимости:** R-01/R-06/R-08/R-09.
- **Тест:** `tests/test_bs_v2_inputs.py::test_raw_contact_evidence_snapshot_is_complete_and_scoped`.
- **Критерий:** golden ordered JSON exact; 0 future rows; other-user fields=0; все queries имеют user predicate.
- **Условие:** `unconditional`.
- **Rollback:** read helper unused; source rows untouched.

### R-16 — Pure contact input assembler

- **Что / результат:** stored rows for one `(user,contact,as_of)` become one complete typed scorer input.
- **Файлы/модули:** новый `src/callprofiler/insight/bs_inputs.py`.
- **Как:** pure transform R-15 snapshot→B/L/M opportunities + exact potential/qualified clusters §3–5;
  outcome/promise dedup; apply one exact §3.2 grounding gate to facts/promises/v001 bs_evidence; call-level
  P; M support only from the enumerated types/spans; continuous UNKNOWN; rejected attempts; all weight-0 signals in
  typed context; no SQL/clock/config.
- **Почему:** C-05…C-18/C-27/C-29; S-CODE-04/S-ROC/S-PHIA: exact missing/provenance contract.
- **Данные:** exhaustive fixture with every signal plus missing/invalid twin.
- **Тир:** T2 — cross-layer read contract.
- **Зависимости:** R-13/R-14/R-15.
- **Тест:** `tests/test_bs_v2_inputs.py::test_contact_input_vector_from_all_existing_signals`.
- **Критерий:** golden typed JSON exact; empty/duration/post-gate confidence changes preserve hash;
  `.59→.61` changes eligibility; `.60…1.00` does not; future excluded; undated outcome contributes
  `N=E=0` and one audit count; promise/M fixtures at 7/8 chars, `.71/.72`, me/s2/UNKNOWN and bare-claim
  boundaries exact; v001 evidence can support only M and never a second L credit; general V/D/style direct weight=0.
- **Условие:** `unconditional`.
- **Rollback:** assembler unused behind flag; source rows unchanged.

### R-17 — Phase-A baseline/legacy reader router

- **Что / результат:** one explicit zero-write `BSView` router gives every surface the same canonical,
  legacy, zero and stale semantics.
- **Файлы/модули:** новый `src/callprofiler/insight/bs_policy.py`, `src/callprofiler/config.py`,
  `configs/features.yaml`, repository readers.
- **Как:** `bs_read_version=baseline|legacy`; initial static default remains `legacy` until R-42;
  baseline reads exact `(bs_formula_version,confidence_formula_version)` canonical key, then exact §8
  zero-write fallback if absent; legacy reads stable-key immutable snapshot, else unchanged avg. Return only
  exact §8 typed source enum/markers; for canonical compare read-only current `bs-callset-1` with stored value
  and set stale without overwriting score/C. Flips are read-only; default becomes baseline only
  when R-01…R-42 rollout completes.
- **Почему:** C-22/C-28; S-CODE-03/S-CONST: rollback must be executable, not promised flag fiction.
- **Данные:** canonical fresh/stale, immutable snapshot, avg-only, zero, exact v1 payload/mapping, future v2
  row and reallocated entity id.
- **Тир:** T2.
- **Зависимости:** R-01/R-13/R-14.
- **Тест:** `tests/test_bs_policy.py::test_phase_a_router_round_trip_preserves_legacy_and_baseline_bytes`.
- **Критерий:** legacy→baseline→legacy→baseline payloads/signatures byte-equal to their first reads;
  stable key survives id reallocation; flips execute 0 writes; same BS version with two confidence versions
  is selected only by the complete version pair; upgraded legacy-only and no-value contacts under baseline
  return exact `legacy_snapshot|avg` C1 `предыдущий расчёт` and zero C1 `нет пригодных данных` without
  INSERT; adding a failed call changes only canonical `stale=true/последний звонок не учтён`, while a
  successful recompute clears it; 100% downstream surface fixtures consume this one type.
- **Условие:** `unconditional`.
- **Rollback:** set reader to legacy; versioned baseline rows retained.

### R-18 — Canonical contact recompute

- **Что / результат:** one idempotent call persists exactly one named-version canonical contact row/signature.
- **Файлы/модули:** новый `src/callprofiler/insight/bs_recompute.py`, `insight/repository.py`.
- **Как:** assemble→pure compute→canonical JSON sorted→source signature; UoW UPSERT
  versioned `contact_bs_metrics` keyed by user/contact/both formula versions, including current
  `bs-callset-1` signature; no projections; no
  update/computed_at change if signature equal.
- **Почему:** C-02/C-22/C-28; S-CODE-03/S-CONST: contact canon and immutable versions enable first-call/rollback.
- **Данные:** no-evidence and grounded contradiction contact, same input twice.
- **Тир:** T2.
- **Зависимости:** R-16/R-17.
- **Тест:** `tests/test_bs_recompute.py::test_contact_canonical_row_and_projections_are_idempotent`.
- **Критерий:** exactly 1 row for named version; contradiction fixture BS>0; second run changes 0 rows and
  computed_at; `bs-details-1` null-vs-zero fixture exact; source signature deterministic and unchanged by
  UI/read flags; source or either version mutation changes it; other formula rows/avg unchanged.
- **Условие:** `unconditional`.
- **Rollback:** R-17 routes legacy; additive canonical rows remain ignored/rebuildable.

### R-19 — Contact-summary compatibility projection

- **Что / результат:** `contact_summaries` mirrors the active canonical pair without changing legacy `avg_bs_score`.
- **Файлы/модули:** `src/callprofiler/aggregate/summary_builder.py`, `insight/bs_recompute.py`.
- **Как:** user/contact UPSERT exact pair/version/as_of after R-18 success; signature skip; never parse raw or
  write `avg_bs_score`; router controls which projection is rendered.
- **Почему:** C-04/C-22/C-24; S-CODE-06/S-CONST: existing summary mechanism must evolve without erasing diagnostic.
- **Данные:** canonical+legacy average, injected projection failure.
- **Тир:** T2.
- **Зависимости:** R-18.
- **Тест:** `tests/test_bs_recompute.py::test_contact_summary_projection_preserves_legacy_average`.
- **Критерий:** pair/version exact canonical; avg byte-identical; failure rolls back projection only, canon readable.
- **Условие:** `unconditional`.
- **Rollback:** legacy router ignores v2 projection; avg remains.

### R-20 — Deterministic entity compatibility projection

- **Что / результат:** only a unique tenant map projects contact BS; unmapped/ambiguous entities remain explicit compatibility states.
- **Файлы/модули:** `src/callprofiler/insight/bs_recompute.py`, `graph/repository.py`, `insight/person_link.py`.
- **Как:** implement exact §7 `v1_linear_repaired_1` equation/goldens and one facade
  `recompute_contact_bs_and_projections`; unique distinct contact→canonical; 0/>1→compatibility score,C1
  with unmapped/ambiguous; unique→ambiguous clears prior v2 payload; never compare numeric ids.
- **Почему:** C-02/C-03/C-25/C-32/C-36; S-CODE-01/S-CONST: entity is not caller and map is many-to-many.
- **Данные:** 1→1, entity→2 contacts, 2 entities→1 contact, no map, id permutation.
- **Тир:** T2.
- **Зависимости:** R-02/R-07/R-09/R-18.
- **Тест:** `tests/test_bs_recompute.py::test_entity_projection_requires_unique_tenant_map`.
- **Критерий:** exact §7 statuses and `0/40/80/100` plus density-cap compatibility goldens; both current
  aggregator paths return identical unrounded floats; facade order canonical→summary→entity occurs once;
  1→1 and 2→1 signatures exact; ambiguous copies 0 contact rows; id permutation changes 0 payload bytes.
- **Условие:** `unconditional`.
- **Rollback:** legacy snapshot remains queryable; entity projection rebuildable.

### R-21 — First-call identity/materialization gate

- **Что / результат:** every ingested call gets a deterministic contact/artifact key and typed pair before any delivery attempt.
- **Файлы/модули:** `src/callprofiler/ingest/ingester.py`,
  `src/callprofiler/pipeline/orchestrator.py`, `src/callprofiler/bulk/loader.py`,
  `db/repository.py`, `graph/repository.py` relation decay, `insight/bs_recompute.py`.
- **Как:** общий `Repository.register_call_with_baseline(...)` принимает `user_id`, metadata и
  `source_md5`; ingester вызывает его после вычисления MD5 и атомарного архива оригинала, bulk loader —
  после parse/MD5 и до transcript persist. Внутри helper один `uow_for(repo._get_conn())` выполняет весь
  DB-регистр: `get_or_create_contact` при phone ищет по
  `(user_id,phone_e164)`, а при NULL phone принимает `placeholder_key='md5-'+source_md5.lower()`, ищет
  только по `(user_id,placeholder_key)` и не по имени; затем `create_call` связывает этот contact и
  `INSERT OR IGNORE` создаёт exact BS0/C1. Все внутренние repository commits подавлены UoW; ошибка в
  любом из трёх DB-шагов оставляет 0 новых contact/call/metric rows; existing call с NULL contact
  связывается в том же UoW; retry/dedup возвращает ту же тройку без orphan NULL-phone contact и без
  сброса existing metric. Ни ingester, ни bulk не выполняют прежнюю раздельную пару
  `get_or_create_contact`/`create_call`. До enrichment уже существует exact §7 association. Resolve the
  non-rewinding §7 as_of once; после analysis
  вызвать R-20 facade synchronously before delivery. No analysis/parse failure leaves 0/1. Scorer exception
  writes `calls.status='error'`+stage message, leaves prior canonical row untouched so R-17 callset mismatch
  exposes `stale=true/последний звонок не учтён`, and suppresses all transport until R-31 terminal adapter;
  no direct card write. Retry updates same row; placeholder never auto-merges and NULL phone uses stable
  `unknown-<placeholder_key>` artifact key.
- **Почему:** C-02/C-23/C-26/C-34; S-CODE-06/S-CONST: owner first-call acceptance and error contract.
- **Данные:** normal contradiction, short, parse_failed, LLM raises, no analysis, scorer raises, role_fragile,
  preexisting `contact_id=NULL`, phone-less new/existing contact, retry, and same two calls processed in
  oldest→newest/newest→oldest order under two wall clocks.
- **Тир:** T2 — pipeline/UoW contract.
- **Зависимости:** R-05/R-11/R-18/R-19/R-20.
- **Тест:** `tests/test_pipeline.py::test_first_call_has_both_indices_before_delivery`.
- **Критерий:** 10/10 pair before any delivery; formerly-null call linked to one same-owner placeholder;
  NULL phone exposes exact stable artifact key to the later R-31 adapter; contradiction BS>0;
  injected failure after each DB statement leaves 0 partial rows, while scorer-after-initializer failure retains
  same contact/row/artifact and exact 0/1+observable error;
  ingester and bulk inventory each calls the shared helper exactly once and has 0 split contact/call writers;
  attempted transport calls=0 until typed pair/error decision; retry one row; second call does not reset;
  both process orders and replay yield identical logical BS/relation hashes and contact-local max persisted
  as_of; interleaved newer call for contact A changes contact B row/signature0;
  initializer/scorer model calls=0; entity projection signature matches contact when uniquely mapped.
- **Условие:** `unconditional`.
- **Rollback:** R-17 legacy route; initializer row retained; error semantics retained.

### R-22 — Bulk/backfill convergence

- **Что / результат:** bulk-enricher and graph-backfill produce the same canonical signature as live for identical stored inputs.
- **Файлы/модули:** `src/callprofiler/bulk/enricher.py`, `cli/commands/graph.py`, `insight/bs_recompute.py`.
- **Как:** after each successful graph update call the R-20 facade once with same role transcript/as_of; no duplicate
  scorer implementation; failures use existing bulk report/status.
- **Почему:** C-21/C-22/C-26; S-CODE-02/S-CONST: current bulk ends at v1 and would diverge from live.
- **Данные:** one canonical fixture through live/bulk/backfill plus injected invalid payload.
- **Тир:** T2.
- **Зависимости:** R-05/R-18/R-19/R-20/R-21.
- **Тест:** `tests/test_bulk_enricher.py::test_bulk_and_backfill_match_live_bs_signature`.
- **Критерий:** three paths pair/components/signature byte-equal; invalid path changes 0 canonical rows; model calls=0.
- **Условие:** `unconditional`.
- **Rollback:** disable secondary hooks; live canonical remains.

### R-23 — Scoped deterministic outcome refresh

- **Что / результат:** scoped deterministic resolver returns exact changed promise keys/contacts without recomputing BS.
- **Файлы/модули:** `src/callprofiler/insight/promise_outcomes.py`.
- **Как:** `use_llm=False`, unresolved OTHER promises only, same user/contact and existing +120-day window;
  persist evidence call/date/quote/method; return sorted changed keys/contacts; all writes use
  `commit_unless_uow`, so standalone owns a commit but an outer UoW owns rollback; idempotent.
- **Почему:** C-05/C-29; S-CODE-04: strongest B must have auditable date/provenance.
- **Данные:** promise call + later done/fail segment + irrelevant second user.
- **Тир:** T2 — derived pipeline state.
- **Зависимости:** R-08/R-09.
- **Тест:** `tests/insight/test_promise_outcomes.py::test_incremental_outcome_refresh_returns_affected_contacts`.
- **Критерий:** unknown→kept/broken once; exact evidence fields; sorted one affected contact; LLM calls=0;
  second run returns empty and changes 0 rows.
- **Условие:** `unconditional`.
- **Rollback:** stop caller; outcome rows derived/rebuildable; promises untouched.

### R-24 — Synchronous outcome recompute hook

- **Что / результат:** one outer UoW makes future outcome, counters and all BS projections converge or roll back together.
- **Файлы/модули:** `src/callprofiler/pipeline/orchestrator.py`, `insight/promise_outcomes.py`,
  `graph/aggregator.py`, `insight/bs_recompute.py`, `db/uow.py`.
- **Как:** immediately after transcript persistence and ASR/pyannote unload, **before** the optional
  `enable_llm_analysis` early return, run synchronous CPU UoW: R-23→dedup affected contacts→R-09 counters for mapped
  entities→R-20 facade; commit only after projections. Exception after outcome or entity projection rolls
  back outcome+counters+canon+projections, calls `update_call_status('error',stage_message)` outside failed
  savepoint and suppresses delivery; success passes affected typed pairs to terminal local-card publication
  even when LLM analysis is disabled; retry sees the unresolved source and converges; no outbox fiction.
- **Почему:** C-05/C-26/C-34/C-36; S-CODE-04/S-CONST: automatic development without swallowed errors or GPU overlap.
- **Данные:** promise+latter kept/broken segment, duplicate key, exception, second user, LLM disabled.
- **Тир:** T2.
- **Зависимости:** R-09/R-20/R-21/R-23.
- **Тест:** `tests/test_pipeline.py::test_outcome_hook_recomputes_once_and_records_failure`.
- **Критерий:** each affected contact facade count=1; counter/contact/entity projection changes; failures
  injected after outcome and after entity leave all derived/outcome hashes exact pre-state; retry resolves and
  produces expected signature; rerun=0 writes; LLM-disabled path still emits updated typed pair for local
  card and makes 0 `LLMClient` calls; visible status/error; GPU calls=0; other user unchanged.
- **Условие:** `unconditional`.
- **Rollback:** disable outcome hook; last canonical pair remains visible.

### R-25 — Graph-replay BS projection order

- **Что / результат:** graph replay rebuilds contact canon then mapped entity to the same score/signature.
- **Файлы/модули:** `graph/replay.py`, `graph/repository.py`, `insight/person_link.py`,
  `insight/mentions.py`, `insight/bs_recompute.py`.
- **Как:** retain R-12 outer UoW through: rebuild `entity_contact_map`→R-09 outcome counters→exact
  repaired-v1 compatibility for every entity→R-20 facade for affected contacts→mention edges→metrics/audit→
  save replay-run; all nested commit paths UoW-aware; no direct id equality.
- **Почему:** C-02/C-21/C-25/C-31/C-32; S-CODE-02/S-CONST: explicit replay invariant.
- **Данные:** mapped name, cooccur map, unmapped entity, two runs.
- **Тир:** T2.
- **Зависимости:** R-09/R-12/R-18/R-19/R-20.
- **Тест:** `tests/test_graph_replay.py::test_replay_recomputes_contact_then_mapped_entity_same_signature`.
- **Критерий:** kept/broken counters, canon and projections match before/after replay; two runs identical;
  failure injected after final entity projection rolls back graph/map/counters/canon/projections to exact
  pre-run hashes; exact unique/ambiguous/unmapped §7 states; row growth 0; source/legacy hashes unchanged.
- **Условие:** `unconditional`.
- **Rollback:** any stop/failure rolls the entire replay UoW back to pre-run hashes; partial map commit is
  forbidden, while previously committed contact canon outside this run remains intact.

### R-26 — Feature/autofit recompute parity

- **Что / результат:** `features-build`, `archetypes-fit` and watcher autofit invoke the same pure recompute.
- **Файлы/модули:** `src/callprofiler/insight/cli_ops.py`, `cli/commands/insight.py`, `pipeline/watcher.py`.
- **Как:** collect exact affected `(user,contact)` after raw feature persistence; call R-20 facade with stored as_of;
  never make first-call path wait for autofit threshold; no LLM/GPU import.
- **Почему:** C-06/C-26; S-CODE-05/S-CONST: named recompute paths and future parity.
- **Данные:** two contacts, feature batch, watcher threshold/no-threshold fixtures.
- **Тир:** T2.
- **Зависимости:** R-18/R-19/R-20.
- **Тест:** `tests/test_watcher_autofit.py::test_autofit_and_archetypes_fit_call_pure_bs_recompute`.
- **Критерий:** each affected contact called once; below-autofit first-call pair still exists; mocked LLM/GPU=0.
- **Условие:** `unconditional`.
- **Rollback:** remove secondary hooks; live/replay baseline remains.

### R-27 — Atomic v1→v2 recompute command

- **Что / результат:** explicit scoped CLI migrates old values reproducibly without destroying v1 first.
- **Файлы/модули:** новый `src/callprofiler/cli/commands/bs.py`, `cli/main.py` registry,
  `insight/bs_recompute.py`.
- **Как:** `bs-recompute --user USER [--as-of YYYY-MM-DD] [--dry-run]`; dry-run default report counts/
  deltas/versions; apply one user in bounded batches, source signature resume; no `--all` implicit user;
  projections update only after canonical row success.
- **Почему:** C-22/C-25/C-28; S-CODE-03/S-CONST: version migration and tenant rollback contract.
- **Данные:** mixed v1/v2/legacy-no-analysis fixture, injected failure mid-batch.
- **Тир:** T2 — CLI SQL mutator/migration.
- **Зависимости:** R-17…R-20/R-25.
- **Тест:** `tests/test_bs_recompute_cli.py::test_v1_to_v2_backfill_is_atomic_and_idempotent`.
- **Критерий:** dry-run changes 0 rows; apply converts 100% eligible contacts; ineligible remain legacy+C1;
  rerun changes 0; failure leaves last complete batch resumable and no half-projection.
- **Условие:** `unconditional`.
- **Rollback:** `bs_read_version=legacy`; recompute rows ignored, not deleted.

### R-28 — Absolute baseline label policy

- **Что / результат:** first user receives deterministic label without any `bs_thresholds` row.
- **Файлы/модули:** новый `src/callprofiler/insight/bs_policy.py`, `graph/calibration.py` reader.
- **Как:** introduce `bs_ui_fixed_1`: exact §9 zero-preserving rule (`0 iff stored0`, otherwise
  `max(1,half_up)`), then
  bands ≤25/≤50/≤75/>75 and low-data flag C<30; version-filter threshold reads; existing percentiles
  available only as `relative_context` when explicit flag true and matching formula version.
- **Почему:** C-10/C-23/C-24/C-33/C-38; S-CODE-06/S-CONST: equal-width display policy, no user calibration.
- **Данные:** empty thresholds, stale v1 thresholds, matching optional v2 thresholds, 25/50/75 plus `.4/.5` twins.
- **Тир:** T1.
- **Зависимости:** R-13/R-14/R-17.
- **Тест:** `tests/test_bs_policy.py::test_baseline_labels_do_not_require_threshold_rows`.
- **Критерий:** `0/0.1/0.4/0.5→0/1/1/1`; scores 25/50/75/76 map B/C/D/E with C≥30;
  `50.4→display50/C`, `50.5→display51/D`; C=29 sets low-data/F consumer state;
  inserting arbitrary threshold rows changes numeric/absolute result 0 times.
- **Условие:** `unconditional`.
- **Rollback:** policy version selects previous label mapping; numbers/version remain.

### R-29 — Admiralty v2 mapping

- **Что / результат:** existing Admiralty grade uses new pair, preserves letter mechanism and replaces info confidence.
- **Файлы/модули:** `src/callprofiler/insight/admiralty.py`, `dashboard/labels_ru.py`.
- **Как:** source letter contract §9.2 from `BS_display`; info digit exact 2/3/4/6 anchors; phrases describe evidence basis;
  exact observable phrase table §9.2; A retains current kept_ratio≥.8/resolved n≥5 plus C≥90 (counts
  internal only); consume only R-17 `BSView`; noncanonical/stale forces F6; remove mean
  events.confidence query and all reliable trait phrases.
- **Почему:** C-11/C-12/C-23/C-24; S-CODE-04/S-CODE-06/S-CONST: preserve grade mechanism, redefine evidence semantics.
- **Данные:** boundary pairs, A eligibility, missing canonical legacy.
- **Тир:** T1.
- **Зависимости:** R-20/R-28.
- **Тест:** `tests/insight/test_admiralty.py::test_admiralty_v2_observational_mapping`.
- **Критерий:** C 29/30/60/90 maps 6/4/3/2; exact six phrases §9.2; changing events.confidence leaves
  grade identical; A requires all three conditions; every legacy/avg/zero/stale view is F6 with exact
  mandatory marker and stored pair still visible; forbidden trait regex absent.
- **Условие:** `unconditional`.
- **Rollback:** previous letter calculation or suppress optional grade; observational phrase table and
  forbidden-regex gate remain mandatory—trait phrases are never restored.

### R-30 — Pure caller-card renderer

- **Что / результат:** one pure typed renderer always retains exact BS/C line within 512 UTF-8 bytes.
- **Файлы/модули:** `src/callprofiler/deliver/card_generator.py`,
  `src/callprofiler/aggregate/summary_builder.py::generate_card_text` pure render adapters,
  новый `src/callprofiler/deliver/card_render.py`.
- **Как:** one shared typed renderer called by both existing generators; input only R-17 `BSView`;
  mandatory `bs:` line before optional advice plus exact source/stale marker; drop optional
  whole lines by fixed priority; BS one-decimal→integer exact zero-preserving §9 rule once; UTF-8 byte measurement;
  `grade:` uses R-29. Не ждать T-19: минимальный
  typed renderer реализуется этим slice.
- **Почему:** C-02/C-23/C-24/C-34; S-CODE-06/S-CONST: owner primary surface and byte contract.
- **Данные:** no history, Cyrillic/emoji, 500-char name, BS `0/.1/.4/.5`, boundaries 511/512/513 bytes.
- **Тир:** T1.
- **Зависимости:** R-19/R-21/R-29.
- **Тест:** `tests/test_card_generator.py::test_typed_card_always_keeps_pair_within_512_bytes`.
- **Критерий:** both public render callables' 100% fixtures contain regex `bs: \d{1,3}/100 .* \d{1,3}/100`;
  exact UTF-8 511/512/513 cases end ≤512; no partial UTF-8/line; full/minimal/error snapshots forbid trait
  phrases and counters; canonical/legacy/avg/zero/stale snapshots have exact §8 markers; null-phone artifact
  label is stable.
- **Условие:** `unconditional`.
- **Rollback:** regenerate surrounding optional lines with prior renderer; mandatory pair renderer remains.

### R-31 — Atomic caller-card publication

- **Что / результат:** every rendered caller card is published only through the existing atomic artifact path.
- **Файлы/модули:** `src/callprofiler/deliver/card_generator.py`,
  `src/callprofiler/aggregate/summary_builder.py::write_card/write_all_cards`,
  `src/callprofiler/artifacts.py`, `src/callprofiler/pipeline/orchestrator.py` terminal callsite,
  `src/callprofiler/dashboard/tools.py`, `src/callprofiler/cli/commands/{contacts.py,query.py}`.
- **Как:** every callable writer delegates to one terminal normal/error adapter, receives the R-21 typed pair,
  resolves phone-or-placeholder key, renders R-30 and passes bytes to `artifacts.atomic_write_text/bytes`;
  no direct `Path.write_text`; error path publishes local minimal card
  and suppresses Telegram. `update_all_cards` publishes phone and placeholder contacts; dashboard uses exact
  `CardGenerator(repo).update_all_cards(user)` and both CLI aliases call the same method. Cleanup preserves
  `^\d+$` and `^unknown-md5-[0-9a-f]{32}$`; it never deletes arbitrary nonnumeric files, and removes only an
  explicit legacy phone alias after its canonical replacement published successfully. Injected exception
  before replace leaves old final intact and no final partial.
- **Почему:** C-23; S-CODE-06/S-CONST T-08: current card direct write violates artifact atomicity.
- **Данные:** old/new card, placeholder, unrelated `.txt`, explicit legacy phone alias, injected
  open/write/replace failures, every CLI/dashboard rebuild entrypoint.
- **Тир:** T1.
- **Зависимости:** R-30.
- **Тест:** `tests/test_card_generator.py::test_card_publish_is_atomic`.
- **Критерий:** inventory finds exactly the shared publisher behind every public card writer and zero direct
  `write_text`; success exact new bytes; each failure exact old bytes; no `.part` exposed as final; all ten
  R-21 first-call cases, including NULL phone, publish ≤512-byte local card containing both numbers;
  publish placeholder→run update-all, both CLI aliases and dashboard rebuild→exactly one current
  `unknown-md5-*` card remains with pair; unrelated file survives and wrong dashboard ctor/method calls=0;
  R-24 LLM-disabled outcome refresh republishes changed pair with zero LLM calls; Telegram error sends=0.
- **Условие:** `unconditional`.
- **Rollback:** keep old final and disable regeneration; DB metrics untouched.

### R-32 — Dossier canonical pair

- **Что / результат:** people list and dossier expose one routed pair, provenance/freshness and its definition.
- **Файлы/модули:** `dashboard/models.py`, `dashboard/db_reader.py`, `dashboard/static/app.js`, labels.
- **Как:** use only R-17 user-scoped `BSView` (no direct entity/avg fallback); two tiles + exact
  source/stale marker + tooltip §1.2 + components; replace low-risk `Надёжный` fallback by
  `сохранённый риск низкий`; fix threshold column names/order only for optional context;
  no dashboard writes/LLM.
- **Почему:** C-02/C-23/C-25; S-CODE-06/S-CONST: current fallback can show two meanings.
- **Данные:** canonical, legacy-only, mapped mismatch, concurrent two-user readers.
- **Тир:** T1 — read-only dashboard.
- **Зависимости:** R-17/R-18/R-28.
- **Тест:** `tests/test_dashboard_db_reader.py::test_dossier_and_list_use_canonical_bs_pair`.
- **Критерий:** list/dossier canonical/legacy_snapshot/avg/zero/stale values, versions and exact markers equal
  the same R-17 view; stale high-C has `последний звонок не учтён`; other-user fields=0; tooltip
  `не детектор лжи`; full payload has no counts/duration or
  `над[её]ж|ненад[её]ж|эмоционально неустойчив`.
- **Условие:** `unconditional`.
- **Rollback:** hide component drilldown; mandatory pair can read projection from contact summary.

### R-33 — Shared compact delivery line

- **Что / результат:** digest and Telegram render the same counter-free ≤300-char BS statement.
- **Файлы/модули:** новый `src/callprofiler/deliver/bs_line.py`, `deliver/digest.py`, `deliver/telegram_bot.py`.
- **Как:** input only R-17 `BSView`; exact line/source/stale suffix §9.3; no call/outcome/fact counts or duration; each digest
  item applies existing 300-char cap after mandatory line preservation.
- **Почему:** C-23/C-24; S-CODE-06/S-CONST: Goal ≤300/no counters; Telegram currently emits call count.
- **Данные:** 0/1, high/low, long contact names, Cyrillic/emoji.
- **Тир:** T1.
- **Зависимости:** R-18/R-19.
- **Тест:** `tests/test_digest.py::test_shared_bs_line_under_300_chars_without_counts`.
- **Критерий:** full digest/Telegram snapshot equality for line; each item ≤300 chars; regex
  `n=|звонков|мин\.|фактов|обещаний:` and trait phrases absent; both numbers present; all four source values
  plus stale canonical render their exact marker with no direct fallback query.
- **Условие:** `unconditional`.
- **Rollback:** revert surrounding transport template; mandatory pair line remains because it fits independently.

### R-34 — Observable promise-outcome wording

- **Что / результат:** `contact_reliability` and its digest consumer return only observed outcome wording.
- **Файлы/модули:** `src/callprofiler/insight/promise_outcomes.py::contact_reliability`, `deliver/digest.py`.
- **Как:** preserve numeric internal summary; user text only exact §9.3 outcome phrases; unresolved means
  `пока неизвестны`; dashboard section title becomes `Исходы обязательств`; never
  `надёжен|надёжность|держит слово`; do not print n/count/days.
- **Почему:** C-05/C-23/C-24; S-CODE-04/S-CONST: outcome criterion is useful but not a personality trait.
- **Данные:** no outcomes, kept, late, broken, mixed and C<30.
- **Тир:** T1.
- **Зависимости:** R-09/R-33.
- **Тест:** `tests/insight/test_promise_outcomes.py::test_reliability_wording_is_observational`.
- **Критерий:** exact phrase snapshot per status; forbidden trait/counter regex absent in 100% cases.
- **Условие:** `unconditional`.
- **Rollback:** retain numeric internal return; disable optional outcome phrase, never restore trait label.

### R-35 — Observable psychology patterns

- **Что / результат:** psychology pattern triggers/labels describe observations only and retain repaired mechanisms.
- **Файлы/модули:** `src/callprofiler/biography/psychology_profiler.py`,
  `src/callprofiler/biography/data_extractor.py::get_behavioral_patterns`,
  `src/callprofiler/dashboard/labels_ru.py`, `dashboard/db_reader.py::_build_character_label`,
  dashboard/card/biography full surface snapshots.
- **Как:** use repaired counters/projection; exact labels §9.3; legacy `reliable` key renders
  `наблюдаемых расхождений мало` only when C≥30; `emotionally_volatile` renders
  `были эмоциональные всплески; на BS не влияет`; `SEVERITY.positive` renders `положительное наблюдение`;
  low/mid/high risk fallbacks render `сохранённый риск низкий|средний|высокий`, never a person type.
- **Почему:** C-01/C-04/C-06/C-23/C-24/C-27; S-CODE-01/S-DEC/S-CONST T-23.
- **Данные:** no evidence, 3 unresolved promises, broken/kept, contradiction, emotion-only.
- **Тир:** T2.
- **Зависимости:** R-07/R-09/R-20/R-28.
- **Тест:** `tests/test_psychology_profiler.py::test_bs_patterns_are_observational`.
- **Критерий:** no-evidence emits no reliability trait; emotion-only changes BS 0; psychology, biography
  and full dashboard/card snapshots contain no `reliable` trait rendering; case-insensitive stem regex
  `над[её]ж|ненад[её]ж|эмоционально\s+неустойчив|лжец|честн` matches 0 user-visible strings.
- **Условие:** `unconditional`.
- **Rollback:** keep raw keys/components; disable optional labels, never restore trait text.

### R-36 — Observable summary advice

- **Что / результат:** summary/card advice follows the exact BS/C table in §9.3 with no trait inference.
- **Файлы/модули:** `src/callprofiler/aggregate/summary_builder.py`, `deliver/card_generator.py` advice adapter.
- **Как:** use only R-17 `BSView`: stale starts `Последний звонок не учтён` and never emits an unqualified
  grade/advice; noncanonical starts its §8 marker; otherwise C<30 preliminary; else `BS_display=0` no observed discrepancy;
  `1≤BS_display≤50` isolated discrepancies; `BS_display>50` verify deadlines/specificity; no
  parse-zero→reliable fallback; whole line counter-free.
- **Почему:** C-01/C-23/C-24; S-CODE-06/S-CONST T-23: current `Надёжный партнёр` is false inference.
- **Данные:** BS0, 0.1, 0.4, 0.5, 50.4, 50.5, C29/30, every routed source, legacy parse-zero,
  high BS/C90 followed by scorer-error call.
- **Тир:** T1.
- **Зависимости:** R-19/R-28/R-30.
- **Тест:** `tests/test_summary_builder.py::test_bs_advice_uses_observational_decision_table`.
- **Критерий:** exact table outputs; stale high-C contains `Последний звонок не учтён`, Admiralty F6 and
  no unmarked recommendation; ≤300 chars; forbidden trait/counter regex absent.
- **Условие:** `unconditional`.
- **Rollback:** omit optional advice line; mandatory pair remains.

### R-37 — Independent latent BS synth

- **Что / результат:** seeded synth produces independent truth, structured facts, promises/outcomes and quality noise without production DB access.
- **Файлы/модули:** `src/callprofiler/insight/synth/bs_profiles.py`, synth corpus/noise loader, tests; spec
  `docs/research/bs-v2/synth-package/README.md`.
- **Как:** implement the complete frozen hash-RNG, seed/grid, channel-probability and hostile-strata table §10;
  README must mirror it, not supply omitted choices; exact byte/tag registry; latent first; 100-call master
  timeline, nested suffix views and resolver-only evidence calls; deterministic expectation grid plus stochastic
  channels; shared L/M and ASR/role error, adversarial M, MNAR, genre, detectable UNKNOWN and undetectable
  swaps; 100 seeds×400 contacts; loader only explicit temp/in-memory and rejects configured path; research
  smoke runs the same DGP/half-up code on seed20260822 rather than a stateful surrogate.
- **Почему:** C-19/C-20/C-30; S-SIM/S-DEC: independent truth and hostile common-mode strata.
- **Данные:** generated only, seeds list committed; no audio/private data.
- **Тир:** T2 — synth ground-truth design.
- **Зависимости:** R-13/R-14/R-16.
- **Тест:** `tests/insight/test_bs_synth_generator.py::test_bs_synth_is_independent_deterministic_and_db_safe`.
- **Критерий:** same seed byte-identical raw fixture; exact 100 seeds/400 contacts/100-call timeline and
  nested 0/1/3/10/100 suffixes; every resolved outcome has due `eNNN` call/date/transcript while first-call
  has none; every raw fact has exact `fact_type`+`quote` schema and survives the current
  FactValidator/R-16 grounding path when clean; every source-call token corpus recomputes exact quantized
  specificity through production `compute_specificity`; closed tag registry rejects unknown tag;
  expectation grid independent of scorer; all named strata present; smoke shares all three quality
  thresholds/probability constants/hash draws and has no `random.Random`/banker's round;
  configured production path raises before open; no sqlite/config import in generator.
- **Условие:** `unconditional`.
- **Rollback:** generator test-only; baseline rollout blocked if its later evaluator fails.

### R-38 — Preregistered synth evaluator

- **Что / результат:** one evaluator emits the exact recovery/noise/sensitivity metrics and pass/fail gates in §10.
- **Файлы/модули:** `src/callprofiler/insight/synth/bs_evaluate.py`, `tests/insight/test_bs_synth_recovery.py`.
- **Как:** route raw R-37 fixtures through R-16; primary default/n100 tau-b with declared tie rule and
  nearest-rank value5; emit clean/mixed and every n panel separately; fixed-denominator confidence sign
  test where ties are failures, optional pre-binned ARI, exact clean/n100 rank-sum comparator and §10.2
  half-loss discordance; emit seed/scenario counts and every OAT sensitivity variant.
- **Почему:** C-19/C-20/C-30/C-33/C-39; S-SIM/S-ROC: verification needs a frozen estimand/loss, not circular examples.
- **Данные:** exact R-37 corpus, no production DB.
- **Тир:** T2.
- **Зависимости:** R-16/R-37.
- **Тест:** `tests/insight/test_bs_synth_recovery.py::test_bs_synth_recovery_and_noise_gates`.
- **Критерий:** expectation tau-b=1; **default/n100** median≥.60/p05≥.50; all clean/default
  n=1/3/10/100 and mixed diagnostics present with no sparse gate; clean median confidence is strictly
  ordered n1<n3<n10<n100 for 100/100 seeds; mixed clean→severe positives≥63/100 with ties retained as
  failures; clean/n100 discordance numerator/denominator/loss formula exact and rate≤10%; OAT variant
  manifest exact; report byte-identical for same seeds.
- **Условие:** `unconditional`.
- **Rollback:** failing gate keeps baseline reader legacy until new formula version/ledger decision.

### R-39 — Global formula invariant suite

- **Что / результат:** one executable suite freezes every algebraic/first-call property in §10.
- **Файлы/модули:** `tests/test_bs_v2_properties.py` plus synth strategies (stdlib/Hypothesis only if already installed).
- **Как:** generate missing/permutation/duplicate/noise/as_of cases; compare ROC/rank-sum sensitivity;
  explicitly mutate empty calls, duration and LLM confidence (`.60…1.00` invariant; gate crossing separate).
- **Почему:** C-08…C-20/C-29/C-30/C-33/C-34; S-ROC/S-SIM/S-CONST: composite index needs algebraic invariants.
- **Данные:** pure generated inputs, 10,000 vectors/seeded matrix.
- **Тир:** T2.
- **Зависимости:** R-13/R-14/R-37/R-38.
- **Тест:** `tests/test_bs_v2_properties.py::test_bs_v2_global_invariants`.
- **Критерий:** 0 failures across ten §10 properties; ROC vs rank-sum discordant pairs ≤10%; runtime has
  no network/model call.
- **Условие:** `unconditional`.
- **Rollback:** failed property blocks v2 flag; never weaken gate without new formula version/ledger WHY.

### R-40 — Tenant ownership closure

- **Что / результат:** a machine-readable BS-v2 inventory proves every new read/write/consumer tenant-scoped.
- **Файлы/модули:** `tests/test_tenant_ownership.py` inventory plus R-06/R-15/R-18…R-36 callsites.
- **Как:** enumerate canonical/snapshot/mutator/projection/surface functions; require user argument and equal-user
  joins; same quote/contact logical keys in two users; DB trigger negative cases.
- **Почему:** C-25; S-CODE-01/S-CODE-06/S-CONST T-03: API fix R-02 is insufficient without all consumers.
- **Данные:** two users with colliding contact/entity ids, names and quotes.
- **Тир:** T2 — SQL ownership hard constraint.
- **Зависимости:** R-02/R-06/R-15/R-18/R-20/R-21…R-36.
- **Тест:** `tests/test_tenant_ownership.py::test_bs_v2_inventory_is_tenant_scoped`.
- **Критерий:** wrong-owner reads return none, mutators affect 0, same quote inserts two tenant rows, all
  surfaces leak 0 fields.
- **Условие:** `unconditional`.
- **Rollback:** stop v2 consumers; ownership tightening is retained, not rolled back to unsafe API.

### R-41 — Contracts and layer maps

- **Что / результат:** layer maps describe one implemented BS-v2 contract and no stale structural-zero claim.
- **Файлы/модули:** `.claude/rules/{graph,insight,db,dashboard,decisions}.md`.
- **Как:** record versions, canonical/snapshot schema, formula equations, replay order, projection ambiguity,
  UI semantics and legacy router; link claims ledger; no workstream/journal edits in this slice.
- **Почему:** C-04/C-21/C-22/C-28; S-CONST art.19: maps are implementation memory.
- **Данные:** committed code/test paths and this plan.
- **Тир:** T0.
- **Зависимости:** R-01…R-40.
- **Тест:** `tests/test_docs_contracts.py::test_bs_v2_plan_and_maps_reference_current_versions`.
- **Критерий:** grep finds score/confidence/router versions in five maps; equations/projection states exact;
  no map says BS≤20 expected after rollout.
- **Условие:** `unconditional`.
- **Rollback:** revert maps only with matching code rollback; never leave code/map mismatch.

### R-42 — Atomic Phase-A activation and closeout

- **Что / результат:** one release state makes the fully gated Phase-A pair the static default and records that exact state.
- **Файлы/модули:** `src/callprofiler/config.py`, `configs/features.yaml`, `docs/sintezdiharea.md`,
  `CHANGELOG.md`, `CONTINUITY.md`.
- **Как:** run §14 acceptance while R-17 safe default is legacy; only after PASS set both dataclass and YAML
  `bs_read_version=baseline`; add successor T-26/`BSV2-R-01…R-52` without rewriting T-19; record exact
  versions/tests and next first eligible conditional R-43/R-48 or ordinary workstream—not R-01. Config+memory
  form one release-state commit; a missing/stale half fails the test.
- **Почему:** C-22/C-28/C-35/C-37; S-CONST art.19: default flip and memory must describe one executable release.
- **Данные:** completed R-01…R-41 results, legacy/baseline config fixtures and maps.
- **Тир:** T2 — production reader activation.
- **Зависимости:** R-01…R-41 and §14 items 2…10 evaluated with the explicit baseline route while static default remains legacy.
- **Тест:** `tests/test_docs_contracts.py::test_bs_v2_phase_a_release_state_is_atomic`.
- **Критерий:** missing config now selects exact Phase-A version pair; legacy explicit route still byte-round-trips
  with 0 writes; an upgraded legacy-only contact still renders legacy number+C1 under missing/default config
  with zero backfill writes; dependency graph includes T-26; CHANGELOG one release entry; CONTINUITY exact versions/tests
  and one real next step; any incomplete gate leaves defaults legacy.
- **Условие:** `unconditional`.
- **Rollback:** set both static defaults to legacy in one release correction; keep schema/rows and observational UI
  safety text; append/overwrite journals to the rollback state.

## 12. Фаза B — optional accumulated-data refinements

Новые boolean candidate flags default false; enum defaults are `baseline|none|v001`; reader default
remains Phase A versions. Existing pipeline flags не меняются. Ни owner labels, ни real-DB learned
thresholds не становятся prerequisite. Phase B может подготовить candidate; activation ждёт Phase C
non-degradation where specified.

События условий:

- `E-B0`: все acceptance §14 Phase A green;
- `E-B1`: explicit `bs_refinement=contextual`; matching thresholds are R-44 output, not an entry prerequisite;
- `E-B2`: R-45 candidate algebra/hostile-synth falsifier green (никогда сам не активирует candidate);
- `E-B3`: `analysis_prompt_candidate=v002`, while `analysis_prompt_active=v001`; production activation false.

### R-43 — Refinement/version routing

- **Что / результат:** one explicit router makes baseline the immutable default and names every optional version.
- **Файлы/модули:** `configs/features.yaml`, `src/callprofiler/config.py`, `insight/bs_policy.py` registry.
- **Как:** add validated enums `bs_refinement=baseline|contextual|style` (default baseline),
  `bs_candidate=none|style` (none), `analysis_prompt_candidate=none|v002` (none), and
  `analysis_prompt_active=v001|v002` (v001). Contextual display requires only R-44 offline PASS and explicit
  flag because it cannot change either number; style/active-v002 routes require matching R-52 PASS manifest.
  Candidate routes are shadow-only; persist selected formula/policy in row/signature; unknown value fail-fast.
- **Почему:** C-08/C-22/C-35; S-ROC/S-CONST: optional must not silently reinterpret baseline.
- **Данные:** config fixtures missing/valid/invalid.
- **Тир:** T1.
- **Зависимости:** R-42.
- **Тест:** `tests/test_features_config.py::test_bs_refinements_default_to_baseline`.
- **Критерий:** missing config selects exact A versions/v001 and no candidate; invalid exits config error;
  style or active-v002 without PASS manifest fails closed to baseline/v001; candidate change requires distinct
  shadow signature/version and changes 0 active rows.
- **Условие:** `if E-B0 = Phase-A acceptance green → implement; else remain baseline`.
- **Rollback:** set `bs_refinement: baseline`.

### R-44 — Versioned contextual percentiles

- **Что / результат:** existing `bs_thresholds` can display user-relative context without changing BS/letter/confidence.
- **Файлы/модули:** `src/callprofiler/graph/calibration.py`,
  `src/callprofiler/graph/repository.py::get_latest_bs_thresholds`,
  `src/callprofiler/dashboard/db_reader.py`, `src/callprofiler/dashboard/static/app.js`.
- **Как:** filter exact formula/policy, `ORDER BY created_at DESC,id DESC`; compute p25/p50/p75/p90 only when
  explicit contextual flag and current existing eligibility; label `relative within your contacts`; never feed
  score, confidence or Admiralty baseline.
- **Почему:** C-24; S-CODE-01/S-CODE-06: develops thresholds without first-user gate.
- **Данные:** 0/2/3/100 synthetic contacts and stale version rows.
- **Тир:** T1.
- **Зависимости:** R-28/R-32/R-43.
- **Тест:** `tests/test_bs_policy.py::test_contextual_thresholds_never_change_numeric_baseline`.
- **Критерий:** toggling flag changes only relative label; score/C/letter byte-equal; <3 shows no context but both
  indices remain.
- **Условие:** `if E-B1 = bs_refinement contextual → relative label; else no context`.
- **Rollback:** flag baseline; rows retained versioned.

### R-45 — Within-contact promise-specificity candidate

- **Что / результат:** one default-off formula version tests a genre-canceling promise-vs-own-baseline specificity gap.
- **Файлы/модули:** `src/callprofiler/insight/bs_index.py`, `insight/bs_inputs.py`,
  `insight/features/specificity.py::compute_specificity`, synth/property tests.
- **Как:** candidate `v2_roc_observed_style_1`; reuse—not redefine—existing `compute_specificity` separately
  on each call's stored `speaker=OTHER` segments (UNKNOWN excluded), accept its raw 0…100 only when existing
  function returns a Feature from at least one nonempty token (zero hits remains the observed value0, not
  missing), then compute recency-weighted
  `sp=mean(specificity | ≥1 valid OTHER promise)` and `sn=mean(specificity | no valid OTHER promise)`;
  available only when both groups nonempty and total calls≥2; `S_gap=clamp((sn-sp)/100,0,1)`; first compute
  exact canonical `L_base=(3*aC*C+aP*P)/(3*aC+aP)`. Style may act only when L_base exists and S is
  available/positive; then the one-sided residual correction is
  `L_style=1-(1-L_base)*(1-S_gap/4)`, otherwise exact `L_base`. Division by4 gives style one ordinal slot
  against the existing 3+1 construct-near slots and caps its effect at one quarter of remaining headroom;
  zero/missing style can never dilute grounded C/P. The earlier convex-average candidate is rejected by
  the frozen positive control (0/100 improvements), not silently retained. Outer 11B/5L/2M unchanged;
  no user z-score. `S_gap` is score-only: it creates zero confidence potential/qualified mass, and
  `c1_effective_evidence_1` continues to compute N/E/A/S from baseline B and grounded C/P L (plus M only
  where §5 already allows it), never from `L_style`; a contact with only specificity therefore remains C=1.
  This conservative freeze avoids silently redefining confidence for a default-off hypothesis.
- **Почему:** C-06/C-07/C-27/C-33; S-CODE-05/S-PRAG/S-ROC: exact weakest style candidate, default weight0 baseline.
- **Данные:** exact token-materialized `specificity_null` and `specificity_signal` §10 strata,
  slope20/40/60 and divisor2/4/8 disclosed sensitivities, plus missing/over-100 specificity.
- **Тир:** T2 — new metric version.
- **Зависимости:** R-26/R-38/R-43.
- **Тест:** `tests/test_bs_v2_refinements.py::test_style_candidate_adds_rank_value_without_genre_false_positive`.
- **Критерий:** goldens `C1/P0/S-missing→L=.75`, `L_base=.75/S=.25→L_style=.765625`,
  only-S`.4→L missing`; only-S keeps exact `N=E=0,C=1`, and adding/removing S changes no confidence
  detail field; baseline byte-identical for every vector when S missing/0; deterministic
  specificity-null `S_gap=0`;
  across stochastic genre-only seeds nearest-rank p95 of `|mean(delta_score|G=1)-mean(delta_score|G=0)|` ≤2.0 displayed
  points (two one-point display steps: declared product loss, not effect size); on `specificity_signal`,
  report all frozen slopes20/40/60 and divisors2/4/8 without selection; canonical slope40/divisor4 candidate
  default/n100 retains tau median≥.60/p05≥.50 and improves tau over baseline in ≥63/100 seeds with ties failures. Any fail emits
  E-B2 FAIL/baseline; PASS only permits Phase-C temporal test and is not real-world validation.
- **Условие:** `if E-B0 AND bs_candidate=style → build and run offline gate; PASS emits E-B2 and a shadow
  candidate, FAIL leaves baseline; no self-dependency on E-B2`.
- **Rollback:** set baseline; candidate rows ignored by version.

### R-46 — Prompt v002 candidate and cache namespace

- **Что / результат:** a default-off prompt produces explicit attribution/grounding fields under a distinct cache key.
- **Файлы/модули:** `configs/prompts/analyze_v002.txt`, `src/callprofiler/analyze/{service.py,prompt_builder.py,
  response_parser.py,canary.py}`, `bulk/enricher.py`, `pipeline/orchestrator.py`, `config.py`.
- **Как:** add `structured_facts.who=ME|S2|UNKNOWN`, `bs_evidence[{quote,type,who}]`, promise
  `due/vague`; quote min8; UNKNOWN remains score-ineligible rather than being coerced to S2.
  One explicit resolver sends the same selected version to prompt filename, PromptBuilder, LLMClient cache
  namespace, parser and persisted `analyses.prompt_version`; remove hardcoded v001 paths from bulk and
  short/error fallbacks. `analysis_prompt_candidate=v002` is consumed only by shadow canary; live/bulk use
  `analysis_prompt_active=v001` until R-52 PASS activation.
- **Почему:** C-11/C-15/C-21; S-LLM/S-CODE-02/S-CONST: prompt bump only Phase B + M4.
- **Данные:** frozen synthetic prompt/canonical responses; no box DB.
- **Тир:** T2 — PROMPT_VERSION/cache invalidation.
- **Зависимости:** R-05/R-08/R-43.
- **Тест:** `tests/test_prompt_builder.py::test_analyze_v002_bs_fields_and_cache_namespace`.
- **Критерий:** live/bulk/fallback/canary record the same explicit selected version; v001 default byte-equal;
  v002 schema rejects missing who/quote; v001/v002 cache hashes differ 100%; candidate flag changes active
  production prompt/caches 0 times.
- **Условие:** `if E-B3 = flag candidate → generate shadow only; activation requires E-C2+E-C4 in R-52`.
- **Rollback:** `analysis_prompt_candidate=none`, `analysis_prompt_active=v001`; old cache selected,
  v002 files remain reproducible.

### R-47 — GPU-safe read-only M4 metrics

- **Что / результат:** one safely locked canary report can compare v001/v002 grounding without DB writes or GPU overlap.
- **Файлы/модули:** `src/callprofiler/analyze/canary.py`, `src/callprofiler/cli/commands/bulk.py`,
  `src/callprofiler/cli/main.py`, `src/callprofiler/cli/utils.py`, новый `src/callprofiler/ops/gpu_lock.py`,
  `src/callprofiler/pipeline/orchestrator.py`, `pipeline/watcher.py`, report dataclass.
- **Как:** implement exact §7 OS advisory lock; pipeline holds it across ASR→unload→LLM. Standalone canary
  loads only config text to locate existing DB/lock, nonblocking-acquires **before DB open and client
  construction**, then opens SQLite URI `mode=ro`+`PRAGMA query_only=ON`; it never calls
  `load_config_and_repo`, `repo.init_db`, migrations, directory creation or file logging. Output parent must
  already exist and only the explicit report is atomically replaced; lock releases in `finally`. Then add parse/truncated,
  required-field completeness, quote-match distribution, OTHER/UNKNOWN attribution, promise vague/due
  completeness; fingerprint server/model/prompt; keep `cache_conn=None` and no repository writes.
- **Почему:** C-11/C-21/C-26; S-LLM/S-CONST `.claude/rules/llm.md` M4.
- **Данные:** fake LLM responses offline, contended/uncontended lock, pre-M11 DB with WAL/cache;
  actual calls only in R-49.
- **Тир:** T2.
- **Зависимости:** R-46.
- **Тест:** `tests/test_canary.py::test_m4_report_contains_bs_grounding_metrics_and_writes_nothing`.
- **Критерий:** contention returns explicit busy before client construction with 0 `ensure_ready`/LLM calls;
  uncontended event order is lock→assert ASR/pyannote absent→LLM→unlock; report schema has all metrics and
  fingerprints; on both successful and contended pre-M11 fixtures `sqlite_master`, migrations, DB/WAL/SHM,
  cache and filesystem inventory are byte-equal except the named report; mkdir/init/schema/write calls=0;
  both variants sample same ordered call ids.
- **Условие:** `if E-B3 candidate exists → report capability; else skip`.
- **Rollback:** retain old canary fields; prompt remains off.

## 13. Фаза C — box verification only

Phase C существует **только** для named box-requiring Phase-B candidate (`style_1` или `prompt_v002`),
прошедшего offline gate. Contextual display R-44 меняет 0 numeric rows и Phase C не требует. Если таких
candidates нет, R-48…R-52 = `not-applicable`, box commands executed=0, Phase A завершена. C не валидирует и не
калибрует baseline, не меняет его constants и не превращает baseline bug в data-calibration task.
Любой fail/skip отключает только candidate. Все операции на verified copy/shadow; production DB
открывается read-only, originals/incoming не затрагиваются.

События условий:

- `E-C0(style_1|prompt_v002)`: для named branch существует соответственно verified backup in temp path
  либо frozen read-only transcript manifest;
- `E-C1(style_1)`: R-48 frozen paired score report PASS;
- `E-C2(prompt_v002)`: R-49 paired real-call M4 **and** semantic synth PASS;
- `E-C3(style_1)`: R-50 frozen temporal-outcome test PASS.
- `E-C4(candidate)`: R-51 candidate-specific rollback rehearsal PASS;
- `E-C5(candidate)`: R-52 atomic release manifest/config state committed.

### R-48 — Frozen paired style reference

- **Что / результат:** one frozen manifest contains paired baseline/style score rows on the same restored copy/as_of.
- **Файлы/модули:** `docs/research/bs-v2/box-package/paired_reference.py`,
  `docs/research/bs-v2/box-package/schemas/style-paired-reference.schema.json`,
  `docs/research/bs-v2/box-package/checklists/R48-style-reference.md`.
- **Как:** only for `style_1`: verified backup→temp restore; source hash; compute immutable baseline and style shadow
  side-by-side with fixed as_of; capture eligible contacts/missingness/signatures; no standalone baseline
  go/no-go and no weight tuning; production URI read-only.
- **Почему:** C-22/C-35; S-CONST/S-SIM: C is only paired optional non-degradation.
- **Данные:** copied box DB, no labels.
- **Тир:** T3.
- **Зависимости:** R-43/R-45; existing T-20 backup/T-24 harness.
- **Тест:** `docs/research/bs-v2/box-package/tests/test_shadow_report_contract.py::test_report_is_read_only_and_complete`.
- **Критерий:** baseline/style contact set 100% paired; source hashes unchanged; cross-tenant=0;
  style rows use separate version; contextual/prompt create 0 metric rows; absent style executes 0 box commands.
- **Условие:** `if E-B2 PASS AND E-C0(style_1) → paired style report; else not-applicable`.
- **Rollback:** discard temp restore/report run; production untouched.

### R-49 — M4 v001/v002 canary

- **Что / результат:** one M4 report decides whether prompt v002 preserves operations and BS semantics.
- **Файлы/модули:** `docs/research/bs-v2/box-package/m4_compare.py`,
  `box-package/prompt-semantic-corpus.json`, R-47 canary command/report.
- **Как:** hash-sort eligible transcript fingerprints and require the first 50; run each twice in deterministic
  AB/BA order by call hash under the R-47 exclusive lock with exact installed llama-server/model; compare parse/truncated, grounded quote,
  role attribution and per-call median latency; no cache/DB write. For 50 paired latency ratios run 10,000
  bootstrap resamples with `U_boot(b,d)=uint64_be(SHA256(utf8("bootstrap|20260822|{b}|{d}"))[0:8])/2**64`
  for zero-based replicate/draw and sample index `floor(50*U_boot)`; freeze sorted result number9500 as the
  nearest-rank one-sided 95% upper percentile of their median;
  10,000 fixes 0.01-percentage-point empirical-CDF resolution, not an accuracy claim. In the same locked,
  zero-write run evaluate a frozen 50-case role-tagged Russian synth cohort through parser→R-16→scorer:
  25 planted positives (10 word↔word contradictions, 15 vague OTHER promises) and 25 negatives (five each:
  concrete promise, explicit correction after new information, polite hedge without commitment, OWNER-only
  discrepancy, ASR-near mismatch without verbatim support). Each family uses five frozen lexical variants;
  corpus SHA and expected eligible C/P type are committed before model output. Run v001/v002 in the same
  AB/BA schedule at temperature0. For 625 positive-negative pairs use §10 half-loss; 25 per class makes one
  entire case 25/625=`.04`, the declared semantic product-loss unit, not an accuracy estimate.
- **Почему:** C-11/C-26/C-35/C-41; S-LLM/S-CONST: prompt/schema candidate requires M4.
- **Данные:** 50 copied/current call transcripts selected deterministically plus frozen 25/25 synthetic
  semantic controls; no owner labels/private text in synth.
- **Тир:** T3.
- **Зависимости:** R-46/R-47; frozen E-C0 transcript manifest (R-48 is not applicable to prompt).
- **Тест:** `docs/research/bs-v2/box-package/tests/test_m4_report_contract.py::test_same_calls_and_fingerprints`.
- **Критерий:** same 50 call ids/fingerprints; invalid count at most baseline+1 (one-call/2pp product-loss);
  grounded and OTHER-attribution counts at least baseline-1; bootstrap upper95 of median latency ratio≤1.00;
  candidate nearest-rank p95≤baseline p95 and both < existing 300s hard timeout; exact paired differences,
  Wilson count intervals and bootstrap seed reported. On semantic synth, v002 target-qualified positives
  ≥v001-1, unsupported C/P positives among 25 negatives ≤v001+1, half-loss ≤v001+`.04`, and median planted
  positive BS > median negative BS; duplicate run input/scorer JSON byte-equal. The real-call ±1 is one
  predeclared 2pp unit; synth ±1 is one 4pp class unit. Fewer than 50, corpus hash mismatch or any operational/
  semantic fail→v001 and no E-C2.
- **Условие:** `if E-B3 AND R-47 PASS AND E-C0(prompt_v002) → run; else not-applicable, v001 stays`.
- **Rollback:** flag false/cache namespace v001; canary writes nothing.

### R-50 — Refinement non-degradation report

- **Что / результат:** one frozen temporal test decides whether style_1 predicts future deterministic outcomes beyond baseline.
- **Файлы/модули:** `docs/research/bs-v2/box-package/style_holdout.py`,
  `docs/research/bs-v2/box-package/schemas/style-holdout.schema.json`.
- **Как:** before scores are inspected freeze `cutoff=max(persisted call date)-120 days`; pre-cutoff scores use
  only earlier rows, while criterion `Y` is mean §4.1 severity of post-cutoff `method=det` kept/late/broken
  outcomes within +120d. Eligible contact has pre-cutoff baseline+candidate opportunity and ≥3 such outcomes.
  Hash-sort eligible contacts and use the first exactly 20 for the confirmatory set; recompute candidate-minus-
  baseline Kendall tau-b after all `2^20` within-contact method-label swaps. One-sided p is
  `count(delta_perm>=delta_observed)/2^20`; ties are included in the numerator. All contacts are diagnostic only.
  Report call_type/unknown genre strata and missingness; no fit/tune.
- **Почему:** C-06/C-07/C-19/C-35/C-40; S-CODE-04/S-PRAG/S-SIM: synth-planted style link cannot prove incremental value.
- **Данные:** copied DB with pre-cutoff raw specificity/promises and post-cutoff deterministic outcomes; no owner labels.
- **Тир:** T3.
- **Зависимости:** R-45/R-48.
- **Тест:** `docs/research/bs-v2/box-package/tests/test_non_degradation_report.py::test_report_uses_frozen_versions_and_as_of`.
- **Критерий:** before reading scores require ≥20 eligible contacts, ≥60 future deterministic outcomes and
  ≥100 confirmatory pairs with `Y_i!=Y_j` and at least one method score strict. E-C3 PASS only if delta>0 and exact p<.05,
  baseline/candidate coverage identical, and no predeclared genre stratum with ≥5 selected contacts reverses
  sign. Three outcomes reuses the existing reliability support gate; 20 fixes feasible exact `2^20`
  enumeration; alpha .05 is the preregistered false-activation budget for this single optional candidate,
  not a learned threshold. Insufficient units or any fail→style off.
- **Условие:** `if E-B2 PASS AND E-C0(style_1) AND E-C1(style_1) → test; else not-applicable/baseline`.
- **Rollback:** discard shadow candidate rows/report; baseline rows untouched.

### R-51 — Candidate-specific rollback rehearsal

- **Что / результат:** one report proves every otherwise-passing candidate can return to baseline before any production activation.
- **Файлы/модули:** `docs/research/bs-v2/box-package/rollback_candidate.py`,
  `docs/research/bs-v2/box-package/checklists/R51-candidate-rollback.md`,
  `docs/research/bs-v2/box-package/schemas/candidate-rollback.schema.json`.
- **Как:** config remains baseline/v001. Style branch on temp restore hashes sources, shadow-reads
  style→baseline→style and recomputes only its versioned rows. Prompt branch with `cache_conn=None` routes
  shadow v002→active v001→shadow v002 over the same frozen transcripts and proves zero DB/cache writes.
  Prompt rehearsal also rechecks the frozen semantic-corpus hash and E-C2 scorer-input/half-loss fingerprint.
  Contextual is not a Phase-C metric/prompt candidate and was already numeric-invariant in R-44. Record time
  and exact before/after fingerprints; never edit production config.
- **Почему:** C-22/C-28/C-35; S-CONST T-25: candidate rollback must precede, not follow, release.
- **Данные:** style verified temp copy and/or prompt frozen transcript manifest; no owner labels.
- **Тир:** T3 — rollback rehearsal.
- **Зависимости:** style requires R-48/R-50 PASS; prompt requires R-49 PASS; T-20/T-25 harness.
- **Тест:** `docs/research/bs-v2/box-package/tests/test_bs_rollback_report.py::test_candidate_specific_rehearsal_precedes_activation`.
- **Критерий:** style baseline pair/signature recovered100% and second style read byte-equal first; prompt
  v001/v002 fingerprints repeat with DB/cache writes0; sources exact, cross-tenant/data-loss0; config remains
  baseline/v001; each applicable branch emits E-C4, any failure emits no release eligibility.
- **Условие:** `if (style_1: E-B2 AND E-C1(style_1) AND E-C3(style_1)) OR
  (prompt_v002: E-B3 AND E-C2(prompt_v002)) → rehearse exactly each satisfied branch; else not-applicable`.
- **Rollback:** discard temp/report state; production and active config were never changed.

### R-52 — Atomic candidate decision and activation

- **Что / результат:** one auditable release state activates only rehearsed candidates or records explicit baseline fallback.
- **Файлы/модули:** `docs/research/bs-v2/box-package/release-manifest.json`,
  `configs/features.yaml`, `.claude/rules/decisions.md`.
- **Как:** map each named candidate to exact E-B/E-C reports, fingerprints, version and WHY. Only after its
  E-C4 PASS, style may set `bs_refinement=style`, or prompt may set `analysis_prompt_active=v002` and clear
  candidate; missing/fail writes baseline/v001(reason). Contextual remains an explicit R-44 display flag.
  Manifest+config+decision form one release state; no tuning or owner-label field.
- **Почему:** C-08/C-22/C-26/C-28/C-35; S-CONST: activation must be explicit, reversible and after rehearsal.
- **Данные:** R-44 and applicable R-48…R-51 reports.
- **Тир:** T3 decision/release.
- **Зависимости:** R-51 and all applicable candidate reports.
- **Тест:** `tests/test_release_manifest.py::test_candidate_activation_requires_matching_rehearsal`.
- **Критерий:** every candidate exactly `enabled(version,rehearsal,report)` or `baseline(reason)`; missing or
  failed rehearsal cannot enable; active config equals manifest; Phase-A versions remain available;
  simulated single-flag rollback restores baseline/v001 with source writes0.
- **Условие:** `if style_1 has E-B2+E-C1+E-C3+E-C4 PASS → activate style; if prompt_v002 has
  E-B3+E-C2+E-C4 PASS → activate v002; each other branch stays baseline/not-applicable`.
- **Rollback:** atomically set style→baseline and/or prompt→v001, append decision correction; stored candidate rows/cache namespace retained.

## 14. Полное acceptance Phase A

Phase A готова только если одновременно:

1. R-01…R-42 green; все conditions literal `unconditional`, каждый slice ≤1 рабочего дня.
2. Fresh/upgrade migration parity, suite and ruff gates green.
3. First-call matrix normal/nonzero, short, parse-failed, no-analysis, LLM/scorer errors, role-fragile,
   null-contact/null-phone/retry: 10/10 associated canonical+minimal-card pairs before delivery;
   first-call C≤5; retry не дублирует/не сбрасывает, placeholder не auto-merge'ится.
4. Card max 512 UTF-8 bytes; digest item max 300 chars; no user-visible counts/duration.
5. Golden BS, clean N/E and raw-n confidence tables exact; dgp2 expectation/default-n100, all sparse
   diagnostics, confidence/noise and property gates §10 green; smoke uses same hash registry.
6. Upgrade full replay: graph_v1→graph_v2 once; two runs same details/signature/counts including replay-run,
   growth0; protected legacy entity/profile/source and second user byte-identical; pre-M11 limited preview
   changes neither schema nor file; injected failure full rollback; process order/wall clock hashes equal.
7. All new mutators require user_id; two-user suite has zero leak/collision.
8. BS-v2 initializer/scorer/recompute adds 0 model/LLM/GPU calls; existing v001 analysis path is unchanged,
   mocked in offline Phase-A tests, and `PROMPT_VERSION` remains v001.
9. Existing mechanisms remain queryable: stable-key v1 snapshot and round-trip, repaired v1 comparator,
   avg self-score, threshold rows, Admiralty, patterns, outcomes and explicit entity projection states.
10. UI strings state observed discrepancy and «не детектор лжи»; low confidence marks, never hides.

Failure in any item routes to its owning R-task. It never creates a requirement for owner labels/real DB calibration.

## 15. Rollback model

- `bs_read_version` selects immutable legacy snapshot or versioned Phase-A baseline with 0 writes; Phase-B flags false.
- M11 additive schema is retained. Never down-migrate/drop table to roll back.
- Source analyses/transcripts/promises/outcomes are immutable inputs; full replay replaces only
  `graph_v1|graph_v2` inside one user UoW; canonical metrics are versioned.
- `bs-recompute --dry-run` default; explicit user/as_of apply.
- Old v1 payload is captured `INSERT OR IGNORE` by stable subject key before first projection; offline R-17
  proves legacy→baseline→legacy→baseline byte-equivalence.
- Prompt v002 has separate cache and one flag; v001 never deleted.
- Card/dashboard/digest regenerate from canonical source, not restored by editing generated files.
- Any cross-tenant/source-hash/replay-growth failure is stop-the-line.

## 16. Место в `docs/sintezdiharea.md`

Зарегистрировать новый successor **T-26 — BS-v2 observed discrepancy + evidence confidence**, namespace
`BSV2-R-01…R-52`, чтобы не конфликтовать с уже существующими research R-01…R-03.

- Не переписывать T-19: его declared scope «existing display, no BS v2» остаётся исторически верным.
- BS-v2 использует завершённые contracts T-03 ownership, T-04 UoW, T-05 migrations, T-08 atomic artifacts.
- R-03…R-27 являются конкретными vertical slices T-15 semantic grounding и T-16 online/bulk convergence, а
  не ждут абстрактного завершения этих задач.
- R-28…R-36 расширяют T-19/T-23; R-37…R-40 пополняют T-24.
- Phase C R-48…R-52 входит в T-25 только для named candidate; никакая Phase-A edge не направлена в C.

Критический путь реализации:

```text
R01 → R02/R03 → R04 → R05 → R06 → R07
R01 → R08 → R09; R06/R09 → R10 → R11 → R12
R13 → R14; sources → R15 → R16 → R17 → R18 → R19 → R20
R20 → R21 → R22; R23/R20 → R24; R12/R09/R20 → R25; R20 → R26 → R27
R17/R20 → R28 → R29 → R30 → R31; R32/R33/R34/R35/R36
R16 → R37 → R38 → R39 → R40 → R41 → R42
optional contextual R43→R44; style R43→R45→R48→R50→R51→R52;
prompt R43→R46→R47→R49→R51→R52
```

Следующий шаг после исследования: **Phase A, R-01**.

## 17. Открытые риски — каждый с проверкой

| Риск | Почему открыт | Проверка / outcome |
|---|---|---|
| RISK-01 late curve 14 days | continuity, не empirical | R-39 sensitivity 7/14/28; >10% pair order → new version before enable |
| RISK-02 contradiction = rational update | current prompt lacks context taxonomy | synth negative-control + evidence drilldown; Phase B v002 instruction; never label lie |
| RISK-03 outcome resolver mistakes speech for deed | det/LLM both inferred from calls | method/quote shown in details; LLM half-weight; future prospective audit can only create new version |
| RISK-04 one fact yields extreme BS | renormalized missing families | confidence one-call ≤low range; UI snapshot/HCI wording; score never hidden |
| RISK-05 180-day decay wrong | no universal literature value | 90/180/360 sensitivity; as_of deterministic; new version if unstable |
| RISK-06 same-call correlation underestimated | many fields one response | max L/M credit/call; duplication property R-39 |
| RISK-07 confident role swap invisible | no UNKNOWN/fragile marker | explicit residual risk; synth expects BS recovery loss, not false C response |
| RISK-08 canonical/projection drift | three read models | R-18 signature, R-19/R-20 and R-25 equality tests |
| RISK-09 card budget forces omission | mandatory line + UTF-8 | R-30 boundary matrix; R-31 atomic path |
| RISK-10 relative thresholds relabel new user | stale/version rows | R-28/R-44 numeric/letter invariance |
| RISK-11 prompt v002 harms parse/latency | exact model/build unknown | R-49 paired M4; fail stays v001 |
| RISK-12 synth is circular | easy inverse construction | latent-first generator R-37 + evaluator R-38 + hostile strata |
| RISK-13 style encodes genre/politeness | specificity is genre-sensitive | baseline0; R-45 only shadow; frozen future det test R-50 or reject |
| RISK-14 performance on 16k calls | joins may scan | indexes/signature/incremental contacts; candidate paired runtime only, never baseline formula gate |
| RISK-15 schema drift central/ad-hoc insight | insight tables currently self-create | M11 fresh/upgrade parity and R-01 idempotence; one authoritative contract |
| RISK-16 low C read as low BS | two numbers cognitively confusable | labels always include nouns/100 + low-data phrase; snapshot review; never combine into one color |
| RISK-17 future leakage | retrospective as_of + negative age | pre-decay future exclusion R-15/R-16; property R-39 |
| RISK-18 censoring changes composition | rejected evidence could disappear | potential N retained; controlled monotonicity + end-to-end paired sign test R-38 |
| RISK-19 map ambiguity leaks identity | entity_contact_map many-to-many | exact R-20 states; unique→ambiguous and id-permutation tests |
| RISK-20 phone-less placeholders fragment one person | automatic merge would be worse corruption | one per existing source_md5, visibly unnamed; no auto-merge; explicit future contact assignment only |
| RISK-21 protected legacy entities accumulate | Phase A cannot reconstruct profiles safely | replay report protected count/keys; byte preservation; separate future owner-authorized cleanup only |
| RISK-22 dgp2 primary is enough-evidence, not first-call accuracy | sparse Bernoulli rank is noisy | publish every n panel; first-call promise limited to visible pair+C≤5, never tau claim |
| RISK-23 GPU advisory lock differs on Windows/dev | lock must work across processes, not metadata | R-47 two-process platform test; conflict fail-closed before client; failure keeps v001 |
| RISK-24 within-contact specificity may add no value | null-safe design can still be useless | R-45 positive/null gates then R-50 future-det gate; any fail leaves baseline |

## 18. Traceability matrix

| Claim + source | Спор → интерпретация → решение | Задача | Test | Criterion |
|---|---|---|---|---|
| C-01/C-23, S-DEC/S-CONST | lie/trait vs owner-visible value → observed pair always, disclaimer | R-21/R-30…R-36 | pipeline/full surface snapshots | 10/10 pair; forbidden trait regex0 |
| C-02/C-34, S-CODE-06 | entity/analysis/phone gate vs first call → normal-or-placeholder initializer before analysis | R-01/R-18/R-21 | null-contact/phone/failures | pair+artifact before delivery; C≤5; retry one row |
| C-03/C-04/C-27, S-CODE-01 | dead v1/freeze vs repair → counters live, general V/D direct0 | R-06…R-09/R-20/R-35 | fact/outcome/pattern fixtures | repaired counts exact; v1 mechanisms retained |
| C-05/C-09, S-PROM/S-CODE-04 | outcome useful but not deed → method/date/quote B + late sensitivity | R-08/R-09/R-23/R-39 | outcome provenance/curve | undated absent; 7/14/28 reported |
| C-06/C-07, S-PRAG/S-CODE-05 | style confound → baseline0, promise-local P; candidate must predict future det | R-16/R-35/R-45/R-50 | input/style holdout | baseline unchanged; fail/insufficient→off |
| C-08/C-33, S-ROC | no effect sizes → ROC ranks + declared constants/loss sensitivity | R-13/R-38/R-39 | golden/sensitivity | equations exact; pair discord≤10% |
| C-10, S-ROC | missing as clean/prior50 → available renormalization + low C | R-13/R-14 | missing vectors | all missing0/1; available zero≠missing |
| C-11/C-17, S-LLM | same-response agreement → M weakest, never corroborates L | R-14/R-16 | common-mode/post-gate mutations | post-gate delta0; L=M bonus0 |
| C-12/C-13/C-14, S-PHIA | probability/volume confusion → N/E evidence strength, empty credit0 | R-14/R-39 | curves/monotonicity | bounded; raw-n exact; empty/duration delta0 |
| C-15/C-29, S-CODE-02 | marginal Q/future clamp → per-cluster q, potential rejects, future exclusion | R-14…R-16/R-39 | quality/as_of properties | rejected cannot raise; future rows0 |
| C-16, S-CODE-01 | decay presented universal → code-continuity180 + 90/360 sensitivity | R-13/R-39 | as_of/decay sensitivity | deterministic; instability→new version |
| C-18, S-PHIA | stability mistaken for truth → unrounded chronological repeatability only | R-14/R-39 | split tie fixture | S=0 until each Ehalf≥2 |
| C-19/C-20/C-30/C-42, S-SIM | circular synth/mixed precision/false rho → closed dgp2, default-n100 tau-b, sparse panels | R-37…R-39 | generator/evaluator/smoke | grid1; default-n100 .60/.50; exact sign; tags closed |
| C-21/C-31, S-CODE-02/S-CONST | partial replay/data loss → protected legacy set, strict UoW, pre-init preview, run UPSERT/as_of | R-03…R-12/R-25 | upgrade/two-run/fault/order | growth0; protected hashes exact; preview schema writes0 |
| C-22/C-28, S-CODE-03 | flag without history → versioned canon + stable legacy snapshot/router | R-01/R-17…R-20/R-27 | migration/round-trip/CLI | v1/v2 byte round-trip; rerun0 |
| C-24, S-CODE-06 | remove consumers vs develop → exact Admiralty/pattern/advice projections | R-28…R-36 | policy/full snapshots | mechanisms remain; observable phrases exact |
| C-25/C-32, S-CONST | numeric identity/best-map shortcut → owner triggers, stable key, unique map only | R-02/R-06/R-20/R-40 | collision/map/tenant | leaks0; ambiguous copies0 |
| C-26/C-45, S-CONST | richer Phase-A LLM/cross-process canary vs 12GB order → CPU A + shared GPU lock in B/C | R-21…R-27/R-46…R-49 | mocked models/lock/canary | Phase-A model0; conflict ensure_ready0 |
| C-35, S-CONST | generic box flow/early enable → type-specific style/prompt branches, rehearsal then activation | R-48…R-52 | condition/release audit | no candidate→0 commands; pre-rehearsal config baseline |
| C-36, S-CODE-02/S-CONST | independent nested commits vs retry-safe convergence → one facade/UoW | R-12/R-20…R-26 | post-outcome/map/entity/mention faults | every table hash rolls back; retry exact |
| C-37, S-CONST | promised future default/backfill trap → legacy-safe slices + atomic release + missing-row fallback | R-17/R-42 | release-state/legacy-only fixture | incomplete→legacy; complete→baseline; fallback/rollback0 writes |
| C-38, S-CONST | rounded number vs false zero wording → zero-preserving display/four-way advice | R-28…R-36 | `.1/.4/.5`, BS0/nonzero snapshots | visible number, band and phrase agree100% |
| C-39/C-40, S-SIM | ambiguous ties/hidden DGP/box tuning → exact losses, hash DGP, frozen units | R-37…R-40/R-50 | evaluator/holdout contract | fixed denominators; exact enumeration; insufficiency off |
| C-41, S-CONST | timeout compliance vs latency non-degradation → paired relative gate plus hard stop | R-47/R-49 | same-50 paired report | upper95 median ratio≤1; p95 candidate≤baseline; <300s |
| C-43, S-CODE-04/S-LLM | per-path grounding choices → one span/role/tie contract and enumerated M support | R-05/R-08/R-16 | boundary matrix | 7/8 chars, .71/.72, me/s2 exact |
| C-44, S-CODE-06 | duplicate card writers → one renderer/atomic publisher/placeholder key | R-30/R-31 | writer inventory+byte boundaries | direct writes0; every writer ≤512 and pair present |
| C-46, S-PRAG | absolute specificity genre confound → within-contact gap + null/positive controls | R-45/R-50 | synth null/positive+holdout | null loss≤2; positive sign gate; real fail→off |

## 19. Hostile review disposition

| Рецензент | Возражение | Изменение/открытый риск |
|---|---|---|
| Статистик/математик | Future leakage; marginal Q; pseudo-agreement; mixed-exposure tau; hidden tags | pre-filter; N/E; B/L A; dgp2 default-n100 + sparse panels/tag registry R-14/R-38/R-39 |
| Deception researcher | General vagueness/blame/style do not equal declared discrepancy | direct0; repaired context/patterns; C/P-only L; future-det criterion only for style candidate |
| Архитектор | Replay duplicates/data loss; preview initializes DB; wall-clock/order; nested commits | protected legacy set; pre-init query-only preview; deterministic as_of/run UPSERT; strict UoW R-10…R-12/R-25 |
| DB/tenant | Schema has multiple DDL owners and no composite ownership guard | full M11 parity + trigger + order fixtures R-01; scoped identity/inventory R-02/R-40 |
| Адвокат владельца | NULL contact/phone loses first-call card; rollback flag had no history | non-merging placeholder+artifact; pre-analysis0/1; immutable snapshot/router |
| Этика/Constitution | Reliable phrases and rounding 0.1→0 create false absence | zero-preserving display, four-way advice, full-surface forbidden snapshots R-28…R-36 |
| Red team | fact-id multi-entity collision, rejected evidence disappears, circular/common-mode synth | stable entity key; potential attempts; hostile shared/MNAR DGP R-06/R-14/R-37 |
| Plan critic | Unowned flip, circular E-B2, wrong paths, generic candidate rows, activation-before-rehearsal | R-42; E-B2 output; exact paths; typed branches; R-51 rehearsal→R-52 activation |
| Operations | Phase C validated baseline; timeout mistaken for non-degradation; cross-process GPU overlap | candidate-only C; paired latency; shared OS lock; frozen style holdout; fail leaves baseline |

Round-3 fatal/high objections are mapped to concrete edits above; no objection is relegated to an
unverifiable risk. Residual RISK-01/02/03/05/07/18 are explicit limitations with offline/versioned
falsifiers, not owner labels or real-DB gates. Final dry-round status is recorded in `99-rounds.md`.

## 20. Definition of Done для программиста

Программист, открыв только этот файл, получает: construct (§1), tables/columns (§2/6), exact
preprocessing/formulas (§3–5), materialization/replay/GPU (§7), versions (§8), exact UI (§9), validation
(§10/14), ordered one-day tasks with files/algorithm/data/tier/deps/test/acceptance/condition/rollback
(§11–13), integration (§16), risks (§17) and traceability (§18).

Финальная механическая проверка плана:

- [x] Phase A tasks R-01…R-42 all `unconditional` and no B/C/box/owner/real-DB dependency.
- [x] No task begins with «исследовать»; every task has exactly one result and one named primary test.
- [x] Fact-type/who/outcomes/live verbatim/replay defects all have Phase A owners.
- [x] Both indices work at n=0/first call and remain visible at low confidence.
- [x] Existing BS/admiralty/pattern/outcome/summary mechanisms are extended, not frozen/deleted.
- [x] Formula/prompt/schema versions and old-value migration/rollback are explicit.
- [x] Phase B default is baseline; PROMPT_VERSION changes only there.
- [x] Phase C validates optional refinements only; Phase A has no incoming dependency from C.
- [x] Every numerical constant is code continuity, ROC mathematics, algebraic derivation or explicitly
  preregistered engineering gate—not presented as an external effect size.
