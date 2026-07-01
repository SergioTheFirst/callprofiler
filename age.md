# age.md — План работ: стилометрический слой возраста (no-ML)

> **Для кого:** Claude Code (Sonnet), исполняющий агент. Читать вместе с `vozrast.md`
> (методология, таблицы, формулы) и картой `.claude/rules/insight.md`.
> **Что строим:** четвёртый класс сигнала возраста — `stylometric` — чисто
> стилометрический, БЕЗ ML/LLM/эмбеддингов. Дополняет существующую маркер-систему,
> не заменяет её.
> **Правило исполнения:** каждая задача самодостаточна. Не додумывать сверх
> написанного. Числа/таблицы брать из `vozrast.md` дословно. Тир задачи (T0–T3) —
> в шапке фазы (Model Routing, `CLAUDE.md`).

---

## 0. Жёсткие решения (обязательны, отклонение = ошибка)

Эти пункты уже приняты по факту чтения кода. НЕ пересматривать без явного гейта.

1. **Слой самодостаточен. НЕ трогать money-path.** Запрещено менять
   `insight/age_estimate.py::_aggregate`, `run_age_estimate`, схему
   `contact_age_estimates`. Причина: `contact_age_estimates.contact_id` —
   `PRIMARY KEY` (одна строка на контакт), второй строки `method='stylometric'`
   туда не вписать (это опровергает `vozrast.md` §9.3 — там ошибка). Плюс это
   тестируемый агрегатор маркеров. **Стиль пишет в СВОЮ таблицу
   `contact_age_style`.**
2. **Скоринг — на АГРЕГАТЕ контакта, не по-разговорно.** Все реплики контакта
   (`speaker='OTHER'`) склеиваются → один вектор признаков → одно распределение
   `P(g)`. Это «документный уровень» (`vozrast.md` §1.4/§3.5 — сильнейший сигнал).
   Требование «доверие растёт с числом разговоров» выполняется через `confidence`
   от `n_conversations`/`total_tokens` (§7). **Ось A по-разговорно + темперированный
   байес (§6.2) — ОТЛОЖЕНО** (см. §Deferred). Ось B = полный пересчёт агрегата.
3. **Переиспользовать существующее, не плодить.** Костяк — `insight/feature_store.py`
   (`build_contact_features`, `assemble_matrix`, `standardize` — z внутри юзера с
   импутацией медианой), `insight/features/base.py` (`Feature`/`Tier`/`tokenize`),
   `insight/features/{formality,pronouns,topical}.py`, `insight/synth/*`,
   `insight/age_markers.py` (read-only, для строки «явные маркеры» и приоритета §4.6).
4. **Инструменты:** numpy + regex. `pymorphy2` — ОПЦИОНАЛЬНО и graceful (import под
   try; нет пакета → морфо-признаки отдают `support_n=0`, ядро работает). НИКАКИХ
   sklearn/torch/sentence-transformers/эмбеддингов (`vozrast.md` §11.3).
5. **Каждый SQL — `WHERE user_id = ?`.** UPSERT — user-scoped guard
   (`WHERE …user_id = excluded.user_id`, паттерн `save_contact_archetype`).
   Идемпотентно.
6. **Приоритет маркеров над стилем (§4.6).** Стиль НЕ отменяет названный факт.
   В выводе: если у контакта есть валидный явный маркер (из `contact_age_estimates`
   `method IN ('marker','relation','combined')`) — блок стиля показывает его и
   помечает свою оценку как «фон». Слияние в одно число — ОТЛОЖЕНО.
7. **Дашборд — чистый read.** Пересчёт — только через action-эндпоинт (пишет БД),
   как `retry-failed`/`extract-names`. Read-пути (`get_person_dossier`) LLM/счёт не
   зовут.

---

## Storage-контракт (создаётся в Фазе 1, дальше неизменен)

Новая таблица (в `insight/repository.py::_SCHEMA`, применяется `apply_insight_schema`):

