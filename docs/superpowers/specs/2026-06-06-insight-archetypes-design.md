# Insight Engine — Архетипы личности из звонков (Design)

- **Дата:** 2026-06-06
- **Статус:** approved (форма + рекомендации согласованы пользователем)
- **Автор:** Claude (Opus, effort max) + Сергей Медведев
- **Связано:** `.claude/rules/graph.md`, `.claude/rules/db.md`, `.claude/rules/pipeline.md`,
  `.claude/rules/narrative-journal.md`, `.claude/rules/biography-*.md`

---

## 1. Цель

Извлечь из ~16k звонков **максимально объёмное понимание каждого человека** и свести
людей в **эмпирические архетипы** (не заданные руками, а обнаруженные кластеризацией).
Результат — карточка контакта («кто это по поведению, что в нём нетипично, как менялось»)
и визуальная карта социального мира. LLM используется минимально (только финальное
именование кластеров); ядро — детерминированная аналитика.

**Не цель:** оценка человека как личности/«хороший-плохой». Метрики — это *паттерны для
внимания*, со ссылкой на доказательства, в трендовой рамке. Наследуем правило
`graph.md`: BS-index и подобное — не приговор человеку.

---

## 2. Hard constraints (определяют архитектуру)

1. **Разработка офлайн, без БД.** Реальная база — на боксе (`C:\calls\data\db\callprofiler.db`).
   На дев-машине БД нет → весь код = чистые функции над контрактом строк; запуск/тесты —
   на **синтетическом корпусе** (schema-accurate temp SQLite).
2. **Только `numpy`** из тяжёлого (есть в `requirements-gigaam.txt`). `sklearn`/`scipy`/`torch`
   НЕ доступны на дев-машине → PCA/k-means/силуэт/ARI пишем на numpy. Никаких новых внешних
   зависимостей (совпадает с «100% local»).
3. **Устойчивость к ошибкам ASR** — first-class требование. Дизайн обязан переживать «немного
   ошибается распознавание» (см. §5).
4. **`WHERE user_id = ?`** во всех запросах (db.md). Идемпотентный персист. `ALTER`/новые
   таблицы, не пересоздание (db.md).
5. **Graceful degradation:** недостоверные роли (`speaker='UNKNOWN'`), пустое `direction`,
   малая выборка — не валят пайплайн, а понижают вес/доверие фичи.

---

## 3. Единица анализа и идентичность

**Единица архетипа = `contact`** (телефонная диада). Там живут лонгитюдные метаданные
(`calls.contact_id`, `call_datetime`, `direction`, `duration_sec`) и текст (`transcripts`
через `calls`). Обогащение из `entity_metrics`/`contact_summaries` по совпадению имени —
опционально (best-effort), не обязательно.

> Развилка решена пользователем: contact, не entity. `entities` (LLM-персоны графа) уже
> нормализованы — используем их как источник имён/тем (ASR-устойчивый), но не как единицу.

---

## 4. Что считаем о человеке — таксономия фич (11 осей, 4 тира устойчивости)

Каждая фича = изолированный модуль. Контракт: `compute(rows) -> dict[name -> (value, support_n, tier)]`.
Чистая функция, юнит-тест против синта.

### Тир IMMUNE (метаданные — ASR не влияет вообще)
1. **temporal** — циркадный профиль (24-bin гистограмма часов), будни/выходные, **burstiness**
   (Goh–Barabási B = (σ−μ)/(σ+μ) межзвонковых интервалов: −1 ровный … +1 взрывной), стаж,
   recency.
2. **reciprocity** — доля исходящих (инициация), асимметрия длительности (кто дольше
   «держит»), частота. (`direction` может быть UNKNOWN → фича понижает support_n; асимметрию
   длительности считаем всегда.)
3. **trajectory** — тренд каденса (наклон звонков/нед.: ускорение/остывание), **точки разлома**
   (CUSUM на ряде каденса/риска).

### Тир ROBUST (агрегаты служебных слов — шум усредняется на сотнях звонков)
4. **hedge** — твёрдость vs уклончивость в утверждениях о будущем («сделаю к пятнице» vs
   «постараюсь/посмотрим/наверное»). Честная замена недоказуемого Trust Score.
