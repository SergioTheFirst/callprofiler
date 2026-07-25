# NeErrorsGR — Playbook устранения дефектов CallProfiler

> **Назначение:** прямые инструкции для агентов-программистов.  
> **Источник:** code review текущего дерева `C:\pro\callprofiler` (2026-07-22).  
> **Область:** `src/callprofiler/**`, `configs/*`, dashboard static, известный долг из `.claude/rules/{bugs,decisions}.md`.  
> **Не делать в рамках этого документа:** массовый рефакторинг «заодно», смена стека, live GPU/LLM на боксе.

---

## 1. Scope и метод

| Что | Как |
|-----|-----|
| Pipeline / GPU / resume | `pipeline/orchestrator.py`, `watcher.py`, `db/repository.py` |
| DB isolation | SQL + `user_id`, `doctor.py`, admin CLI |
| Analyze / LLM | `analyze/llm_client.py`, `llm_cache.py` |
| Aggregate / cards | `aggregate/summary_builder.py`, `deliver/card_generator.py` |
| Dashboard | `dashboard/{db_reader,server,tools,static/app.js}` |
| Graph / insight / bio | contracts + id-spaces, silent key mismatches |
| Security | import-audio, tools endpoints, local-only assumption |

**Метки статуса находки:**
- **CONFIRMED** — видно в текущем коде (path+symbol).
- **UNVERIFIED/BOX** — логика/контракт; нужна проверка на реальной БД бокса.
- **RESOLVED-in-memory** — закрыто в bugs.md; **не** повторять как open, если код уже исправлен.

**Уже RESOLVED (не чинить повторно):** FTS5 search, BOM .bat, stalled normalizing stage0, WAV delete config, OOM unload order (batch path), WAL `query_only`, pyannote in-memory, risk_thresholds в **card_generator**, feedback `user_id` в bot (handle_feedback читает `_get_user_id`).

---

## 2. Severity legend

| Уровень | Когда | SLA для агента |
|---------|--------|----------------|
| **P0** | Потеря/порча данных, OOM, silent wrong data в user-facing UI, security write path | Немедленно, отдельный commit |
| **P1** | Нарушение CONSTITUTION (`user_id`), silent contract mismatch, fragile runtime | В ближайшем vertical slice |
| **P2** | Perf@16k, maintainability, dead paths, inconsistent thresholds | После P0–P1 |
| **P3** | Style, backlog UX, optional hardening | По явному запросу / backlog |

---

## 3. Findings (by priority)

---

### F-01 · P0 · CONFIRMED — `open_promises`: ключ `payload` vs UI `what`

**Где проявляется**
- Writer: `src/callprofiler/aggregate/summary_builder.py` → `_extract_open_promises` / `_extract_open_debts` / `_extract_personal_facts` (поля `"payload"`, `"deadline"`).
- Reader UI: `src/callprofiler/dashboard/static/app.js` → `promiseItemHtml` / entity modal (`p.what`, `p.due`).
- Reader path: `dashboard/db_reader.py` → `get_contact_profile` / `get_person_dossier` JSON-loads `contact_summaries.open_promises` as-is.

**Почему проблема**  
Боевой путь summary_builder пишет `{"id","who","payload","deadline"}`, UI читает `what`/`due` → текст обещания = `?`, дедлайн не показывается. Тихая порча UX (не 500).

**К чему ведёт**  
Владелец не видит открытые обещания/долги в досье; F1 ✓/✗ кнопки есть (id есть), но смысл строки потерян; feedback по «пустым» строкам бессмыслен.

**Атомарный fix**
1. **Канон ключей (рекомендуется dual-compat, без ломки старых строк БД):**
   - В `summary_builder._extract_open_promises` писать **оба** ключа:  
     `"what": e.get("payload") or e.get("what") or ""`,  
     `"payload": ...` (оставить),  
     `"due": e.get("deadline") or e.get("due")`,  
     `"deadline": ...` (оставить).
   - То же для `_extract_open_debts` и `_extract_personal_facts` (`fact`/`what`/`payload` — выровнять с app.js).
2. **UI defense (обязательно):** в `promiseItemHtml`:  
   `escapeHtml(p.what || p.payload || '?')` и `p.due || p.deadline`.
