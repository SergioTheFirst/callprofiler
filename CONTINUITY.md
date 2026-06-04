# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history preserved in git. Overwrite each session; append-only logs live in CHANGELOG.md.

**Goal (incl. success criteria):**
- Рабочий локальный pipeline `C:\calls\in` → текст (GigaAM v3) → БД → LLM-анализ → дашборд/Telegram.
- Текущий фокус: устойчивость основного анализа звонка для unattended-прогона 17k + видимость в дашборде.

**Workflow (durable, 2026-06-04):**
- Пользователь снял запрет: Claude **коммитит и пушит в `main` БЕЗ пер-действенного согласования**.
- Правило: **каждый значимый шаг сперва в файлы памяти проекта** (CONTINUITY/CHANGELOG/.claude/rules/*),
  **потом** `commit`+`push origin main`. Push to main only, no feature branches, no attribution footer.

**Constraints/Assumptions:**
- 100% local. Windows. LLM = llama-server @127.0.0.1:8080. SQLite, no ORM, каждый запрос фильтрует `user_id`.
- **Пишем код на ЭТОЙ машине (без GPU/transformers/моделей/данных), запускаем на ДРУГОЙ (бокс с GPU).**
  В этой среде стоит только torch+numpy → реальный ASR/диаризация/прогон здесь невозможны; БД здесь пустая.
- `data_dir = C:\calls\data`.

**State (2026-06-04):**

🟢 **Дашборд: переключатель профилей (user_id)** — ДОБАВЛЕНО, тесты 42/42 зелёные.
`db_reader.get_user_ids()` (кросс-юзер мета-листинг) + `/api/users` + `/api/users/select` +
поллер форсит tick при смене профиля + dropdown в шапке (`index.html`/`app.js`/`style.css`).
Смена профиля → reload. **Зачем критично:** `start-dashboard.bat` жёстко стартует `--user serhio`,
а на боксе `serhio` = БИТЫЙ юзер (все звонки error «файл не найден»); рабочие **16645 done — под
юзером `me`**. Переключатель serhio→me показывает реальные данные (это и была «статичная картинка»).

📐 **Дизайн: перенос устойчивости biography → call-analysis** — записан в `.claude/rules/decisions.md`
(«Port biography resilience…»). Анализатор уже взял ВЫХОДНОЙ дин.бюджет (`output_budget.py`) +
клип входа (`prompt_budget.py`). Брать дальше (по приоритету): (1) мемоизация LLM-вызовов +
retry-без-падения (`ResilientLLMClient`/`bio_llm_calls` → общий `llm_cache`), (2) пер-задачные
бюджеты токенов (triage/extract/deep), (3) разбить монолит-анализ на gated-проходы (за флагом,
canary-50), (4) входной бюджет как пропорц. конкуренция, (5) версии промптов по задачам.
НЕ брать: пер-айтемные checkpoint-таблицы (status уже resume), психопрофиль в пер-звонок, 9-секц. бюджеты.

**Prod-данные на боксе (из прошлого diag):** ~16645 done под `me`, 2349 error, 754 normalizing(stage0);
юзер `serhio` битый (кандидат на снос через `cleanup.bat purge-user`). Все legacy-транскрипты speaker=UNKNOWN.

**Next:**
- Ждём выбор пользователя, какую ветку дизайна реализовать первой. Рекомендация: **#1 мемоизация+retry**
  (макс. ROI надёжности на 17k, мин. риск, переиспользует biography-код) → затем #2 task-бюджеты.
- Реализация — через planner + tdd-guide (RED→GREEN), тесты, code-review, затем commit+push main.
- На боксе: запустить `start-dashboard.bat`, переключить профиль serhio→me, убедиться что 16645 видны.

**Open questions (UNCONFIRMED):**
- Общий `llm_cache` (новый модуль/таблица `llm_calls`) vs переиспользовать `bio_llm_calls` с `pass_name='analysis'`.
- Гейты для P-deep: только priority≥70, или ещё длина/наличие structured_facts.

**Working set (files/ids/commands):**
- Touched (uncommitted → коммитится этой сессией): `dashboard/{server,db_reader}.py`,
  `dashboard/static/{app.js,style.css}`, `dashboard/templates/index.html`, `CHANGELOG.md`,
  `.claude/rules/decisions.md`, `CONTINUITY.md`, `CLAUDE.md`.
- Tests (бокс): `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
- Dashboard tests (здесь, зелёные): `pytest tests/test_dashboard_server.py tests/test_dashboard_tools.py tests/test_dashboard_export.py -q`
