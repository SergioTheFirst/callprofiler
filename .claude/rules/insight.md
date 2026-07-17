# Insight Engine Rules (архетипы личности)

> Карта слоя insight — отвечать на вопросы по архетипам/фичам ОТСЮДА, не перечитывая код.
> Полный дизайн: `docs/superpowers/specs/2026-06-06-insight-archetypes-design.md`.
> План MVP: `docs/superpowers/plans/2026-06-06-insight-archetypes-mvp.md`.
> Граф-сущности (`entities`) — ОТДЕЛЬНЫ от этого слоя (см. `graph.md`).

---

## Что это

Из звонков собираются **по-контактные поведенческие фичи** → контакты кластеризуются в
**эмпирические архетипы** (обнаруженные, не заданные руками). НЕ оценка человека —
паттерны для внимания (как `graph.md` про BS-index).

## Пофактовое ✓/✗ подтверждение (F1)

`fact_feedback(user_id, item_kind CHECK IN promise|event|deep_fact, item_key TEXT, verdict
CHECK IN confirmed|rejected, source, created_at)` — составной PK `(user_id,item_kind,item_key)`,
`set_fact_verdict`/`get_verdicts` (`insight/repository.py`). item_key — `str(rowid)`: `event`
для events.id (bot `/promises`, dashboard person-dossier promises из summary_builder JSON),
`promise` для legacy `promises.promise_id` (dashboard граф-модалка), `deep_fact` зарезервирован
для M8 (таблицы ещё нет). **Rejected не рендерится нигде** (digest.py `_merged_open_items`,
db_reader.py `_apply_fact_verdicts` — оба выбрасывают до передачи наверх, не просто прячут в UI).
Повторный тап = UPSERT (последнее решение — источник истины, история не копится).

## Напоминания по подтверждённым обещаниям (F2)

`reminders(reminder_id, user_id, item_kind, item_key, text, due_at, chat_id, sent_at,
enabled, consecutive_errors)` — только по явному тапу «🔔 Напомнить» + владелец сам
называет дату (инвариант 18, `deliver/reminders.py`). `parse_due_ru` — ДЕТЕРМИНИРОВАННЫЙ
RU-парсер (сегодня/завтра/послезавтра/день недели-ближайший будущий/через N дней/DD.MM[.YYYY]
+ опц. время), никакого LLM. Self-disabling: `consecutive_errors>=5 → enabled=0` + один
алерт владельцу. Тикер — plain `asyncio`-таск через `Application.post_init` (НЕ
`job_queue` — тот требует доп. пакет `python-telegram-bot[job-queue]`/APScheduler,
не установлен и не нужен ради 60с-интервала). **Все callback-хендлеры, трогающие
конкретный `reminder_id`/`item_key`, обязаны гейтиться `_get_user_id`** (snooze без
этого гейта был CRITICAL — чужой reminder_id переносился без проверки, security-review
2026-07-17 до коммита; `snooze_reminder()` теперь и на уровне SQL требует `user_id`).

## Role-fragile звонки (шум-доктрина, инлайн-задача №7 — OzaluplivanieFable.md §4.2)

`calls.role_fragile` (INTEGER, миграция аддитивна — `db/repository.py::_migrate`, схема
`schema.sql`): `1` если доля `speaker='UNKNOWN'` сегментов звонка > `UNKNOWN_SHARE_THRESHOLD=0.3`
(`diarize/role_assigner.py::is_role_fragile`). `role_assigner.assign_speakers` не отдаёт
скалярную уверенность overlap-назначения — margin-критерий НЕДОСТУПЕН, работает только
UNKNOWN-доля. Пишется пайплайном (`orchestrator.py`, оба пути `process_call`/`process_batch`)
сразу после `save_transcripts`, ДО `update_pipeline_stage(...,2)`.

**Контракт для потребителей (обязателен при реализации соответствующих задач):**
- **M8 deep-extract, B3 promise_outcomes, B5 request_balance, B7 finance** (who-критичные
  извлечения): item с `who IN ('OWNER','OTHER')` из role_fragile-звонка → ДРОП. Items без
  зависимости от `who` (type='fact' без атрибуции) — оставлять.
- **Дашборд:** бейдж «⚠ роли могли спутаться» в детали звонка (`get_call_detail` отдаёт
  `role_fragile`, `app.js::renderCallDetail` рендерит — реализовано 2026-07-16).