3. **Регресс-тест:** unit: summary_builder JSON содержит `what`; dashboard fixture: seed только `payload` → render не `?`.  
   Файл: `tests/test_dashboard_dossier.py` или `tests/test_summary_builder_promises.py`.
4. **Миграция данных (опц.):** one-shot CLI/SQL: для строк `contact_summaries` где JSON имеет payload без what — backfill (не обязателен если dual-read).

**DoD:** досье «Открытые обещания» показывает текст; pytest green; запись в CHANGELOG.

---

### F-02 · P0 · CONFIRMED — `_finalize_note` asyncio loop без fallback

**Где**  
`src/callprofiler/pipeline/orchestrator.py` → `_finalize_note` (~558):  
`asyncio.get_event_loop().run_until_complete(self.telegram.send_note_ready(...))`  
**без** `except RuntimeError` + `new_event_loop`.

**Контраст**  
`_deliver` / send_summary (~978–989) **уже** имеет fallback на `new_event_loop`.

**Почему**  
После `asyncio.run(...)` в том же потоке (тесты, event_bus, другой helper) `get_event_loop()` → `RuntimeError: There is no current event loop`. Уведомление о note молча падает в outer except (log only).

**К чему ведёт**  
Голосовые заметки (F4) «готовы» в БД, Telegram-notify не уходит; в full-suite flaky; в проде — если кто-то добавит `asyncio.run` в watcher-thread.

**Атомарный fix**
1. Вынести helper (один раз):
```python
def _run_coro(coro) -> None:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
        loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)
        finally:
            loop.close()
```
2. Заменить оба call site: `_finalize_note` **и** send_summary path на `_run_coro(...)`.
3. **Не** звать `asyncio.run` внутри pipeline (event_bus — см. F-10).
4. Тест: без ambient loop, mock telegram, assert `send_note_ready` called once.

**DoD:** note notify работает без pre-existing loop; regress test.

---

### F-03 · P1 · CONFIRMED — `summary_builder` risk emoji через BSCalibrator (чужая шкала)

**Где**  
`aggregate/summary_builder.py` → `_risk_emoji_with_calibration` (~80–95):  
`BSCalibrator.get_label(float(risk), user_id)` на **risk_score**, хотя калибратор обучен на **bs_index**.

**Контраст**  
`deliver/card_generator.py` уже на `risk_thresholds` + `insight.risk_calibration.risk_emoji` (A4 fixed).

**Почему**  
Семантическая подмена шкалы: risk 0–100 красятся порогами BS. Карточка Android и summary-bullets могут расходиться.

**К чему ведёт**  
Неверные 🔴/🟡/🟢 в текстах, собранных summary_builder; доверие к risk ломается.

**Атомарный fix**
1. Скопировать паттерн `card_generator._risk_emoji_with_calibration` (lazy conn → `get_latest_risk_thresholds` → `risk_emoji`).
2. Удалить использование BSCalibrator для risk в summary_builder.
3. Fallback 30/70 оставить.
4. Тест: файловый Repository + risk_thresholds row → emoji соответствует **risk** percentiles, не BS.

**DoD:** один код-путь калибровки risk (shared helper ideally in `insight/risk_calibration.py`).

---

### F-04 · P1 · CONFIRMED — doctor checks без `WHERE user_id = ?`

**Где**  
`src/callprofiler/doctor.py`:
- `_check_queue_stuck` — `SELECT call_id FROM calls WHERE status NOT IN (...)` (все users).
- `_check_error_burst` — `FROM calls WHERE datetime(created_at) >= ...` (все).
- `_check_input_silence` — `MAX(...) FROM calls` без user_id.
- (см. также reminders/global counts).

**Почему**  
CONSTITUTION 2.5 / `.claude/rules/db.md`: queries к calls/contacts/… **MUST** filter `user_id`. Doctor-отчёт в Telegram/dashboard смешивает профили.

**К чему ведёт**  
Ложный FAIL «застряли» из-за чужого user; или маскировка проблем keeper'а; multi-profile machine = ложные алерты.