```sql
CREATE TABLE IF NOT EXISTS contact_age_style (
    contact_id      INTEGER PRIMARY KEY,
    user_id         TEXT    NOT NULL,
    group_code      TEXT,                 -- argmax группа: 'G1'..'G6'
    group_json      TEXT,                 -- {"G1":0.0,...,"G6":0.08} сумма=1
    birth_year_low  INTEGER,
    birth_year_high INTEGER,
    birth_year_point INTEGER,
    confidence      INTEGER NOT NULL CHECK (confidence BETWEEN 1 AND 100),
    confidence_level INTEGER NOT NULL CHECK (confidence_level BETWEEN 1 AND 5),
    n_conversations INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    top_json        TEXT,                 -- [["Т1 карьера",0.31],["Ч6",0.18],...]
    warnings_json   TEXT,                 -- ["мало данных","специфичный регистр"]
    table_version   TEXT,                 -- TABLE_VERSION+RULES_VERSION
    computed_at     TEXT    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cage_style_user ON contact_age_style(user_id);
```

Никакой таблицы `contact_age_evidence` (per-разговорные посылки) в MVP НЕ заводить —
она нужна только для темперированного байеса (ОТЛОЖЕН). `top_json`+`group_json`
покрывают отчёт §10.2.

## Версии и биннинг (константы, объявить в `age_style/tables.py`)

- `TABLE_VERSION = "age-style-v1"`, `RULES_VERSION = "age-rules-v1"`. Бамп любой →
  пересчёт (кэш-инвалидация, паттерн `PROMPT_VERSION`).
- Группы: `G1 0-17, G2 18-25, G3 26-35, G4 36-45, G5 46-60, G6 60+`
  (`vozrast.md` §2.3). Центры для проекции в год рождения:
  `{G1:12,G2:21,G3:30,G4:40,G5:53,G6:68}`.
- z-бины (`vozrast.md` §4.2): 5-бинные по z — `≤−1 / −1..−0.33 / −0.33..0.33 /
  0.33..1 / >1` = очень низк./низк./средн./высок./очень выс.; 3-бинные (сленг/
  архаизмы/читаемость): `z<−0.5 / −0.5..0.5 / >0.5` = нет-низк./средн./высок.
  (однонаправленные Л1/Л2 — бин «нет» = отсутствие маркеров, не по z).

---

## Фаза 0 — Preflight + фикс дизамбигуации маркеров  *(T1: Opus /fast; 1 файл-фикс + чтение)*

**Цель:** снять риск и закрыть явную ошибку пользователя «Внуково ≠ внуки» ДО новой логики.

| # | Действие | Детали | Приёмка |
|---|---|---|---|
| 0.1 | Прочитать | `insight/feature_store.py` (`build_contact_features`,`assemble_matrix`,`standardize`), `insight/features/{formality,pronouns,topical}.py`, `insight/synth/{corpus,archetypes,phrasebank,noise}.py`, `cli/commands/insight.py`, `dashboard/db_reader.py::get_person_dossier`, `dashboard/server.py` (tools-эндпоинты), `pipeline/watcher.py::_run_insight_fit`. Не писать код. | — |
| 0.2 | **Фикс Внуково** в `insight/age_markers.py` | Регэксп `grandkids` сейчас `\bвну[кч]\w*` → ловит «Внуково» (аэропорт). Сузить: `re.compile(r"\bвну[кч](?!ово)\w*", re.I)` **и** добавить контекст-гард (по образцу `_RE_JUBILEE_NOT_PERSON`): `_RE_GRANDKIDS_NOT = re.compile(r"внуково|аэропорт|рейс|прил[её]т|вылет|терминал", re.I)` — в цикле `_STAGES` для `grandkids` пропускать матч, если `_RE_GRANDKIDS_NOT.search(text[max(0,m.start()-30):m.end()+30])`. | 0.3 |
| 0.3 | Регресс-тест | `tests/insight/test_age_markers_vnukovo.py`: `test_vnukovo_airport_not_grandkids` (реплики «встречаю рейс в Внуково», «еду в аэропорт Внуково» → 0 сигналов `grandkids`); `test_real_grandkids_still_detected` («у меня трое внуков», «нянчу внучку» → есть `grandkids`). | `pytest tests/insight/test_age_markers_vnukovo.py -q` зелёный |