5. **directive** — императивы / «нужно/должен/давай».
6. **formality** — русская T-V: доля «ты»- vs «вы»-обращений + **асимметрия владелец↔контакт**
   (ты↔вы = статусный разрыв). Частотные слова → ASR-устойчиво.
7. **pronouns** — профиль я/мы/ты + тренд «мы» (крепнущий альянс), всплески «ты»
   (конфронтация). (Пеннебейкер, валидированная психолингвистика.)
8. **lexical** — type-token richness, средняя длина реплики, доля вопросов.

### Тир AFFECTIVE/TOPICAL (из готового LLM-анализа — `analyses`/`entity_metrics`)
9. **affective** — распределение `risk_score`, `profanity_density`, микс `call_type`,
   `emotional_pattern`/`avg_risk` из `entity_metrics` (если связан).
10. **topical** — TF-IDF по `key_topics` + `entities`: что ИМЕННО ОН поднимает; редкие темы =
    отличительные (анти-шум на «все про деньги»).

### Тир FRAGILE/GATED (зависит от диаризации — включается условно)
11. **dominance** — talk-ratio (доля времени OWNER vs OTHER), длина реплики, удержание «пола»
    (длиннейший монолог), направление вопросов. **Гейт:** включается только если доля
    `UNKNOWN`-сегментов у контакта ниже порога (напр. <0.3); иначе фичи отдают `support_n=0`
    и не входят в вектор.

---

## 5. Механика устойчивости к ASR (не декларация, а конкретика)

- **Относительное пространство.** Каждую ось z-нормируем **внутри контактов одного
  пользователя**. Архетип = «нетипичность относительно твоего круга», не абсолют → постоянная
  компонента ошибки ASR сокращается.
- **Вес фичи = w_tier × min(support_n / n0, 1).** Хрупкие фичи и малая выборка весят меньше в
  кластеризации и помечаются «предварительно» в карточке. `w_tier`: immune=1.0, robust=0.8,
  affective=0.6, fragile=0.4 (стартовые, калибруются на синте).
- **Имена/сущности — из канонизированных `entities.normalized_key`,** не из сырых токенов
  транскрипта (ASR калечит имена сильнее всего).
- **Noise-injection регресс-тесты.** На синт-корпусе с впрыснутым ASR-шумом каждая текст-фича
  обязана остаться в допуске от чистого значения (tolerance band per feature). Гейт в CI.

---

## 6. Архетип-движок

Пайплайн `archetypes.py` (numpy-only):

1. **Сборка вектора** контакта из `contact_features` (упорядоченный список осей).
2. **Импутация** пропусков медианой оси; **взвешивание** по §5; **z-score** внутри пользователя.
3. **PCA** (numpy SVD) → снижение размерности до ~8-10 компонент (стабильность, шумоподавление).
4. **k-means** (numpy, k-means++ init, фикс. seed, несколько рестартов) — k выбирается по
   **силуэту** (реализуем на numpy).
5. **Валидация на ground-truth синта:** **ARI** (Adjusted Rand Index, numpy) между
   восстановленными кластерами и заложенными метками. Цели в тестах: **ARI ≥ 0.6 (чисто),
   ≥ 0.4 (с ASR-шумом)**. Не проходит — движку нельзя верить, фаза не закрыта.
6. **Именование кластеров:** ОДИН LLM-проход на боксе по центроиду (топ-|z| оси → человеческий
   ярлык: «ночной зависимый», «транзакционный брокер»). Офлайн/без LLM —
   детерминированный фолбэк-ярлык из топ-осей.
7. **Персист** в `archetype_models` + `contact_archetypes` (идемпотентно, per user_id).

---

## 7. Изменения схемы (`apply_insight_schema(conn)` — идемпотентно)

