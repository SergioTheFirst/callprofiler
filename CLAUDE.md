# CallProfiler

**Mission:** audio → transcript → local LLM → Telegram/Android + психопортрет личности. Think a lot, show little.

## Communication (user-authorized 2026-06-05, updated 2026-07-01)
- Reply **short, to the point, no filler**. No preambles/recaps/"want me to also...". English.
- **Plugins always on:** `ponytail` at `ultra` (YAGNI-max, smallest diff, challenge scope before adding
  it) + `caveman` (terse). Save tokens everywhere possible.
- Не перечитывать код на вопрос. Ответы про pipeline/db/graph/llm/insight/dashboard брать из карт
  `.claude/rules/*`; код читать ТОЛЬКО если карта не покрывает (и тогда обновить карту).
- В конце задачи: память → `commit` + `push origin main` → короткий итог.

## Hard Constraints
- 100% local. No cloud / Docker / Redis / Celery / ORM / Ollama.
- LLM: `llama-server.exe -m "C:\models\Qwen3.5-9B.Q8_0.gguf" -ngl 99 -c 16384` → `http://127.0.0.1:8080/v1/chat/completions`.
  Модель зафиксирована (инвариант 27, decisions.md 2026-07-16) — смена только по canary-протоколу и явной команде.
- ASR: GigaAM v3 RNN-T (`C:\models\GigaAM-v3-rnnt`, in-process, GPU обязателен — CPU = RuntimeError).
  Whisper = только fallback (`asr_backend: whisper`, C-01).
- GPU sequential: GigaAM+pyannote (~5GB, ко-резидентны в Фазе 2) → unload → LLM (~10GB Q8_0).
  Never concurrent — 12GB RTX 3060, иначе OOM.
- Every SQL: `WHERE user_id = ?`. Tokens: `os.environ.get()`. Errors: log+DB+continue, `except: pass` запрещён.
- Schema: только новая запись в `db/migrations.py::ALL_MIGRATIONS` (checksummed, применённую не править)
  + `schema.sql` в sync. `restore` боевой БД — только через `backup`/`verify-backup` (T-20 гейт).
- **Dev/run split:** код пишется ЗДЕСЬ (нет БД/GPU/ffmpeg/моделей) — всё тестируемое офлайн
  (mock/synth, insight = numpy-only); реальный прогон = «проверка на боксе», фиксировать в CONTINUITY.
