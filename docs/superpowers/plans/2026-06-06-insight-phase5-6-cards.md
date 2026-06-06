# Insight Phase 5-6 — Cluster naming + person-archetype card

**Goal:** Первый видимый результат — `person-archetype --user X --contact Y` печатает читаемую карточку:
архетип + уверенность + отличительные черты (фразами) + темы + последний контакт. Кластеры получают
детерминированные имена по топ-осям. LLM-уточнение имени — опциональный шов (на боксе), офлайн не нужен.

**Контекст:** `.claude/rules/insight.md`. Карточка строится из УЖЕ посчитанных фич (`contact_features`,
`contact_archetypes`). Домен-правило (CLAUDE.md): не вываливать сырые counts/durations — черты фразами.

---

## Крух: словарь интерпретаций (`insight/labels.py`)

`FEATURE_LABELS: dict[name -> (ru_name, high_phrase, low_phrase)]` — что значит высокий/низкий z:

```
evening_ratio   ("вечерние",  "звонит по вечерам",            "почти не вечером")
night_ratio     ("ночные",    "звонит ночью",                  "")
business_ratio  ("рабочее",   "звонит в рабочие часы",         "")
weekend_ratio   ("выходные",  "часто на выходных",             "")
burstiness      ("ритм",      "звонит вспышками",              "звонит размеренно")
outgoing_ratio  ("инициатива","обычно ты звонишь ему",         "обычно он звонит тебе")
calls_per_week  ("частота",   "очень частый контакт",          "редкий контакт")
mean_duration_sec ("длит.",   "долгие разговоры",              "короткие разговоры")
tenure_days     ("стаж",      "давний контакт",                "недавний контакт")
cadence_slope   ("динамика",  "отношения активизируются",      "отношения остывают")
hedge_ratio     ("уклончив.", "уклончив, неуверенная речь",    "говорит твёрдо")
directive_ratio ("директивн.","директивен, командует",         "")
vy_ratio        ("формальн.", "на «вы», формально",            "на «ты», неформально")
we_ratio        ("общность",  "часто «мы»",                    "")
i_ratio         ("я-фокус",   "часто «я», самофокус",          "")
lexical_ttr     ("словарь",   "богатая речь",                  "скупая речь")
question_ratio  ("вопросы",   "много расспрашивает",           "")
mean_risk       ("риск-фон",  "высокий риск-фон",              "спокойный фон")
risk_volatility ("волатильн.","эмоционально нестабилен",       "ровный")
max_risk        ("пики",      "были острые моменты",           "")
profanity_mean  ("мат",       "много мата",                    "")
topic_diversity ("темы",      "широкий круг тем",              "узкий круг тем")
topic_focus     ("фокус",     "зациклен на теме",              "")
```

- `describe_dim(name, z, thr=1.0)` → high_phrase если z≥thr, low_phrase если z≤−thr (и она непустая), иначе None.
- `cluster_label(top_dims)` → детерминированное имя кластера: 1-2 ярчайшие фразы через « · », напр.
  «звонит по вечерам · высокий риск-фон». Fallback «кластер N» если нет ярких осей.

---

## Phase 5: обогатить `cli_ops.run_archetypes_fit`

После `fit_archetypes` (есть `projection` Zp, `centroids` в PCA-проекции, `labels`, плюс Z в фич-пространстве):
1. **Per-cluster профиль** (фич-пространство): `profile[c][name] = mean(Z[members==c, j])`.
   Топ-|z| оси кластера → `cluster_label`. Сохранить в `archetype_models.labels` = JSON `{c: name}`.
2. **Membership** контакта: `dist = ||Zp[i] − centroids[labels[i]]||`; `membership = 1/(1+dist)`.
3. **distinctive_dims** контакта (фич-пространство): топ-5 фич по |Z[i,j]| с |z|≥0.8 →
   `[{"dim": name, "z": round(z,2), "phrase": describe_dim(name,z)}]` (только непустые phrase).
4. **confidence** из `total_calls`-фичи контакта: ≥20 `high`, 6-19 `medium`, <6 `low`.
Сохранить per contact в `contact_archetypes` (label из cluster, membership, distinctive_dims JSON, confidence).

---

## Phase 6: `insight/cards.py` + CLI `person-archetype`

`build_card(conn, user_id, contact_id) -> dict | None`:
- Прочитать `contact_archetypes` (label, membership, confidence, distinctive_dims). Нет строки → None.
- Имя: `contacts.display_name`/`guessed_name`.
- Evidence (без сырых counts в заголовке): `last_seen` = MAX(call_datetime); `top_topics` = топ-3 по
  частоте из `analyses.key_topics`; `note` = последний непустой `analyses.hook`/`summary` (если есть).
- Вернуть `{contact_id, name, archetype, membership, confidence, traits:[phrase...], topics, last_seen, note}`.

CLI `cmd_person_archetype(args)` (`cli/commands/insight.py`, регистрация в `main.py`, `--user`+`--contact`):
печать читаемой карточки; `--json` → dict. Нет данных → понятное сообщение.

---

## Тесты (`tests/insight/`)
1. `test_labels.py` — describe_dim (high/low/None по порогу; пустая low → None), cluster_label детерминизм.
2. `test_cards.py` — на синт-корпусе: fit → build_card(contact) возвращает archetype/traits непустые,
   confidence из support, last_seen корректен; неизвестный contact → None; user-изоляция.
3. `test_person_archetype_cli.py` — smoke: run_features_build→run_archetypes_fit→build_card печатает.

## Acceptance
- `PYTHONPATH=src python -m pytest tests/insight/ -q` зелёное; полный набор без регресса (было 610/2).
- Глазами: карточка реального синт-контакта читаема, черты осмысленны.

## Conventions / scope
- Только `insight/**`, `cli/**`, `tests/insight/**`. numpy only. Детерминированные имена (LLM — позже, шов).
- Черты — фразами из FEATURE_LABELS (данные), не сырые числа. Не показывать counts/durations в заголовке.
