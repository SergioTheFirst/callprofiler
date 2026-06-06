# Insight Phase 3 — AFFECTIVE/TOPICAL features Implementation Plan

> **For agentic workers:** TDD, по модулю. Тест: `PYTHONPATH=src python -m pytest tests/insight/ -q`.
> Python 3.10, numpy only. Коммиты БЕЗ атрибуции. **НЕ коммить** — отчитайся (файлы, вывод тестов,
> фактические ARI-числа).
>
> **⚠ ОБЯЗАТЕЛЬНО (прошлый агент это нарушил):** в тестах ИСПОЛЬЗОВАТЬ канонические
> `from callprofiler.insight.archetypes import fit_archetypes, adjusted_rand_index`. ЗАПРЕЩЕНО
> писать свою ARI/k-means или создавать новые util-модули. `adjusted_rand_index` ограничен [-1,1];
> если видишь значение >1 — у тебя баг, останавливайся и чини, не «обходи».

**Goal:** Добавить AFFECTIVE (риск/мат/типы звонков) и TOPICAL (темы) фичи — больше измерений
профиля контакта. Доказать МАРГИНАЛЬНУЮ ценность: архетип, отличимый ТОЛЬКО по affective
(twin business по метаданным+тексту), разделяется лишь при добавлении affective-фич.

**Контекст:** `.claude/rules/insight.md`, design-doc §4 (тир AFFECTIVE w=0.6, оси 9-10). Образец
фич-модуля — `features/temporal.py`. Контракт — `features/base.py` (`Feature`, `Tier`).
Источник данных — таблица `analyses` (per call): `risk_score` (0-100), `profanity_density` (REAL),
`call_type` (TEXT), `key_topics` (JSON-массив строк).

---

## Почему НЕ «рост ARI на дефолтных 4»

На дефолтном синт-корпусе ARI уже = 1.0 после Фазы 2 (текст разводит всё). Поэтому ценность
Фазы 3 доказывается **отдельным 5-шаблонным корпусом** с twin-архетипом, отличимым только по
affective. На ДЕФОЛТНЫХ 4 affective лишь обогащает (ARI остаётся 1.0).

---

## Корпус: генерация `analyses` + affective-регистры

### `synth/archetypes.py` — поля в `ArchetypeTemplate` (frozen dataclass, с дефолтами)

```python
risk_mu: float = 30.0       # медиана risk_score
risk_sigma: float = 12.0    # волатильность риска
profanity_mu: float = 0.02  # средняя profanity_density
topics: tuple = ("дела",)   # пул тем для key_topics
```

Дефолтные 4 шаблона — добавить значения (варьировать, чтобы affective не был вырожденным):
- night_dependent: risk_mu=55, risk_sigma=18, profanity_mu=0.02, topics=("личное","ночь","тревога","деньги")
- business_transactional: risk_mu=25, risk_sigma=8, profanity_mu=0.01, topics=("сделка","оплата","сроки","договор")
- fading_tie: risk_mu=30, risk_sigma=10, profanity_mu=0.0, topics=("дела","встреча","как-дела")
- intimate_frequent: risk_mu=20, risk_sigma=12, profanity_mu=0.03, topics=("семья","планы","отдых","дом")

### `synth/archetypes.py` — метод `sample_analysis(rng)` → dict

```python
def sample_analysis(self, rng):
    risk = int(min(100, max(0, rng.normal(self.risk_mu, self.risk_sigma))))
    prof = float(max(0.0, rng.normal(self.profanity_mu, 0.01)))
    n_top = int(rng.integers(1, 4))
    topics = list(rng.choice(self.topics, size=min(n_top, len(self.topics)), replace=False))
    return {"risk_score": risk, "profanity_density": prof,
            "call_type": self.name, "key_topics": topics}
```

### `synth/corpus.py` — вставлять `analyses` (одна на звонок)

В цикле по звонкам, после INSERT call (есть `call_id`):
```python
a = tmpl.sample_analysis(rng)
import json
conn.execute(
    "INSERT INTO analyses(call_id, risk_score, profanity_density, call_type, key_topics) "
    "VALUES (?,?,?,?,?)",
    (call_id, a["risk_score"], a["profanity_density"], a["call_type"], json.dumps(a["key_topics"])),
)
```
(остальные колонки analyses — по DEFAULT в схеме.) НЕ трогать генерацию calls/transcripts.

### `synth/archetypes.py` — `AFFECTIVE_TEMPLATES` (ТОЛЬКО для value-теста)