- **Git (user-authorized 2026-06-04, C-05):** локально — commit+push в `main` напрямую, без веток и
  без пер-действенного подтверждения. Облачный harness может навязать ветку+PR — тогда PR вливать
  сразу; ДВЕ параллельные облачные сессии запрещены (2026-08-21: PR #17/#18 сделали один фикс дважды).
  Rule: сперва память (CONTINUITY/CHANGELOG/.claude/rules/*), потом commit+push. Сломал `main` →
  `git revert` + push; `--force` запрещён.

## Paths & Commands
```
Project: C:\pro\callprofiler\          DB: C:\calls\data\db\callprofiler.db
Data:    C:\calls\data                 Audio: …\users\{uid}\audio\{originals,normalized}\
Ref:     C:\pro\mbot\ref\manager.wav   Input: C:\calls\in (protected — reset не трогает)
Install: pip install -e ".[dev,full]"  (бокс/dev, Python 3.12 + torch 2.6.0+cu124) · ".[cloud]" (CI/облако, без ML)
Test:    python -m pytest -q   (PYTHONPATH не нужен; 0 failed обязательно, актуальный baseline — CONTINUITY)
Lint:    ruff check --select F821,E9,F7,F63,F82 src tests   (CI-гейт, держать зелёным — ловит NameError-класс)
cmds: watch · process FILE --user U · dashboard --user U · doctor · backup/verify-backup/restore ·
      bulk-enrich · graph-replay · biography-run · features-build · archetypes-fit · age-estimate ·
      obligations-digest · (полный список: `python -m callprofiler --help`, ~60 команд)
```

## Model Routing v2 (главный рычаг экономии токенов — enforce strictly)

**Принцип:** тир задачи = **blast radius ошибки** (что сломается, если ошибиться), НЕ объём работы.
Объём ≠ сложность: 50 однотипных правок — это T0/T1. Старт всегда с минимально достаточного тира.

| Тир | Модель | Effort | Типы работ (этот проект) |
|-----|--------|--------|--------------------------|
| **T0** | Haiku 4.5 | low | Q&A по картам `.claude/rules/*`; формат/rename/docstring/опечатки; 1-файловый патч по готовому образцу; CHANGELOG/CONTINUITY/память; grep/лог-триаж; чтение вывода pytest |
| **T1** | Opus `/fast` | medium | рутина по известному паттерну: CLI-команда по образцу, тесты к готовому фиксу, багфикс с репро и известным классом (bugs.md), рефакторинг внутри модуля без смены контрактов, дашборд JS/read-only эндпоинты, .bat/env-скрипты, ревью одного диффа |
| **T2** | Opus | high | новая фича в 1-2 модулях; баг без репро / heisenbug (WAL, SSE, ASR/diarization quirks); смена контрактов между слоями; SQL-схема/миграция; правка LLM-промптов (`PROMPT_VERSION` bump = инвалидация кэша); insight: новые фичи-тиры/метрики; дизайн synth ground-truth |
| **T3** | **Fable 5** | **max** | архитектурно-стратегическое: новый workstream; всё трогающее Hard Constraints — GPU/VRAM-порядок, пути удаления данных (wav/mp3/purge/reset/restore), терминальные статусы и resume/reclaim-семантика; дизайн multi-day прогонов 16k+ (resilience/idempotency); ревизия CONSTITUTION/ARCHITECTURE/CLAUDE.md; неоднозначная спека; genuinely novel |

**Жёсткие гейты (экономить ЗДЕСЬ запрещено — история: OOM 2026-06-06, data-loss watcher 2026-06-03,
restore-откат 2026-08-10):**
- **→ T3:** GPU sequencing / VRAM-бюджет · удаление/перемещение/восстановление файлов данных ·
  терминальные статусы / stalled-reclaim / resume · любое решение уровня `decisions.md`.
- **→ T2+:** любой SQL write-path (user_id isolation) · миграция · `PROMPT_VERSION` / кэш-инвалидация ·
  контракты слоёв extraction→aggregation→interpretation (graph) и pass-контракты biography/insight.

**Механика:**
- В начале задачи объявить тир. Текущие model/effort не соответствуют → предложить `/model` + `/effort`
  одной строкой. Соответствие: T0=Haiku+low, T1=Opus+`/fast`+medium, T2=Opus+high, T3=Fable+max.
- Задача в ходе работы коснулась гейта выше → стоп, переоценить тир, эскалировать. Без гейта —
  НЕ эскалировать («важность» не повод).
- T0/T1-задача пришла на Fable/max → решать по-минимуму, БЕЗ компенсации глубиной: лишнее
  чтение/размышление = слив токенов.

**Субагенты (T0/T1 — БЕЗ субагентов, самопроверка диффа; модель через `model:` параметр):**
| Субагент | Триггер | model |
|----------|---------|-------|
| Explore | вопрос >1 файла, карты не покрывают (codegraph = primary tool) | haiku |
| planner | T2/T3 фича >2 файлов | sonnet |
| code-reviewer | после записи кода в T2/T3 | sonnet |
| security-reviewer | SQL write / удаление файлов / auth / внешний ввод | sonnet |
| tdd-guide | новый модуль или фикс без регресс-теста | sonnet |

**Отчёт субагента — не доказательство** (уроки 2026-06-06, 2026-08-08): после агента САМОМУ
проверить `git diff` и пересчитать ключевую метрику канонической функцией; зелёные тесты агента
≠ доказанное утверждение. Утверждение «работает на чистом окружении» верифицировать РЕАЛЬНОЙ
командой в чистом venv, не симуляцией (2026-08-21: два бага из-за «измерено заглушкой»).

## Session Start (every session)
1. `.codegraph/` exists → `codegraph_search` affected symbols before any Read.
2. Read `CONTINUITY.md` + last 5 lines `CHANGELOG.md` → print "State: … / Next: …".
3. `git status -sb` + `gh pr list` — открытый PR облачной сессии влить/закрыть ДО новой работы.
4. Объявить тир задачи (T0-T3) по Model Routing.

**Текущая входная точка исполнения:** `docs/sintezdiharea.md` (T-00…T-25, production-ready
фундамент; контракты CP-0 — `docs/decisions/CP-0-contracts.md`). Статус/следующая задача — в CONTINUITY.
Продуктовые фичи (`opsus5.md`) — после CP-5.

## .codegraph (mandatory)
`codegraph_search` / `codegraph_callers` / `codegraph_impact` **before every edit**.
Multi-file вопросы → Explore-субагент (haiku) с codegraph как primary tool.
If `.codegraph/` missing → `codegraph init -i` first.

## Skills (только релевантный, ≤2 на задачу — скиллы тоже стоят токенов; субагенты считаются отдельно)
| Trigger | Skill |
|---------|-------|
| DB schema / SQL | `sql-pro` + `.claude/skills/db-migration.md` |
| Python module | `python-patterns` |
| LLM prompt | `prompt-engineer` |
| Bug | `.claude/skills/fix-bug.md` + `systematic-debugging` |
| Architecture (T3) | `architecture-patterns` + `grill-me` |
| Security-гейт | `007` |

## Memory Protocol (обновлять ПОСТОЯННО, не в конце — по ходу работы)
- `CONTINUITY.md` — current state + next step only. **Overwrite** each session (not append).
- `CHANGELOG.md` — one line per logical change. Append only.
- `.claude/rules/pipeline.md` → **Pipeline Map** — стадии/статусы/файлы. Менять при смене конвейера.
- `.claude/rules/bugs.md` — non-obvious root cause + regression test ref + **способ решения**. One block per bug.
- `.claude/rules/decisions.md` — architectural WHY + **планы**. One paragraph per decision.
- `.claude/rules/{db,graph,llm,insight,dashboard,biography-*}.md` — карты слоёв; хуки/способы решения туда, не в код-комменты.
- **Rule: add only non-obvious facts. Never duplicate what's already in code or rules.**
- **Каждый значимый шаг: сперва в память (эти файлы), потом `commit`+`push origin main`.**

## Domain
- `[me]` = Сергей Станиславович Медведев (always owner). `[s2]` = other. Roles may be swapped — LLM determines.
- Output: ≤300 chars/item, ≤3 facts/item. Never show counts/durations to user.
- Дашборд: РОВНО 2 функции — ход обработки + досье личности; НИКОГДА не зовёт LLM и не пишет в БД.

## Prohibited
ORM · Ollama · cloud LLM · auto-merge contacts · verbose output (>300 chars) · features outside current
phase · premature abstraction · T3-глубина на T0/T1-задаче · чтение кода, покрытого картами ·
субагенты в T0/T1 · эскалация тира без гейта · `git push --force` · правка применённой миграции ·
`print()` вместо logger в prod-модулях

## Reference Files (load on demand — NOT at session start)
`@docs/sintezdiharea.md` `@docs/decisions/CP-0-contracts.md` `@ARCHITECTURE_v5.md` `@CONSTITUTION.md` (19 статей)
`@AGENTS.md` `@docs/TESTING.md` `@configs/prompts/analyze_v001.txt`
`@.claude/rules/db.md` `@.claude/rules/pipeline.md` `@.claude/rules/llm.md` `@.claude/rules/graph.md`
`@.claude/rules/insight.md` `@.claude/rules/dashboard.md` `@.claude/rules/biography-*.md`
`@.claude/rules/bugs.md` `@.claude/rules/decisions.md` `@src/callprofiler/biography/CLAUDE.md`
`@.claude/skills/fix-bug.md` `@.claude/skills/db-migration.md`