**Атомарный fix**
1. Сигнатуры: `run_checks(config, conn, user_id: str | None = None)`.
2. Если `user_id` задан — **все** call/reminder queries + `AND user_id=?`.
3. Call sites: watcher `_maybe_send_doctor_report`, dashboard `/api/health-report`, CLI `doctor` — передавать active user (`me` / args).
4. Если multi-user scan нужен — явный mode `all_users=True` + per-user sections в message (не смешивать ids).
5. Тесты: seed 2 users, stuck only on B → check for A is OK.

**DoD:** doctor для `me` не видит чужие call_id.

---

### F-05 · P1 · CONFIRMED — admin `status` CLI: global COUNT без user isolation

**Где**  
`cli/commands/admin.py` ~249:  
`SELECT status, COUNT(*) FROM calls GROUP BY status` — без user_id.  
`get_pending_calls()` / `get_error_calls()` могут быть global (см. repository signatures).

**Почему / к чему**  
Та же multi-user путаница в ops; не security hole на single-operator box, но нарушает инвариант и путает debug.

**Атомарный fix**
1. Добавить `--user` (default `me`) в status command.
2. Все COUNT/lists: `AND user_id=?`.
3. `get_stalled_calls(user_id=...)` / `get_error_calls(..., user_id=...)` — всегда передавать user из CLI.

---

### F-06 · P1 · CONFIRMED — `_unload_models` глотает ошибки unload

**Где**  
`orchestrator.py` `_unload_models` (~618–627):  
`except Exception: pass` на pyannote и ASR unload.

**Почему**  
CONSTITUTION 6.4 / pipeline: errors must log. Silent unload failure → VRAM not freed → **OOM** на LLM phase (Hard Constraint history 2026-06-06).

**Атомарный fix**
```python
except Exception as exc:
    logger.warning("unload pyannote failed: %s", exc, exc_info=True)
```
(и то же для ASR). Не raise — pipeline continues, но WARNING обязателен.

**Тест:** mock unload raises → assert warning logged; process continues.

---

### F-07 · P1 · CONFIRMED (partial) — dashboard risk colors hardcode 30/60 vs card 30/70 + risk_thresholds

**Где**  
`dashboard/static/app.js` — множество мест: `risk >= 60` / `>= 30` (calls list, dossier, entities…).  
`db_reader.py` ~313, ~452 — server-side class thresholds.  
Cards: calibrated `risk_thresholds` (p50/p85).

**Почему**  
Три шкалы: card calibrated, app.js 30/60, some code 30/70. decisions.md A4: dashboard cleanup **отложен**.

**К чему**  
Строка «жёлтая» в UI, 🟢 на Android-карточке — недоверие.

**Атомарный fix**
1. API: `/api/overview` или `/api/person` отдаёт `risk_thresholds: {green_max, yellow_max}` (из `get_latest_risk_thresholds`, fallback 30/70).
2. app.js: одна функция `riskClass(n, thr)` — как уже частично для BS (`thr.green_max` ~1076).
3. Заменить все литералы 60/30 risk-class на `riskClass`.
4. db_reader server-side labels — same thr.
5. Тест: mock thresholds 20/50 → class boundaries change.

**DoD:** один источник порогов risk на всех поверхностях.

---

### F-08 · P1 · CONFIRMED — biography `data_extractor` SELECT entity without user_id

**Где**  
`biography/data_extractor.py` ~35: `SELECT * FROM entities WHERE id=?`  
(затем берёт user_id из row). Сравнить: `psychology_profiler.py` делает `WHERE id=? AND user_id=?`.

**Почему**  
Id collision across users theoretically; CONSTITUTION isolation; defense-in-depth.

**Атомарный fix**  
Требовать `user_id` в API `extract_*(conn, entity_id, user_id)` и SQL `WHERE id=? AND user_id=?`.  
Call sites — передать user_id.  
Тест: entity id exists for other user → empty/denied.

---

### F-09 · P2 · CONFIRMED — `events/event_bus.py` dead for cross-process + `asyncio.run` poison

**Где**  
`events/event_bus.py` `emit_event_sync` → `asyncio.run(_broadcast)` when no loop.  
Dashboard SSE реально: DB poller `MAX(updated_at)` (server.py comments ~60–63).  
`emit_event_sync` почти не wired из orchestrator.