**DoD:** оба теста зелёные; существующие `tests/insight/test_age_*` не сломаны
(`pytest tests/insight -q`).

---

## Фаза 1 — Схема + синтетический age-ground-truth  *(T2: Opus high; SQL-write + новая таблица)*

**Цель:** офлайн-полигон и хранилище. Без реальной БД проверяем восстановление возраста.

| # | Действие | Детали | Приёмка |
|---|---|---|---|
| 1.1 | Создать таблицу | В `insight/repository.py` добавить DDL `contact_age_style` (см. Storage-контракт) в `_SCHEMA`. Функция `save_contact_age_style(conn, user_id, *, contact_id, group_code, group_dist, birth_low, birth_high, birth_point, confidence, confidence_level, n_conversations, total_tokens, top, warnings, table_version)` — INSERT…ON CONFLICT(contact_id) DO UPDATE … `WHERE contact_age_style.user_id = excluded.user_id` (копия паттерна `save_contact_archetype`; `group_dist`/`top`/`warnings` через `json.dumps(..., ensure_ascii=False)`). `load_contact_age_style(conn, user_id, contact_id=None)`. | 1.4 |
| 1.2 | Ридеры | `apply_insight_schema` уже вызовет DDL (idempotent) — убедиться, что новая таблица в `_SCHEMA`. Миграций колонок пока нет (таблица новая). | — |
| 1.3 | Синт ground-truth | В `insight/synth/` добавить `age_profiles.py`: словарь `AGE_TEMPLATES` — по одному профилю на группу G1..G6, каждый задаёт для генератора реплик: набор лексики жизненного этапа (Т1), поколенческих реалий (Т2), плотность сленга (Л1) / архаизмов (Л2), целевую среднюю длину слова в слогах (Ч6), целевое лексическое разнообразие (богатство словаря → MATTR). Расширить `SyntheticCorpus.build(...)` параметром `age_ground_truth: dict[contact_id,int]` — генерировать `transcripts` (speaker='OTHER') из шаблона группы + прописывать `calls.call_datetime`, чтобы возраст↔год рождения был проверяем. | 1.4 |
| 1.4 | Тест инфраструктуры | `tests/insight/test_age_style_schema.py`: `test_schema_idempotent` (двойной `apply_insight_schema` без ошибок); `test_save_load_roundtrip` (сохранил→прочитал, user-guard: чужой user_id не перезаписывает); `test_synth_age_corpus_builds` (корпус с известными возрастами собирается, у каждого контакта есть реплики OTHER и дата). | `pytest tests/insight/test_age_style_schema.py -q` зелёный |

**DoD:** таблица применяется идемпотентно; синт-корпус с заложенным возрастом
строится офлайн; `save/load` user-scoped. Гейт проекта: SQL-write → самопроверка
диффа на `WHERE user_id`, guard в UPSERT.

---

## Фаза 2 — Признаки (несущее ядро) + лексиконы  *(T2: Opus high; чистые функции + тесты)*

**Цель:** каждый признак — чистая функция `→ Feature(value, support_n, tier)` над
репликами контакта. Только ядро `vozrast.md` §3.11 (несущие); слабое/FRAGILE — ОТЛОЖЕНО.

**Ядро (реализовать ровно это):** Т1 (лексика жизненного этапа), Т2 (поколенческие
реалии), Л1 (молодёжный сленг), Л2 (архаизмы/советизмы), Ч6 (длина слова в слогах),
Р3 (MATTR), Р4 (MTLD), Р5 (Yule K), М1 (доля «я» vs «мы»); плюс **переиспользовать**
`formality.py` (Ст1), `topical.py`, `pronouns.py`.

