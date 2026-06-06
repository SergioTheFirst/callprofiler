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
features-build --user X   → contact_features (по-контактные фичи)
archetypes-fit --user X   → archetype_models + contact_archetypes (кластеры)
```
Чистая логика — `insight/cli_ops.py` (тестируется без argparse). Обёртки —
`cli/commands/insight.py`. Регистрация — `cli/main.py` (dispatch dict).

---

## Фичи — 11 осей, 4 ТИРА устойчивости к ASR

| Тир | w | Оси (MVP = только IMMUNE) |
|---|---|---|
| **IMMUNE** | 1.0 | temporal (циркад/burstiness/tenure/recency), reciprocity (outgoing_ratio/mean_dur/calls_per_week/total), trajectory (cadence_slope/changepoints) |
| ROBUST | 0.8 | hedge, directive, formality(ты/вы), pronouns, lexical — **Фаза 2, ещё нет** |
| AFFECTIVE | 0.6 | risk-распр, profanity, call_type, emotional_pattern — **Фаза 3** |
| FRAGILE | 0.4 | dominance (talk-ratio/turns) — **Фаза 4, гейт по доле UNKNOWN** |

Каждая фича: `Feature(value, support_n, tier)` (`features/base.py`). Чистая функция над
списком строк `calls`/`transcripts`.

## Устойчивость к ASR (механика)

- **z-score ВНУТРИ контактов юзера** (относительно, не абсолют → постоянная ошибка ASR гасится).
- **вес = w_tier × min(support_n/n0,1)**; `support_floor=2` → ниже бракуется в NaN (импут медианой).
- имена/темы — из канонизированных `entities`, не из сырых токенов.
- **noise-injection тесты** (`synth/noise.py`) — Фаза 2 (для текст-фич).

## Движок (numpy-only, `archetypes.py`)

вектор → импут+z-score (`feature_store.standardize`) → **PCA(SVD)** → **k-means++** (seed=0,
10 рестартов) → k по **силуэту** → персист. Валидация — **ARI** против ground-truth синта.

**ARI-гейт (CI):** `tests/insight/test_recovery.py` ≥0.6 (чисто), ≥0.4 (малая выборка).

**⚠ Известный потолок метаданных (2026-06-06):** на синте ARI≈0.71, движок выбирает **k=3 при
истинных 4** — кластеры ЧИСТЫЕ, но **business_transactional + fading_tie сливаются** (оба дневные,
сбалансированные; различие = траектория/объём, одномерно, тонет в z-пространстве). Разведут
**Фаза 3 affective** (спад вовлечённости) / **Фаза 2 текст** (формальность/хедж). НЕ лечится
подгонкой шаблонов (самообман). recency не помогает: в синте все контакты кончаются на end_date.

---

## Таблицы (`repository.apply_insight_schema`, идемпотентно)

- `contact_features (contact_id, user_id, feature_set, feature_name, value, support_n, tier)`
  PK `(contact_id, feature_name)`; UPSERT с guard `WHERE user_id=excluded.user_id`.
- `archetype_models (model_id, user_id, version, k, silhouette, n_contacts, feature_list,
  centroids, labels)` — лог прогонов (накопление = намеренный audit-trail).
- `contact_archetypes (contact_id PK, user_id, model_id, cluster_idx, archetype_label,
  membership, distinctive_dims, confidence, evidence)`; UPSERT с user-scoped guard.

`contact_id` глобально уникален → принадлежит одному user_id; reads всегда `WHERE user_id=?`.

---

## Офлайн-разработка (нет БД на дев-ПК)

`synth/corpus.py SyntheticCorpus.build()` — schema-accurate temp SQLite из `db/schema.sql` +
ground-truth метки (`synth/archetypes.py DEFAULT_TEMPLATES`: night_dependent / business_
transactional / fading_tie / intimate_frequent). Всё тестируется офлайн (numpy-only).

---

## Файлы

```
src/callprofiler/insight/
  repository.py  feature_store.py  archetypes.py  cli_ops.py
  features/{base,temporal,reciprocity,trajectory}.py   # +linguistic/... Фаза 2+
  synth/{corpus,archetypes,noise}.py
cli/commands/insight.py        tests/insight/*
```

## Чего ещё НЕТ (отдельные планы)

Фаза 2 текст-фичи · Фаза 3 affective/topical · Фаза 4 dominance · Фаза 5 LLM-именование
кластеров · Фаза 6 карточки (`person-archetype`) · Фаза 7 визуализация (карта/эго-сеть/ЭКГ).