**Почему**  
Дублирующий канал; `asyncio.run` закрывает loop → aggravates F-02; false sense of real-time.

**Атомарный fix**
1. **Minimal:** document as dead; delete call sites if any; make `emit_event_sync` no-op logger.debug (or remove module from exports).
2. **Do not** wire emit into orchestrator without design — poller is correct for multi-process.
3. If keep for in-process tests — never use `asyncio.run` from pipeline thread; only `call_soon_threadsafe` to dashboard loop (complex; YAGNI).

---

### F-10 · P2 · CONFIRMED — LLMClient init always hits live HTTP «test» completion

**Где**  
`analyze/llm_client.py` `_verify_connection` (~90–115): POST real chat completion max_tokens=10 at construct time.

**Почему**  
- Медленный/хрупкий import path (biography/bulk create client).  
- Тратит GPU tokens.  
- При занятом server / cold start — ConnectionError валит весь batch start, хотя retry в `complete()` уже есть.

**Атомарный fix**
1. Replace with lightweight GET/HEAD health if llama-server supports (`/health` or `/v1/models`); else optional `verify=False` default for cache-only paths.
2. Or: lazy verify on first `complete()`, not `__init__`.
3. Keep fail-fast only for CLI commands that require live LLM (`bulk-enrich`, `biography-run`).

---

### F-11 · P2 · CONFIRMED — single shared SQLite connection `check_same_thread=False`

**Где**  
`db/repository.py` `_get_conn` (~25–33): one long-lived conn, `check_same_thread=False`, WAL.

**Почему**  
Watcher + ThreadPoolExecutor(ffmpeg) + dashboard tools write may share Repository instance. SQLite allows concurrent readers; concurrent writers on same conn from multiple threads → intermittent `database is locked` / corruption risk under load.

**Атомарный fix (осторожно, T2+)**
1. Short-term: document «one writer thread owns repo»; ffmpeg pool only I/O, no DB.
2. Medium: `threading.local()` conn per thread OR connect-per-operation with busy_timeout.
3. Never share Repository conn across processes.
4. Test under concurrent write stress (optional).

---

### F-12 · P2 · CONFIRMED — dashboard tools / import write paths without auth

**Где**  
`dashboard/server.py`: POST `/api/tools/*`, import-audio, contact-note, fact-verdict, user select — no auth middleware.  
Assumption: localhost single operator (CONSTITUTION local-only).

**Почему**  
If dashboard bound `0.0.0.0` or exposed via tunnel — anyone can inject audio, retry, rewrite notes.

**Атомарный fix**
1. Bind default `127.0.0.1` only (verify CLI `dashboard` host).
2. Optional: shared secret header from env `DASHBOARD_TOKEN` for mutating routes.
3. Log all tools mutations with user_id.
4. Document in README: never expose port 8765 publicly.

---

### F-13 · P2 · CONFIRMED — `get_stalled_calls()` / `process_pending` without user_id by default

**Где**  
`orchestrator.process_pending` → `get_stalled_calls()` no arg → all users.  
OK for single-profile `me`; multi-user machine processes everyone’s stalled in one batch (may be intentional).

**Fix**  
If product is single-profile: pass `user_id=me` from watcher for clarity.  
If multi: keep global but document; GPU batch should group by user for path isolation.

---

### F-14 · P2 · UNVERIFIED/BOX — contact_summaries on real box may predate dual-key

**Связано с F-01.**  
После dual-key write, old rows still only `payload`. UI dual-read covers; optional backfill script.

**Box check:**  
`SELECT open_promises FROM contact_summaries WHERE user_id='me' LIMIT 5;`  
If only `payload` — F-01 UI dual-read is mandatory before rebuild.

---

### F-15 · P2 · CONFIRMED — card text ≤512 bytes truncation

**Где**  
`deliver/card_generator.py` (Android overlay limit). Known IDEA bugs.md.

**Impact**  
Long advice/grade lines cut silently.

**Fix (optional P3 if no user pain)**  
Priority-trim: grade + risk + top 1 promise first; then hook; drop lower bullets. Unit test length ≤512 UTF-8 bytes.

---

### F-16 · P3 · BACKLOG — Telegram no durable queue

**Где**  
bugs.md: bot process death → lost notifications.