| # | Действие | Детали | Приёмка |
|---|---|---|---|
| 2.1 | Лексиконы-данные | `insight/age_style/lexicons/`: `slang.txt`, `archaisms.txt`, `realia_by_epoch.txt` (формат `слово<TAB>birth_year_low<TAB>birth_year_high`), `life_stage.txt` (формат `слово<TAB>G-код`). Наполнить по спискам из `vozrast.md` §3.1/§3.8 (кринж/краш/зашквар/чил/рофл/вайб/база…; давеча/сберкнижка/талоны/партком…; дискотека/кассета/пейджер→≤1975, Денди/ICQ→1980-1990, тикток/твич→≥2000; школа/ЕГЭ→G1, сессия/общага→G2, ипотека/декрет→G3-G4, внуки/пенсия→G5-G6). Одна лемма/строка, `#`-комментарии. Загрузчик `age_style/lexicons.py::load_lexicon(name)`. | 2.5 |
| 2.2 | `features/diversity_age.py` | `mattr(tokens, window=50)`, `mtld(tokens, threshold=0.72)`, `yule_k(tokens)` → каждая возвращает `Feature`, `tier=ROBUST`, `support_n=len(tokens)`; при `len(tokens) < window`/`< 50` → `support_n=0` (не голосует). Считать по **леммам, агрегат всех реплик контакта** (§3.5). Length-invariant по построению. Numpy-only. | 2.5 |
| 2.3 | `features/readability_age.py` | `mean_syllables_per_word(tokens)` (Ч6): слоги = число гласных `аеёиоуыэюя` в слове; `Feature`, `tier=ROBUST`. НЕ реализовывать индексы Флеша/ARI/Ч1–Ч5 (FRAGILE, ОТЛОЖЕНО — §Deferred). | 2.5 |
| 2.4 | `features/morphosyntax_age.py` | `pronoun_i_ratio(tokens)` (М1): доля `{я,мне,меня,мной,мой,моя,мои,мо[её]}` от суммы I+We(`{мы,нас,нам,нами,наш,наша,наши}`); закрытый список, БЕЗ морфологии → `tier=IMMUNE`. POS-профиль (М2/М3) — под `try: import pymorphy2`; нет пакета → `support_n=0`. | 2.5 |
| 2.5 | `features/lexical_age.py` | `slang_density`, `archaism_density` (на 1000 слов, ↓/↑, однонаправленные), `life_stage_profile(tokens)` → доминирующий G-кластер + плотность (Т1), `realia_birth_year(tokens)` → (birth_low,birth_high) при попадании (Т2). Матч по лексиконам 2.1 (сравнение surface-леммы; `ё→е`, lower). `Feature` + отдельная структура для Т1/Т2 (несут группу/год, не скаляр). | 2.6 |
| 2.6 | Тесты признаков | `tests/insight/test_age_features.py`: `test_mattr_length_invariant` (один и тот же стиль на 200 и 800 токенов → \|Δmattr\|<0.05 — ключевое свойство §3.5); `test_syllables_ru` («программирование»→6, «дом»→1); `test_pronoun_i_ratio`; `test_slang_density_youth_high`; `test_archaism_density_old_high`; `test_life_stage_maps_group` (реплика про ЕГЭ→G1, про внуков→G6); каждая — чистая функция, офлайн. | `pytest tests/insight/test_age_features.py -q` зелёный |

**DoD:** ядро §3.11 покрыто; length-robustness разнообразия доказан тестом;
morpho-признаки graceful без pymorphy2; лексиконы — данные, не код.

---

## Фаза 3 — Таблицы вероятностей + скорер + правила  *(T2: Opus high; контракты слоёв)*

**Цель:** признаки → распределение `P(g)` на экспертных таблицах, линейный пул,
деконфликт корреляции, гейты. Без обучения.