- **A1 digest / F5 daily report:** строки, построенные из role_fragile-звонков, помечать
  суффиксом `(?)` (задача ещё не реализована — применить при исполнении A1/F5).

**Единица анализа = `contact`** (телефонная диада, где живут метаданные). НЕ `entity`.

---

## Конвейер (CLI, per user_id, идемпотентно)

```
features-build --user X                → contact_features (по-контактные фичи)
archetypes-fit --user X                 → archetype_models + contact_archetypes (кластеры+имена+membership+черты)
person-archetype --user X --contact Y   → читаемая карточка (архетип/близость/черты-фразы/темы)
```
Чистая логика — `insight/cli_ops.py` (тестируется без argparse). Обёртки —
`cli/commands/insight.py`. Регистрация — `cli/main.py` (dispatch dict).

**Карточка/имена (Фаза 5-6):** `archetypes-fit` пишет per-кластер ДЕТЕРМИНИРОВАННОЕ имя (топ-|mean z|
осей → `labels.cluster_label`), membership (1/(1+dist до PCA-центроида)), distinctive_dims (топ-|z| осей
контакта с фразами из `labels.FEATURE_LABELS`), confidence (по total_calls). `cards.build_card` =
read+format из `contact_archetypes`/`contacts`/`calls`/`analyses` (черты ФРАЗАМИ, без сырых counts).
LLM-уточнение имён — шов на боксе (офлайн не нужен).

**Визуализация (Фаза 7, дашборд, ECharts):** вкладка «Архетипы» (`templates/index.html` +
`static/app.js loadInsight`). 4 вида: **карта PCA-2D** (scatter по cluster + центроиды),
**эго-сеть** (force-graph: owner-центр, узлы=контакты, размер=объём, цвет=кластер), **циркад**
(heatmap часы×дни недели), **ЭКГ отношений** (line активность+риск по месяцам, пикер контакта).
Тот же паттерн, что карточка: `archetypes-fit` ПИШЕТ координаты (`pca_x/pca_y` = первые 2 оси
проекции `Zp[i][:2]` в `cli_ops`), дашборд = чистый read. Бэкенд: `dashboard/db_reader.py`
`get_insight_{pca,network,circadian,ecg}` (+`_archetype_map`) — все `WHERE user_id=?`, guarded
(нет fit → пусто, не 500). Эндпоинты `/api/insight/{pca,network,circadian,ecg,contacts}` в
`dashboard/server.py`. НЕ подписана на SSE (статична между прогонами fit). Визуальная проверка — бокс.

---

## Фичи — 11 осей, 4 ТИРА устойчивости к ASR

| Тир | w | Оси (MVP = только IMMUNE) |
|---|---|---|
| **IMMUNE** | 1.0 | temporal (циркад/burstiness/tenure/recency), reciprocity (outgoing_ratio/mean_dur/calls_per_week/total), trajectory (cadence_slope/changepoints) |
| ROBUST | 0.8 | ✓ **Фаза 2:** hedge/directive/question/lexical (`linguistic.py`), formality ты/вы (`formality.py`), we/i (`pronouns.py`). По речи КОНТАКТА (speaker≠OWNER, fallback все). Маркеры/фразбанк = данные. **B1:** tempo_cps/reply_latency_ms/tempo_accel (`tempo.py`) — из start_ms/end_ms сегментов, строго speaker=OTHER (без fallback), UNKNOWN не участвует. **B2:** specificity (`specificity.py`) — числа/даты/деньги/время на whitespace-токенах (НЕ `base.tokenize()` — тот вырезает цифры); entity-хиты НЕ считаются в v1 (decisions.md). **B5:** request_balance (`linguistic.py::compute_request_balance`) — (req_other−req_owner)/сумма по regex-маркерам просьб, ОБЕ стороны раздельно (не fallback-паттерн модуля), UNKNOWN пропускается целиком, гейт сумма≥3 |
| AFFECTIVE | 0.6 | ✓ **Фаза 3:** affective (`affective.py`: mean_risk/risk_volatility/max_risk/profanity_mean) + topical (`topical.py`: topic_diversity/topic_focus Herfindahl). Из `analyses` (risk/profanity/key_topics). **B4:** emo_anger/emo_anxiety/emo_joy/emo_contempt (`emotion_palette.py`) — лексиконная плотность (per-mille) на речи контакта, 4 лексикона в `age_style/lexicons/emo_*.txt` (переиспользует `age_style.lexicons.load_lexicon` + `lexical_age.lexicon_hits`, не новый загрузчик). `Tier.AFFECTIVE`, но роутится в `_TEXT_FNS` (читает `segments`, не `analyses`) — тир и группа-источник в `feature_store.py` независимы. **B6:** accommodation (`accommodation.py`) — медиана per-call (align_contact−align_owner) множеств контентных слов (len≥4, минус ~40 стоп-слов), звонки с |A|<20 или |B|<20 пропущены; >0 = контакт лексически подстраивается под владельца |
| FRAGILE | 0.4 | dominance (talk-ratio/turns) — **Фаза 4, гейт по доле UNKNOWN** |

