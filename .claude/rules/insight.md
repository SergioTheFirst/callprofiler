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
  features/{base,temporal,reciprocity,trajectory,linguistic,formality,pronouns,affective,topical}.py
  synth/{corpus,archetypes,noise,phrasebank}.py
  # build_contact_features маршрутизирует META(calls)+TEXT(segments)+AFFECTIVE(analyses)
cli/commands/insight.py        tests/insight/*
```

## Чего ещё НЕТ (отдельные планы)

Фаза 4 dominance (gated по UNKNOWN) · Фаза 5 LLM-именование кластеров · Фаза 6 карточки
(`person-archetype`) · Фаза 7 визуализация (карта/эго-сеть/ЭКГ).