| # | Действие | Детали | Приёмка |
|---|---|---|---|
| 3.1 | `age_style/tables.py` | Скопировать таблицы `vozrast.md` §4.2 **дословно**: Т-Л1(Ч6,5 бин), Т-Л2(MATTR,5 бин), Т-Л3(сленг,3), Т-Л4(архаизмы,3), Т-Л5(«я»,3), Т-Л6(жизненный этап — маппинг кластера→P(g)), Т-Л7(читаемость — НЕ используется в MVP, но занести). Формат: `TABLES: dict[feature_id -> {bin_label -> [P_G1..P_G6]}]`. Каждая строка нормирована (сумма=1) — добавить `assert` в `__main__`-самопроверке. `TABLE_VERSION`, `RULES_VERSION`, `GROUP_CODES`, `GROUP_CENTERS`, z-бины (см. Биннинг). | 3.4 |
| 3.2 | `age_style/weights.py` | `BASE_WEIGHTS` = колонка «Старт-вес» §3.11 для реализованных признаков (Т1 .95, Т2 .90, Л1 .85, Л2 .80, Ч6 .80, Р3 .80, Р4 .75, М1 .70, Р5 .55, Ст1 .60). `TIER_MULT = {IMMUNE:1.0,ROBUST:0.8,AFFECTIVE:0.6,FRAGILE:0.4}`. `context_mod(feature_id, call_type)` — §4.5: тема «работа/деловое» (из `analyses.call_type`) → ↓ вес Л1/Л3; «семья/личное» → ↑ Т1. `w = base·tier·support_factor·context_mod`, `support_factor=min(support_n/n0,1)`. | 3.4 |
| 3.3 | `age_style/scorer.py` | `score_contact(features: dict, call_types: list) -> tuple[dict P(g), dict contributions]`. Шаги (§4.4): (a) **деконфликт корреляции** — блок разнообразия (Р3/Р4/Р5) входит как ОДИН усреднённый голос, не три; (b) однонаправленные Л1/Л2 — бин «нет» ≈ равномерен (не тянет); (c) Т1/Т2 — прямой маппинг кластера/года, не z-бин; (d) **взвешенный линейный пул** `P(g)=Σ wᵢPᵢ(g)/Σ wᵢ`; (e) отбраковка `support_n < support_floor(2)`. `contributions` = вклад каждого признака (для top_json). | 3.5 |
| 3.4 | `age_style/rules.py` | `RULES_VERSION`. Гейты/санити (§5.3): `gate_enough_data(n_conv, total_tokens)` (мало → уровень 1, без argmax); `sanity_bimodal(P)` (два пика → пометить конфликт, не усреднять в центр); `edge_bonus` (доминирует кластер школа/ЕГЭ или внуки/пенсия → бонус к краю, компенсация регрессии к среднему §5.3). Каждое правило — чистая функция, версионируется. | 3.5 |
| 3.5 | Тесты движка | `tests/insight/test_age_scorer.py`: `test_tables_rows_normalized` (все строки §4.2 сумма≈1); `test_readability_counted_once` (деконфликт: блок разнообразия из 3 мер даёт вклад как один голос, не 3×); `test_clean_profile_recovers_group` (чистый синт-профиль G-k → argmax P = G-k для G2/G4/G6); `test_slang_absence_neutral` (нет сленга → не омолаживает пожилого); `test_gate_low_data` (2 реплики → gate «мало данных»). | `pytest tests/insight/test_age_scorer.py -q` зелёный |

**DoD:** на синте `P(g)` указывает верную группу для чистых профилей; деконфликт
корреляции проверен; гейт «мало данных» срабатывает.

---

## Фаза 4 — Год рождения + доверие + оркестратор записи  *(T2: Opus high; ось B + семантика уверенности)*

**Цель:** `P(g)` → интервал года рождения → доверие → UPSERT в `contact_age_style`.
Полный вход `run_style_estimate`.

