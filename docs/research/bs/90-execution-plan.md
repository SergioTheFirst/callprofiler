# 90 — План разработки: «Надёжность обязательств» (CR) + индекс уверенности (CI) — T-26 после CP-5

> Единственный deliverable исследования. Читается и исполняется без остальных файлов `docs/research/bs/`;
> ссылки на C-n (claims-ledger), L-nnn (литература), D-n (data-surface), S-n (surprise-ledger) — для
> «почему», не для исполнения. Контракт: задачи `R-01…R-30` в порядке исполнения, каждая ≤1 дня, ровно
> один проверяемый результат; поля: что · файлы · как · почему · данные · тир · зависимости · тест ·
> приёмка · условие · rollback. Эксперименты для бокса — тоже R-задачи с правилом решения, записанным
> ДО данных. Пути — относительно `src/callprofiler/`, если не указано иное.

---

## 0. Концепция — что измеряем и что НЕ измеряем

**Измеряем.** `CR` — частоту исполнения обязательств, которые контакт берёт перед владельцем, в
диаде `(user_id, contact_id)`; с апостериорным интервалом. И `CI` — калиброванную уверенность системы
в показанной фразе о CR. Единица — `contact_id` (не graph-`entity`).

**НЕ измеряем и не показываем:** ложь, bullshit, намерение, честность, «доверие», черты личности,
эмоциональную неустойчивость, уклончивость/противоречивость как черты (C-01, C-02, C-03, C-17).
Слова «ненадёжен», «врёт», «BS», буквы A–F — запрещены в любом UI-тексте (тест R-12/R-10).

**Почему так.** Текущий `bs_index` = `20·min(contradictions/total_calls,1)` — 4 из 5 членов формулы
структурно ≡ 0 (D1: `graph/repository.py:399-402` схлопывает vagueness/blame_shift/emotion_spike в
`'fact'`; `broken_promise` никто не производит), атрибуция говорящего потеряна (D2), дословность в
боевом пути не проверяется (D3), «калибровка» ранговая (D6). Оживлять нечего: «BS» не имеет внешнего
критерия (C-01, C-04). Единственный сигнал с внешним критерием — исходы обещаний (C-05, L-089–L-096).

**Старый BS.** `graph/aggregator.py::_bs_v1_linear` и колонка `entity_metrics.bs_index`
(`bs_formula_version='v1_linear'`) **остаются как есть** — `EntityMetricsAggregator` продолжает
выполняться (инвариант `graph.md`: `entity_metrics = f(events)`), колонка не читается ни одним
production-потребителем после R-02/R-12–R-14. Это и есть `LEGACY_UNVERIFIED` для BS (T-23).

---

## 1. Источники данных

| Таблица/колонка | Роль | Замечания |
|---|---|---|
| `promise_outcomes(user_id, promise_key PK, contact_id, call_id, side, what, due, status kept\|late\|broken\|unknown, days_late, quote, evidence_date, confidence, method det\|llm)` | **первичный** — исходы | `insight/promise_outcomes.py`; `side='contact'` только; `who='UNKNOWN'` уже исключён там |
| `calls.role_fragile`, доля `speaker='UNKNOWN'` сегментов звонка-обещания | `w_role` | `diarize/role_assigner.py:12-23`; доля считается из `transcripts` |
| `outcome_feedback` (новая, R-04) | подтверждённые исходы владельца (вес 1.0) | ✓/✗ из досье и бота |
| `reliability_params` (новая, R-04) | приор α₀/β₀, q_det/q_llm, h, w_role-режим, флаги, версия | одна строка на `user_id`+version |
| `fact_feedback` | НЕ вход (семантика confirm/reject факта, не исхода) | остаётся как есть |
| `entity_metrics.bs_index`, `contact_summaries.avg_bs_score`, LLM `bs_score/bs_evidence` | **не входы** (D5) | остаются в БД/raw_response как legacy |

---

## 2. Признаки — формулы

Для каждого обещания i контакта (только `side='contact'`):

- `y_i ∈ {1 (исполнено: kept∪late), 0 (broken)}`; `unknown` → не в α/β, но в покрытие.
- `w_label,i` = 1.0 если есть `outcome_feedback` (и `y_i` берётся оттуда); иначе `q_det` при
  `method='det'`, `q_llm` при `method='llm'` (из `reliability_params`; до E-1 — `q_det=0.7`, `q_llm=0.6`,
  `calibrated=0`).
- `w_role,i` = `1 − unknown_share(call_id_i)` (режим `continuous`) или `1` (режим `off`) — E-9.
- `w_time,i` = `0.5^(age_days_i / h)`; `h=∞` → 1 — E-8.
- `w_i = w_label,i · w_role,i · w_time,i`.
- `coverage = (kept+late+broken) / (kept+late+broken+unknown)`.
- `n_unknown_overdue` = `unknown` с `due < today − 2` и ≥2 звонками с контактом после `due`.
- `repeat_unfulfilled` = число групп обещаний (word-overlap ≥0.8 по `normalize_lemma`-токенам `what`,
  как в `promise_outcomes._content_words`) с ≥2 элементами за последние 180 дней без `kept/late`.
- `certainty_i` (только E-5/R-26) — det-regex по `quote` обещания:
  `\b(точно|гарантир\w*|сто процентов|100%|обязательно|железно|без вопросов|однозначно)\b` (ё-норм).

---

## 3. Preprocessing

- Текст обещаний/цитат не меняется (verbatim хранится). Сравнения — через `insight/textnorm.norm_quote`
  и `features.base.normalize_lemma` (ё→е), как в M8/B3.
- Даты: `promise_outcomes.due` (может быть NULL → `n_unknown_overdue` не считает).
- UNKNOWN-доля звонка: `SELECT SUM(speaker='UNKNOWN')*1.0/COUNT(*) FROM transcripts WHERE call_id=?`
  (кэшируется в `contact_reliability.mean_unknown_share`).

---

## 4. Агрегация и неопределённость

- Приор: `α₀, β₀` методом моментов по долям исполнения контактов юзера с ≥5 разрешёнными исходами
  (`m = mean(p_c)`, `v = var(p_c)`; `k = m(1−m)/v − 1`; `α₀ = m·k`, `β₀ = (1−m)·k`; если контактов < 10
  или `v ≤ 0` → `α₀=β₀=1`). Хранится в `reliability_params`, пересчитывается при `reliability-build`.
- Posterior: `α = α₀ + Σ w_i·y_i`, `β = β₀ + Σ w_i·(1−y_i)`; `n_eff = Σ w_i`.
- Медиана `m`, 80%-интервал `[q10, q90]` Beta(α,β) — численно (сетка 20001 точек, как `00_ci_demo.py`,
  numpy-only; ошибка < 1e-3).
