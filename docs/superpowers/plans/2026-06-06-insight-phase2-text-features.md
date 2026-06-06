# Insight Phase 2 — ROBUST text features Implementation Plan

> **For agentic workers:** реализуй TDD, по одному модулю. Тест-команда:
> `PYTHONPATH=src python -m pytest tests/insight/ -q`. Python 3.10, numpy only.
> Стиль коммитов БЕЗ атрибуции. **НЕ коммить** — по завершении отчитайся (файлы + вывод тестов
> + финальные ARI-числа); коммит сделает оркестратор после ревью.

**Goal:** Добавить ROBUST текст-фичи (хедж, директивность, формальность ты/вы, местоимения,
лексика), которые **разводят business_transactional и fading_tie** (метаданные их сливали —
см. `.claude/rules/insight.md` «Известный потолок»). Доказать ростом ARI на синте.

**Контекст для чтения:** `docs/superpowers/specs/2026-06-06-insight-archetypes-design.md` (§4 тиры,
§5 ASR-устойчивость), `.claude/rules/insight.md`. Образец фич-модуля — `src/callprofiler/insight/
features/temporal.py`. Контракт — `features/base.py` (`Feature(value, support_n, tier)`, `Tier`).

---

## Архитектурное изменение: текст-фичи в `feature_store`

Текущие фичи берут `calls` (метаданные). Текст-фичи берут СЕГМЕНТЫ транскрипта. Контракт:

- В `features/base.py` добавить:
  ```python
  import re
  _WORD_RE = re.compile(r"[а-яёa-z]+", re.IGNORECASE)
  def tokenize(text):
      return _WORD_RE.findall((text or "").lower())
  def count_markers(words, markers):
      return sum(1 for w in words if w in markers)
  ```
- Текст-фичи сигнатура: `fn(segments, reference_now=None)` где `segments` — список
  `{"speaker": str, "text": str}`. Считать по речи КОНТАКТА: `speaker != "OWNER"`; если таких нет —
  fallback на все сегменты (роли на реальных данных часто UNKNOWN). Тир = `Tier.ROBUST`.
- В `feature_store.py`:
  - переименовать `_IMMUNE_FNS` → `_META_FNS` (оставить alias `_IMMUNE_FNS = _META_FNS` для совместимости тестов).
  - добавить `_TEXT_FNS = (compute_linguistic, compute_formality, compute_pronouns)`.
  - `build_contact_features`: помимо `calls` дочитать сегменты per contact:
    ```sql
    SELECT t.speaker, t.text FROM transcripts t JOIN calls c ON c.call_id=t.call_id
    WHERE c.user_id=? AND c.contact_id=? ORDER BY t.call_id, t.start_ms
    ```
    Прогнать `_META_FNS(calls)` + `_TEXT_FNS(segments)`, смёржить. Если сегментов нет — текст-фичи
    просто не добавятся (их fns вернут `{}` на пустом входе).

---

## Корпус: генерация транскриптов по речевым регистрам (КРУХ — отсюда рост ARI)

Расширить `synth/archetypes.py` и `synth/corpus.py`.

### Регистры (добавить поля в `ArchetypeTemplate`, frozen dataclass)

```python
formality: float   # p использовать вы-форму (0=всегда ты, 1=всегда вы)
hedge: float       # доля хедж-вставок в реплике контакта
directive: float   # доля директив-вставок
we: float          # доля «мы»-вставок
verbosity: int     # ~слов в реплике контакта
```

Профили (бизнес vs затухание ОБЯЗАНЫ различаться по тексту):

| template | formality | hedge | directive | we | verbosity |
|---|---|---|---|---|---|
| night_dependent | 0.10 | 0.55 | 0.10 | 0.20 | 14 |
| business_transactional | 0.90 | 0.10 | 0.60 | 0.30 | 9 |
| fading_tie | 0.55 | 0.70 | 0.10 | 0.10 | 7 |
| intimate_frequent | 0.05 | 0.20 | 0.25 | 0.60 | 14 |

### Фразбанки (в `synth/corpus.py` или новый `synth/phrasebank.py`)

```python
HEDGE = ["наверное", "может быть", "посмотрим", "если получится", "я не уверен", "вроде бы"]
DIRECTIVE = ["сделай это", "нужно срочно", "давай так", "пришли мне", "перезвони потом"]
VY = ["вы говорили", "вам удобно", "как вас понял"]
TY = ["ты говорил", "тебе удобно", "как тебя понял"]
WE = ["мы решим", "у нас получится", "нам надо"]
NEUTRAL = ["да хорошо", "понятно", "ясно ну", "в общем", "ладно тогда", "по работе вопрос"]
OWNER_POOL = ["так записал", "понял принял", "ну давай", "хорошо договорились", "ага слушаю"]
```

### Генератор (метод `ArchetypeTemplate.sample_segments(rng)` → list[{"speaker","text"}])

Для каждого звонка эмитить 2-4 пары OWNER/OTHER. Реплика OTHER собирается так: начать с
`verbosity//4` фраз из NEUTRAL, затем по вероятностям подмешать: HEDGE (p=hedge), DIRECTIVE
(p=directive), WE (p=we), и VY (p=formality) либо TY (p=1-formality). Склеить в строку. OWNER —
1-2 фразы из OWNER_POOL. ~30% реплик OTHER заканчивать «?» для question_ratio.

