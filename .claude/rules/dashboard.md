# Dashboard Rules (карта слоя — отвечать отсюда, код не перечитывать)

**Доктрина (юзер, 2026-06-11): у дашборда РОВНО 2 функции** — (1) ход обработки файлов,
(2) всё о психологическом портрете личностей («нажал имя — знаешь всё»). Остальное — обслуга этих двух.
План внедрения досье: `docs/superpowers/plans/2026-06-11-dashboard-person-dossier.md`.

**Паттерн:** CLI/пайплайн ПИШЕТ → дашборд ЧИСТЫЙ read (`PRAGMA query_only=ON`, WAL-фикс — bugs.md
2026-06-04). Дашборд НИКОГДА не зовёт LLM и не пишет в БД. Слой не заполнен → секция пустая, не 500.

**Kill-criteria (`ozalupennieStrategic5.md` §7.6, портфель A-D завершён 2026-07-17):** замер
использования = grep access-лога uvicorn по endpoint'ам (`/api/mirror`, `/api/insight/lifeline`,
`/api/person`, и т.д.) раз в 4 недели; фича без обращений — кандидат на удаление. Кода под это
не пишем — лог уже есть (uvicorn access log).

**Русификация характеристики (2026-06-13):** весь видимый enum-словарь личности (темперамент/
мотивация/паттерны/severity/тип/факты/тренд/эмоц.паттерн) переводится в RU в `dashboard/labels_ru.py`
— презентационный слой; источник английский НАМЕРЕННО (psychology_profiler кормит книжные промпты
biography, менять нельзя). `get_entity_profile`/`get_character_profile`→`localize_character`,
`get_person_dossier`→`localize_dossier` (in-place, идемпотентно, неизвестное не теряется). `severity`
КЛЮЧ сохранён (фронт красит по нему) + `severity_label` для показа; англ. `label` паттерна (из
`_extract_patterns`) русифицируется пофразно. Статичные подписи entity-модалки — в app.js
`renderEntityTab`; `entity_type` фронт показывает как `entity_type_label`.

**T-23 (2026-08-22):** темперамент / Big Five (OCEAN) / «мотивация» УДАЛЕНЫ из `psychology_profiler` (методы снесены, payload `entity_profiles` их больше не пишет; legacy-строки с этими ключами игнорируются), из портретных промптов biography (`p5-v4`), из досье/entity-модалки/`labels_ru`/`models.py`/`dashboard/config.py`. Остаются только наблюдаемые паттерны/ритм/связи/факты. Любой возврат — только из валидированного явного опросника (CONSTITUTION, T-23).

## Вкладки (templates/index.html)
`overview` (+ **«Здоровье»**, F7: collapsible-панель `#health-panel` — те же doctor-чеки F6 через
`GET /api/health-report` (`doctor.run_checks` напрямую, threadpool, никакой записи в БД); 🔴-бейдж
в шапке `#header-health-badge` при любом FAIL; кнопка «Обновить») · `calls` · `search` ·
`entities` (**«Личности»**: «Зеркало» владельца (A3, collapsible, СВЕРХУ вкладки) → таблица людей
`#people-table` с поиском + «Упомянутые персоны (граф)» + модалки) · `insight` («Архетипы», 5 видов,
Ф7 + D2 «Линия жизни» — Gantt из `bio_arcs`, `/api/insight/lifeline`) · `system`.
SSE-тик обновляет активную вкладку (bugs.md 2026-06-05).

**Досье-UI (Ф3):** клик по строке людей / точке PCA (`_cid` в data) / узлу эго-сети (`id='c{cid}'`)
→ модал `#person-overlay` (`openPersonDossier`/`renderDossier` в app.js): шапка-архетип + **Admiralty-
грейд строкой под именем** (A7, `d.admiralty`, `grade_line()` реюз из A6) → индексы
(Риск/BS по `bs_thresholds` если есть/Доверие) →

**группа «Речь»** (`dossierLayer()` — заголовок-разделитель, CSS `.dossier-layer-title`):
**возраст** («~48 лет (40–55) · уверенность 35/100» + evidence-цитаты; из `contact_age_estimates`,
возраст к ТЕКУЩЕМУ году из birth_year_point) → **возраст (стиль)** (group-бары G1-G6/★-доверие/
топ-вклады/явные маркеры/кнопка «Определить возраст ↻» → `POST /api/tools/age-recompute?contact_id=`;
из `contact_age_style`, отдельный 4-й сигнальный класс — `.claude/rules/insight.md` «Возраст-стиль»)
→ черты-фразы («Отличительное»).