**Fix (later)**  
Table `outbox_messages` or file queue; bot drain on start. Out of scope unless user prioritizes.

---

### F-17 · P3 — style / maintainability (batch, not one PR each)

| Item | Location | Fix recipe |
|------|----------|------------|
| Huge modules | `db_reader.py` ~1800+, `app.js`, biography | Split readers by domain when next feature touches file |
| `OllamaClient = LLMClient` alias | llm_client.py | Deprecate; grep+remove if unused |
| CLI print() | cli/commands/* | OK for CLI UX; production modules must use logger (already mostly clean) |
| Duplicate risk threshold literals | app.js ×8 | Covered by F-07 |
| `on_event("startup")` FastAPI deprecated | server.py | Migrate lifespan context when next FastAPI bump |

---

### F-18 · P1 · CONFIRMED — id-space / bio_behavior_patterns (already fixed pattern — guard for regressions)

**Context**  
bugs.md 2026-07-02: do not re-read `bio_behavior_patterns` by graph entity_id.  
`get_character_profile` must use PsychologyProfiler patterns.

**Agent rule**  
Any new dashboard query to `bio_*` must: (1) `_has_table`, (2) join by **name**/`bio_scene_entities`, never assume id equality with graph entities or contacts.

**Regression tests already exist** — do not delete `test_character_patterns_ignore_colliding_bio_behavior_patterns_row`.

---

### F-19 · P2 · CONFIRMED — summary_builder vs card_generator dual card paths

**Где**  
Two generators of human-facing risk/bullets; drift (F-03).

**Fix**  
Shared `format_risk_emoji(user_id, risk, conn)` in `insight/risk_calibration.py`; both import.  
YAGNI full merge of card formats — only risk emoji + open_promises key schema (F-01).

---

### F-20 · P2 · Architecture — graph ≠ biography ≠ contact id spaces

**Где**  
Documented in `.claude/rules/dashboard.md` / graph.md. Still footgun for new code.

**Problem**  
`contact_id` ≠ `entities.id` ≠ `bio_entities.entity_id`. Link = `entity_contact_map` or name match.

**Agent rule when adding features**
1. Prefer `entity_contact_map` (confidence ≥ 0.6).
2. Never JOIN `bio_entities.entity_id = entities.id`.
3. Add `_has_table` guards for optional layers.

---

## 4. Atomic remediation roadmap (ordered)

Execute as small vertical slices; each: tests → CHANGELOG → commit (project rules).

### Slice 0 — Contract smoke (0.5 day)
| Step | Action | Finding |
|------|--------|---------|
| 0.1 | Grep `payload`/`what` in summary_builder + app.js; confirm F-01 still present | F-01 |
| 0.2 | Grep `BSCalibrator` in summary_builder; confirm F-03 | F-03 |
| 0.3 | Grep `get_event_loop().run_until_complete` without RuntimeError in orchestrator | F-02 |

### Slice 1 — Silent data contracts (P0) **← start here**
| Step | Action | Files |
|------|--------|-------|
| 1.1 | Dual-key write `what`+`payload`, `due`+`deadline` in summary_builder extractors | `aggregate/summary_builder.py` |
| 1.2 | Dual-read in `promiseItemHtml` and entity promise render | `dashboard/static/app.js` |
| 1.3 | Unit tests dual-key + render | `tests/` |
| 1.4 | Rebuild one contact summary in test DB; assert UI keys | — |

### Slice 2 — Runtime fragility (P0/P1)
| Step | Action | Files |
|------|--------|-------|
| 2.1 | `_run_coro` helper; wire note + summary notify | `orchestrator.py` |
| 2.2 | Log unload failures (no bare pass) | `orchestrator.py` |
| 2.3 | Tests for note notify without loop | `tests/test_orchestrator_*.py` |

### Slice 3 — Risk scale consistency (P1)
| Step | Action | Files |
|------|--------|-------|
| 3.1 | summary_builder → risk_thresholds (copy card_generator) | `summary_builder.py` |
| 3.2 | Optional: extract shared helper | `insight/risk_calibration.py` |
| 3.3 | Dashboard thr API + app.js `riskClass` | `db_reader.py`, `server.py`, `app.js` |
| 3.4 | Tests calibrated emoji + UI class | `tests/` |