```sql
CREATE TABLE IF NOT EXISTS contact_features (
    contact_id   INTEGER NOT NULL REFERENCES contacts(contact_id),
    user_id      TEXT    NOT NULL REFERENCES users(user_id),
    feature_set  TEXT    NOT NULL,         -- temporal|reciprocity|...
    feature_name TEXT    NOT NULL,
    value        REAL,
    support_n    INTEGER NOT NULL DEFAULT 0,
    tier         TEXT    NOT NULL,         -- immune|robust|affective|fragile
    computed_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (contact_id, feature_name)
);
CREATE INDEX IF NOT EXISTS idx_cfeat_user_set ON contact_features(user_id, feature_set);

CREATE TABLE IF NOT EXISTS archetype_models (
    model_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL REFERENCES users(user_id),
    version      TEXT    NOT NULL,         -- arch-v1
    k            INTEGER NOT NULL,
    silhouette   REAL,
    n_contacts   INTEGER,
    feature_list TEXT,                     -- JSON ordered dims
    centroids    TEXT,                     -- JSON
    labels       TEXT,                     -- JSON cluster_idx -> name
    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_archetypes (
    contact_id       INTEGER PRIMARY KEY REFERENCES contacts(contact_id),
    user_id          TEXT    NOT NULL REFERENCES users(user_id),
    model_id         INTEGER REFERENCES archetype_models(model_id),
    cluster_idx      INTEGER NOT NULL,
    archetype_label  TEXT,
    membership       REAL,                 -- 0..1 близость к центроиду
    distinctive_dims TEXT,                 -- JSON [{dim,zscore,interp}]
    confidence       TEXT,                 -- high|medium|low (по support)
    evidence         TEXT,                 -- JSON [{call_id,date,quote}]
    computed_at      TEXT    DEFAULT CURRENT_TIMESTAMP
);
```

Все `*.normalized_key`/имена берём из `entities`. Без новых тяжёлых индексов на `transcripts`
(FTS5 уже есть).

---

## 8. Данные на входе (контракты строк — что читает каждая фича)

- **temporal/reciprocity/trajectory:** `SELECT call_id, contact_id, direction, call_datetime,
  duration_sec FROM calls WHERE user_id=? AND contact_id=? ORDER BY call_datetime`.
- **hedge/directive/formality/pronouns/lexical/dominance:** `SELECT t.speaker, t.text,
  t.start_ms, t.end_ms FROM transcripts t JOIN calls c ON c.call_id=t.call_id WHERE c.user_id=?
  AND c.contact_id=? ORDER BY t.call_id, t.start_ms`.
- **affective:** `SELECT a.risk_score, a.call_type, a.profanity_density, a.key_topics FROM
  analyses a JOIN calls c ON c.call_id=a.call_id WHERE c.user_id=? AND c.contact_id=?`.
- **topical:** `key_topics` (analyses) + `entities`/`relations` по user_id.
- **enrichment:** `entity_metrics`, `contact_summaries` по совпадению имени (best-effort).

---

## 9. Визуализация (на существующем FastAPI-дашборде, `dashboard/`)

`viz.py` готовит данные (numpy), фронт рисует:
- **Карта архетипов** — PCA-2D проекция векторов контактов, цвет = кластер.
- **Эго-сеть** контакта — окрестность из `relations`/совместных упоминаний.
- **ЭКГ отношения** — лонгитюд (каденс + реципрокность + risk + синхрония) по контакту.
- **Циркадная тепловая карта** по контакту.

UMAP не берём (зависимость) → PCA-2D на numpy.

---

## 10. Фазовый план (каждая фаза самостоятельно ценна, изолирована, TDD)

| Фаза | Содержание | Шипается | Зависит |
|---|---|---|---|
| **0** | Синт-корпус (`synth/`) + ASR-шум + schema loader + контракт вектора + тест-скелет + `repository.apply_insight_schema` | `pytest` зелёный офлайн без БД | — |
| **1** | IMMUNE-фичи (temporal, reciprocity, trajectory, burstiness, CUSUM) + метадата-only архетип-проход | Архетипы работают без ролей/текста | 0 |
| **2** | ROBUST текст-фичи (hedge, directive, formality ты/вы, pronouns, lexical) + noise-тесты | Речевой паспорт | 0 |
| **3** | AFFECTIVE/TOPICAL (analyses, entity_metrics, TF-IDF, relations) | Обогащённый вектор | 0 |
| **4** | GATED dominance (условно по доле UNKNOWN) | Динамика власти, где роли годны | аудит ролей |
| **5** | Движок: сборка→импут→z→PCA→k-means→силуэт→**ARI-гейт**→именование→персист | Архетипы пользователя | 1-4 |
| **6** | Карточки + CLI (`person-archetype`, `archetypes-fit/list`, `features-build`) | Карточка с доказательствами + флагом доверия | 5 |
| **7** | Визуализация (карта/эго-сеть/ЭКГ/циркад) | Дашборд-вкладка | 5 |