- `cr-v1n` (условно, R-17): Rogan–Gladen на долях до posterior:
  `p_adj = (p_obs − (1−spec)) / (sens − (1−spec))`, clamp [0,1]; `sens/spec` из E-1 по `method`;
  применяется только если `sens − (1−spec) ≥ 0.2`.
- `cr-v1c` (условно, R-18): `unknown_overdue` входят как `y=0` с весом `w_i·π_b`, где `π_b` =
  измеренная в E-2 доля провалов среди adjudicated overdue-unknown.

---

## 5. Индекс уверенности CI (1–100)

- **Семантика.** `CI` = вероятность (в %), что истинная доля исполнения лежит в пределах ±0.1 от
  показанной медианы. Критерий калибровки: среди контактов с `CI≈X` доля случаев, где adjudicated доля
  попала в окно, ≈ X%.
- **Формула.** `CI = clamp(round(100·∫_{lo}^{lo+0.2} Beta(r;α,β)dr), 1, 100)`, `lo = clamp(m−0.1, 0, 0.8)`.
- **Фраза** от `m`: ≥0.8 «держит слово»; [0.6,0.8) «в основном держит»; [0.4,0.6) «через раз»;
  [0.2,0.4) «чаще не выполняет»; <0.2 «почти не выполняет».
- **Тир evidence** от `n_eff`: 0 → `no_data`; <2 → `insufficient`; <4 → `limited`; <8 → `moderate`;
  ≥8 → `substantial` (пороги — параметры `reliability_params.tier_cuts`, пере-привязываются E-3).
- **Гейты показа (C-20).** Факты (строки исходов) — всегда. Фраза — при `CI ≥ 50` И тир ≥ `limited`;
  при `50 ≤ CI < 60` — «похоже, …». Негативные фразы (<0.4) — дополнительно `n_eff ≥ 4`. Покрытие
  < 0.3 → `CI := min(CI, 59)`. Число `CI` — только при `reliability_params.numeric_ci_enabled=1`
  (R-20); до того — слово тира.
- **Что НЕ поднимает CI:** число звонков, длительность, давность общения без обещаний, LLM-`confidence`,
  тир контакта. Тест R-07.
- **Уровни.** Per-claim класс evidence у каждой строки факта: `E0` (owner-подтверждён), `E1`
  (det/llm-исход с цитатой), `E3` (unknown). Per-contact CI — только для головной фразы. Агрегации
  «средней уверенности» нет.

---

## 6. Схема БД (R-04) — миграция 10 в `db/migrations.py::ALL_MIGRATIONS` + `db/schema.sql`

```sql
CREATE TABLE IF NOT EXISTS reliability_params (
  user_id TEXT NOT NULL REFERENCES users(user_id),
  version TEXT NOT NULL,                      -- 'cr-v1' | 'cr-v1n' | 'cr-v1c'
  alpha0 REAL NOT NULL, beta0 REAL NOT NULL,
  q_det REAL NOT NULL DEFAULT 0.7, q_llm REAL NOT NULL DEFAULT 0.6,
  sens_det REAL, spec_det REAL, sens_llm REAL, spec_llm REAL,   -- E-1 (NULL до измерения)
  pi_unknown_broken REAL,                     -- E-2 (NULL до измерения)
  half_life_days REAL,                        -- NULL = без затухания (E-8)
  role_weight_mode TEXT NOT NULL DEFAULT 'continuous' CHECK(role_weight_mode IN ('continuous','off')),
  tier_cuts TEXT NOT NULL DEFAULT '[2,4,8]',  -- JSON: n_eff cuts insufficient/limited/moderate/substantial
  calibrated INTEGER NOT NULL DEFAULT 0,      -- 1 после E-1
  numeric_ci_enabled INTEGER NOT NULL DEFAULT 0, -- 1 после E-3 стадии 2
  params_hash TEXT NOT NULL, computed_at TEXT NOT NULL,
  PRIMARY KEY (user_id, version)
);
CREATE TABLE IF NOT EXISTS contact_reliability (
  contact_id INTEGER PRIMARY KEY REFERENCES contacts(contact_id),
  user_id TEXT NOT NULL REFERENCES users(user_id),
  version TEXT NOT NULL, params_hash TEXT NOT NULL,
  alpha REAL NOT NULL, beta REAL NOT NULL, n_eff REAL NOT NULL,
  n_kept INTEGER NOT NULL, n_late INTEGER NOT NULL, n_broken INTEGER NOT NULL,
  n_unknown INTEGER NOT NULL, n_unknown_overdue INTEGER NOT NULL, n_confirmed INTEGER NOT NULL,
  coverage REAL NOT NULL, mean_unknown_share REAL,
  median REAL NOT NULL, q10 REAL NOT NULL, q90 REAL NOT NULL,
  ci INTEGER NOT NULL CHECK(ci BETWEEN 1 AND 100),
  phrase_key TEXT NOT NULL,                   -- 'keeps'|'mostly'|'half'|'often_not'|'rarely'|'no_data'
  tier TEXT NOT NULL,                         -- no_data|insufficient|limited|moderate|substantial
  show_phrase INTEGER NOT NULL,               -- гейт §5 уже применён
  repeat_unfulfilled INTEGER NOT NULL DEFAULT 0,
  recent_phrase_key TEXT,                     -- фраза по исходам последних 180 дн., если ≥3
  computed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contact_reliability_user ON contact_reliability(user_id);
CREATE TABLE IF NOT EXISTS outcome_feedback (
  user_id TEXT NOT NULL REFERENCES users(user_id),
  promise_key TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK(verdict IN ('kept','broken','unknown')),
  source TEXT NOT NULL DEFAULT 'dashboard', created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, promise_key)
);
```
`contact_reliability` — DERIVED, полный rebuild на `user_id`. Старых значений для миграции нет
(новые таблицы); `entity_metrics.bs_index` не трогается.

---

## 7. Где пересчитывается; GPU; инвариант replay

- `reliability-build --user X` (R-08): `DELETE … WHERE user_id=?` → fit приора → insert всех контактов с
  ≥1 обещанием `side='contact'` (остальные — нет строки = `no_data`). numpy/SQL, без LLM/GPU →
  допустимо в ASR-окне.
- Вызовы: в конце `run_promise_outcomes` (CLI `promise-outcomes`), в watcher `_run_insight_fit` после
  `recompute_tiers`, после записи `outcome_feedback` (точечно для одного контакта — та же функция с
  `contact_ids=[…]`, но приор не пересчитывается).