**группа «Поведение»:** паттерны (severity-цвет) → психотип → ритм (TREND_RU) → факты-цитаты →
противоречия → обещания.

**группа «Место в сети»:** личное → связи → **финансовая экспозиция** (B7, `d.finance`:
фраза + до 3 quote+дата событий-оснований; `insight/finance.py::finance_exposure`, guarded
try/except в `db_reader.py`, None → нет секции) → **через упоминания** (C1, `d.mentions`:
«о нём говорят» top-3 + исходящий счётчик; `insight/mentions.py`, guarded `_has_table
('mention_edges')`).

**группа «Динамика»:** динамика по годам → **«Поворотные сцены»** (A7, 2026-07-17: `d.pivotal_scenes`,
дата+synopsis≤300; guarded `_has_table('bio_scene_entities')`+`('bio_scenes')`; см. ниже — НЕ читает
`bio_portraits.pivotal_scenes`) → **«Дрейф стиля»** (B8, `d.drift`: до 2 осторожных фраз,
`insight/age_style/drift.py::style_drift`, live-вычисление numpy/regex в `db_reader.py`,
FRAGILE-gated по доле UNKNOWN, guarded try/except).

**«Напряжения»** (A7, вне 5-слойной сетки — по смыслу межслойная, сводит их): `d.tensions`, каждая
строка фраза+2 evidence; `insight/tension.py::cross_layer_tensions()`, ровно 5 детерминированных
правил по `dims`(distinctive_dims сырые z из contact_archetypes)/`evolution`/`indices.
emotional_pattern`, без данных → правило молча не срабатывает.

**группа «Что делать»:** **флаг затухания** (C3, шапка слоя: `d.dormant` — `insight/dormancy.py::
dormant_valuable`, вызван с `top=10**6` — этот контакт целиком, не top-5 digest-выборка; guarded
try/except) → **«Моя заметка»** (M6: свободное ручное поле владельца, `contact_notes`
table, `_has_table`-guarded read → ключ `owner_note`; `POST /api/tools/contact-note`
{contact_id,note} — пустая строка удаляет, cap 2000, UPSERT user-guarded; `set_contact_note` сама
вызывает `apply_insight_schema`) → интерпретация (persisted или подсказка `profile-all`) → совет.

звонки (клик → call detail) → кнопки «ЭКГ →» (insight-пикер) и «Граф-персона →» (старая entity-модалка).
**Ф4 уже встроена:** `profile-all --user me` зовёт `build_profile` (LLM on) → интерпретации
персистятся в `entity_profiles` с memoization-сигнатурой; досье их читает. Запускать в LLM-окне.

**Поворотные сцены — источник (A7 non-obvious):** `bio_scenes` has NO `entity_id` column, и
`bio_portraits.pivotal_scenes` хранит LLM-time позиционные индексы в ЭФЕМЕРНЫЙ список сцен,
переданный в промпт при сборке портрета — НЕ стабильный `scene_id` (резолвить их означало бы
показать ЧУЖУЮ сцену без предупреждения, тот же класс ошибки, что id-пространство bio_entities
≠ graph entities, bugs.md 2026-07-02). Реальная связь — junction `bio_scene_entities(scene_id,
entity_id)`. Читаем top-`importance` сцены контакта через
`bio_scene_entities ⋈ bio_scenes ⋈ bio_entities` (имя контакта = `canonical_name`, регистронезависимо,
связь ТОЛЬКО по имени как и весь остальной bio-слой) — надёжно, ничего не гадаем.

## Эндпоинты (server.py, все через DashboardDBReader, `WHERE user_id=?`)
- Обработка: `/api/overview` `/api/calls[/{id}]` `/api/search` `/api/system[/logs]` `/api/sse`
  `/api/stats` `/api/history` `/api/daily*` + tools (`retry-failed`, `reprocess`, `extract-names`,
  `rebuild-cards`, `age-recompute?contact_id=` — полная популяция юзера синхронно, без GPU/LLM)
  + export (`calls.csv`, `book.md`).