### Slice 4 — user_id isolation (P1)
| Step | Action | Files |
|------|--------|-------|
| 4.1 | doctor checks take user_id | `doctor.py`, watcher, dashboard health, CLI |
| 4.2 | admin status --user | `cli/commands/admin.py` |
| 4.3 | biography data_extractor AND user_id | `data_extractor.py` + callers |
| 4.4 | Multi-user isolation tests | `tests/` |

### Slice 5 — LLM / dead code / ops (P2)
| Step | Action | Files |
|------|--------|-------|
| 5.1 | Lazy or health-check LLM verify | `llm_client.py` |
| 5.2 | event_bus no-op or remove asyncio.run path | `events/event_bus.py` |
| 5.3 | Dashboard bind 127.0.0.1 + document | CLI dashboard, README |
| 5.4 | Conn-per-thread design note / optional impl | `repository.py` |

### Slice 6 — Backlog (P3)
| Step | Action |
|------|--------|
| 6.1 | Card 512-byte priority trim |
| 6.2 | Telegram outbox queue |
| 6.3 | Split oversized modules when next feature touches them |

---

## 5. Per-finding fix template (copy for PR)

```markdown
## Fix: F-XX
- Severity: P?
- Files:
- Steps: (numbered)
- Tests:
- CONSTITUTION check: user_id / GPU / no forbidden stack
- CHANGELOG + CONTINUITY
```

---

## 6. Anti-patterns while fixing

1. **Do not** merge bio_entities ids with graph entities ids.  
2. **Do not** load ASR+LLM concurrent (VRAM).  
3. **Do not** `except: pass` on GPU unload or file delete without log.  
4. **Do not** change `PROMPT_VERSION` without cache invalidation awareness.  
5. **Do not** rewrite risk to use BS thresholds again (A4 regression).  
6. **Do not** fix F-01 only in UI or only in writer — **both**.  
7. **Do not** implement Docker/Redis/ORM «for scale».

---

## 7. Suggested regression test map

| Finding | Test idea |
|---------|-----------|
| F-01 | `test_open_promises_payload_renders_as_what` |
| F-02 | `test_finalize_note_notify_without_running_loop` |
| F-03 | `test_summary_risk_emoji_uses_risk_thresholds_not_bs` |
| F-04 | `test_doctor_queue_stuck_scoped_to_user` |
| F-06 | `test_unload_models_logs_failure` |
| F-07 | `test_risk_class_uses_api_thresholds` |
| F-08 | `test_data_extractor_requires_user_id` |

---

## 8. Priority matrix (executive)

| ID | Sev | Layer | Confirmed | Effort |
|----|-----|-------|-----------|--------|
| F-01 | P0 | aggregate+dashboard | yes | S |
| F-02 | P0 | pipeline | yes | S |
| F-03 | P1 | aggregate | yes | S |
| F-04 | P1 | doctor | yes | M |
| F-05 | P1 | CLI admin | yes | S |
| F-06 | P1 | pipeline GPU | yes | S |
| F-07 | P1 | dashboard UI | yes | M |
| F-08 | P1 | biography | yes | S |
| F-09 | P2 | events | yes | S |
| F-10 | P2 | LLM | yes | S |
| F-11 | P2 | db | yes | L |
| F-12 | P2 | security | yes | M |
| F-13 | P2 | pipeline | yes | S |
| F-14 | P2 | data | box | S |
| F-15–17 | P3 | deliver/UX | mixed | — |
| F-18–20 | P1/P2 | architecture | guards | ongoing |

**Recommended first PR:** Slice 1 (F-01) + Slice 2 (F-02, F-06) — max user impact, small blast radius.

---

## 9. Verification of this document

Agents verifying NeErrorsGR.md:
1. File at repo root UTF-8.
2. Spot-check ≥5 findings: paths exist, defect still present or marked resolved after fix.
3. Layers covered: pipeline, db/doctor, dashboard, aggregate/contracts, biography/graph notes.
4. Roadmap ordered; each finding has numbered steps.

---

*End of NeErrorsGR.md — apply slices top-down; do not re-derive root causes already listed.*