- `graph-replay` **не вызывает** `reliability-build` (граф не вход) — инвариант `graph.md` сохранён
  без изменений. Один пункт всё же касается графа: R-03 (verbatim в боевом пути) — это усиление
  существующего validator, replay-детерминизм не меняется.

---

## 8. Versioning и миграция старых значений

- `CR_VERSION` в `insight/reliability.py`; `reliability_params.version`; `params_hash = sha1(JSON всех
  полей params)` в каждой строке `contact_reliability` — смена любого параметра ⇒ rebuild (как
  `TABLE_VERSION` age_style).
- `PROMPT_VERSION` analyze-промпта НЕ меняется в R-01…R-28 (D-13). Меняется только в R-29 (условно) —
  тогда кэш `llm_calls` инвалидируется штатно (`llm.md`).
- `promise_outcomes` (`PROMPT_VERSION_PROMISE='promise-v1'`) не меняется.

---

## 9. UI

**Карточка (`deliver/card_generator.py`, ≤512 байт).** Строка `grade:` заменяется строкой
`надёжность: {фраза} · {тир-слово | ув. N}` или `надёжность: данных мало`. Бюджет: самая длинная
фраза «похоже, чаще не выполняет · недостаточно» = 43 символа ≈ 80 байт UTF-8 против `grade: B3 —
обычно надёжен, информация возможно верна` (≈85 байт) — не длиннее текущей.
**Досье (`dashboard/db_reader.py::get_person_dossier`, `static/app.js`).** Секция «Надёжность
обязательств» в слое «Поведение» (вместо `promise_outcomes`-фразы и `admiralty`): (1) фраза+тир/CI
если `show_phrase`, иначе «данных мало»; (2) до 5 строк исходов: дата · «обещал …» · исход · класс
(✓ подтверждено / по разговору / неизвестно) · кнопки ✓/✗; (3) `repeat_unfulfilled>0` → строка
«одно и то же обещал несколько раз без исполнения» + цитаты; (4) data-quality: «роли в части звонков
неясны» (mean_unknown_share>0.3), «исходы известны по малой части обещаний» (coverage<0.3);
(5) «недавнее vs общее» если `recent_phrase_key` задан и отличается. Индексы `bs_index`, `admiralty`
из `indices`/шапки удаляются.
**Digest (`deliver/digest.py`).** `_reliability_note` → фраза из `contact_reliability` только при
`show_phrase=1`; ≤300 симв. сохраняется.
**Бот.** Кнопки `ov|{promise_key}|k` / `ov|{promise_key}|b` под строками обещаний в `/promises` и в
ежедневном отчёте (F5) — тот же паттерн, что `fv|…` (`telegram_bot.py:560-605`), гейт `_get_user_id`.

---

## 10. Место в `docs/sintezdiharea.md` и зависимости

Новая запись **T-26 — Reliability v2: CR + CI** (P1, после CP-5), как конкретизация D-01 («начать
максимум с одной измеренной проблемы»). Зависимости: T-05 (миграции — есть), T-15/T-23 (классы
evidence — CR вводит свои `E0/E1/E3` локально, совместимо), T-19 (RiskPolicy — не пересекается: риск
не трогаем), T-20 (backup перед box-package). R-01…R-15 не требуют CP-5 технически (только
контактное пространство), но продуктово — после CP-5 по решению владельца.

---

## 11. Задачи

### Фаза A — фундамент (dev-ноутбук, всё офлайн)

#### R-01 · Бокс: подготовка и baseline-замеры (E-0a)
- **Что:** копия боевой БД для исследования + три замера на ней: мёртвые члены BS (D1), покрытие исходов,
  качество ролей.
- **Файлы:** `docs/research/bs/box-package/README.md`, `scripts/01_bs_dead_terms.py`,
  `scripts/02_promise_coverage.py`, `scripts/03_role_quality.py` (уже написаны; боевую БД не открывают —
  принимают `--db` путь копии).
- **Как:** `watch` остановлен; `python -m callprofiler backup` → `verify-backup` → копия в
  `C:\calls\research\callprofiler-YYYYMMDD.db`; запуск трёх скриптов → `box-package/results/E0a.md`.
- **Почему:** C-04 фальсификатор; S-2 (сколько контактов вообще имеют исходы); C-07.
- **Данные:** копия БД. **Тир:** T0 (бокс, чтение). **Зависимости:** —.
- **Тест:** smoke `scripts/*.py --synth` на дев-ноутбуке (каждый скрипт строит свою мини-БД).
- **Приёмка:** результаты записаны; `MAX(bs_index) ≤ 20` и отсутствие `event_type` вне CHECK-списка
  подтверждены (если НЕТ — стоп, пересмотреть D1 до продолжения).
- **Условие:** unconditional. **Rollback:** не нужен (чтение копии).

#### R-02 · Удаление мёртвых потребителей: `advice` без `bs_score`, 4 trait-паттерна
- **Что:** `aggregate/summary_builder._generate_advice` перестаёт использовать `bs_score`
  (`avg_bs_score` больше не считается — колонка остаётся, пишется `NULL`); `biography/psychology_profiler.
  _extract_patterns` удаляет `contradictory`, `vague_communicator`, `blame_shifter`,
  `emotionally_volatile` (входы ≡ 0, D1) и `reliable` (D8); `promise_breaker` остаётся до R-13.
- **Файлы:** `aggregate/summary_builder.py:378-420,509-530`, `biography/psychology_profiler.py:244-266`,
  `dashboard/labels_ru.py` (PATTERN_NAME — удалить 4 ключа), тесты.
- **Как:** удалить ветки; `advice` = по `risk` и долгам; `_compute_weighted_bs_score` удалить.
- **Почему:** D1, D5, D8, C-17; deletion over addition.
- **Тир:** T1. **Зависимости:** —.
- **Тест:** `tests/test_summary_builder.py::test_advice_ignores_bs_score`;
  `tests/test_psychology_profiler.py::test_patterns_only_promise_breaker_and_high_risk` (паттерны из
  метрик с `vagueness_count=5` → отсутствуют).
- **Приёмка:** grep `bs_score` в `aggregate/`, `biography/psychology_profiler.py` → 0 вхождений;
  suite зелёный.
- **Условие:** unconditional. **Rollback:** `git revert` одного коммита; данных не трогает.

#### R-03 · Verbatim-гейт цитат в боевом пути
- **Что:** `GraphBuilder.update_from_call` получает транскрипт во всех вызовах.
- **Файлы:** `graph/builder.py:191`, `pipeline/orchestrator.py:994`, `bulk/enricher.py:276`,
  `db/uow.py:8`, тест.
