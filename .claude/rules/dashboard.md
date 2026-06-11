# Dashboard Rules (карта слоя — отвечать отсюда, код не перечитывать)

**Доктрина (юзер, 2026-06-11): у дашборда РОВНО 2 функции** — (1) ход обработки файлов,
(2) всё о психологическом портрете личностей («нажал имя — знаешь всё»). Остальное — обслуга этих двух.
План внедрения досье: `docs/superpowers/plans/2026-06-11-dashboard-person-dossier.md`.

**Паттерн:** CLI/пайплайн ПИШЕТ → дашборд ЧИСТЫЙ read (`PRAGMA query_only=ON`, WAL-фикс — bugs.md
2026-06-04). Дашборд НИКОГДА не зовёт LLM и не пишет в БД. Слой не заполнен → секция пустая, не 500.

## Вкладки (templates/index.html)
`overview` · `calls` · `search` · `entities` (**«Личности»**: таблица людей `#people-table` с поиском
+ «Упомянутые персоны (граф)» + модалки) · `insight` («Архетипы», 4 вида, Ф7) · `system`.
SSE-тик обновляет активную вкладку (bugs.md 2026-06-05).

**Досье-UI (Ф3):** клик по строке людей / точке PCA (`_cid` в data) / узлу эго-сети (`id='c{cid}'`)
→ модал `#person-overlay` (`openPersonDossier`/`renderDossier` в app.js): шапка-архетип → индексы
(Риск/BS по `bs_thresholds` если есть/Доверие) → **возраст** («~48 лет (40–55) · уверенность 35/100»
+ evidence-цитаты; из `contact_age_estimates`, возраст к ТЕКУЩЕМУ году из birth_year_point) →
черты-фразы → паттерны (severity-цвет) → психотип →
ритм (тренд словами TREND_RU) → факты-цитаты → противоречия → обещания → личное → связи → динамика
по годам → интерпретация (persisted или подсказка `profile-all`) → совет → звонки (клик → call detail)
→ кнопки «ЭКГ →» (insight-пикер) и «Граф-персона →» (старая entity-модалка).
**Ф4 уже встроена:** `profile-all --user me` зовёт `build_profile` (LLM on) → интерпретации
персистятся в `entity_profiles` с memoization-сигнатурой; досье их читает. Запускать в LLM-окне.

## Эндпоинты (server.py, все через DashboardDBReader, `WHERE user_id=?`)
- Обработка: `/api/overview` `/api/calls[/{id}]` `/api/search` `/api/system[/logs]` `/api/sse`
  `/api/stats` `/api/history` `/api/daily*` + tools (`retry-failed`, `reprocess`, `extract-names`,
  `rebuild-cards`) + export (`calls.csv`, `book.md`).
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