---

## 11. Структура пакета

```
src/callprofiler/insight/
    __init__.py
    repository.py        # apply_insight_schema, CRUD (WHERE user_id=?)
    synth/
        corpus.py        # SyntheticCorpus: temp SQLite из schema.sql + ground-truth
        archetypes.py    # шаблоны-распределения известных архетипов
        noise.py         # inject_asr_noise(text, rate)
    features/
        base.py          # Feature protocol + tier enum
        temporal.py reciprocity.py trajectory.py
        linguistic.py    # hedge, directive, lexical, questions
        formality.py pronouns.py affective.py topical.py dominance.py
    feature_store.py     # сборка вектора, z-score, персист
    archetypes.py        # PCA/kmeans/silhouette/ARI/fit/assign/naming
    cards.py             # карточка контакта с доказательствами
    viz.py               # данные для дашборда
tests/insight/           # синт-фикстуры, ARI-цели, noise-допуски
```

CLI: регистрация в `cli/main.py` + `cli/commands/`, по образцу существующих.

---

## 12. Стратегия тестирования

- **Ground-truth recovery:** синт закладывает K архетипов → движок обязан восстановить
  (ARI ≥ 0.6 чисто).
- **Noise robustness:** тот же тест с ASR-шумом → ARI ≥ 0.4; каждая текст-фича в tolerance band.
- **Per-feature unit:** известный вход → известный выход (AAA).
- **Idempotency:** повторный `features-build`/`archetypes-fit` → 0 дублей, стабильный результат
  (фикс. seed).
- **user_id isolation:** два юзера в синте не протекают друг в друга.
- **Graceful:** UNKNOWN-роли/пустой direction/малый n → фича не падает, отдаёт корректный
  support_n.

---

## 13. Модель-роутинг по фазам (CLAUDE.md)

- Дизайн/спека/движок (Фаза 0,5): **Opus high/max**.
- Фич-модули/CRUD/тесты (Фаза 1-4,6): **Opus Fast medium** / Haiku на простой 1-файл.
- Ревью: **code-reviewer** после каждого код-райта; **security-reviewer** на `repository.py`
  (БД/ввод/user_id).
- Виз (Фаза 7): фронт — `frontend-design` skill.

---

## 14. Риски и митигации

| Риск | Митигация |
|---|---|
| ASR-шум топит текст-фичи | тиринг+взвешивание+относит. z-score+noise-тесты (§5) |
| Диаризация мертва → dominance бесполезен | GATED, n=0, не входит в вектор; остальное работает |
| Малая выборка контакта → шумный архетип | support_n → confidence-флаг в карточке |
| Кластеры не бьются с реальностью | ARI-гейт на синте; силуэт; эго-проверка глазами |
| Псевдоточность / эффект Барнума | тренды+диапазоны, ссылки на цитаты, без сырых «оценок-истин» |
| Подтверждающее искажение | каждая метрика линкуется на дословную цитату+дату |
| PCA/kmeans нестабильность | фикс. seed, k-means++, рестарты, выбор по силуэту |

---

## 15. Открытые вопросы (решаются по ходу, не блокируют старт)

- Точные пороги `w_tier`, `n0`, UNKNOWN-гейт — калибруются на синте в Фазе 1-4.
- Финальный список лексических маркеров (хедж/директив/формальность для русского) — растёт по
  мере Фазы 2; держим в конфиге, не в коде.
- Связь contact↔entity для обогащения — best-effort по имени; формализуется в Фазе 3.