Каждая фича: `Feature(value, support_n, tier)` (`features/base.py`). Чистая функция над
списком строк `calls`/`transcripts`.

## Устойчивость к ASR (механика)

- **z-score ВНУТРИ контактов юзера** (относительно, не абсолют → постоянная ошибка ASR гасится).
- **вес = w_tier × min(support_n/n0,1)**; `support_floor=2` → ниже бракуется в NaN (импут медианой).
- имена/темы — из канонизированных `entities`, не из сырых токенов.
- **noise-injection тесты** (`synth/noise.py`) — ✓ `test_text_noise_tolerance.py`: агрегатный ARI и
  разделимость когорт переживают шум (отдельная фича плывёт, кластеризация — нет).

## Движок (numpy-only, `archetypes.py`)

вектор → импут+z-score (`feature_store.standardize`) → **PCA(SVD)** → **k-means++** (seed=0,
10 рестартов) → k по **силуэту** → персист. Валидация — **ARI** против ground-truth синта.

**ARI-гейт (CI):** `tests/insight/test_recovery.py` ≥0.6 (чисто), ≥0.4 (малая выборка).

**⚠ k-selection (Фаза 3 находка):** силуэт-авто-k СЛИВАЕТ почти-близнецов, отличимых лишь по одному
тиру (affective-only twin business↔volatile → k=4 вместо 5), независимо от наличия тех фич. Поэтому
маргинальный вклад тира меряем при ИСТИННОМ k (`test_phase3_affective_value.py` @k=5: text 0.71 →
+affective 1.0). На реале: per-contact affective-фичи всё равно в `contact_features` (карточка покажет
«высокий риск» по сырым фичам), даже если кластер близнецов не расщепил. Roadmap тонкой грануляции —
задаваемый k / gap-statistic.

**Потолок метаданных РЕЗОЛВЕД текст-фичами (Фаза 2, 2026-06-06):** только метаданные → k=3 / ARI≈0.71
(business+fading сливались — различие одномерно). **+ROBUST текст-фичи → k=4 / ARI=1.0** на синте
(noise_rate 0.3 → ARI 0.968). business (formal/directive/low-hedge) vs fading (hedge-heavy/vague)
разделимы по речи. Гейт `test_phase2_recovery.py` (full>meta И full≥0.85, КАНОНИЧЕСКАЯ
`archetypes.adjusted_rand_index`). НЕ лечилось подгонкой шаблонов.

---

## Таблицы (`repository.apply_insight_schema`, идемпотентно)

- `contact_features (contact_id, user_id, feature_set, feature_name, value, support_n, tier)`
  PK `(contact_id, feature_name)`; UPSERT с guard `WHERE user_id=excluded.user_id`.
- `archetype_models (model_id, user_id, version, k, silhouette, n_contacts, feature_list,
  centroids, labels)` — лог прогонов (накопление = намеренный audit-trail).
- `contact_archetypes (contact_id PK, user_id, model_id, cluster_idx, archetype_label,
  membership, distinctive_dims, confidence, evidence, pca_x, pca_y)`; UPSERT с user-scoped guard.
  `pca_x/pca_y` = первые 2 оси PCA-проекции (Фаза 7, карта). Добавлены idempotent ALTER-миграцией
  (`_MIGRATIONS` в `repository.apply_insight_schema` — legacy-таблицы апгрейдятся без recreate).
