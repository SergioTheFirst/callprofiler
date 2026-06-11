# Age Estimation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Оценка возраста контакта (диапазон + точка + уверенность 1-100) из всей совокупности данных; отображение в досье «Личности» и списке людей.

**Architecture:** Трёхступенчатая оценка по убыванию точности: (1) **прямые маркеры** в транскриптах (regex, без LLM, дёшево на 16k) → (2) **реляционные якоря** (родство/роль относительно владельца, возраст владельца из конфига) → (3) **LLM-пасс** по выборке реплик (лексика поколения, реалии, обращения) с verbatim-evidence и memoization. Сигналы агрегируются в `contact_age_estimates`; дашборд = чистый read (LLM из дашборда запрещён — bugs.md 2026-06-11). Паттерн слоёв как в graph.md: extraction (детерминир.) → interpretation (LLM) разделены, LLM-результат пересчитываем без повторной оплаты (hash-кэш).

**Tech Stack:** sqlite3, regex/python (Ф0-Ф1 без зависимостей), llama-server (Ф2, только LLM-окно), существующие synth-корпус и phrasebank для офлайн-тестов.

**Тиры:** Ф0=T2 (SQL write + новая таблица), Ф1=T1, Ф2=T2 (промпт/PROMPT_VERSION-гейт), Ф3=T1 (UI).

---

## Источники сигнала (что используем)

| Сигнал | Источник | Точность | Пример |
|---|---|---|---|
| Прямое упоминание | `transcripts.text` (speaker≠OWNER) | ±1-2 года, conf 85-95 | «мне сорок пять», «юбилей 50», «1978 года» |
| Жизненный этап | то же + `events.quote` | ±7, conf 60-80 | «на пенсии», «внуки», «после армии», «сессию сдаю» |
| Реляционный якорь | `entities.attributes.role` / алиасы p2 (family/одноклассник) + `owner_birth_year` | ±3-10, conf 50-85 | «мама» → owner+~25; «одноклассник» → owner±2 |
| Обращения владельца | реплики OWNER к контакту | слабый, conf ≤40 | «молодой человек», по имени-отчеству |
| Лексика поколения / реалии | LLM по выборке реплик | ±10-15, conf 25-50 | сленг, «дискотека/клуб», ЕГЭ/экзамены, канцелярит |

Уверенность итоговая = max по методам с бонусом за согласие независимых сигналов (+10 за каждый согласный, cap 95); противоречие сигналов → понижение до min+10 и расширение диапазона.

---

## Ф0 — схема + маркер-экстрактор (без LLM)

### Task 0.1: таблица + детерминированный экстрактор

**Files:**
- Modify: `src/callprofiler/insight/repository.py` (_SCHEMA)
- Create: `src/callprofiler/insight/age_markers.py`
- Create: `src/callprofiler/insight/age_estimate.py` (агрегатор сигналов → UPSERT)
- Modify: `src/callprofiler/config.py` + `configs/base.yaml`: `owner_birth_year: 0` (0 = неизвестен, якоря выкл)
- Modify: `src/callprofiler/cli/main.py` + `cli/commands/insight.py`: команда `age-estimate --user X [--contact N] [--llm]`
- Test: `tests/insight/test_age_markers.py`, `tests/insight/test_age_estimate.py`

DDL:

```sql
CREATE TABLE IF NOT EXISTS contact_age_estimates (
    contact_id  INTEGER PRIMARY KEY,
    user_id     TEXT    NOT NULL,
    age_low     INTEGER,
    age_high    INTEGER,
    age_point   INTEGER,
    confidence  INTEGER NOT NULL CHECK (confidence BETWEEN 1 AND 100),
    method      TEXT    NOT NULL,          -- 'marker'|'relation'|'llm'|'combined'
    evidence    TEXT,                      -- JSON [{quote, signal, weight}]
    prompt_version TEXT,                   -- для llm-метода
    computed_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```
UPSERT по contact_id с guard `WHERE user_id = excluded.user_id` (паттерн contact_archetypes).

`age_markers.py` — чистые функции над списком реплик контакта `[(text, call_datetime)]`:

```python
# Прямые: r"мне\s+(\d{2})(?:\s|-)?(?:лет|год)" ; словесные числа 20-90 (двадцать..девяносто
# + один..девять); r"(\d{2})[-\s]?лети[ея]" (юбилей); r"\b(19[3-9]\d|200\d)\s*год[ау]?\s*рожден"
# Этапные: пенси- → (60,80); внук/внучк → (50,85); армию отслужил недавно → (20,30);
# сессия/универ/общага → (17,25); ЕГЭ сдаю → (16,18); "школу заканчива" → (15,18)
# Каждый матч → AgeSignal(low, high, conf, quote≤120, signal_name, dt)
# Возраст ИНДЕКСИРУЕТСЯ к дате звонка: упомянул «мне 45» в 2021 → в 2026 точка 50.
```

Failure-mode: реплика владельца о СЕБЕ («мне 50») не должна попасть — берём только speaker≠OWNER; «мне 45 минут ехать» — отсечь по контексту (`лет|год` обязательны).