### `SyntheticCorpus.build` — вставлять транскрипты

- добавить параметр `noise_rate: float = 0.0`.
- на каждый звонок: получить сегменты (`sample_segments`), для OTHER-текста при `noise_rate>0`
  применить `inject_asr_noise(text, noise_rate, seed=<детерминир.>)`; вставить в `transcripts`
  (`call_id, start_ms (инкремент), end_ms, text, speaker`).
- метаданные звонков НЕ менять (Фаза 1 тесты должны остаться зелёными).

---

## Фич-модули

### `features/linguistic.py`

Маркеры (в модуле, lowercase):
```python
HEDGE = {"наверное","наверно","возможно","может","кажется","вроде","типа","посмотрим",
         "попробую","постараюсь","неуверен"}  # + многословные ловим по подстроке отдельно? нет — по словам
DIRECTIVE = {"сделай","сделайте","нужно","надо","должен","должны","давай","давайте",
             "пришли","пришлите","отправь","перезвони","бери","держи","срочно"}
```
Фичи (Tier.ROBUST, support_n = всего слов контакта):
- `hedge_ratio` = count(HEDGE)/words
- `directive_ratio` = count(DIRECTIVE)/words
- `question_ratio` = доля сегментов контакта с "?" в тексте (support_n = число сегментов)
- `lexical_ttr` = uniq(words)/words
- `mean_turn_words` = words / число реплик контакта
Пустой вход / 0 слов → `{}`.

### `features/formality.py`
```python
VY = {"вы","вас","вам","вами","ваш","ваша","ваше","ваши"}
TY = {"ты","тебя","тебе","тобой","твой","твоя","твоё","твое","твои"}
```
- `vy_ratio` = count(VY)/(count(VY)+count(TY)); если знаменатель 0 → фичу не добавлять.
  support_n = count(VY)+count(TY). Tier.ROBUST.

### `features/pronouns.py`
```python
WE = {"мы","нас","нам","нами","наш","наша","наше","наши"}
I  = {"я","меня","мне","мной","мой","моя","моё","мое","мои"}
```
- `we_ratio` = count(WE)/words, `i_ratio` = count(I)/words. support_n=words. Tier.ROBUST.
Пустой вход → `{}`.

---

## Тесты (`tests/insight/`)

1. `test_linguistic.py` — на ручных сегментах: текст с 2 хедж-словами из 10 → hedge_ratio=0.2;
   директивы; question_ratio; ttr; пустой → {}. Фильтрация OWNER (речь OWNER не считается в фичи контакта).
2. `test_formality.py` — «вы вам ты» → vy_ratio=2/3; нет ни вы ни ты → фичи нет.
3. `test_pronouns.py` — «мы нам я» → we_ratio/i_ratio корректны.
4. `test_base.py` — дополнить: `tokenize` (пунктуация/регистр), `count_markers`.
5. `test_phase2_recovery.py` (ГЛАВНЫЙ — доказать ценность):
   ```python
   # META-only ARI vs META+TEXT ARI на одном корпусе (с транскриптами)
   # build_contact_features(..., feature_fns=_META_FNS) -> ari_meta
   # build_contact_features(...) (META+TEXT по умолчанию)  -> ari_full
   # assert ari_full > ari_meta
   # assert ari_full >= 0.85
   ```
6. `test_text_noise_tolerance.py`:
   ```python
   # corpus clean vs corpus(noise_rate=0.3), тот же seed
   # ARI(full features) на шумном >= 0.6
   # для контрольного контакта hedge_ratio(noisy) в пределах ±0.15 от clean
   ```

Существующие `test_recovery.py` (Фаза 1, META-only через `_META_FNS`/`_IMMUNE_FNS`) — должны
остаться зелёными (метаданные не менялись). Если `test_recovery` использует дефолтные fns и теперь
подхватит текст — обнови его на явный `feature_fns=_META_FNS`, ИЛИ оставь (ARI вырастет, ≥0.6 верно).

---

## Acceptance gate

- `PYTHONPATH=src python -m pytest tests/insight/ -q` — всё зелёное.
- `test_phase2_recovery`: `ari_full > ari_meta` И `ari_full >= 0.85`.
- `test_text_noise_tolerance`: ARI на шумном ≥0.6.
- Полный набор `PYTHONPATH=src python -m pytest tests/ -q` — без регресса (было 557 passed, 2 skipped;
  станет больше за счёт новых insight-тестов; старые НЕ падают).
- Доложить: список файлов, вывод тестов, фактические `ari_meta`/`ari_full`/`ari_noisy`.

## Conventions

- Маркеры/фразбанки — данные в модулях/конфиге, НЕ хардкод в логике (DRY).
- Чистые функции, AAA-тесты, `frozen=True` dataclass.
- НЕ трогать пайплайн/orchestrator/graph/biography. Только `insight/` + `tests/insight/`.
- numpy only; никаких новых зависимостей.