- **Как:** в builder: если `transcript_text is None` — загрузить сам через `self._repo` (`SELECT text
  FROM transcripts WHERE call_id=? ORDER BY start_ms`, join '\n'); вызывающих не менять (один гард в
  общей функции — все пути). Порог `MIN_MATCH_RATIO=0.72` не менять (E-1 даст цифру для пересмотра).
- **Почему:** D3, C-06, C-07 — без гейта граф до replay содержит непроверенные цитаты.
- **Тир:** T2 (путь записи анализа). **Зависимости:** —.
- **Тест:** `tests/test_graph_builder.py::test_update_from_call_loads_transcript_and_rejects_
  nonverbatim` (факт с цитатой не из транскрипта → `facts_rejected==1`, в events не попал).
- **Приёмка:** на synth-БД с подменённой цитатой факт отброшен; `graph-replay` на тестовой БД даёт
  тот же результат, что и боевой путь (детерминизм).
- **Условие:** unconditional. **Rollback:** revert; events не меняются ретроактивно.

#### R-04 · Миграция 10: `reliability_params`, `contact_reliability`, `outcome_feedback`
- **Что:** DDL §6.
- **Файлы:** `db/migrations.py` (`Migration(10, "reliability_tables", _m010_reliability_tables)`),
  `db/schema.sql`, `tests/test_migrations.py`.
- **Как:** `CREATE TABLE IF NOT EXISTS` ×3 + индекс; в `schema.sql` те же DDL.
- **Почему:** C-16; семантика `outcome_feedback.verdict` (исход) ≠ `fact_feedback.verdict`
  (confirm/reject) — отдельная таблица, CHECK `fact_feedback` не трогаем (recreate запрещён, db.md).
- **Тир:** T2 (SQL write-path/миграция). **Зависимости:** —.
- **Тест:** `tests/test_migrations.py::test_m010_idempotent_and_schema_sql_in_sync` (свежая БД из
  `schema.sql` → все миграции no-op; checksum журнала).
- **Приёмка:** `apply_migrations` на копии боевой БД (бокс, R-01 копия) проходит; `PRAGMA user_version=10`.
- **Условие:** unconditional. **Rollback:** миграция аддитивна; таблицы можно `DROP` вручную — в коде
  отката нет (применённую миграцию не править).

#### R-05 · Synth: генератор обещаний и исходов с ground truth
- **Что:** `insight/synth/promises.py` — для каждого контакта архетипа задаётся истинная доля `p_true`,
  генерируются `promise_outcomes` (det/llm-метод, `unknown` по заданной доле покрытия, опц.
  MNAR-смещение), `calls` с UNKNOWN-долями; возвращает словарь `contact_id → p_true`.
- **Файлы:** `insight/synth/promises.py`, `insight/synth/corpus.py` (вызов в `build(..., promises=True)`),
  `tests/insight/test_synth_promises.py`.
- **Как:** `random.Random(seed)`; `n_promises ~ Poisson(λ_arch)`; `y ~ Bernoulli(p_true)`; ярлык
  det с точностью `q_true` (переворот); покрытие `c_arch`; MNAR: `P(unknown|y=0) = c·(1+δ)`.
- **Почему:** S-11/D10 — без этого CI/калибровка не тестируемы офлайн. Synth — механизм, не evidence.
- **Тир:** T2 (дизайн ground truth). **Зависимости:** —.
- **Тест:** `test_synth_promises.py::test_ground_truth_rates_recoverable` (при q=1, c=1 эмпирическая
  доля → `p_true` ±0.05 при n≥200).
- **Приёмка:** `SyntheticCorpus.build(promises=True)` заполняет `promise_outcomes` по реальной DDL
  (из `insight/promise_outcomes.py`), `synth` остаётся совместим с прежними тестами (ARI-гейт зелёный).
- **Условие:** unconditional. **Rollback:** флаг `promises=False` по умолчанию.

#### R-06 · `insight/reliability.py` — чистые функции и rebuild
- **Что:** `posterior(alpha0, beta0, outcomes) -> (alpha, beta, n_eff)`; `beta_median_q(alpha, beta) ->
  (median, q10, q90)`; `ci_window(alpha, beta, half=0.1) -> int`; `phrase_key(median)`; `tier(n_eff,
  cuts)`; `gates(...) -> show_phrase`; `fit_prior(rates)`; `build_contact_reliability(conn, user_id,
  contact_ids=None) -> stats`; `CR_VERSION='cr-v1'`.
- **Файлы:** `insight/reliability.py` (новый, ≤400 строк), `insight/repository.py` (не трогать —
  DDL в миграции).
- **Как:** §2–§5 дословно; веса `w_label` из `reliability_params` (строка создаётся с дефолтами при
  первом build); `outcome_feedback` перекрывает `y` и даёт `w_label=1`; Beta через сетку (numpy,
  `np.linspace(0,1,20001)`, `scipy` не использовать — нет в зависимостях); `repeat_unfulfilled` по
  `_content_words` (импорт из `promise_outcomes`); `recent_phrase_key` по исходам ≤180 дн., если ≥3.
- **Почему:** C-05, C-10, C-11, C-13, C-16, C-19, C-20.
- **Тир:** T2. **Зависимости:** R-04, R-05.
- **Тест:** `tests/insight/test_reliability.py` (см. R-07).
- **Приёмка:** `build_contact_reliability` на synth (R-05) пишет строку на каждый контакт с ≥1
  обещанием; `params_hash` совпадает при повторном вызове.
- **Условие:** unconditional. **Rollback:** модуль не подключён к UI до R-10; удаление файла.

#### R-07 · Тесты свойств CR/CI (офлайн)
- **Что:** один файл тестов, фиксирующий свойства §5.
- **Файлы:** `tests/insight/test_reliability.py`.
- **Как (функции):** `test_ci_monotone_in_n_at_fixed_rate`; `test_ci_bounds_1_100_and_n0_equals_prior_
  mass`; `test_determinism_double_build_identical`; `test_total_calls_does_not_change_ci` (два
  контакта: одинаковые исходы, 5 vs 500 звонков → равные строки кроме contact_id);
  `test_negative_phrase_requires_n_eff_4`; `test_coverage_below_03_caps_ci_59`;
  `test_unknown_share_lowers_n_eff`; `test_confirmed_outcome_weight_1_overrides_det`;
  `test_order_invariance`; `test_synth_calibration_ece_le_005` (synth R-05, q=1, c=1, 300 контактов:
  доля контактов с `|p_true − median| ≤ 0.1` в бине CI ≈ CI; ECE по 5 адаптивным бинам ≤ 0.05);
  `test_no_forbidden_words_in_phrases` («ненадёж», «врёт», «BS», «A–F»).