- `entity_contact_map (user_id, entity_id, contact_id, method 'name'|'cooccur', confidence)`
  PK `(user_id, entity_id, contact_id)` — МЯГКАЯ сшивка graph-entity↔contact (Ф1 досье,
  `person_link.build_entity_contact_map`): name-match 0.95 (любой тип, нормализация lower/ё→е) +
  cooccur 0.6+0.3·share (только PERSON, share≥0.6 ∧ n≥3 звонков, owner исключён). DERIVED: полный
  rebuild per user; вызывается в конце `archetypes-fit` И в Step 9 `graph-replay` (entity_id там
  пересоздаются). CLI: `person-link --user X [--dry-run]`. Колонко-адаптивна: base-`entities` из
  schema.sql без `is_owner`/`events.entity_id` (их добавляет apply_graph_schema) → фильтры по PRAGMA,
  без graph-слоя отдаёт нули, не падает. НЕ слияние контактов.

- `contact_age_estimates (contact_id PK, user_id, age_low/high/point, birth_year_low/high/point,
  confidence 1-100 CHECK, method 'marker'|'relation'|'llm'|'combined', evidence JSON,
  prompt_version, llm_prompt_hash, llm_result)` — оценка возраста (план age-estimation, 2026-06-11).
  UPSERT user-guarded. **Агрегация в пространстве ГОДА РОЖДЕНИЯ** → дашборд выводит возраст к
  текущей дате (динамика); age_* = срез на computed_at.

- `contact_tiers (user_id, contact_id PK, tier, score, prev_tier, computed_at)` — см. секцию
  «Тиры контактов» ниже.

`contact_id` глобально уникален → принадлежит одному user_id; reads всегда `WHERE user_id=?`.

---

## Тиры контактов — Эббингауз-забывание (F8, `tiers.py`)

`score = retention(days_since_last_call, strength(call_count)) * log1p(total_talk_minutes)`,
`retention = exp(-days/(30*strength))`, `strength = 1+log1p(call_count)` — касание поднимает,
тишина опускает, TAU_DAYS=30. Тир по ПЕРЦЕНТИЛЯМ score внутри юзера (не абсолютным порогам):
top 5%→`core`, до 25%→`active`, до 60%→`warm`, до 90%→`cold`, хвост/0 звонков→`archive`.
`recompute_tiers()` — UPSERT, старый tier → `prev_tier` (переходы для C3/F5 «перешли в остывшие»).
**Триггеры (все дёшево, numpy/SQL-only):** watcher `_run_insight_fit` (реальный ночной автофит,
каждый debounced цикл) · конец `bulk_enrich()` · после `obligations-digest`. **Потребители:**
`enricher.select_pending_calls` сортирует очередь по тиру (core первым, `TIER_RANK_SQL_CASE`) —
до первого прогона (таблицы нет) деградирует к прежнему хронологическому порядку; дашборд
`get_people`/`get_person_dossier` — колонка/бейдж с русской меткой (`labels_ru.TIER`) + сортировка
списка. Biography-очередь (per-entity, не per-contact) сознательно НЕ трогается здесь — это
предмет будущей F21 (`ночной хук... очередь по тирам F8`), которая уже резолвит entity→contact
через `entity_contact_map`.

---

## Deep-extract — map-reduce по длинным звонкам (M8, `deep_extract.py`)

Снимает слепоту head+tail-клипа основного analyze-промпта (llm.md: >3000 символов → 1500+1500):
`chunk_text()` режет ПОЛНЫЙ транскрипт на символьные чанки (9000/800 overlap, разрез по
word-boundary) → каждый чанк — отдельный LLM-вызов (`LLMClient(cache_conn=conn)`, json_mode,
temperature 0.1) → JSON `{"items":[{type,who,what,quote,deadline}]}`. Таблицы `deep_facts`
(PK `user_id,item_key` — sha1(call_id|type|what[:60])[:16], дедупит перекрытия чанков) и
`deep_scans` (гейт повторного прогона без `--force`). **Границы: результат — СВОЯ таблица,
НЕ events/graph** (replay-инвариант graph.md, прецедент B2) — дисплей-слой + материал для
`obligations-digest` (A1 `extra_sections`). Гейты на item: `who` не в {OWNER,OTHER} → дроп,
`quote` не substring чанка (по `textnorm.norm_quote`, §4.1 шум-доктрина — ASR-пунктуация/
регистр/ё не режут валидные находки) → дроп ЦЕЛИКОМ (факту без цитаты веры нет), `what`
пустой → дроп, `type` не в {promise,debt,fact,date} → дроп. CLI: `deep-extract --user X
[--min-duration 600] [--min-priority N] [--limit 100] [--force]`; llama-server недоступен →
exit 2 (только на первом реальном чанке — пустая выборка сеть не трогает). Потребители:
досье «Из длинных разговоров» (guarded `_has_table`, top-5) · digest секция «🔎 Из глубокого
прохода» (только promise/debt, `recent_deep_lines`, ≤300 симв/строка).