- `/api/audio/{call_id}` (M2, 2026-07-16): `FileResponse` архивного mp3/wav из `calls.audio_path`;
  404 без записи/файла ИЛИ если путь вне `data_dir` (defense-in-depth). Клик по строке транскрипта
  в call-detail (`app.js`) мотает `<audio>` на `start_ms/1000`.
- `/api/tools/import-audio?name=` (M5, 2026-07-17, security-sensitive): raw body → `tools.
  save_incoming_audio` пишет в `users.incoming_dir` (watcher подхватывает штатно) — whitelist
  расширений, size-cap 512MB, path-traversal через `Path(name).name`, Windows reserved-device-name
  гард (CON/NUL/AUX/COM1-9/LPT1-9), атомарная запись `.part`→`os.replace`. Никакого
  python-multipart (инвариант 2) — тело как есть.
- Личности: `/api/characters` (список entities+metrics+psychology), `/api/character/{entity_id}`
  (модалка, app.js:541), `/api/contact/{contact_id}`, `/api/analytics`.
- Досье (Ф2): `/api/people` (список контактов + архетип + BS через map + `age_point`/`age_confidence`
  guarded; колонка «Возраст» в таблице, серым при conf<50; наполняет `age-estimate`/autofit) и
  `/api/person/{contact_id}` → `get_person_dossier` — агрегатор: contact_summaries (risk) +
  contact_archetypes (label/traits-фразы) + entity-слой через `entity_contact_map` (top-confidence) +
  `PsychologyProfiler(include_llm=False)` (паттерны/temporal/social/network/evolution/top_facts) +
  сохранённая интерпретация из `entity_profiles` + bio_contradictions + bs_thresholds. Все секции
  guarded `_has_table`/`_has_column` (слоёв может не быть; `trust_score` в entity_metrics добавляет
  ТОЛЬКО biography-схема). LLM из дашборда НЕ вызывается никогда (bugs.md 2026-06-11).
- Insight: `/api/insight/{pca,network,circadian,ecg,contacts}`.
- `/api/mirror` (A3, 2026-07-17): `get_mirror` читает `owner_mirror` (payload считает и пишет
  `mirror-build --user X` CLI, НЕ дашборд) — guarded `_has_table`/пустая строка → `{}`, не 500.

## Ключевые ридеры (db_reader.py)
- `get_all_characters` — entities ⋈ entity_metrics ⋈ entity_profiles(profile_type='psychology',
  payload temperament/motivation) + has_portrait(bio_portraits). Лейбл — `_build_character_label`.
- `get_character_profile(entity_id)` — метрики (bs_index/trust_score/volatility/conflict_count/
  emotional_pattern) + bio_behavior_patterns + bio_contradictions(top-5) + контакт ПО РАВЕНСТВУ
  имени/алиаса + open promises + recent calls. **Дыры: `temporal=None`, `network=None`** (заглушки) —
  закрываются досье-планом.
- `get_contact_profile(contact_id)` — contacts + contact_summaries (global_risk, avg_bs_score,
  open_promises/debts/personal_facts, advice) + recent calls + linked_entities по LIKE-имени.
- insight 4 ридера — guarded (нет fit → пусто).

## Кто наполняет данные (источник «пустых вкладок»)
| Авто в прогоне watch | Только вручную (CLI) |
|---|---|
| analyses, contact_summaries, promises | `features-build`+`archetypes-fit` → contact_features/contact_archetypes (**пустая вкладка «Архетипы» = fit не запускали**) |
| entities/relations/events/entity_metrics (BS): orchestrator.py:833 + enricher.py:504, `enable_graph_update=True` дефолт (config.py:85) | психология: entity_profiles (graph/repository.py:602), bio_behavior_patterns/bio_contradictions (biography/repo.py:804,859) — биография/профайлер-пассы |

`PsychologyProfiler.build_profile()` (biography/psychology_profiler.py) — live-расчёт
(patterns/temporal/social/evolution/top_facts + LLM-interpretation), НИЧЕГО не персистит,
к дашборду пока НЕ подключён. Контракт выхода — `biography-style.md`.

## Id-пространства (не путать)
`contact_id` (диада, телефон) ≠ graph `entities.id` (LLM-персона; contact_id-колонки НЕТ) ≠
`bio_entities`. Связь сейчас — только равенство имени в ридерах; персистная `entity_contact_map` —
по плану досье (Ф1).