- **Почему:** каждое свойство — фальсификатор из ledger (C-11, C-13, C-19, C-20).
- **Тир:** T1. **Зависимости:** R-06.
- **Приёмка:** все зелёные; ECE на synth ≤ 0.05 (synth, не evidence).
- **Условие:** unconditional. **Rollback:** —.

#### R-08 · CLI `reliability-build` + хуки пересчёта
- **Что:** команда и три точки вызова §7.
- **Файлы:** `cli/commands/insight.py::cmd_reliability_build` (по образцу `cmd_promise_outcomes:73-87`),
  `cli/main.py` (dispatch dict + `sub.add_parser`), `insight/promise_outcomes.py::run_promise_outcomes`
  (в конце — `build_contact_reliability`), `pipeline/watcher.py:339` (после `recompute_tiers`),
  `insight/cli_ops.py::run_reliability_build`.
- **Как:** как `run_style_estimate` — исключения логируются, цикл watcher не роняют.
- **Почему:** §7; GPU-порядок не затрагивается (numpy).
- **Тир:** T1. **Зависимости:** R-06.
- **Тест:** `tests/insight/test_cli_smoke.py::test_reliability_build_smoke`;
  `tests/test_watcher_autofit.py::test_autofit_calls_reliability_after_tiers` (мок порядка).
- **Приёмка:** `python -m callprofiler reliability-build --user u1` на synth-файле печатает
  `contacts=… with_phrase=… tiers={…}`.
- **Условие:** unconditional. **Rollback:** убрать вызовы; таблица остаётся.

#### R-09 · `contact_reliability()` читает новую таблицу; старые фразы удалены
- **Что:** `insight/promise_outcomes.contact_reliability(conn,user_id,contact_id)` возвращает
  `{phrase_key, phrase, tier, ci, show_phrase, numeric}` из `contact_reliability`; константы
  `_KEPT_RATIO_HIGH/_MID`, `_MIN_RELIABILITY_N` и фразы «держит слово через раз» удаляются.
- **Файлы:** `insight/promise_outcomes.py:51-53,383-398`, `insight/labels_ru`-аналог: словарь фраз в
  `insight/reliability.py::PHRASES_RU`.
- **Как:** один SELECT; нет строки → `{tier:'no_data', show_phrase:0}`.
- **Почему:** один источник фраз; старые пороги 0.8/0.5 без интервала (C-12).
- **Тир:** T1. **Зависимости:** R-06. **Тест:** `tests/insight/test_promise_outcomes.py::test_contact_
  reliability_reads_table` (обновить существующие тесты фраз).
- **Приёмка:** все потребители (`digest.py:226-237`, `db_reader.py:991-1006`) работают без правок
  сигнатуры.
- **Условие:** unconditional. **Rollback:** revert.

#### R-10 · Досье: секция «Надёжность обязательств», удаление `admiralty`/`bs_index`
- **Что:** §9 «Досье»: `get_person_dossier` → `dossier["reliability"] = {phrase, tier, ci, numeric,
  show_phrase, outcomes[≤5: {date, what, status, evidence_class, promise_key, quote}], repeat_unfulfilled,
  quality: [...], recent_phrase}`; `indices.bs_index`, `dossier["admiralty"]` удаляются; `app.js`
  рендер секции; `labels_ru` — тиры/фразы.
- **Файлы:** `dashboard/db_reader.py:755-760,991-1006,1121-1130,1140`, `dashboard/static/app.js`
  (секция «Надёжность обещаний» в слое «Поведение»), `dashboard/labels_ru.py`, `tests/test_dashboard_
  dossier.py`.
- **Как:** guarded `_has_table('contact_reliability')` → без таблицы секция пуста, не 500; LLM не
  зовётся; `evidence_class`: `E0` если есть `outcome_feedback`, `E1` если `status≠unknown`, иначе `E3`.
- **Почему:** C-12, C-17, C-18 retracted, C-20; dashboard.md доктрина (read-only).
- **Тир:** T1 (read-only). **Зависимости:** R-09.
- **Тест:** `test_dashboard_dossier.py::test_reliability_section_gates` (CI<50 → `show_phrase=0`, факты
  есть); `::test_dossier_has_no_bs_or_admiralty_keys`; `::test_reliability_section_absent_table_no_500`.
- **Приёмка:** JSON досье не содержит ключей `bs_index`, `admiralty`, `trust_score`-из-bs; секция
  рендерится на synth.
- **Условие:** unconditional. **Rollback:** revert; данные не меняются.

#### R-11 · ✓/✗ исхода: эндпоинт дашборда и кнопки бота → `outcome_feedback`
- **Что:** `POST /api/tools/outcome-verdict {promise_key, verdict}` (user-guarded UPSERT) + точечный
  `build_contact_reliability(conn, user_id, contact_ids=[cid])`; бот: `ov|{promise_key}|k|b` в
  `/promises` и F5-отчёте.
- **Файлы:** `dashboard/server.py`, `dashboard/tools.py` (по образцу `contact-note`), `insight/
  reliability.py::set_outcome_verdict`, `deliver/telegram_bot.py` (по образцу `handle_fact_verdict:
  579-605`), `deliver/digest.py` (кнопки), тесты.
- **Как:** `verdict∈{kept,broken,unknown}`; проверка, что `promise_key` принадлежит `user_id`
  (`SELECT 1 FROM promise_outcomes WHERE user_id=? AND promise_key=?`) — иначе 404; лог.
- **Почему:** C-10 стадия 2 (петля — источник калибровочных ярлыков), C-12 путь поднятия уверенности.
- **Тир:** T2 (write-path, внешний ввод) + security-reviewer (CLAUDE.md гейт).
- **Зависимости:** R-04, R-08.
- **Тест:** `tests/test_dashboard_tools.py::test_outcome_verdict_user_scoped_and_rebuilds` (чужой
  `promise_key` → 404; свой → строка + `contact_reliability.n_confirmed+=1`); `tests/test_telegram_
  outcome_verdict.py::test_ov_callback_requires_user` .
- **Приёмка:** после ✓ CI контакта не уменьшается (w=1 ≥ q_det) — тест.
- **Условие:** unconditional. **Rollback:** отключить роут/кнопки; таблица остаётся.

#### R-12 · Карточка: строка `надёжность:` вместо `grade:`; удаление `admiralty.py`
- **Что:** `_grade_line` → `_reliability_line` по §9; `insight/admiralty.py` и `tests/insight/
  test_admiralty.py` удаляются; `info_grade` исчезает (C-06).