| # | Действие | Детали | Приёмка |
|---|---|---|---|
| 4.1 | `age_style/accumulate.py` | `to_birth_year(P, reference_year) -> (low, high, point)`: спроецировать P(g) на годы через `GROUP_CENTERS` (возраст группы → год рождения = ref_year − center), интервал = 10/90-перцентили взвешенного по P распределения точек, point = медиана. **MVP: агрегат-уровень** (одно P на контакт). Темперированный байес по-разговорно — ОТЛОЖЕН (§Deferred, оставить `# ponytail:` метку с апгрейд-путём). | 4.4 |
| 4.2 | `age_style/confidence.py` | `confidence(n_conv, total_tokens, agreement, has_marker) -> (int 1-100, level 1-5)` по §7.1/§7.2 упрощённо: `conf = clamp(100·sigmoid(a·log(ESS_proxy)+b·agreement+c·marker_bonus−d·conflict))`, `ESS_proxy` от `n_conv`+`total_tokens`; уровни-гейты §7.1 (`<3 разг. ИЛИ <150 слов → level 1`). `agreement` = 1−нормэнтропия(P). Формула-коэффициенты — стартовые константы с `# ponytail: калибровать §15`. | 4.4 |
| 4.3 | `age_style/estimate_style.py` | `run_style_estimate(conn, user_id, *, reference_now=None, stale_only=False) -> dict(stats)`. Поток: `apply_insight_schema` → выбрать всех контактов (`SELECT contact_id … WHERE user_id=? … GROUP BY`, как `age_estimate`) → для каждого собрать реплики `speaker='OTHER'` (тот же SQL-паттерн `age_estimate.py`) → признаки (Фаза 2, агрегат) → **z внутри популяции через `feature_store.assemble_matrix`+`standardize`** → бины → `scorer.score_contact` → `rules` → `accumulate.to_birth_year` → прочитать явные маркеры из `contact_age_estimates` (has_marker, §4.6) → `confidence` → `save_contact_age_style`. Полная популяция (как `archetypes-fit`; z требует всех контактов). `stale_only` — как в `age_estimate`: пропустить контакты без новых звонков (по `computed_at`). Non-fatal per-contact (log+continue, `pipeline.md`). | 4.4 |
| 4.4 | Тесты накопления/доверия | `tests/insight/test_age_style_estimate.py`: `test_confidence_grows_with_conversations` (тот же профиль на 3 vs 40 разговорах → conf(40)>conf(3), интервал уже) — **прямое требование заказчика**; `test_birth_year_from_reference` (G4 в 2021 и 2026 → один год рождения, разный возраст); `test_low_data_level1_no_point` (1 разговор → level 1, без точки); `test_idempotent` (двойной прогон → та же строка); `test_recovery_groups` (синт G2/G4/G6 → argmax верный, ARI-подобный гейт ≥0.6 как в insight); `test_user_isolation`. | `pytest tests/insight/test_age_style_estimate.py -q` зелёный |

**DoD:** уверенность растёт с числом качественных разговоров; «мало данных»→level 1;
пересчёт идемпотентен; год рождения стабилен во времени; изоляция по user_id.
Гейт: security-reviewer на SQL-write (самопроверка `WHERE user_id`, UPSERT guard).

---

## Фаза 5 — CLI + watcher-autofit + Dashboard (кнопка + блок)  *(T1 UI/CLI + T2 action-эндпоинт)*

**Цель:** запуск из CLI, инкрементально в прогоне, кнопка «Определить возраст» в досье.

| # | Действие | Детали | Приёмка |
|---|---|---|---|
| 5.1 | CLI | `insight/cli_ops.py`: `run_style_estimate(conn, user_id, **kw)` — делегат к `age_style.estimate_style.run_style_estimate` (паттерн существующего `run_age_estimate`-делегата). `cli/commands/insight.py`: подкоманда `age-style --user X [--stale-only]`. Зарегистрировать в `cli/main.py` dispatch. | 5.5 |
| 5.2 | watcher-autofit | `pipeline/watcher.py::_run_insight_fit`: добавить вызов `cli_ops.run_style_estimate(conn, user_id, stale_only=True)` рядом с существующим `run_age_estimate`. Non-fatal (в общий try/except autofit), БЕЗ GPU/LLM (numpy/regex — можно во время ASR-прогона). Лог: `age-style est=%d skip=%d`. | 5.5 |
| 5.3 | Dashboard read | `dashboard/db_reader.py::get_person_dossier`: добавить секцию `dossier["age_style"]` из `contact_age_style`, **guarded `_has_table("contact_age_style")`** (нет таблицы → `None`, не 500 — паттерн `dashboard.md`). Поля: group_code, group_json, birth_year_point, возраст-к-текущему-году (`date.today().year - birth_year_point`), confidence, confidence_level, n_conversations, top_json, warnings_json. Read-only (`query_only`). | 5.5 |
| 5.4 | Dashboard action + UI | `dashboard/server.py`: `@fa.post("/api/tools/age-recompute")` (по образцу `_tools_extract_names`) → `run_style_estimate(conn, user_id)` (полная популяция, синхронно — секунды, без GPU/LLM) → вернуть свежую строку контакта. `static/app.js`+`templates/index.html`: в модалку досье (`renderDossier`) добавить блок «ВОЗРАСТ (стиль)» по макету `vozrast.md` §10.2 (группа, распределение-бары, интервал, ★-доверие, «Разговоров: N», топ-вклады, строка «Явные маркеры: …», кнопка «Определить возраст ↻»). Возраст серым при `confidence<50` (как age-колонка, `dashboard.md`). Не подписывать на SSE. | 5.5 |
| 5.5 | Тесты интеграции | `tests/test_dashboard_age_style.py`: `test_dossier_age_style_guarded_no_table` (нет таблицы → секция None, не 500); `test_dossier_reads_style_row`; `test_age_recompute_endpoint_writes_and_returns`. Офлайн (temp SQLite/synth), read-only коннект не пишет. | `pytest tests/test_dashboard_age_style.py -q` зелёный |