**F26 голосовые заметки (осторожный режим, `NOTE_MIN_DURATION=30`):** `call_type='note'`
(F4) ТЕПЕРЬ входят в отбор со своим порогом (независимо от `min_duration` обычных звонков),
но с гейтами ЖЁСТЧЕ (ASR-шум на одноголосой заметке — юзер-риск): `who` фиксирован — ТОЛЬКО
`OWNER` (модель предложила `OTHER` → галлюцинация, дроп); `type` ⊂ {promise,fact} (нет
`debt`/`date` — заметке не с кем спорить о долге); **числовой гейт** — цифры в `what`
(включая словесные числа «один..двадцать, тридцать..девяносто, сто..тысяча»,
`extract_numbers()`, БЕЗ композиции «двадцать три»→23) обязаны присутствовать в `quote`,
иначе дроп (искажение суммы ASR — риск №1). `contact_id` заметки — ВСЕГДА из БД (спец-контакт
«Мои заметки», `phone_e164='self:notes'`), никогда из LLM. Потребители: `recent_deep_lines`
префиксует такие строки 🎙; досье self:notes-контакта секцию «Из длинных разговоров» НЕ
показывает (self-леджер живёт в digest, не в чужом досье).

---

## Возраст (age-estimate)

`age_markers.py` (чистые regex) + `age_estimate.py` (агрегатор+LLM). 3 ступени:
1. **Маркеры** (conf 60-92): «мне 45 лет» (цифры/словесные числа, лет|год обязательны — отсечка
   «45 минут»), «мне исполнилось N», «1978 года рождения», юбилей (только со «своим» контекстом
   «у меня/моё», анти: свадьба/завод), этапные (пенсия/внуки/армия/сессия/ЕГЭ/школа). Только
   speaker='OTHER' (UNKNOWN не верим — может быть владелец). Third-person guard («мама на пенсии»).
2. **Якоря** (гейт `owner_birth_year` в конфиге, 0=выкл): НАПРАВЛЕННЫЕ — owner говорит «мам»
   (усечённый вокатив; полное «мама» игнор) → контакт-родитель +20..+35; contact говорит «пап» →
   контакт-ребёнок; одноклассник/однокурсник ±2 (85), служили вместе ±3 — с любой стороны.
3. **LLM** (`age_v001.txt`, `PROMPT_VERSION_AGE='age-v1'`): топ-40 длинных реплик (клип 6000) +
   10 обращений владельца + det-сигналы как контекст; temp 0.1, max_tokens 800, timeout 120;
   парсер срезает `<think>`/fences (Qwen3.5); verbatim-гейт: цитата не substring поданного →
   выброс −15, 0 валидных → отброс целиком (но кэшируется); cap conf 50.

**Агрегат:** классы точности (прямой 3 > этапный 2 > якорь 1 > LLM 0); внутри класса согласие →
пересечение интервалов + 10/независимый сигнал (cap 95), конфликт → конверт + conf=min+10;
ниже классом конфликт → высший побеждает, conf=min+10; LLM-конфликт → интервал не двигается, −15.
**Память LLM:** sha1(prompt+версия) в строке; det-пересчёт реюзает оплаченный llm_result.
**Динамика:** в watcher `_run_insight_fit` зовётся со `stale_only=True` (только контакты со
звонками новее computed_at; пустая дата → не skip); use_llm в watcher ЗАПРЕЩЁН (GPU занят ASR).
CLI: `age-estimate --user X [--contact N] [--llm]`. Тесты: `tests/insight/test_age_*.py`.

**v2 (2026-07-03, ensemble-план `docs/superpowers/plans/2026-07-03-age-ensemble-v2.md`):**
- Гарды fixager Ф5: pension-future («выйду на пенсию» ≠ пенсионер), ЕГЭ-not-self, расширенный
  third-person; конфликт низшего класса теперь МЯГКИЙ (−10/сигнал, не обвал до min+10).