- **Файлы:** `deliver/card_generator.py:1-27,179-199`, `insight/admiralty.py` (rm), тесты карточки.
- **Как:** строка из `contact_reliability()` (R-09); без строки в таблице → `надёжность: данных мало`.
- **Почему:** C-17, C-18 retracted, S-6; 512-байтный бюджет не ухудшается (§9 расчёт).
- **Тир:** T1. **Зависимости:** R-09.
- **Тест:** `tests/test_card_generator.py::test_reliability_line_variants_and_byte_budget` (3
  варианта + самая длинная фраза + эмодзи-имя → ≤512 байт, строка не режется);
  `::test_card_has_no_grade_or_letters`.
- **Приёмка:** grep `admiralty` в `src/` → 0.
- **Условие:** unconditional. **Rollback:** revert (карточки регенерируются из канонических данных).

#### R-13 · `psychology_profiler`: `promise_breaker` → CR-фраза
- **Что:** паттерн `promise_breaker` (broken/total_promises ≥0.4 из `entity_metrics`, где broken≡0)
  заменяется элементом `{"name":"reliability","severity": по phrase_key, "label": фраза}` из
  `contact_reliability` через `entity_contact_map` (top-confidence), только при `show_phrase=1`.
- **Файлы:** `biography/psychology_profiler.py:244-263`, `dashboard/labels_ru.py`, тесты.
- **Как:** `severity`: keeps/mostly → `positive`, half → `medium`, often_not/rarely → `high`;
  нет строки → паттерн отсутствует (не `neutral`-заглушка).
- **Почему:** C-17 (ярлык → частота поведения), D8.
- **Тир:** T1. **Зависимости:** R-09. **Тест:** `tests/test_psychology_profiler.py::test_reliability_
  pattern_from_contact_reliability`.
- **Приёмка:** `entity_metrics.broken_promises` нигде не читается для паттернов (grep).
- **Условие:** unconditional. **Rollback:** revert.

#### R-14 · Digest: фраза из CR с гейтом
- **Что:** `_reliability_note` использует `contact_reliability()` (R-09): суффикс только при
  `show_phrase=1`; «(?)» для role_fragile-строк сохраняется.
- **Файлы:** `deliver/digest.py:226-237,279`, `tests/test_digest.py`.
- **Тир:** T1. **Зависимости:** R-09. **Тест:** `test_digest.py::test_reliability_suffix_gated_by_ci`.
- **Приёмка:** строки ≤300 симв. **Условие:** unconditional. **Rollback:** revert.

#### R-15 · Карты памяти и CHANGELOG
- **Что:** `.claude/rules/insight.md` (секция «Надёжность обещаний (B3)» → CR/CI: формулы, таблицы,
  гейты, версии), `dashboard.md` (секция досье: удалить admiralty/bs, добавить reliability),
  `graph.md` (BS-формула помечена `LEGACY_UNVERIFIED`, не читается), `llm.md` (`bs_score/bs_evidence`
  не читаются), `bugs.md` (запись D1/D2/D3 с фиксом), `decisions.md` (абзац решения), `CHANGELOG.md`,
  `docs/sintezdiharea.md` (T-26).
- **Тир:** T0. **Зависимости:** R-02…R-14. **Тест:** нет (docs). **Приёмка:** карты отвечают на
  «как считается надёжность» без чтения кода. **Условие:** unconditional.

### Фаза B — бокс: измерения с правилом решения (каждая — R-задача)

