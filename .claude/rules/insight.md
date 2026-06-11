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
| ROBUST | 0.8 | ✓ **Фаза 2:** hedge/directive/question/lexical (`linguistic.py`), formality ты/вы (`formality.py`), we/i (`pronouns.py`). По речи КОНТАКТА (speaker≠OWNER, fallback все). Маркеры/фразбанк = данные |
| AFFECTIVE | 0.6 | ✓ **Фаза 3:** affective (`affective.py`: mean_risk/risk_volatility/max_risk/profanity_mean) + topical (`topical.py`: topic_diversity/topic_focus Herfindahl). Из `analyses` (risk/profanity/key_topics) |
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

`contact_id` глобально уникален → принадлежит одному user_id; reads всегда `WHERE user_id=?`.

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
  features/{base,temporal,reciprocity,trajectory,linguistic,formality,pronouns,affective,topical}.py
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