- Новые прямые (класс 3): `born_in` («я родился в 1978»), `since_year` («я с 75-го года»,
  анти-гард глаголов занятости), `age_slangnum` (сорокет/полтинник/тридцатник),
  `age_approx` («мне под/за/к сорок»). Год-якорные события (класс 2): школу закончил/поступил/
  закончил вуз/армия «в NN-м» → возраст на событии → год рождения.
- **KIN-арифметика** (класс 2, `extract_kin_signals`): третье-личные упоминания СВОИХ родных
  контакта больше не выбрасываются, а конвертируются: «у дочки ЕГЭ» → ребёнку 16-18 → контакту
  36-58; «сыну 30 лет» → 50-70; «маме 85» → 45-67; внуки-этап → 50-85. Гард чужих родных
  («у твоей/вашей») + «мне» в зазоре. `_PRIORITY` покрывает ВСЕ новые сигналы (без записи →
  класс 1 по умолчанию — не забывать при добавлении).

---

## Возраст-стиль (age_style) — 4-й сигнальный класс, no-ML стилометрия (2026-07-01)

Реализация плана `age.md` (методология `vozrast.md`) — ОТДЕЛЬНАЯ система от `age_markers.py`/
`age_estimate.py` выше (своя таблица `contact_age_style`, свой пайплайн `insight/age_style/`,
никогда НЕ ПИШЕТ в `contact_age_estimates`; READ-ONLY читает `method`/`birth_year_*` оттуда —
см. «Marker-vs-style» ниже). Источник: реплики `speaker='OTHER'` по ВСЕМ звонкам контакта
(агрегат-уровень, не per-conversation).

**Поток:** сырые фичи (`features/{diversity_age,readability_age,morphosyntax_age,lexical_age}.py`)
→ z-score ВНУТРИ популяции юзера (`feature_store.assemble_matrix`+`standardize`, тот же контракт,
что и архетипы) → биннинг по 8 вероятностным таблицам (`age_style/tables.py`, дословно
vozrast.md §4.2, Σ=1 на строку) → **взвешенный линейный пул** голосов по группам G1-G6
(`scorer.py`; Р3/Р4/Р5-разнообразие — ОДИН объединённый голос, деконфликт коррелирующих
измерений) → год рождения (`accumulate.py`, взвешенный перцентиль P(группа)) → confidence
(`confidence.py`, sigmoid ESS/agreement/marker-bonus/conflict) → UPSERT `contact_age_style`
(`estimate_style.py` — оркестратор).

**Год рождения анкорится к СРЕДНЕМУ ГОДУ ЗВОНКОВ контакта** (`_anchor_year`), НЕ к дате
прогона — иначе тот же стиль давал бы разный год рождения в зависимости от того, когда именно
вызван `run_style_estimate` (vozrast.md §2.2). `reference_year` пробрасывается в Т2
(реалии→год) явно — нет тихого дефолта на `date.today()`.

**Гейты:** `n_conversations<3` или `total_tokens<150` → confidence_level=1, БЕЗ точки (широкий
приор, не ложная точность). Bimodal-конфликт (два пика P(группа)) → НЕ усредняется в фиктивный
центр, а помечается warning + понижается confidence. G1/G6 (края) получают edge-bonus —
компенсация регрессии к среднему (стиль сам по себе недооценивает крайние возраста).