Общие условия: `backup` → `verify-backup` → копия в `C:\calls\research\`; `watch` остановлен на время
скриптов; скрипты читают ТОЛЬКО копию; adjudication владельца — `box-package/adjudication-request.md`
(≤40 элементов, рандомизированный порядок, без показа CI/метода — C-14).

#### R-16 · E-1: точность исходов (+E-1b чувствительность)
- **Что:** стратифицированная выборка ≤30 обещаний с `status∈{kept,late,broken}` (по методу det/llm
  и статусу) → владелец отмечает истинный исход → `sens/spec` по методу; роль перепутана (да/нет).
- **Файлы:** `box-package/scripts/02_promise_coverage.py --adjudication-request` (выборка),
  `scripts/04_cr_eval.py --adjudicated FILE` (расчёт q/sens/spec + sensitivity ±0.05),
  `box-package/results/E1.md`.
- **Как:** `q_det = (TP+TN)/n_det`; `sens = TP/(TP+FN)`, `spec = TN/(TN+FP)` (позитив = исполнено);
  bootstrap 80%-CI; чувствительность: CI контактов при q±0.05 — доля контактов, меняющих фразу.
- **Почему:** C-05 (кандидат → доказуемо), C-07, R-1.
- **Тир:** T1 (скрипты) / владелец. **Зависимости:** R-01, R-08 (таблица заполнена на копии).
- **Тест:** `scripts/04_cr_eval.py --synth` (на synth с известным q воспроизводит q ±0.05).
- **Приёмка/правило решения (записано до данных):**
  - `q_det ≥ 0.75` → `reliability_params.q_det := q_det` (и `q_llm` аналогично), `calibrated=1`,
    версия `cr-v1` → далее R-19.
  - `0.6 ≤ q_det < 0.75` → R-17 (`cr-v1n`), затем R-19.
  - `q_det < 0.6` → det-исходы получают `w_label=0.3`, фраза только по `E0`+llm; задача «улучшить
    det-regex» (новая R-31, не в этом плане) — R-19 откладывается до повторного E-1.
  - Роль перепутана в ≥5% элементов → `role_weight_mode='continuous'` обязателен (R-23 пропускается).
- **Rollback:** параметры — строка `reliability_params`; откат = предыдущая строка версии.

#### R-17 · `cr-v1n`: Rogan–Gladen (условно)
- **Что:** вторая версия формулы с коррекцией §4; включается `reliability_params.version='cr-v1n'`.
- **Файлы:** `insight/reliability.py` (ветка по версии), тест `test_reliability.py::test_rg_correction_
  and_guard` (при `sens−(1−spec)<0.2` — не применяется; synth с известным шумом восстанавливает p_true).
- **Тир:** T2. **Зависимости:** R-16. **Условие:** `if E-1 → 0.6 ≤ q_det < 0.75`.
- **Приёмка:** на synth с q=0.65 ECE улучшается vs `cr-v1` ≥0.03. **Rollback:** версия `cr-v1`.

#### R-18 · E-2: цензура/survivor bias
- **Что:** ≤10 `unknown`-обещаний с прошедшим сроком и ≥2 последующими звонками (часть тех же ≤40
  элементов) → владелец: исполнено/нет → `π_b = P(провал|unknown_overdue)`; сравнить с долей провалов
  среди разрешённых `π_r`.
- **Файлы:** `scripts/02_promise_coverage.py --overdue-sample`, `scripts/04_cr_eval.py --censoring`,
  `results/E2.md`.
- **Почему:** C-19 (fatal у обоих судей).
- **Тир:** T1/владелец. **Зависимости:** R-16 (та же сессия adjudication).
- **Правило решения:** `|π_b − π_r| ≤ 0.10` → MAR: cap покрытия 0.3 снимается (`coverage_cap=0`);
  `> 0.10` → `cr-v1c` (R-06 ветка, `pi_unknown_broken := π_b`), cap остаётся; n<8 adjudicated →
  решение отложено, cap остаётся (консервативно).
- **Тест:** `test_reliability.py::test_v1c_unknown_overdue_enters_with_pi`. **Rollback:** версия.

#### R-19 · E-3 стадия 1: reliability diagram CI
- **Что:** по adjudicated элементам R-16/R-18 (≤40) для их контактов: попадание adjudicated доли в окно
  ±0.1 vs CI → reliability diagram (адаптивные бины по 8–10 элементов), Brier, ECE_adapt с bootstrap
  по контактам; побочно — ECE накопленного `fact_feedback` vs стратифицированной выборки (C-14).
- **Файлы:** `scripts/04_cr_eval.py --calibration`, `results/E3-stage1.md`.
- **Тир:** T1. **Зависимости:** R-16.
- **Правило решения:** отчёт ПРЕДВАРИТЕЛЬНЫЙ; числовой CI не включается ни при каком исходе стадии 1.
  Если ECE_adapt > 0.25 (верх 80%-CI) — пересмотреть `tier_cuts` (сдвиг вверх на 1 шаг) и фразовые
  пороги не трогать; иначе — без изменений. Переход к R-20.
- **Rollback:** `tier_cuts` в `reliability_params`.

#### R-20 · E-3 стадия 2: накопление ✓/✗ и включение числа
- **Что:** ежемесячный запуск `scripts/04_cr_eval.py --calibration --source outcome_feedback`;
  когда ≥150 подтверждённых исходов по ≥30 контактам: ECE_adapt ≤ 0.15 (верх 80%-CI ≤ 0.20) →
  `numeric_ci_enabled=1`.
- **Файлы:** те же; `results/E3-stage2-YYYYMM.md`.
- **Тир:** T0 (запуск) / T1 (temperature). **Зависимости:** R-11, R-19.
- **Правило решения:** порог не достигнут → продолжать; ECE > 0.15 → temperature `T` на logit(CI)
  (подбор на случайной половине контактов, проверка на другой; `reliability_params.temperature`);
  повторный провал на проверочной половине → число остаётся выключенным, решение задокументировать;
  < 20 verdicts за 8 недель → R-7 риск: упростить петлю (кнопки в F5-отчёте на первом экране), порог
  НЕ снижать.
- **Тест:** `test_reliability.py::test_temperature_scaling_is_monotone_and_identity_at_1`.
- **Rollback:** `numeric_ci_enabled=0`.

#### R-21 · E-8: затухание evidence
- **Что:** temporal holdout: для каждого контакта исходы до даты T₀ (последние 6 месяцев копии —
  holdout) → предсказание доли исполнения holdout-исходов при `h ∈ {∞, 365, 180}`; log-loss с cluster
  bootstrap (80%-CI разностей), отдельно по тирам контактов (core/active vs остальные).
- **Файлы:** `scripts/05_temporal_holdout.py --decay`, `results/E8.md`.
- **Почему:** C-15 (обязателен по judge-1), minority по тирам.
- **Тир:** T1. **Зависимости:** R-16 (q в параметрах).
- **Правило решения:** `h=∞` по умолчанию; меняется, только если 80%-CI разности log-loss(h)−log-loss(∞)
  < 0 целиком; если по тирам знаки расходятся и обе CI не содержат 0 → `half_life_days` по тирам
  (JSON в `reliability_params`, ветка R-06 версии `cr-v1` с параметром) — иначе единый h.
- **Тест:** `scripts/05_temporal_holdout.py --synth` (на synth с искусственным дрейфом выбирает
  конечный h; без дрейфа — ∞). **Rollback:** параметр.

#### R-22 · E-4: предсказательная ценность
- **Что:** тот же holdout: предсказание исходов holdout по CR (posterior mean) vs базовая доля юзера vs
  частота звонков (naive) — log-loss/AUC с bootstrap.
- **Файлы:** `scripts/05_temporal_holdout.py --predictive`, `results/E4.md`.
- **Правило решения:** lift над базовой долей с 80%-CI > 0 → фразы остаются предиктивными («держит
  слово»); иначе — дескриптивный режим: `PHRASES_RU` вариант «в известных случаях держал слово»
  (`reliability_params.phrase_mode='descriptive'`), число CI всё равно относится к доле исполнения
  (семантика не меняется).
- **Тир:** T1. **Зависимости:** R-21 (тот же скрипт). **Тест:** `--synth` (с p_true-разбросом lift>0).
- **Rollback:** `phrase_mode`.

#### R-23 · E-9: режим `w_role`
- **Что:** Brier/ECE из R-19/R-20 при `role_weight_mode ∈ {continuous, off}`.
- **Файлы:** `scripts/04_cr_eval.py --role-mode`, `results/E9.md`.
- **Правило решения:** разница Brier < 0.005 → `off` (проще); иначе лучший. Пропускается, если R-16
  показал ≥5% перепутанных ролей (тогда `continuous`).
- **Тир:** T0. **Зависимости:** R-19. **Условие:** `if E-1 role confusion < 5%`.

#### R-24 · Калибровка age-confidence тем же скриптом
- **Что:** `scripts/04_cr_eval.py --calibration --target age` — по контактам со spot-check возраста
  (владелец знает возраст ≤20 контактов из существующего списка «Личности»): попадание в интервал
  `age_fused` vs `age_confidence`.
- **Почему:** единый контракт «калиброванный %» (D-12); age-confidence никогда не проверялся (data-
  surface §9).
- **Правило решения:** ECE_adapt > 0.25 → задача в age-план (отдельная, не здесь): пересмотр cap/бонусов;
  иначе — запись «совместимо».
- **Тир:** T1. **Зависимости:** R-19. **Rollback:** —.

### Фаза C — лингвистические сигналы: только эксперименты

#### R-25 · E-5: маркеры уверенности
- **Что:** det-regex §2 по цитатам обещаний контакта; 20 совпадений → владелец: «это действительно
  уверенное обещание?» (точность); затем для контактов с ≥5 исходов в обеих группах — Δ с cluster
  bootstrap; мощность для Δ=0.2 при наблюдаемых n.
- **Файлы:** `scripts/06_certainty.py`, `results/E5.md`.
- **Почему:** C-09 (эксперимент, без Франкфурт-языка).
- **Правило решения:** точность < 0.8 → стоп (сигнал закрыт); ≥0.8 и 80%-CI Δ по ≥10 контактам
  исключает 0 с медианой Δ ≥ 0.15 → R-26; иначе — закрыт, запись в ledger.
- **Тир:** T1/владелец. **Зависимости:** R-16. **Тест:** `--synth`.

#### R-26 · Строка «уверенные обещания сбываются не чаще» (условно)
- **Что:** в досье (слой «Поведение») строка с 2 цитатами, только при `show_phrase=1`, обеих группах
  ≥5 и CI контакта ≥60; без числа.
- **Файлы:** `insight/reliability.py::certainty_delta`, `db_reader.py`, `app.js`, тест.
- **Тир:** T1. **Условие:** `if E-5 → A`. **Rollback:** флаг `certainty_enabled`.

#### R-27 · E-6: таксономия «противоречий»
- **Что:** 20 LLM-фактов `contradiction` (после `graph-replay` на копии — verbatim-проверенных) →
  владелец относит к классу: reminiscence / смена позиции по новой информации / ASR-роль / реальное
  противоречие в обязательстве или факте.
- **Файлы:** `scripts/07_contradictions.py`, `results/E6.md`.
- **Правило решения:** доля 4-го класса ≥ 0.6 → `contradiction` остаётся в промпте как E2-факт с
  цитатой (без числа; показывается в досье «Противоречия» только с цитатами обеих сторон); < 0.6 →
  R-29 исход B (удалить тип из промпта при следующем bump).
- **Тир:** T1/владелец. **Зависимости:** R-03 (verbatim), R-01.

#### R-28 · E-7: хеджирование как предиктор исходов
- **Что:** относительная хедж-плотность (z внутри контакта, окна 90 дн., сегменты после прямого
  запроса владельца по `_RE_REQUEST` из `features/linguistic.py`) vs исход следующего окна; cluster
  bootstrap; отдельно — доля «хедж↑ → исполнено».
- **Файлы:** `scripts/08_hedge.py`, `results/E7.md`.
- **Правило решения:** 80%-CI эффекта исключает 0 И доля «хедж↑ → исполнено» < 0.3 → кандидат в
  ковариату CR (roadmap, отдельный план с holdout); иначе — закрыт.
- **Тир:** T1. **Зависимости:** R-16.

#### R-29 · Bump промпта анализа (условно)
- **Что:** `analyze_v002.txt` + `PROMPT_VERSION` bump: исход A (E-6 ≥0.6) — добавить `who: Me|S2` в
  `structured_facts` и определения `contradiction`; исход B — удалить `vagueness/blame_shift/emotion_spike`
  (и `contradiction`, если E-6 < 0.6) из `fact_type`, удалить `bs_score/bs_evidence` из схемы ответа.
  В обоих исходах `repository.insert_fact_event` пишет `who` из факта (если есть) вместо `'UNKNOWN'`.
- **Файлы:** `configs/prompts/analyze_v002.txt`, `analyze/prompt_builder.py`, `graph/repository.py:406-415`,
  `canary-analyze` отчёт.
- **Почему:** D2, D4, D5; `PROMPT_VERSION` = T2-гейт с кэш-инвалидацией (llm.md); canary (M4) обязателен.
- **Тир:** T2. **Зависимости:** R-27, R-28. **Условие:** `if E-6 → A | B`.
- **Тест:** `tests/test_prompt_builder.py::test_v002_schema_fields`; canary parse_fail% не хуже v001.
- **Rollback:** `PROMPT_VERSION` назад; кэш старой версии цел.

#### R-30 · E-10: документация расхождения и закрытие
- **Что:** на копии: `r(bs_index, CR median)` по контактам с ≥5 исходов (через `entity_contact_map`),
  доля контактов, сменивших «цвет» (старый label → новая фраза/«данных мало»); запись в `decisions.md`
  и `sintezdiharea.md` T-26 статус; `bugs.md` D1–D3.
- **Файлы:** `scripts/01_bs_dead_terms.py --compare`, `results/E10.md`, карты памяти.
- **Тир:** T0. **Зависимости:** R-16…R-23. **Условие:** unconditional.

---

## 12. Валидация — сводка

| Уровень | Что | Где |
|---|---|---|
| Офлайн (CI-гейт) | свойства CI (монотонность/границы/детерминизм/независимость от звонков/негатив n≥4/покрытие), synth-ECE ≤ 0.05, verbatim-гейт, миграция в sync, карточка ≤512, досье без bs/admiralty, запрещённые слова | R-03, R-04, R-07, R-10, R-12 |
| Бокс (pre-registered) | E-0a baseline → E-1/E-1b → E-2 → E-3(1) → E-8 → E-4 → E-9 → E-3(2) → E-5/E-6/E-7 | R-01, R-16–R-28 |
| Непрерывно | ECE по `outcome_feedback` ежемесячно; `numeric_ci_enabled` только по порогу | R-20 |

## 13. Acceptance всего плана

1. Ни одна production-поверхность (карточка, досье, digest, бот, паттерны, advice) не читает
   `bs_index`, `bs_label`, `avg_bs_score`, `bs_score`, `admiralty` — тест `tests/test_no_bs_consumers.py`
   (grep-тест по `src/` вне `graph/aggregator.py`, `graph/calibration.py`, legacy-колонок).
2. Для каждого контакта с ≥1 обещанием существует строка `contact_reliability` с `ci ∈ [1,100]`,
   фразой и тиром; rebuild детерминирован.
3. Факты-исходы показываются всегда; фраза — только по гейтам §5; число — только после R-20.
4. E-1…E-9 выполнены с записанными правилами; решения применены как строки `reliability_params`.
5. Suite зелёный (baseline CONTINUITY), `ruff F821` зелёный, карты обновлены.

## 14. Rollback всего слоя

`reliability_params.version` → предыдущая; UI-флаги (`show_phrase` считается при build) → rebuild;
полный откат = revert коммитов R-08…R-14 (таблицы остаются, не читаются); миграция 10 аддитивна.
`entity_metrics.bs_index` никогда не удалялся → старый UI восстанавливается revert-ом.

## 15. Открытые риски (каждый — с экспериментом)

См. `70-synthesis.md` §5: R-1 (E-1), R-2 (E-2), R-3 (E-8), R-4 (E-3), R-5 (E-4), R-6 (E-0/E-9), R-7
(мониторинг R-20), R-8 (E-5/E-6/E-7). Дополнительно: **R-9** — `promise_outcomes` сам зависит от
качества извлечения обещаний (`promises`/`events`), точность которого не измерялась: E-1 попутно
фиксирует «это вообще было обещание?» (ответ «нет» = FP извлечения) — доля FP > 0.3 → отдельная
задача на извлечение обещаний ДО стадии 2.