- [ ] Тесты (RED): прямой возраст со словесным числом; индексация к дате звонка; пенсия→диапазон; реплики OWNER игнорируются; «45 минут» не матчится; пусто → None.
- [ ] Реализация → GREEN → `age_estimate.run_age_estimate(conn, user_id, use_llm=False)`: реплики контакта из transcripts (JOIN calls по contact_id, speaker≠OWNER) → сигналы → агрегат (пересечение диапазонов, conf-формула выше) → UPSERT. Идемпотентно.
- [ ] CLI + полный suite → security-reviewer (SQL write) → память (insight.md) → commit/push.

---

## Ф1 — реляционные якоря

### Task 1.1: anchors из graph-ролей

**Files:** Modify: `src/callprofiler/insight/age_estimate.py`; Test: дополнить `test_age_estimate.py`.

- [ ] Если `owner_birth_year > 0`: по `entity_contact_map` найти entity контакта → `entities.attributes`/aliases роль (p2: colleague|client|friend|family) и текст-маркеры родства в репликах («мам», «сынок», «бабушк», «одноклассни», «служили вместе»):
  мать/отец → owner_age+20..+35 (conf 70); сын/дочь → owner_age−35..−18 (70); одноклассник/однокурсник → owner_age±2 (85); «вместе служили» → ±3 (75).
- [ ] Якорь = ещё один AgeSignal в общий агрегат (метод 'relation'). Тесты: family-якорь сдвигает диапазон; без owner_birth_year якоря выключены; конфликт якоря и прямого маркера → прямой побеждает, conf падает.
- [ ] Commit/push.

---

## Ф2 — LLM-пасс (LLM-окно, memoized)

### Task 2.1: промпт + вызов + verbatim-валидация

**Files:**
- Create: `configs/prompts/age_v001.txt`
- Modify: `src/callprofiler/insight/age_estimate.py` (`_llm_estimate`)
- Test: `tests/insight/test_age_llm.py` (mock requests.post)

**Промпт-контракт (русский, ОДИН JSON, без markdown — конвенции llm.md):**

```json
{"age_low": 40, "age_high": 55, "age_point": 48, "confidence": 35,
 "evidence": [{"quote": "дословная реплика", "signal": "лексика|реалия|обращение"}],
 "reasoning": "1 фраза"}
```

Input: до 40 самых длинных реплик контакта (клип 6000 символов) + 10 обращений владельца + найденные Ф0/Ф1 сигналы как контекст. Правила в промпте: evidence — ТОЛЬКО дословные цитаты; не выдумывать; lexика-only → confidence ≤ 40; прямых чисел не изобретать.

- [ ] **Verbatim-гейт (анти-галлюцинация, как validator графа):** каждая evidence-цитата проверяется substring-ом по поданному тексту; отсутствует → выбросить, confidence −15. 0 валидных evidence → результат отбрасывается целиком.
- [ ] **Memoization:** sha1(prompt+PROMPT_VERSION_AGE) — повторный run не платит токенами (паттерн сигнатуры психопрофайлера); `prompt_version='age-v1'` в строке. Бамп версии = пересчёт.
- [ ] Гейт исполнения: только по флагу `--llm`; НЕ в watcher-autofit (LLM нельзя при ASR — Hard Constraint); таймаут 120s, ошибка → log+skip+continue (pipeline.md Fallback).
- [ ] Агрегат 'combined': llm-сигнал входит с весом своей confidence; маркеры/якоря всегда приоритетнее при конфликте.
- [ ] Тесты mock-LLM: парсинг; галлюцинированная цитата отброшена и conf снижен; кэш-hit без второго вызова. → commit/push.

---

## Ф3 — отображение

### Task 3.1: досье + список

**Files:** Modify: `dashboard/db_reader.py` (`get_person_dossier`: секция `age`; `get_people`: `age_point`, `age_confidence` — guarded `_has_table('contact_age_estimates')`), `static/app.js` (секция «Возраст» в renderDossier: «~48 лет (40-55) · уверенность 35/100» + evidence-цитаты; колонка «Возраст» в people-table: «~48» серым при conf<50), `templates/index.html` (th), `tests/test_dashboard_dossier.py` (+2 теста: с оценкой / без таблицы).

- [ ] Тесты → реализация → suite → память (dashboard.md) → commit/push.

---

## Чеклист на боксе

1. `configs/base.yaml`: задать `owner_birth_year` (иначе якоря выкл).
2. `age-estimate --user me` (маркеры+якоря, минуты на 16k) → досье показывает возраст.
3. `age-estimate --user me --llm` — в LLM-окне (llama-server жив, ASR не идёт).
4. Спот-чек 10 знакомых контактов: возраст попадает в реальный диапазон? evidence-цитаты настоящие?

## Roadmap (вне плана)

age_band как FRAGILE-ось insight-кластеризации; калибровка confidence на размеченной выборке; авто-режим маркер-части в watcher-autofit (флаг).

## Self-review

- Возраст + уверенность 1-100 ✓ (CHECK в DDL); отображение в профиле ✓ (Ф3); «вся совокупность ресурсов» ✓ (транскрипты обеих сторон, events-цитаты, graph-роли+map, owner-якорь, LLM-лексика). Анти-галлюцинация и кэш — учтены уроками graph.md/профайлера. Дашборд LLM не зовёт ✓.