**Таблицы:** ch6 (слоги/слово), diversity (MATTR/MTLD/Yule's K, объединены), slang/archaism
(однонаправленные — отсутствие нейтрально, не тянет вверх), i_ratio/vy_ratio (доля «я»/«вы»),
life_stage (кластер «своей» темы: школа_егэ/вуз_сессия/ипотека_декрет/карьера/внуки_пенсия),
realia (год из упомянутых реалий эпохи). Лексиконы (`age_style/lexicons/*.txt`) — данные, не код.

**v2 (2026-07-03, `TABLE_VERSION=age-style-v2`/`RULES_VERSION=age-rules-v2` — на боксе нужен
полный пересчёт):** fixager Ф1-Ф4 (лексиконы: `=`-точный матч убил омонимы «база/аккурат/диал/
сериал»; support_n=ХИТЫ, не корпус — у slang/archaism тоже; z ВСЕГДА по полной популяции,
stale-фильтр только на записи; пол ширины интервала = span доминирующей группы × widen).
Новые оси: **discourse** (репертуар филлеров «типа/короче/жесть» vs «значит/понимаешь/стало
быть», по RAW-доле young/(young+old), гейт ≥3 хитов), **kancelyarit** (однонаправленный вверх,
business-тема ×0.6), **morphosyntax** (предлоги М3 + подчинит. союзы С3 закрытыми списками,
ОДИН объединённый голос как diversity), **tempo** (слов/сек из start_ms/end_ms OTHER-сегментов,
FRAGILE ×0.4, ↓ с возрастом), **prior** (популяционный приор G3-G5 взрослых контактов, вес 0.25,
всегда голосует — гасит ложные G1/G2; пустые фичи → пул = приор, НЕ uniform; в marker_conflict
НЕ участвует). Лексиконы умеют БИГРАММЫ (пробел в стеме: «ласковый май», «стало быть», «по
блату»). Реалии пере-датированы по reminiscence bump (артефакт пика Y → рождение Y-30..Y-10;
пейджер 1960-82, денди/сега 1980-92) + одиночные хиты разных стемов дают ПЕРЕСЕЧЕНИЕ эпох
(дизъюнктные → None). Синт-генератор G4 очищен от советизмов (был подгон под v1-таблицы).

**CLI:** `age-style --user X [--stale-only]`. **Watcher:** `_run_insight_fit` зовёт
`run_style_estimate(stale_only=True)` инкрементально, безмодельно (numpy/regex — не конфликтует
с ASR-GPU, в отличие от `age-estimate --llm`). **Dashboard:** секция «Возраст (стиль)» в досье
(группа-бары/★-доверие/топ-вклады/явные маркеры) + `POST /api/tools/age-recompute?contact_id=`
— **пересчитывает ВСЮ популяцию юзера** (не только запрошенный contact_id: z-score
популяционный, точечный пересчёт всё равно требует того же прохода), возвращает свежую
строку контакта. Синхронно в threadpool, без GPU/LLM — доктрина дашборда не нарушена.

**Marker-vs-style (2026-07-02, фикс):** `estimate_style._get_marker` читает валидный явный
маркер (`method IN marker/relation/combined`, НЕ `llm` — та же по духу слабая догадка, что и
весь этот модуль) из `contact_age_estimates` и передаёт в `scorer.score_contact(..., marker=)`.
Маркер входит в пул как узкая сильная посылка (вес `2.5×confidence/100` — обычно перевешивает
СУММУ style-голосов за счёт концентрации на одной группе, vozrast.md §7.1 «маркер побеждает»).
Конфликт `argmax(style-only) != argmax(marker)` → `marker_conflict` → warning «расходится с
явным маркером» + штраф в Conflict-члене `confidence()` (было: ТОЛЬКО внутренняя бимодальность,
маркер давал плоский бонус вне зависимости от согласия со стилем — баг). `confidence()` принимает
`marker_strength: float` (0.0 или confidence/100), не булев флаг. **Список «Личности»
(`get_people`)** — fallback на `contact_age_style`, если нет marker/LLM-оценки (`age_source:
'marker'|'style'|None`); раньше контакты БЕЗ явного маркера (ради которых age_style и строился)
не получали возраст в списке вообще.

Тесты: `tests/insight/test_age_{markers_vnukovo,style_schema,features,scorer,style_estimate}.py`
+ `tests/test_dashboard_age_style.py` + v2: `test_age_{markers_v2,kin,discourse,tempo,
morphosyntax,prior,realia_v2,lexicons_fp,features_support_n,markers_guards,fusion}.py`.

---

## Возраст-FUSION — единая итоговая оценка (2026-07-03)

`insight/age_fusion.py::fuse_age(marker_row, style_row, ref_year)` — ЧИСТАЯ функция
(`FUSION_VERSION='fuse-v1'`), без БД: вычисляется на ЧТЕНИИ (db_reader/tools), НЕ хранится —
нет staleness и нет цикла «стиль читает своё же» (contact_age_estimates не трогается).
Правила: (1) marker∩style непусто → интервал ОТ МАРКЕРА (стиль шумный, не сужает), conf+5
cap 95, source='marker+style'; (2) дизъюнкт → маркер побеждает, conf−10 floor 20, warning
«стиль расходится»; (3) только marker → как есть; llm-метод → cap 50, source='llm'/'llm+style';
(4) только style (level≥2, birth_point есть) → cap conf 70, source='style'; (5) ничего → None.
Потребители: `get_people` (колонка возраста списка = fused, `age_source`),
`get_person_dossier` → `age_fused` (первая строка возрастного блока досье), ответ
`age-recompute`. **Кнопка «Пересчитать возраст ↻»** (досье, ВСЕГДА видна): маркер-пасс этого
контакта (`run_age_estimate(contact_id=…, owner_birth_year=…)`, БЕЗ LLM) + `run_style_estimate`
всей популяции → возвращает age/age_style/age_fused + hints: `owner_birth_year` не задан (P8),
`hint_diarization` при 0 OTHER-реплик (P9).

---

## Финансовая экспозиция (B7, `finance.py`) — display-only, читает `events` напрямую

Единственный insight-модуль этой секции, который сам ходит в БД (`conn` в сигнатуре) —
остальные фичи чистые функции над `segments`/`calls`/`analyses`, эта — над `events`
(`event_type IN ('promise','debt')`, `status='open'`), т.к. агрегирует ЧЕРЕЗ звонки, а не
внутри одного. `extract_amounts(text)` — regex по цифрам (словесные числа "сорок тысяч"
НЕ ловятся, только цифры), множители тыс/к/млн, валюты RUB/USD/EUR по маркеру
(руб/₽/р, доллар/$/бакс, евро/€). `finance_exposure(conn,user_id,contact_id)` — на
событие берётся МАКСИМУМ сумм из payload+quote (не сумма — оба текста часто пересказывают
один факт), поперёк событий — `low`=крупнейшая разовая, `high`=сумма разовых максимумов.
`exposure_phrase`/`format_amount_range` — «на нём завязано ~40–90 тыс ₽ + ~2 тыс $».
Досье: секция «Финансовая экспозиция» в слое «Место в сети» (`db_reader.get_person_dossier`
→ `dossier["finance"]`, guarded try/except, None → нет секции) + до 3 quote+дата событий-
оснований. Digest: `_amount_suffix` в `deliver/digest.py` дописывает сумму ТОЛЬКО к overdue-
строкам (гейт по наличию `days_overdue` в item), считает от what+quote САМОГО item, не
агрегат по контакту — переиспользует `extract_amounts`/`format_amount_range`, не
`finance_exposure` (тот аггрегирует по контакту, не по одному item).

---

## Офлайн-разработка (нет БД на дев-ПК)

`synth/corpus.py SyntheticCorpus.build()` — schema-accurate temp SQLite из `db/schema.sql` +
ground-truth метки (`synth/archetypes.py DEFAULT_TEMPLATES`: night_dependent / business_
transactional / fading_tie / intimate_frequent). Всё тестируется офлайн (numpy-only).

---

## Файлы

```
src/callprofiler/insight/
  repository.py  feature_store.py  archetypes.py  cli_ops.py  labels.py  cards.py  person_link.py
  age_markers.py  age_estimate.py   # возраст: маркеры/якоря/LLM (см. секцию выше)
  tiers.py                          # F8: Эббингауз-тиры (см. секцию выше)
  deep_extract.py                   # M8: map-reduce deep-extract (см. секцию выше)
  finance.py                        # B7: финансовая экспозиция (см. секцию выше)
  features/{base,temporal,reciprocity,trajectory,linguistic,formality,pronouns,affective,topical}.py
  features/{tempo,specificity,emotion_palette,accommodation}.py       # B1/B2/B4/B6
  age_style/lexicons/emo_{anger,anxiety,joy,contempt}.txt          # B4 данные
  synth/{corpus,archetypes,noise,phrasebank}.py
  # build_contact_features маршрутизирует META(calls)+TEXT(segments)+AFFECTIVE(analyses)
cli/commands/insight.py        tests/insight/*
dashboard/{db_reader,server}.py  templates/index.html  static/app.js   # Фаза 7 визуализация
tests/test_dashboard_insight.py                                         # reader офлайн + эндпоинты
```

## Чего ещё НЕТ (отдельные планы)

Фаза 4 dominance (gated по UNKNOWN, ОТЛОЖЕНА — хрупкая диаризация) · Фаза 5 LLM-УТОЧНЕНИЕ имён
кластеров (детерминированные уже есть; LLM-шов на боксе) · Фаза 7 интерактив (клик точки PCA/узла
сети → карточка контакта; per-contact циркад). Базовая визуализация (Ф7) СОБРАНА.