**DoD:** `age-style --user me` считает и пишет; кнопка пересчитывает и показывает
отчёт §10.2; read-only доктрина цела; секции guarded. На боксе (ручная проверка,
фиксировать в CONTINUITY): спот-чек 10 знакомых контактов — попадает ли интервал.

---

## Deferred (НЕ делать в этом плане; каждый — со своим триггером)

- **Ось A по-разговорно + темперированный байес** (`vozrast.md` §6.2). Триггер:
  калибровка (§15) покажет, что агрегат-уровень недооценивает N. Тогда — таблица
  `contact_age_evidence` + `accumulate` продукт правдоподобий с `α·R_k`.
- **Индексы читаемости Ч1–Ч5, синтаксис С1–С5, hapax Р7, эмоции Э1–Э3, дискурс
  Д1–Д5** — FRAGILE/слабые (§3.11). Триггер: спот-чек покажет нехватку сигнала.
  (Ч7 «доля многосложных», С3 «подчинит. союзы» — кандидаты первыми.)
- **Слияние стиля в `_aggregate`/`combined`** (§4.6 одним числом). Триггер: явный
  запрос показать единую цифру. Тогда — контролируемая правка money-path +
  регресс-тесты, что маркеры не сломаны.
- **Демпстер–Шафер** (§7.4), **age_band как FRAGILE-ось архетипов** (§15.4),
  **проверка сохранности хезитаций GigaAM** (§15.4, определяет судьбу Д4).
- **pymorphy2 POS-профиль (М2/М3), падежи (М6)** — включатся сами, когда пакет
  встанет на боксе (graceful-заглушки уже в 2.4).

## Guardrails (ponytail — нарушение = переделка)

- НЕ добавлять sklearn/torch/эмбеддинги. НЕ обучать веса (только экспертные таблицы
  + ручная калибровка). НЕ трогать `_aggregate`/`contact_age_estimates`. НЕ заводить
  per-разговорную таблицу в MVP. НЕ считать читаемость как 5 голосов (деконфликт).
  НЕ анализировать `speaker='UNKNOWN'`/`OWNER` (только `OTHER`, §2.7). НЕ показывать
  ложную точку при level 1 (широкий интервал + «мало данных»).

## Порядок / зависимости

```
Ф0 → Ф1 → Ф2 → Ф3 → Ф4 → Ф5
     (схема) (признаки) (движок) (год+доверие) (CLI+UI)
Калибровка §15 — сквозная, после Ф4 на реальных данных (бокс).
```

**Определение готовности всего:** `pytest tests/insight tests/test_dashboard_age_style.py -q`
зелёный; `age-style --user me` пишет `contact_age_style`; кнопка в досье работает;
`vozrast.md`-инварианты (грубые группы, интервал+доверие, рост с объёмом, приоритет
маркеров) соблюдены. Память → commit → push (`CLAUDE.md`).