5 шаблонов: business_transactional, fading_tie, intimate_frequent, night_dependent (как в DEFAULT)
+ пятый **`volatile_client`** — КОПИЯ business_transactional по ВСЕМ метаданным и текст-регистрам
(hours, n_calls, tenure, p_out, dur, cadence, formality, hedge, directive, we, verbosity — идентичны
business), НО affective контраст:
```python
ArchetypeTemplate("volatile_client", (15, 35), (120, 300),
    hours=(10, 11, 14, 15, 16), p_weekend=0.02, p_out=0.5,
    dur_mu=180, dur_sigma=0.5, cadence_trend=0.0,
    formality=0.90, hedge=0.10, directive=0.60, we=0.30, verbosity=9,   # == business
    risk_mu=80, risk_sigma=25, profanity_mu=0.15,                        # affective-контраст
    topics=("сделка","оплата","сроки","договор"))                        # == business
```
**НЕ добавлять volatile в DEFAULT_TEMPLATES** (иначе сломаются Phase-1/2 тесты). DEFAULT остаётся 4.

---

## Фич-модули (сигнатура `fn(analyses, reference_now=None)`, тир AFFECTIVE)

`analyses` — список dict `{risk_score, profanity_density, call_type, key_topics}`
(`key_topics` может быть JSON-строкой или уже списком — обработать оба). Пустой вход → `{}`.

### `features/affective.py`
- `mean_risk` = avg(risk_score)
- `risk_volatility` = pstdev(risk_score) (0 если <2)
- `max_risk` = max(risk_score)
- `profanity_mean` = avg(profanity_density)
support_n = len(analyses). Tier.AFFECTIVE.

### `features/topical.py`
Распарсить key_topics (json.loads если строка; список — как есть). Собрать частоты тем по контакту.
- `topic_diversity` = uniq_topics / total_topic_mentions (0 если нет тем)
- `topic_focus` = Herfindahl = sum((cnt_i/total)**2) по темам (1.0 = одна тема, ниже = разнообразнее)
support_n = total_topic_mentions. Tier.AFFECTIVE. Нет тем → `{}`.

---

## `feature_store.py`

- `from .features.affective import compute_affective` + `from .features.topical import compute_topical`.
- `_AFFECTIVE_FNS = (compute_affective, compute_topical)`.
- default `feature_fns = _META_FNS + _TEXT_FNS + _AFFECTIVE_FNS`.
- В `build_contact_features` дочитать analyses per contact:
  ```sql
  SELECT a.risk_score, a.profanity_density, a.call_type, a.key_topics
  FROM analyses a JOIN calls c ON c.call_id=a.call_id
  WHERE c.user_id=? AND c.contact_id=?
  ```
  и `for fn in feature_fns: if fn in _AFFECTIVE_FNS: feats.update(fn(analyses_rows, reference_now=...))`.

---

## Тесты (`tests/insight/`)

1. `test_affective.py` — unit: список analyses → mean/volatility/max/profanity корректны; пустой → {}.
2. `test_topical.py` — unit: key_topics (и список, и JSON-строка) → diversity/focus; пустой/битый JSON → graceful (нет краша).
3. `test_phase3_affective_value.py` — VALUE (канонические fit_archetypes + adjusted_rand_index):
   ```python
   from callprofiler.insight.synth.archetypes import AFFECTIVE_TEMPLATES
   # corpus на 5 шаблонах (templates=AFFECTIVE_TEMPLATES)
   # ari_text = recover(_META_FNS+_TEXT_FNS)        # volatile≡business -> сливаются, ARI<1
   # ari_aff  = recover(_META_FNS+_TEXT_FNS+_AFFECTIVE_FNS)  # affective разводит twin
   # assert ari_aff > ari_text
   # assert ari_aff >= 0.85
   ```
   (helper recover как в `test_phase2_recovery.py`: build_contact_features→assemble→standardize→
   fit_archetypes(k_range=range(2,8))→adjusted_rand_index vs ground_truth.)
4. Существующие тесты — остаются зелёными: `test_phase2_recovery` (явно _META_FNS/_+TEXT, affective
   не подмешан → ARI=1.0 на 4), `test_recovery` (meta), `test_cli_smoke` (дефолт-fns теперь с affective —
   проверяет k≥2/n_assigned, не точный ARI). `test_corpus` использует len(DEFAULT_TEMPLATES) → ок.

---

## Acceptance gate

- `PYTHONPATH=src python -m pytest tests/insight/ -q` — зелёное.
- `test_phase3_affective_value`: `ari_aff > ari_text` И `ari_aff >= 0.85` (если twin не разделяется —
  усилить affective-контраст volatile, НЕ порог).
- Полный `PYTHONPATH=src python -m pytest tests/ -q` — без регресса (было 595 passed, 2 skipped).
- Доложить: файлы, summary-строки, фактические `ari_text`/`ari_aff` (печать из scratch-прогона
  канонической ARI).

## Conventions
- Темы/риск-параметры — данные в шаблонах; маркеры — module-level.
- Только `insight/**` + `tests/insight/**`. numpy only. НЕ создавать новых util-модулей; ARI/kmeans
  брать из `archetypes.py`.
