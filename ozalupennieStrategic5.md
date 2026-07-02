# ozalupennieStrategic5.md — Исполнение STRATEGIC_PLAN_v5 (портфель Ф0 → Ф-A → Ф-B → Ф-C → Ф-D)

> **Для кого:** Claude Code (Sonnet), исполняющий агент. Источник целей: `STRATEGIC_PLAN_v5.md`
> (читать §1-§9 перед стартом). Карты слоёв: `.claude/rules/{insight,dashboard,graph,db,llm,pipeline}.md`.
> **Что это:** атомарная декомпозиция портфеля A1-A6, B1-B8, C1/C3, D1-D3 + гейты качества §7.
> Все сигнатуры/схемы/якоря ниже ПРОВЕРЕНЫ по коду 2026-07-02 — не переизобретать, использовать как написано.
> **Правило исполнения:** задачи строго по порядку. Каждая задача самодостаточна; не додумывать
> сверх написанного; сомнение → СТОП и вопрос, не импровизация. После КАЖДОЙ задачи:
> `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q` зелёный →
> строка в `CHANGELOG.md` → `git commit` → `git push origin main`.

---

## 0. Глобальные инварианты (нарушение любого = провал задачи)

1. **Каждый** SELECT/UPDATE/DELETE: `WHERE user_id = ?`. Каждый UPSERT: guard
   `WHERE user_id = excluded.user_id` (образец: `insight/repository.py`).
2. Никаких новых pip-зависимостей. Только stdlib + numpy + requests (+ существующие).
   Никаких sklearn/scipy/эмбеддингов/векторных БД (отвергнуто, STRATEGIC_PLAN §5).
3. **Дашборд** = чистый read (`PRAGMA query_only=ON`): НИКОГДА не зовёт LLM, НИКОГДА не пишет в БД.
   Каждый новый читатель db_reader guarded `_has_table`/`_has_column` — слоя нет → пустая секция, не 500.
4. **LLM** = llama-server `http://127.0.0.1:8080/v1/chat/completions`, `requests.post()` напрямую,
   timeout 120. LLM-вызовы ТОЛЬКО из CLI-команд (LLM-окно), никогда из watcher/dashboard.
   Каждый LLM-вызов мемоизирован (hash в строке таблицы — паттерн `insight/age_estimate.py`).
   Сервер недоступен → понятная ошибка + exit 2, НЕ ретрай-луп.
5. Сигнал от `speaker='UNKNOWN'` НИКОГДА не атрибутируется человеку. Реплики контакта = `OTHER`,
   владельца = `OWNER`.
6. Каждое видимое пользователю утверждение: цитата+дата ИЛИ confidence-гейт — иначе не показывается.
   ≤300 символов на элемент. Не показывать количество звонков / длительности в user-facing тексте
   (количество обещаний/долгов — можно).
7. Тесты офлайн (mock LLM, temp-SQLite из `db/schema.sql`), без GPU/ffmpeg/реальной БД.
   Реальный прогон = «проверка на боксе», отмечено в задаче.
8. Новые фичи-оси — контракт `Feature(value, support_n, tier)` (`insight/features/base.py`),
   z-score внутри популяции юзера, тир-веса IMMUNE 1.0 / ROBUST 0.8 / AFFECTIVE 0.6 / FRAGILE 0.4.
9. Схема: только аддитивные `CREATE TABLE IF NOT EXISTS` / idempotent ALTER через `_MIGRATIONS`-паттерн
   `insight/repository.apply_insight_schema`. Существующие таблицы не пересоздавать. Обновлять schema-док.
10. **Запретная зона для этого плана (T3-гейты, СТОП при касании):** `configs/prompts/analyze_v001.txt`
    и его `PROMPT_VERSION` (инвалидация кэша 16k!), GPU-порядок/orchestrator/watcher, пути удаления
    файлов (reset/cleanup), терминальные статусы и resume, `bs_thresholds` (на ней graph-health).
    Задача требует их тронуть → остановиться и доложить, НЕ делать.
11. Коммиты: `feat|fix|docs(scope): ...`, push в `main`. Память: строка в CHANGELOG после каждой
    задачи; `.claude/rules/insight.md`/`dashboard.md` обновлять при изменении слоя (кратко, только неочевидное).

---

## 1. Проверенные якоря кодовой базы (карта для реюза — НЕ переписывать эти функции)

| Что | Где | Сигнатура / факт |
|---|---|---|
| FTS5-поиск | `db/repository.py:796` | `search_transcripts(self, user_id, query, limit=50)` — phrase-MATCH; для ask нужен СВОЙ OR-запрос (задача A2) |
| Feedback write | `db/repository.py:935` | `set_feedback(self, analysis_id, feedback)`; значения `'ok'` / `'inaccurate'` (`deliver/telegram_bot.py:186`) |
| Feedback кнопки | `deliver/telegram_bot.py:163` | `handle_feedback` — **БАГ: строка ~191 использует несуществующую `user_id` → NameError** (задача 0.2) |
| Отправка в TG | `deliver/telegram_bot.py:55` | `send_summary` — async, требует запущенный app; для one-shot CLI слать через `requests.post` Bot API (задача A1) |
| events write | `db/repository.py:1078` | `save_events(call_id, events)`; колонки events: `user_id, contact_id, call_id, event_type('promise','debt',...), who('OWNER','OTHER','UNKNOWN'), payload, source_quote, confidence, deadline, status('open','fulfilled','broken','expired','resolved')` |
| promises DDL | `db/schema.sql:79` | `promises(promise_id, user_id, contact_id, call_id, who, what, due, status='open')` |
| transcripts DDL | `db/schema.sql:47` | `transcripts(segment_id, call_id, start_ms, end_ms, text, speaker)` |
| analyses DDL | `db/schema.sql:56` | есть `feedback TEXT`, `risk_score`, `priority`, `key_topics`, `call_type`, `profanity_density` |
| contact_summaries | `db/schema.sql:231` | `total_calls, last_call_date, global_risk, top_hook, open_promises(JSON), open_debts(JSON), personal_facts(JSON), contact_role, advice` |
| Роутер фич | `insight/feature_store.py` | `_META_FNS/_TEXT_FNS/_AFFECTIVE_FNS` (tuple compute-fn); `build_contact_features(conn, user_id, feature_fns=None, reference_now=None)`; сегменты сейчас `SELECT t.speaker, t.text` (B1 расширяет); `assemble_matrix(per_contact_features, support_floor=2)`; `standardize(X, col_weights)` |
| Метки осей | `insight/labels.py:7` | `FEATURE_LABELS = {name: (краткое, фраза_high, фраза_low)}`; helper `label(name, z, thr)` |
| BS-калибровка | `graph/calibration.py` | `BSCalibrator.calibrate(user_id)` → перцентили p25/p50/p75/p90 → `save_bs_thresholds`; `get_label(bs_index, user_id) -> (label, emoji)`; labels: reliable/noisy/risky/unreliable/uncalibrated |
| bs_thresholds DDL | `graph/repository.py:205` | append-only: `user_id, reliable_max, noisy_max, risky_max, unreliable_max, entity_count, std_dev, created_at`; читается `get_latest_bs_thresholds`. **НЕ ТРОГАТЬ** (граф-health) |
| Карточка | `deliver/card_generator.py:139` | `generate_card(user_id, contact_id) -> str` (key:value строки, `MAX_CARD_BYTES=512`, `_truncate_bytes`); `write_card(...)` в `{phone}.txt`; `_risk_emoji_with_calibration(risk, user_id)` — **семантический баг: применяет BS-пороги к risk-шкале** (задача A4) |
| CLI-регистрация | `cli/main.py:~575,~660-680` | `sub.add_parser("age-style", ...)` + dict `COMMANDS = {"age-style": cmd_age_style, ...}`; обёртки в `cli/commands/insight.py` (паттерн: load_config → sqlite3.connect → run → print → return 0) |
| insight-схема | `insight/repository.py` | `apply_insight_schema(conn)` idempotent + `_MIGRATIONS`-dict (ALTER-донакат); UPSERT-guard образец там же; `entity_contact_map(user_id, entity_id, contact_id, method, confidence)` |
| LLM-паттерн | `insight/age_estimate.py` | requests.post + парсер `<think>`/fences + verbatim-гейт цитат + memo `sha1(prompt+PROMPT_VERSION)` per-row. Копировать ЭТОТ паттерн для всех новых LLM-пассов |
| age_style | `insight/age_style/estimate_style.py` | `run_style_estimate(conn, user_id, *, reference_now=None, stale_only=False) -> stats`; лексикон-лоадер с `=`-точным матчем (`age_style/lexicons.py`, после fixager Ф1) |
| Психопрофайлер | `biography/psychology_profiler.py` | `build_profile(entity_id, user_id, include_llm=False)` — live-расчёт, ничего не персистит |
| Досье | `dashboard/db_reader.py` | `get_person_dossier(contact_id)` — агрегатор секций, все guarded; рендер `static/app.js` → `openPersonDossier`/`renderDossier`; RU-словарь `dashboard/labels_ru.py::localize_dossier` (in-place, идемпотентно) |
| Тул-эндпоинты | `dashboard/server.py`, `dashboard/tools.py` | образец: `POST /api/tools/age-recompute?contact_id=` → sync-метод в tools.py в threadpool, без GPU/LLM |
| Тест-фикстуры | `tests/insight/test_age_style_estimate.py` | temp-SQLite из `db/schema.sql` + `apply_insight_schema`; синт-корпус `insight/synth/corpus.py` (`SyntheticCorpus`) для ground-truth |
| Конфиг | `config.py` | `load_config()`; `owner_birth_year` (default 0); `TELEGRAM_BOT_TOKEN` из env |
| bio-таблицы | `biography/schema.py` | `bio_scenes(call_datetime, importance, scene_type, synopsis, key_quote, ...)`, `bio_arcs(title, arc_type, start_date, end_date, status, synopsis, importance, ...)`, `bio_portraits(entity_id, prose, traits, pivotal_scenes, ...)`. Перед SELECT сверить `PRAGMA table_info` — биографии на боксе может не быть, всё guarded |

Перед каждой правкой файла: `codegraph_search` затронутого символа (если codegraph-тулы доступны),
иначе Grep якоря из таблицы. Якорь не найден → СТОП, доложить (код мог уехать).

---

## Ф0 — Качество прежде фич (порядок принципиален, STRATEGIC_PLAN §7)

### Задача 0.1 — Гейт: fixager.md исполнен *(проверка, кода нет)*

- [ ] Проверить: `Grep "RULES_VERSION" src/callprofiler/insight/age_style/` — версия v2 и тесты
  `tests/insight/test_age_lexicons_fp.py` существуют → fixager.md исполнен, идти дальше.
- [ ] Если НЕ исполнен: остановиться, исполнить `fixager.md` (отдельный план, 6 фаз) ЦЕЛИКОМ, затем вернуться сюда.

### Задача 0.2 — A5: замкнуть feedback-петлю *(T2: баг + потребитель поля)*

**Цель:** кнопки [OK]/[Неточно] реально пишут `analyses.feedback`; поле потребляется досье и калибровкой.

**Файлы:** Modify: `deliver/telegram_bot.py`, `dashboard/db_reader.py`, `static/app.js`.
Test: `tests/test_feedback_loop.py` (новый), дополнение `tests/test_dashboard_dossier.py`.

1. **Фикс NameError.** В `handle_feedback` (`telegram_bot.py:163`) переменная `user_id` не определена
   (строка `analysis = self.repo.get_analysis(user_id, call_id)`). Фикс: в начале функции
   `user_id = self._get_user_id(update)`; если `None` → `await query.edit_message_text(text="❌ Не найден ваш user_id"); return`.
2. **Читатель в досье.** `db_reader.py`: в `get_person_dossier` добавить ключ `feedback` (guarded
   `_has_column("analyses", "feedback")`):
   ```sql
   SELECT SUM(CASE WHEN a.feedback='inaccurate' THEN 1 ELSE 0 END) AS wrong_n,
          SUM(CASE WHEN a.feedback='ok' THEN 1 ELSE 0 END) AS ok_n,
          MAX(CASE WHEN a.feedback='inaccurate' THEN c.call_datetime END) AS last_wrong
     FROM analyses a JOIN calls c ON c.call_id = a.call_id
    WHERE c.user_id = ? AND c.contact_id = ?
   ```
   Возвращать `{"wrong_n":…, "ok_n":…, "last_wrong":…}`.
3. **Бейдж.** `app.js::renderDossier`: если `d.feedback && d.feedback.wrong_n > 0` — под шапкой строка
   (muted, оранжевый): `«Сводки этого контакта помечались как неверные (последний раз: <дата>) — доверие к автоматике снижено»`.
4. **Тесты.** `tests/test_feedback_loop.py`:
   - `test_handle_feedback_writes_analyses_feedback` — фейковые update/context (SimpleNamespace,
     `query.answer`/`edit_message_text` = AsyncMock), `_get_user_id` замокан → после вызова
     `analyses.feedback == 'inaccurate'` в temp-БД. (До фикса тест падает NameError — написать СНАЧАЛА.)
   - `test_dossier_feedback_badge_data` (в test_dashboard_dossier.py) — сеем analysis с feedback='inaccurate'
     → в ответе `/api/person/{cid}` ключ `feedback.wrong_n == 1`; БД без колонки → ключ отсутствует, не 500.

**DoD:** оба теста зелёные, полный pytest зелёный. Commit: `fix(feedback): close A5 loop — NameError in handle_feedback + dossier badge`.

### Задача 0.3 — Спот-чек-сэмплер *(T1; §7.3 — «замер» по Ст.2.3)*

**Цель:** CLI выгружает случайную стратифицированную выборку для РУЧНОЙ проверки владельцем (WER/роли/обещания).

**Файлы:** Create: `src/callprofiler/insight/spotcheck.py`; Modify: `cli/main.py`, `cli/commands/insight.py`.
Test: `tests/insight/test_spotcheck.py`.

1. `spotcheck.py`:
   ```python
   def build_spotcheck(conn, user_id: str, n: int = 25, seed: int = 0) -> str:
       """Markdown: n случайных done-звонков, стратифицированных по длительности
       (короткие <60s / средние / длинные >600s — поровну). Для каждого: call_id,
       дата, контакт, audio_path, транскрипт с ролями, summary/risk/promises из analyses,
       и чек-лист: - [ ] текст верен  - [ ] роли верны  - [ ] обещания верны."""
   ```
   SQL: `SELECT ... FROM calls WHERE user_id=? AND status IN ('done','transcribed')`; выборка
   `random.Random(seed).sample` внутри страт. Транскрипт: `SELECT speaker, text FROM transcripts ... ORDER BY start_ms`,
   строки `[OWNER]/[OTHER]/[?]: текст`.
2. CLI `spotcheck-sample --user X [--n 25] [--out PATH]` (default out `C:\calls\spotcheck.md`),
   обёртка в `cli/commands/insight.py` по паттерну `cmd_age_style`, регистрация в `COMMANDS`.
3. Тест: temp-БД, 9 звонков трёх длительностей с транскриптами → markdown содержит 9 секций,
   каждая с `- [ ]` чек-листом и ролями; повторный вызов с тем же seed → идентичный вывод.

**DoD:** тест зелёный. Прогон на боксе — вручную владельцем (вне плана). Commit: `feat(insight): spotcheck-sample CLI for manual WER/roles audit`.

### Задача 0.4 — role-UNKNOWN% на вкладке System *(T1; §7.4 master-gate FRAGILE)*

**Файлы:** Modify: `dashboard/db_reader.py` (метод get_system/stats — найти Grep `def get_system`), `static/app.js` (System tab).
Test: дополнение `tests/test_dashboard_*` (файл с system-тестами — найти Grep `api/system` в tests/).

1. db_reader: метод `get_role_unknown_share(days: int = 30) -> dict`:
   ```sql
   SELECT AVG(CASE WHEN t.speaker='UNKNOWN' THEN 1.0 ELSE 0.0 END) AS share, COUNT(*) AS n
     FROM transcripts t JOIN calls c ON c.call_id = t.call_id
    WHERE c.user_id = ? AND c.created_at >= datetime('now', ?)
   ```
   (`?` = `f"-{days} days"`). Кэшировать в атрибуте `(monotonic, value)` c TTL 60s — SSE-тик каждые 2s,
   полный скан 660k строк на каждый тик недопустим. Включить в ответ `/api/system`.
2. app.js System tab: строка `Роли: X% UNKNOWN за 30 дней — мастер-гейт FRAGILE-сигналов` (красным при >40%).
3. Тест: сеем 3 сегмента UNKNOWN + 1 OWNER → share 0.75 в `/api/system`.

**DoD:** тест зелёный. Commit: `feat(dashboard): role-UNKNOWN% master-gate metric on System tab`.

---

## Ф-A — Доставить уже добытое

### Задача A1 — Леджер обязательств + Telegram-дайджест *(T2)*

**Цель:** еженедельный push: просроченные обещания/долги В ОБЕ стороны, каждая строка с цитатой и датой.

**Файлы:** Create: `src/callprofiler/deliver/digest.py`; Modify: `cli/main.py`, новый `cli/commands/deliver.py`.
Test: `tests/test_digest.py`.

**Интерфейсы (Produces — используется A6, C3, D1, D3):**
```python
# deliver/digest.py
def overdue_items(conn, user_id: str, today: str | None = None) -> list[dict]:
    """Каждый item: {side: 'owner'|'contact', contact_id, contact_name, what,
    deadline, call_date, quote, origin: 'events'|'promises', days_overdue}."""
def open_items(conn, user_id: str, today=None) -> list[dict]      # то же, deadline >= today или NULL
def build_digest(conn, user_id: str, today=None,
                 extra_sections: list[tuple[str, list[str]]] | None = None) -> str
def send_telegram(text: str, chat_id: str, token: str) -> bool     # requests.post Bot API sendMessage, parse_mode=HTML
```

1. **Источники** (UNION, оба существуют — якоря §1):
   - `events`: `WHERE user_id=? AND event_type IN ('promise','debt') AND status='open' AND deadline IS NOT NULL`
     → what=`payload`, quote=`source_quote`, side: `who='OWNER'`→'owner', `'OTHER'`→'contact'
     (`who='UNKNOWN'` — ПРОПУСКАТЬ, инвариант 5).
   - `promises`: `WHERE user_id=? AND status='open' AND due IS NOT NULL` → what=`what`, quote=NULL,
     side по `who` (значения посмотреть в данных: Grep запись `save_batch` в `db/repository.py:947+`;
     эвристика: `who` содержит 'me'/'OWNER' → owner, иначе contact).
   - call_date: JOIN calls по call_id → `date(call_datetime)`. contact_name: JOIN contacts,
     `COALESCE(display_name, guessed_name, phone_e164, '?')`.
   - Дедуп UNION: ключ `(call_id, lower(what)[:40])`, events приоритетнее (у них цитата).
   - `days_overdue = (date(today) - date(deadline)).days`; overdue = `deadline < today`.
   - Статусы в БД НЕ мутировать (переходы статусов — слой B3, дайджест только показывает).
2. **build_digest** — HTML для Telegram, секции (пустые не выводить):
   ```
   📋 <b>Обязательства на неделю</b>

   🔴 Просрочено ИМИ:
   • <контакт>: <what ≤120> — обещано <call_date>, срок <deadline>
     «<quote ≤120>»
   🟠 Просрочено ВАМИ:
   • ... (side='owner')
   🗓 Открытые со сроком на 14 дней: ...
   ```
   Топ-10 на секцию по days_overdue. Каждая строка ≤300 симв. `extra_sections` — крючок для C3/D1
   (список (заголовок, строки)); просто дописываются в конец.
3. **CLI** `digest --user X [--send] [--out PATH]`: build → print (или в файл); `--send` →
   `send_telegram(text, users.telegram_chat_id, os.environ['TELEGRAM_BOT_TOKEN'])`; нет chat_id/token →
   понятная ошибка exit 2. ВНИМАНИЕ: имя `digest` в COMMANDS может конфликтовать — проверить dict;
   если занято (бот-команда — нет, но проверь), назвать `weekly-digest`.
4. **Расписание:** файл `digest.bat` в корне проекта (по образцу существующих .bat, ASCII без BOM):
   `python -m callprofiler digest --user me --send` + строка в README-комментарии: регистрация в
   Windows Task Scheduler еженедельно (вручную владельцем).
5. **Тесты** (`tests/test_digest.py`, фикстура-паттерн из `tests/insight/test_age_style_estimate.py`):
   - `test_overdue_bucketing`: events с deadline вчера (who=OTHER), завтра (OTHER), вчера (OWNER),
     вчера (UNKNOWN) → overdue_items: 2 элемента (UNKNOWN отброшен), стороны верные.
   - `test_promises_and_events_dedup`: одинаковый what в promises и events по одному call_id → 1 item с цитатой.
   - `test_digest_contains_quote_and_date`: в тексте есть и цитата, и дата звонка, и дедлайн.
   - `test_user_isolation`: события чужого user_id не попадают.
   - `test_send_telegram_posts` — mock `requests.post` → вызван с chat_id/text.

**DoD:** тесты зелёные, полный pytest зелёный. Обновить `.claude/rules/dashboard.md`? — нет (не дашборд);
добавить 3 строки в `.claude/rules/insight.md`? — нет; создать раздел «Delivery» НЕ надо — одна строка в CHANGELOG.
Commit: `feat(deliver): obligations ledger + weekly telegram digest (A1)`.

### Задача A2 — `ask`: вопрос к архиву *(T2; LLM-окно)*

**Цель:** «что мы решили с гаражом?» → FTS5 top-k фрагментов → LLM-синтез, каждый факт со ссылкой [n] → детерминированные источники (контакт, дата).

**Файлы:** Create: `src/callprofiler/ask.py`, `configs/prompts/ask_v001.txt`; Modify: `cli/main.py`,
`cli/commands/insight.py` (или новый `cli/commands/ask.py`), `insight/repository.py` (таблица кэша).
Test: `tests/test_ask.py`.

**Схема** (добавить в `apply_insight_schema`, idempotent):
```sql
CREATE TABLE IF NOT EXISTS ask_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    question TEXT NOT NULL,
    prompt_hash TEXT NOT NULL UNIQUE,
    answer TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    prompt_version TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**Интерфейсы:**
```python
PROMPT_VERSION_ASK = "ask-v1"
def retrieve(conn, user_id: str, question: str, k: int = 8) -> list[dict]:
    """Фрагменты: {idx, call_id, contact_name, date, text}."""
def answer_question(conn, user_id: str, question: str, *, llm_url: str,
                    k: int = 8, timeout: int = 120) -> dict:
    """{answer, citations: [{n, contact, date, call_id}], from_cache: bool}"""
```

1. **retrieve:** токены вопроса `re.findall(r"[а-яёa-z0-9]{3,}", question.lower())` минус стоп-слова
   (мини-набор: что, как, когда, где, почему, мы, я, он, она, они, это, был, была, было, с, у, про, наш).
   FTS-выражение: каждый токен в кавычках (`"` внутри токена → `""`), соединить ` OR `.
   SQL — копия структуры `search_transcripts` (repository.py:796: подзапрос rowid+rank → JOIN transcripts →
   JOIN calls `WHERE c.user_id=?` → ORDER BY rank), LIMIT 40 хитов. Группировать по call_id (максимум 3
   звонка), для каждого хита добрать контекст: сегменты того же call с `ABS(start_ms - hit.start_ms) <= 45000`
   (≤5 сегментов), склеить в фрагмент `[{i}] {дата}, {контакт}:\n[OWNER/OTHER]: текст...` ≤700 симв.
   k фрагментов, суммарный клип 6000 симв. 0 токенов или 0 хитов → вернуть [].
2. **Промпт** `configs/prompts/ask_v001.txt`:
   ```
   Ты — архивный ассистент владельца телефонного архива. Тебе дан вопрос и пронумерованные
   фрагменты реальных разговоров. Отвечай ТОЛЬКО на основе фрагментов. Каждое утверждение
   помечай ссылкой на фрагмент в квадратных скобках: [1], [3]. Если во фрагментах нет ответа —
   напиши ровно: «В архиве не нашлось». Не выдумывай. Без рассуждений и преамбул. Ответ ≤ 120 слов, по-русски.

   ВОПРОС: {question}

   ФРАГМЕНТЫ:
   {fragments}
   ```
3. **answer_question:** фрагментов нет → `{"answer": "В архиве не нашлось", "citations": [], ...}` БЕЗ LLM.
   Иначе: prompt_hash = `hashlib.sha1((prompt + PROMPT_VERSION_ASK).encode("utf-8")).hexdigest()`;
   есть в ask_log (`WHERE user_id=? AND prompt_hash=?`) → вернуть из кэша. Нет → HTTP-вызов по паттерну
   `age_estimate.py` (тот же парсер `<think>`/fences; temperature 0.2, max_tokens 400). Цитирование
   ДЕТЕРМИНИРОВАННОЕ: из ответа собрать `re.findall(r"\[(\d+)\]", answer)` → citations по НАШИМ метаданным
   фрагментов (модельным цитатам не верим — verbatim-гейт не нужен, источники наши). Ссылок нет и ответ
   не «не нашлось» → перед ответом добавить строку `⚠ без ссылок на фрагменты — доверие снижено`.
   INSERT в ask_log. ConnectionError → `RuntimeError("llama-server недоступен — запустите LLM-окно")`.
4. **CLI** `ask --user X "вопрос текстом"`: print ответ + блок `Источники:` (`[n] контакт — дата`).
   llm_url из config (Grep `llm` в `config.py` — поле сервера уже есть для analyze; переиспользовать).
5. **Telegram** (опционально, если быстро): `/ask` command в telegram_bot по образцу `cmd_search`,
   зовёт `answer_question`; НЕ делать, если бот-архитектура требует >30 строк — CLI достаточно (YAGNI).
6. **Тесты** (LLM = mock `requests.post`):
   - `test_retrieve_finds_planted_fact`: сеем транскрипт «решили ставить гараж у забора» → retrieve(«что решили с гаражом») содержит фрагмент этого call.
   - `test_answer_citations_map_to_calls`: mock-ответ `Гараж у забора [1]` → citations[0].call_id = верный.
   - `test_cache_hit_no_second_llm_call`: два вызова → `requests.post` вызван 1 раз, from_cache=True.
   - `test_no_hits_no_llm`: вопрос без совпадений → «В архиве не нашлось», post не вызван.
   - `test_fts_quote_injection_safe`: вопрос с `"` и `MATCH` внутри → не падает.

**DoD:** тесты зелёные. В `.claude/rules/insight.md` добавить 5 строк секцию «ask» (таблица ask_log, версия промпта).
Commit: `feat(ask): question-answering over archive via FTS5+LLM with deterministic citations (A2)`.

### Задача A4 — Калибровка risk-порогов по корпусу *(T1-T2)*

**Цель:** risk-цвета из перцентилей 16k вместо 30/70 с потолка; заодно починить семантический баг
(BS-пороги применялись к risk в `card_generator._risk_emoji_with_calibration`).

**Файлы:** Create: `src/callprofiler/insight/risk_calibration.py`; Modify: `insight/repository.py`
(таблица), `deliver/card_generator.py`, `cli/main.py`+`cli/commands/insight.py`, `dashboard/db_reader.py`.
Test: `tests/insight/test_risk_calibration.py`.

**Схема** (в `apply_insight_schema`):
```sql
CREATE TABLE IF NOT EXISTS risk_thresholds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    green_max REAL NOT NULL,   -- p50 распределения risk_score
    yellow_max REAL NOT NULL,  -- p85
    analysis_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_risk_thresholds_user ON risk_thresholds(user_id, created_at);
```

1. `risk_calibration.py` (numpy):
   ```python
   def calibrate_risk(conn, user_id: str) -> dict:
       # risk_score всех analyses юзера, ИСКЛЮЧАЯ feedback='inaccurate' (вход A5!),
       # и risk_score > 0 (нули-заглушки коротких звонков не искажают перцентили)
       # < 50 значений -> {"ok": False, "reason": "too_few"} и НЕ писать
       # иначе INSERT (append-only, как bs_thresholds) green_max=p50, yellow_max=p85
   def get_latest_risk_thresholds(conn, user_id: str) -> dict | None
   def risk_emoji(risk: float, thresholds: dict | None) -> str:
       # None -> fallback: <30 🟢, <70 🟡, else 🔴 (нынешнее поведение)
   ```
2. `card_generator._risk_emoji_with_calibration`: заменить тело — вместо `BSCalibrator.get_label(risk,...)`
   читать `get_latest_risk_thresholds` (guarded try/except + `_has_table`-подобная проверка) → `risk_emoji`.
   BSCalibrator в карточке больше НЕ используется для risk (для BS остаётся где был).
3. `db_reader`: в `get_person_dossier` и `/api/people` уже есть risk — добавить ключ
   `risk_emoji` через тот же `risk_emoji(...)` (guarded), фронт красит по нему (app.js: заменить
   локальные пороги, Grep `70` в app.js рядом с risk — если найдено).
4. CLI `calibrate-risk --user X` → print перцентили и записанные пороги.
5. **Тесты:**
   - `test_percentiles_written`: 100 analyses risk 1..100 → green_max≈50, yellow_max≈85.
   - `test_wrong_feedback_excluded`: пометить топ-10 feedback='inaccurate' → yellow_max ниже.
   - `test_too_few_no_write`: 10 строк → ok=False, таблица пуста.
   - `test_emoji_fallback_without_thresholds`: None → старые 30/70.
   - `test_card_uses_calibrated`: пороги green_max=5 → risk 10 даёт 🟡 в generate_card.

**DoD:** тесты зелёные. Прогон `calibrate-risk --user me` — на боксе. Commit:
`feat(insight): risk threshold calibration from corpus percentiles; fix BS-thresholds misapplied to risk (A4)`.

### Задача A6 — Карточка v2 *(T1)*

**Цель:** + «лучшее время звонка» (IMMUNE), + Admiralty-грейд, + просрочки из A1. Бюджет 512 байт священен.

**Файлы:** Create: `src/callprofiler/insight/admiralty.py`, `src/callprofiler/insight/call_time.py`;
Modify: `deliver/card_generator.py`. Test: `tests/insight/test_admiralty.py`, `tests/test_card_v2.py`.

1. `call_time.py` — чистая функция:
   ```python
   def best_call_time(calls: list[dict]) -> str | None:
       """calls: [{call_datetime, duration_sec}]. Бакеты: будни-день(9-18)/будни-вечер(18-23)/
       выходные/ночь(23-7). Взвешивание: звонки за последние 180 дней ×2. Топ-бакет с долей
       >=0.45 и support >=8 звонков -> фраза ('будни днём'|'будни вечером'|'на выходных'|'ночью');
       иначе None (не показываем — инвариант 6)."""
   ```
2. `admiralty.py` — чистое отображение поверх метрик (STRATEGIC_PLAN §6):
   ```python
   SOURCE_PHRASES = {"A": "надёжен, слово держит", "B": "обычно надёжен", "C": "сигнал шумный",
                     "D": "бывали срывы", "E": "ненадёжен", "F": "данных мало"}
   INFO_PHRASES = {"2": "информация вероятно верна", "3": "информация возможно верна",
                   "4": "достоверность сомнительна", "6": "достоверность не оценить"}
   def source_grade(bs_label: str | None, kept_ratio: float | None = None, kept_n: int = 0) -> str:
       # kept_ratio>=0.8 и kept_n>=5 и bs_label=='reliable' -> 'A'   (kept_* появится в B3; до того None)
       # 'reliable'->'B', 'noisy'->'C', 'risky'->'D', 'unreliable'->'E', None/'uncalibrated'->'F'
   def info_grade(avg_confidence: float | None) -> str:
       # >=0.8->'2', >=0.6->'3', <0.6->'4', None->'6'   ('1'/'5' зарезервированы под C2)
   def grade_line(src: str, info: str) -> str:
       # f"{src}{info} — {SOURCE_PHRASES[src]}, {INFO_PHRASES[info]}"
   ```
   avg_confidence: `SELECT AVG(confidence) FROM events WHERE user_id=? AND contact_id=? AND created_at >= datetime('now','-180 days')`.
   bs_label: контакт → entity через `entity_contact_map` (top-confidence, guarded) → `BSCalibrator.get_label(bs_index, user_id)[0]`; пути нет → None.
3. `card_generator.generate_card`: после `risk:`-строки добавить (в порядке приоритета усечения —
   сначала режутся нижние):
   - `due: <краткое what ≤60> (просрочено N дн.)` — первый элемент `digest.overdue_items` этого контакта
     (импорт из A1; фильтр по contact_id);
   - `grade: B2 — обычно надёжен, информация вероятно верна` (admiralty);
   - `call: будни днём` (best_call_time; None → строка не пишется).
   Данные собрать через `self.repo._get_conn()` (паттерн уже в файле). Всё в try/except → карточка
   не падает никогда, деградирует до v1.
4. **Тесты:**
   - admiralty: табличные (`('reliable',None,0)->'B'`, `('reliable',0.9,6)->'A'`, `(None,...)->'F'`; info 0.85->'2', None->'6').
   - call_time: 20 будних дневных звонков → «будни днём»; 5 звонков → None (support-гейт).
   - card v2: сеем overdue event + пороги → карточка содержит `due:` и `grade:`, длина ≤512 байт;
     БД без insight-таблиц → карточка v1 без падения.

**DoD:** тесты зелёные. Commit: `feat(card): v2 — overdue, admiralty grade, best call time (A6)`.

### Задача A3 — «Зеркало»: досье владельца *(T2)*

**Цель:** надёжность обещаний владельца, тренд его риска, концентрация зависимости, смена регистра.

**Файлы:** Create: `src/callprofiler/insight/mirror.py`; Modify: `insight/repository.py` (таблица),
`cli/main.py`+`cli/commands/insight.py`, `dashboard/db_reader.py`, `dashboard/server.py`, `static/app.js`.
Test: `tests/insight/test_mirror.py`, дополнение dashboard-тестов.

**Схема** (в `apply_insight_schema`):
```sql
CREATE TABLE IF NOT EXISTS owner_mirror (
    user_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,          -- JSON
    computed_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

1. `mirror.py::build_mirror(conn, user_id, today=None) -> dict` + `save_mirror(conn, user_id, payload)`
   (UPSERT c user-guard). Payload (каждый блок с числами-основаниями, фразы ≤300):
   - `promises`: по A1 `overdue_items`/`open_items` side='owner': open_n, overdue_n, фраза
     («вы должны 3 вещи, 1 просрочена» / «за вами долгов нет»).
   - `risk_trend`: AVG(risk_score) по месяцам за 12 мес (SQL GROUP BY strftime('%Y-%m')), наклон
     (numpy polyfit deg=1); |slope|>1.0/мес → фраза «фон ваших разговоров становится напряжённее/спокойнее», иначе «ровный».
   - `dependency`: доля топ-3 контактов в сумме duration_sec за 180 дней + их имена; >0.6 →
     «общение сконцентрировано на 3 людях: …» (это и есть концентрация зависимости).
   - `register`: формальность речи ВЛАДЕЛЬЦА по контактам — переиспользовать `compute_formality`
     (`insight/features/formality.py`), но подав сегменты `speaker='OWNER'` per contact (прочитать
     сегменты SQL-ом из feature_store-паттерна, поменяв фильтр на OWNER; НЕ менять сам formality.py,
     если он фильтрует внутри — тогда добавить в него параметр `side='OTHER'` default, обратная совместимость).
     Выход: топ-3 контакта с максимальной формальностью владельца и топ-3 с минимальной →
     «подчёркнуто на „вы“ с: …; свободнее всего с: …» (support ≥40 токенов OWNER на контакт).
2. CLI `mirror-build --user X` → build+save+print краткий свод.
3. Дашборд: `db_reader.get_mirror()` guarded (`_has_table('owner_mirror')`) → `GET /api/mirror`;
   app.js: блок «Зеркало» СВЕРХУ вкладки «Личности» (collapsible, паттерн существующих секций),
   пусто → подсказка «запустите mirror-build --user me».
4. **Тесты:** синт-БД: promises owner-side с просрочкой; риск растущий (10→60 по месяцам);
   3 контакта 80% времени → фразы всех 4 блоков присутствуют; идемпотентность save; дашборд:
   guarded-пусто без таблицы, payload отдаётся при наличии.

**DoD:** тесты зелёные. Обновить `.claude/rules/dashboard.md` (3 строки: /api/mirror, вкладка).
Commit: `feat(insight): owner mirror — self-dossier aggregates + dashboard section (A3)`.

### Задача A7 — Доктрина §6: досье 5 слоёв + Admiralty в шапке + противоречия как контент *(T2)*

**Файлы:** Create: `src/callprofiler/insight/tension.py`; Modify: `dashboard/db_reader.py`,
`dashboard/labels_ru.py` (при новых enum), `static/app.js`. Test: `tests/insight/test_tension.py`,
дополнение `tests/test_dashboard_dossier.py`.

1. **5 слоёв** — presentational: в `get_person_dossier` добавить ключ `layers` — маппинг существующих
   секций на слои (dict: behavioral=[patterns, temporal, promise_outcomes*], speech=[age_style, formality,
   traits], relational=[network, mentions*, finance*], dynamic=[evolution, drift*, pivotal_scenes*],
   practical=[advice, obligations, best_time]; * — появятся в Ф-B/Ф-C, ключи писать сразу, рендер guarded).
   app.js::renderDossier: сгруппировать вывод секций под 5 заголовками
   («Поведение» / «Речь» / «Место в сети» / «Динамика» / «Что делать») — существующие рендер-функции
   секций НЕ переписывать, только порядок и заголовки-группы.
2. **Admiralty в шапке досье:** db_reader считает `grade_line` (реюз `insight/admiralty.py` из A6,
   guarded) → app.js: строка под именем.
3. **Поворотные сцены:** guarded `_has_table('bio_portraits')`: `SELECT prose, pivotal_scenes FROM
   bio_portraits` для entity контакта (через entity_contact_map) → резолв сцен из `bio_scenes`
   (id-пространство bio_entities ≠ graph entities — связь ТОЛЬКО по имени, см. bugs.md 2026-07-02;
   если связь ненадёжна → секцию не показывать, НЕ гадать) → секция «Поворотные сцены» (дата + synopsis ≤300).
4. **tension.py** — детерминированные правила расхождения слоёв:
   ```python
   def cross_layer_tensions(d: dict) -> list[dict]:
       """d = собранное досье ДО локализации. Каждое правило guarded на наличие данных.
       Возврат: [{phrase, evidence_a, evidence_b}] — evidence = 'метка: значение'."""
   ```
   Правила v1 (ровно эти 5, без творчества):
   | # | Условие A | Условие B | Фраза |
   |---|---|---|---|
   | 1 | formality/vy_ratio z>1 (из contact_features) | night_ratio z>1 | «подчёркнуто формален — но звонит ночью» |
   | 2 | hedge z>1 | directive z>1 | «уклончив в формулировках, но при этом командует» |
   | 3 | risk_trend растёт (evolution по годам, последний > первого +15) | emotional_pattern тёплый/positive | «тон тёплый, но напряжение разговоров растёт» |
   | 4 | kept_ratio<0.5, n>=3 (B3, guarded отсутствие) | specificity z>1 (B2, guarded) | «говорит конкретно и уверенно, но слово держит редко» |
   | 5 | outgoing_ratio z<-1 (он звонит сам) | request_balance z>1 (он же просит; B5, guarded) | «сам ищет контакта и сам же просит — похоже, вы ему нужнее» |
   Чтение contact_features: `SELECT feature_name, value FROM contact_features WHERE user_id=? AND contact_id=?` —
   там сырые значения; z считать на месте: подтянуть mean/std по популяции юзера тем же SQL-ом
   (2 запроса, numpy), либо проще — брать `distinctive_dims` из `contact_archetypes` (там уже топ-|z|),
   правило срабатывает по вхождению имени оси в distinctive_dims с нужным знаком. Взять ВТОРОЙ путь (дешевле, уже посчитано).
   Секция досье «Напряжения» — каждая строка: фраза + два evidence. Пусто → секции нет.
5. **Тесты:** tension — синтетическое досье с distinctive_dims под правило 1 и 2 → ровно 2 напряжения,
   фразы точные; отсутствие ключей (нет B3/B5) → правила 4/5 молча пропущены. Дашборд-тест: досье
   содержит `layers` и (при данных) `tensions`; graph-only БД → не 500.

**DoD:** тесты + полный pytest зелёные. Обновить `.claude/rules/dashboard.md` (слои, tensions, admiralty).
Commit: `feat(dossier): 5-layer triangulation view, admiralty header, cross-layer tensions (A7 / §6)`.

---

## Ф-B — Новые сигнальные классы (капельно, по одному; каждый: фича → лейблы → синт-тест → секция досье)

**Общий контракт задач B:** новый модуль в `insight/features/` (или соседний), регистрация в
`feature_store.py` (добавить fn в нужный tuple `_TEXT_FNS`/`_AFFECTIVE_FNS` — этого достаточно, роутер
подхватит), записи в `labels.FEATURE_LABELS` (формат `(краткое, high-фраза, low-фраза)`), synth-тест
разделимости когорт (образец: `tests/insight/test_phase3_affective_value.py` — при ИСТИННОМ k, урок
decisions.md 2026-06-06), участие в noise-tolerance НЕ обязательно (агрегатный тест уже есть).
После КАЖДОЙ B-задачи обновить секцию тиров в `.claude/rules/insight.md` (1 строка на ось).

### Задача B3 — Поведенческая надёжность обещаний *(T2; killer-сигнал; det + мемоизированный LLM)*

**Файлы:** Create: `src/callprofiler/insight/promise_outcomes.py`, `configs/prompts/promise_outcome_v001.txt`;
Modify: `insight/repository.py`, `cli/main.py`+`cli/commands/insight.py`, `dashboard/db_reader.py`,
`static/app.js`, `deliver/digest.py` (обогащение), `insight/admiralty.py` НЕ трогать (грейд сам подхватит kept_ratio через вызов). Test: `tests/insight/test_promise_outcomes.py`.

**Схема** (в `apply_insight_schema`):
```sql
CREATE TABLE IF NOT EXISTS promise_outcomes (
    user_id TEXT NOT NULL,
    promise_key TEXT NOT NULL,        -- sha1(f"{call_id}|{who}|{what_lower[:80]}")[:16]
    contact_id INTEGER,
    call_id INTEGER NOT NULL,         -- звонок, где обещано
    side TEXT NOT NULL CHECK(side IN ('owner','contact')),
    what TEXT NOT NULL,
    due TEXT,
    status TEXT NOT NULL CHECK(status IN ('kept','late','broken','unknown')),
    evidence_call_id INTEGER,
    evidence_date TEXT,
    evidence_quote TEXT,
    days_late INTEGER,
    method TEXT NOT NULL CHECK(method IN ('det','llm')),
    confidence REAL NOT NULL,
    llm_prompt_hash TEXT,
    llm_result TEXT,
    prompt_version TEXT,
    computed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, promise_key)
);
```

**Интерфейсы (Produces):**
```python
PROMPT_VERSION_PROMISE = "promise-v1"
def run_promise_outcomes(conn, user_id: str, *, use_llm: bool = False,
                         llm_url: str | None = None, llm_limit: int = 200) -> dict  # stats
def contact_reliability(conn, user_id: str, contact_id: int) -> dict | None:
    """{kept_ratio, n, median_delay_days, phrase} ; n<3 -> None (не показываем)."""
```

1. **Источник обещаний:** events `event_type IN ('promise','debt')` c payload/source_quote/deadline/who
   (+ promises-таблица UNION, дедуп как в A1). side из who; `who='UNKNOWN'` — пропуск.
2. **Дет-эвристика:** для каждого обещания contact-side — последующие (до +120 дней) сегменты
   `speaker='OTHER'` ЭТОГО contact_id (JOIN calls); для owner-side — `speaker='OWNER'` в звонках этого контакта.
   Содержательные слова обещания: токены `len>=4` из what минус стоп. Матч сегмента = ≥1 общее слово И:
   - `_RE_DONE = re.compile(r"\b(сделал|сделала|отправил|отправила|перев[ёе]л|привез|привезла|готово|закончил|оплатил|скинул|выслал|подписал|доделал)\w*", re.I)` → kept
     (дата evidence > due+2дн → late, days_late = разница);
   - `_RE_FAIL = re.compile(r"\b(не\s+смог|не\s+получилось|не\s+успел|забыл|не\s+вышло|сорвалось|отменилось)\w*", re.I)` → broken-кандидат.
   kept-матч побеждает broken при обоих. confidence: 0.6 (1 общее слово), 0.75 (≥2). Ничего → unknown.
   evidence_quote = текст сегмента ≤240, evidence_date = дата звонка.
3. **LLM-пасс** (только `--llm`, только unknown, максимум llm_limit за прогон, memoization по
   `sha1(prompt + PROMPT_VERSION_PROMISE)` — есть строка с тем же hash и llm_result → реюз без HTTP):
   промпт `promise_outcome_v001.txt`:
   ```
   Обещание из телефонного разговора {date}: «{quote_or_what}» (срок: {due|не назван}).
   Ниже — более поздние фрагменты разговоров с тем же человеком. Определи судьбу обещания.
   Ответ строго JSON без пояснений: {"status":"kept|late|broken|unknown","quote":"дословная цитата-доказательство из фрагментов или пустая","days_late":число или null}
   ФРАГМЕНТЫ:
   {candidates}
   ```
   candidates = топ-6 фрагментов по пересечению слов (та же эвристика), клип 4000. Парсер + verbatim-гейт
   цитаты (не substring поданного → status оставить, quote='', confidence −0.15) — паттерн age_estimate.
   LLM-результат пишется с method='llm', confidence base 0.5 (kept/broken), 0.35 (late).
4. **Агрегат:** `contact_reliability`: kept_ratio=(kept)/(kept+late+broken); фразы:
   ≥0.8 «держит слово»; ≥0.5 «держит слово через раз»; <0.5 «чаще не выполняет обещанное»;
   `median_delay_days>2` → добавить «обычно с опозданием около N дней» (N→неделя/двух недель при 5-9/10-18).
5. **Потребители:** досье — секция «Надёжность обещаний» в слое behavioral (фраза + до 3 последних
   исходов: what → status, evidence_date, quote); карточка A6 grade: в вызов `source_grade` передать
   kept_ratio/n из `contact_reliability` (guarded); digest A1: к overdue-items contact-side дописать
   `(держит слово через раз)` если reliability есть.
6. **CLI:** `promise-outcomes --user X [--llm] [--llm-limit 200]`.
7. **Тесты (все офлайн, LLM mock):**
   - `test_det_kept`: обещание «привезу документы» + через 3 дня OTHER-сегмент «привёз документы, всё подписал» → kept, evidence_quote совпадает.
   - `test_det_late`: due вчера, исполнение через 10 дней → late, days_late=9±1.
   - `test_det_broken`: «не получилось с документами» → broken.
   - `test_unknown_goes_llm_memoized`: unknown + mock LLM kept → status kept, второй прогон БЕЗ HTTP (пост 1 раз).
   - `test_verbatim_gate`: mock-цитата не из фрагментов → quote пуст, confidence снижена.
   - `test_idempotent_rerun`: повторный run → 0 новых строк, статусы стабильны.
   - `test_reliability_phrase_thresholds`: 4 kept/1 broken → «держит слово»; n=2 → None.
   - `test_unknown_speaker_ignored`: исполнение в UNKNOWN-сегменте НЕ засчитывается.

**DoD:** тесты + полный pytest. `.claude/rules/insight.md` — секция «Надёжность обещаний» (5 строк).
Commit: `feat(insight): promise outcomes — behavioral reliability with det+LLM linkage (B3)`.

### Задача B1 — Темп и ритм речи из таймстампов *(T2 из-за правки роутера, сама фича T1)*

**Файлы:** Create: `insight/features/tempo.py`; Modify: `insight/feature_store.py` (SELECT сегментов
+ регистрация), `insight/labels.py`. Test: `tests/insight/test_tempo.py`.

1. **Роутер:** в `build_contact_features` расширить SELECT сегментов:
   `SELECT t.call_id, t.speaker, t.text, t.start_ms, t.end_ms FROM ...` (осталь­ное без изменений —
   существующие текст-фичи читают только speaker/text из dict, обратная совместимость; прогнать
   ВЕСЬ tests/insight как регресс).
2. `tempo.py::compute_tempo(segments, reference_now=None) -> dict[str, Feature]` (регистрация в `_TEXT_FNS`):
   - `tempo_cps` — знаков/сек речи КОНТАКТА: sum(len(text))/sum((end_ms-start_ms)/1000) по OTHER-сегментам
     с dur ≥ 500ms; support_n = число таких сегментов; tier ROBUST.
   - `reply_latency_ms` — медиана пауз: для пар подряд идущих сегментов ОДНОГО call_id
     (OWNER→OTHER) gap = other.start_ms − owner.end_ms, брать 0 < gap < 15000; support_n = число пар.
   - `tempo_accel` — медиана по звонкам отношения cps(последняя треть сегментов OTHER) / cps(первая треть);
     звонки с <6 OTHER-сегментов пропускать; support_n = число звонков.
   Нет end_ms/пустые → фичи не эмитить (роутер терпит отсутствие ключей).
3. Лейблы: `"tempo_cps": ("темп", "говорит быстро, напористо", "говорит медленно, размеренно")`,
   `"reply_latency_ms": ("паузы", "отвечает с паузами, обдумывает", "отвечает мгновенно")`,
   `"tempo_accel": ("разгон", "к концу разговора ускоряется — возбуждается", "")`.
4. **Тесты:** синт-сегменты с известными ms → cps точен (assert ±0.01); латентность — медиана пар;
   UNKNOWN-сегменты не участвуют; <500ms сегменты отброшены; когортный тест: «быстрые» vs «медленные»
   контакты (профили сегментов) разделяются по tempo_cps (mean diff > 1σ).
5. Досье: оси попадают в существующие черты-фразы автоматически (distinctive_dims/labels) — отдельной секции НЕ делать.

**DoD:** тесты + регресс tests/insight зелёные. Commit: `feat(insight): speech tempo/rhythm features from timestamps (B1)`.

### Задача B2 — Специфичность vs вода *(T1)*

**Файлы:** Create: `insight/features/specificity.py`; Modify: `feature_store.py` (`_TEXT_FNS`), `labels.py`.
Test: `tests/insight/test_specificity.py`.

1. `compute_specificity(segments, reference_now=None)`: по OTHER-токенам:
   ```python
   _RE_NUM = re.compile(r"\d")
   _MONTHS = {"январ","феврал","март","апрел","мая","мае","июн","июл","август","сентябр","октябр","ноябр","декабр"}
   _WDAYS = {"понедельник","вторник","сред","четверг","пятниц","суббот","воскресень"}
   _RE_MONEY = re.compile(r"(руб|₽|тыс|тысяч|млн|миллион|долла|евро)", re.I)
   _RE_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
   ```
   value = (числовые токены + месяц/день-хиты (prefix-матч по норм. токену) + money-хиты + time-хиты)
   / total_tokens × 100. Ключ `"specificity"`, tier ROBUST, support_n = total_tokens//100 (полный вес от ~200 токенов при n0=2… НЕТ: support_n = число ХИТОВ + мин(total_tokens//200, 5) — урок fixager P2: support от попаданий; проще: support_n = число хитов).
   Канонизированные entity-хиты в v1 НЕ считаем (потребовали бы менять сигнатуру роутера под alias-set) —
   зафиксировать это отступление в decisions.md при исполнении.
2. Лейбл: `"specificity": ("конкретность", "говорит конкретно: числа, даты, суммы", "говорит обтекаемо, без конкретики")`.
3. **BS-index v2 НЕ делать.** Специфичность в BS-формулу не вливается: граф derived ТОЛЬКО из events
   (`graph.md` layer contract), транскрипт-сигнал сломал бы replay-детерминизм. Вместо этого:
   специфичность уже видна в досье (черты) и работает анти-двойником hedge в кластеризации;
   Admiralty (A6) остаётся точкой сведения. Записать в decisions.md (это отклонение от буквы
   STRATEGIC_PLAN §5.B2 в пользу инварианта graph.md — решение принято на T3-ревью 2026-07-02).
4. **Тесты:** «завтра в 15:30 переведу 40 тысяч рублей» → высокая specificity; «ну там посмотрим,
   как пойдёт, наверное» → 0; когортный synth-тест конкретных vs водянистых.

**DoD:** тесты зелёные. Commit: `feat(insight): specificity-vs-vagueness axis (B2)`.

### Задача B4 — Эмоциональная палитра *(T1; лексиконы-данные)*

**Файлы:** Create: `insight/features/emotion_palette.py`, `insight/features/lexicons/emo_anger.txt`,
`emo_anxiety.txt`, `emo_joy.txt`, `emo_contempt.txt`; Modify: `feature_store.py` (`_AFFECTIVE_FNS`? НЕТ —
читает segments → `_TEXT_FNS`, tier у Feature свой AFFECTIVE), `labels.py`. Test: `tests/insight/test_emotion_palette.py`.

1. Лексиконы — формат `age_style/lexicons` (один стем на строку; `=` = точный матч токена; `#` комментарий).
   Загрузчик РЕИСПОЛЬЗОВАТЬ из `age_style/lexicons.py` (import), не писать свой. Содержимое (ровно это,
   пополнение — только с тестом):
   - `emo_anger.txt`: `бесит, бесил, злюсь, злит, разозли, ярость, взбесил, достал, задолбал, заколебал, ненавиж, орал, наорал, хамств, наглост, обнагле, =псих, психует, психанул, возмутит, возмущ, скандал, руган, разруга`
   - `emo_anxiety.txt`: `боюсь, боязн, страшно, страх, тревож, переживаю, переживал, волнуюсь, волнует, нервнича, нервы, паник, кошмар, ужас, опасаюсь, опасно, вдруг, =неужели, страшновато, жутко`
   - `emo_joy.txt`: `рад, рада, радост, счастлив, здорово, отлично, прекрасно, чудесно, ура, кайф, доволен, довольна, обожаю, восторг, классно, супер, замечательно, поздравля`
   - `emo_contempt.txt`: `презира, ничтож, жалкий, жалкая, убог, позорищ, позор, =клоун, клоуны, бездар, тупиц, идиот, кретин, дилетант, шарашк, =цирк`
   (только однословные стемы — токенайзер многословных не берёт; при пополнении это правило держать.)
2. `compute_emotion_palette(segments, ...)`: OTHER-токены (normalize как в age_style: lower, ё→е);
   4 фичи `emo_anger|emo_anxiety|emo_joy|emo_contempt` = хиты/токены×1000; tier AFFECTIVE;
   support_n = число хитов (урок P2).
3. Лейблы: гнев→(«гнев», «часто раздражается и злится», ''), тревога→(«тревога», «много тревожится и опасается», ''),
   радость→(«позитив», «часто радуется, тёплый тон», ''), презрение→(«презрение», «позволяет себе презрительные оценки», '').
4. Досье: секция «Эмоциональная палитра» в слое speech — 4 мини-бара (паттерн group-баров age_style
   в app.js) из значений contact_features (db_reader guarded SELECT по 4 именам фич).
5. **Тесты:** плантированные реплики каждой эмоции → соответствующая фича > 0, остальные 0;
   «база данных» не триггерит ничего (наследие P1 — точный матч работает); support_n = хитам.

**DoD:** тесты зелёные. Commit: `feat(insight): emotional palette lexicon features (B4)`.

### Задача B5 — Баланс просьб *(T1)*

**Файлы:** Modify: `insight/features/linguistic.py` (новая функция там же — просьбы тематически её),
`feature_store.py` (fn добавить в `_TEXT_FNS`), `labels.py`. Test: дополнение `tests/insight/test_linguistic_extra.py` (новый).

1. В `linguistic.py` добавить (существующие функции НЕ трогать):
   ```python
   _RE_REQUEST = re.compile(r"\b(прошу|попрошу|можешь|сможешь|мог бы|могла бы|сделай|скинь|отправь|пришли|привези|принеси|помоги|выручи|одолжи|займи|подскажи|посмотри|узнай|напомни)\b", re.I)
   def compute_request_balance(segments, reference_now=None) -> dict[str, Feature]:
       # req_other = хиты в OTHER-сегментах; req_owner = в OWNER; UNKNOWN пропуск
       # value = (req_other - req_owner) / (req_other + req_owner)  при сумме >=3, иначе не эмитить
       # ключ "request_balance", tier ROBUST, support_n = req_other + req_owner
   ```
2. Лейбл: `"request_balance": ("просьбы", "чаще просит он", "чаще просите вы")`.
3. Досье: подпись «кто кому нужен» появится через черты + правило 5 tension (A7) — отдельной секции нет.
4. **Тесты:** OTHER 5 просьб / OWNER 1 → value>0.6; поровну → ~0; сумма 2 → фичи нет; UNKNOWN не считается.

**DoD:** тесты зелёные. Commit: `feat(insight): request/offer balance axis (B5)`.

### Задача B6 — Аккомодация (лексическое выравнивание) *(T2)*

**Файлы:** Create: `insight/features/accommodation.py`; Modify: `feature_store.py` (`_TEXT_FNS`), `labels.py`.
Test: `tests/insight/test_accommodation.py`.

1. `compute_accommodation(segments, ...)`: группировать по call_id; на звонок: множества контентных
   токенов (len≥4, lower/ё→е, минус стоп-набор ~50 слов — inline frozenset: который, чтобы, просто,
   давай, сейчас, потом, здесь, очень, можно, нужно, будет, есть, этот, така(я/ой не влезут — точные формы:
   такой, такая, такое, тогда, когда, ничего, что-то, вообще, короче, понял, поняла, привет, пока, алло, ага, угу, значит, кстати, например, конечно, спасибо, пожалуйста, слушай, смотри, говорю, говорит))
   A=OWNER, B=OTHER; звонки с |A|<20 или |B|<20 пропустить. `align_contact=|A∩B|/|B|`, `align_owner=|A∩B|/|A|`;
   value = median(align_contact − align_owner) по звонкам (>0 = контакт подстраивается под владельца).
   Ключ `"accommodation"`, tier AFFECTIVE, support_n = число учтённых звонков.
2. Лейбл: `("подстройка", "подстраивается под вашу речь", "вы подстраиваетесь под его речь")`.
3. **Тесты:** синт-звонок, где OTHER повторяет 60% слов OWNER, OWNER уникален → value>0;
   зеркальный случай → value<0; короткие звонки отброшены. Когортный synth: «подстраивающиеся» vs
   «доминирующие» профили фраз → разделение.

**DoD:** тесты зелёные. Commit: `feat(insight): lexical accommodation asymmetry (B6)`.

### Задача B7 — Финансовая экспозиция *(T2 — деньги = внимательность, но только отображение)*

**Файлы:** Create: `src/callprofiler/insight/finance.py`; Modify: `dashboard/db_reader.py`, `static/app.js`,
`deliver/digest.py`. Test: `tests/insight/test_finance.py`.

1. `finance.py`:
   ```python
   _RE_AMOUNT = re.compile(
       r"(\d[\d\s]{0,9}(?:[.,]\d{1,2})?)\s*(тыс\w*|к\b|млн|миллион\w*)?\s*(руб\w*|₽|р\b|доллар\w*|\$|бакс\w*|евро|€)",
       re.I)
   def extract_amounts(text: str) -> list[tuple[float, str]]:
       # ('40 тыс руб' -> (40000.0,'RUB')); множители: тыс/к=1e3, млн=1e6; валюты RUB/USD/EUR
   def finance_exposure(conn, user_id: str, contact_id: int) -> dict | None:
       # events open promise/debt этого контакта: суммы из payload+source_quote (max по событию,
       # не сумма дублей); итог по валютам: {"RUB": [low, high], ...} где low=max разовой, high=сумма;
       # пусто -> None
   def exposure_phrase(exp: dict) -> str:   # «на нём завязано ~40–90 тыс ₽ + ~2 тыс $»
   ```
   Формат чисел: тыс/млн с округлением до 1 значащей после запятой; НЕ копейки.
2. Досье: слой relational, секция «Финансовая экспозиция» (фраза + до 3 событий-оснований: quote+дата) —
   guarded, None → нет секции. Digest: к overdue-строкам с суммой дописывать её.
3. **Тесты:** extract_amounts таблично («сорок тысяч» словами НЕ ловим — только цифры, тест фиксирует);
   «перекину 40 тыс руб» → (40000, RUB); «650 р» → (650, RUB); «2к $»... `$` после к — ловится ли
   регексом — тест; дубль-события не задваивают high; None без событий.

**DoD:** тесты зелёные. Commit: `feat(insight): financial exposure from debt/promise events (B7)`.

### Задача B8 — Дрейф стиля по годам *(T2; FRAGILE, gated)*

**Файлы:** Create: `src/callprofiler/insight/age_style/drift.py`; Modify: `dashboard/db_reader.py`, `static/app.js`.
Test: `tests/insight/test_style_drift.py`.

1. `drift.py::style_drift(conn, user_id, contact_id, min_tokens_per_year=500, min_years=3) -> list[str]`:
   OTHER-сегменты контакта по годам (`strftime('%Y', c.call_datetime)`); годы с ≥min_tokens;
   на год считать 3 измерения СУЩЕСТВУЮЩИМИ функциями age_style (импорт из features age_style:
   slang_density, mean_syllables_per_word, vy_ratio — точные имена взять из `insight/age_style/features/*`,
   Grep `def ` там); тренд = polyfit deg1; |Δ за период| ≥ 25% диапазона значения → фраза:
   slang↓ «сленга в речи становится меньше», syllables↑ «речь становится тяжелее и формальнее»,
   vy↑ «переходит на более официальное „вы“» (и симметричные ↓/↑). ≤2 фразы, каждая с суффиксом
   «(осторожная оценка по стилю)».
   **Гейт FRAGILE:** доля UNKNOWN-сегментов у контакта >40% → вернуть [] (метрика из задачи 0.4 —
   но локально по контакту: 1 SQL).
2. Досье: слой dynamic, секция «Дрейф стиля» рядом с evolution; live-вычисление в db_reader guarded
   try/except (один контакт = дёшево; numpy/regex, доктрина дашборда не нарушена — чтение+расчёт, без записи).
3. **Тесты:** синт-контакт: 2021 сленговые реплики, 2024 формальные «вы» → ≥1 фраза о формализации;
   <3 лет данных → []; UNKNOWN>40% → [].

**DoD:** тесты зелёные. Commit: `feat(insight): style drift over years, FRAGILE-gated (B8)`.

---

## Ф-C — Реляционный интеллект

### Задача C3 — Алерты затухания ценных связей *(T1)*

**Файлы:** Create: `src/callprofiler/insight/dormancy.py`; Modify: `deliver/digest.py` (вызов секции),
`dashboard/db_reader.py` (флаг в досье). Test: `tests/insight/test_dormancy.py`.

1. `dormancy.py::dormant_valuable(conn, user_id, today=None, top: int = 5) -> list[dict]`:
   ценность: контакт имел ≥1 календарный год с ≥26 звонками (SQL GROUP BY год) ИЛИ суммарная
   длительность в топ-квартиле юзера. Затухание: `days_since_last > max(60, 3 × median_gap_days)`
   (median_gap по датам его звонков; персональный ритм, не общий порог). Выход:
   `{contact_id, name, last_date, why: 'раньше вы говорили почти каждую неделю' | 'один из самых длинных собеседников'}`.
   Сортировка по (past-value убыв, days_since_last убыв), top-5.
2. Digest A1: секция `😴 Спящие ценные связи` через `extra_sections` (строка: имя — «тишина с <last_date>; why»).
   Досье: строка-флаг в шапке practical-слоя, если контакт в списке.
3. **Тесты:** контакт 30 звонков еженедельно в 2024, тишина 8 месяцев → в списке; регулярный ежемесячный
   с gap 30 дней и паузой 45 → НЕ в списке (3×30=90>45); мелкий контакт (5 звонков) → не в списке.

**DoD:** тесты зелёные. Commit: `feat(insight): dormancy alerts for valuable ties (C3)`.

### Задача C1 — Граф упоминаний *(T2)*

**Файлы:** Create: `src/callprofiler/insight/mentions.py`; Modify: `insight/repository.py` (таблица),
`cli/main.py`+`cli/commands/insight.py`, `dashboard/db_reader.py`, `static/app.js`. Test: `tests/insight/test_mentions.py`.

**Схема** (в `apply_insight_schema`):
```sql
CREATE TABLE IF NOT EXISTS mention_edges (
    user_id TEXT NOT NULL,
    src_contact_id INTEGER NOT NULL,   -- кто говорил
    dst_contact_id INTEGER NOT NULL,   -- о ком (контакт, на которого замаплена персона)
    mention_count INTEGER NOT NULL,
    last_date TEXT,
    sample_quote TEXT,
    PRIMARY KEY (user_id, src_contact_id, dst_contact_id)
);
```

1. `mentions.py::build_mention_edges(conn, user_id) -> dict` — DERIVED, полный rebuild
   (DELETE WHERE user_id=? → INSERT; паттерн entity_contact_map):
   источник: `events` c `entity_id IS NOT NULL` JOIN calls (contact_id = src) JOIN
   `entity_contact_map` (entity→dst contact, `confidence >= 0.6`, только PERSON-entities —
   JOIN entities по entity_type; колонка есть в base-схеме) — рёбра src→dst, `dst != src`;
   владельцу-entity рёбра не строить (Grep `is_owner` в graph-слое; колонка добавляется graph-схемой —
   фильтр по PRAGMA-проверке, как в `person_link.py`). mention_count=COUNT, sample_quote=любой
   `source_quote` ≤200, last_date=MAX(call_datetime).
2. CLI `mentions-build --user X`; также дописать вызов в конец `graph-replay` аналогично
   `build_entity_contact_map` (Grep `person_link` в CLI/graph_replay — встать рядом, entity_id
   пересоздаются replay-ем, map и edges строятся после).
3. Досье (слой relational): секция «Через упоминания»: (a) «о нём говорят: <src-имена>» (top-3 по count,
   каждая с sample_quote+датой); (b) «общие люди» — контакты Z, упомянутые и этим контактом, и владельцем...
   у владельца нет src-контакта — вместо этого: пересечение dst-упоминаний этого контакта с dst других
   контактов НЕ делать (комбинаторика; YAGNI v1) — только (a) + счётчик исходящих «сам упоминает N ваших контактов».
4. **Тесты:** сеем events с entity_id + map: X упоминает персону→Z дважды → ребро (X,Z,2) с цитатой;
   confidence 0.5 в map → ребра нет; повторный build → те же строки (идемпотент); досье Z содержит «о нём говорят: X».

**DoD:** тесты зелёные. `.claude/rules/insight.md` — 3 строки про mention_edges. Commit:
`feat(insight): mention graph contact→contact via entity_contact_map (C1)`.

### Задача C2 — Эхо информации: **НЕ ДЕЛАТЬ** *(T3-гейт)*

STRATEGIC_PLAN §8 присваивает C2 тир T3 (высокий риск шума, новый pass-контракт). Вне полномочий
этого плана и исполнителя-Sonnet. Пропустить; при попытке юзера заказать — ответ: «C2 требует
T3-сессии (Fable), см. ozalupennieStrategic5.md». Ничего не коммитить.

---

## Ф-D — Нарратив (леверидж biography; всё guarded — bio-таблиц на боксе может не быть)

### Задача D1 — «В этот день» *(T1)*

**Файлы:** Modify: `deliver/digest.py`, `cli/commands/deliver.py`. Test: дополнение `tests/test_digest.py`.

1. В `digest.py`:
   ```python
   def on_this_day(conn, user_id: str, today=None) -> list[str]:
       # guarded _has_table('bio_scenes') (скопировать хелпер-паттерн из dashboard/db_reader.py);
       # SELECT call_datetime, synopsis, key_quote FROM bio_scenes
       #  WHERE user_id=? AND importance>70 AND strftime('%m-%d', call_datetime)=strftime('%m-%d', ?)
       #    AND strftime('%Y', call_datetime) < strftime('%Y', ?)
       # строки: «N лет назад: <synopsis ≤200> — „<key_quote ≤100>"»
   ```
2. `build_digest` вызывает сам (секция `🗓 В этот день`); CLI `on-this-day --user X [--send]` — тот же
   рендер одной секции (для ежедневного Task Scheduler).
3. **Тесты:** сцена ровно год назад importance 80 → строка «1 год назад»; importance 50 → нет;
   БД без bio_scenes → пусто, не исключение.

**DoD:** тесты зелёные. Commit: `feat(deliver): on-this-day anniversaries in digest (D1)`.

### Задача D2 — Линия жизни в дашборде *(T1)*

**Файлы:** Modify: `dashboard/db_reader.py`, `dashboard/server.py`, `static/app.js`, `templates/index.html`.
Test: `tests/test_dashboard_insight.py` дополнение.

1. db_reader `get_lifeline() -> list[dict]` guarded `_has_table('bio_arcs')`:
   `SELECT title, arc_type, status, start_date, end_date, importance FROM bio_arcs WHERE user_id=?
   AND start_date IS NOT NULL ORDER BY importance DESC LIMIT 40`.
2. `GET /api/insight/lifeline` (рядом с существующими insight-эндпоинтами). app.js: пятый вид на
   вкладке «Архетипы» — «Линия жизни»: ECharts custom/bar — горизонтальные полосы по годам
   (x = время start→end (end NULL → start+30д), y = индекс арки, цвет по arc_type, tooltip = title+status).
   Пусто → подсказка «biography не запускалась».
3. **Тест:** сеем 2 арки → эндпоинт отдаёт 2 записи; без таблицы → [], не 500.

**DoD:** тест зелёный. `.claude/rules/dashboard.md` — 1 строка. Commit: `feat(dashboard): life-line timeline from bio_arcs (D2)`.

### Задача D3 — Квартальный отчёт о социальной вселенной *(T2; LLM-окно)*

**Файлы:** Create: `src/callprofiler/insight/quarterly.py`, `configs/prompts/quarterly_v001.txt`;
Modify: `insight/repository.py` (таблица), `cli/main.py`+`cli/commands/insight.py`. Test: `tests/insight/test_quarterly.py`.

**Схема** (в `apply_insight_schema`):
```sql
CREATE TABLE IF NOT EXISTS insight_reports (
    user_id TEXT NOT NULL,
    period TEXT NOT NULL,            -- '2026-Q2'
    prompt_version TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    body_md TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, period, prompt_version)
);
```

1. `quarterly.py`:
   - `gather_aggregates(conn, user_id, period) -> dict` — ТОЛЬКО агрегаты, НИКАКИХ транскриптов
     (STRATEGIC_PLAN D3): risers/fallers (топ-8 контактов по |Δ звонков| квартал vs предыдущий, имена+направление),
     risk-сдвиги (контакты с |Δ avg risk| ≥ 15, имена+знак), новые персоны (entities PERSON, created_at
     в квартале, топ-8), незакрытое (A1 overdue counts по сторонам + топ-3 старейших с датами),
     спящие ценные (C3 reuse), при наличии — сдвиги надёжности (B3 kept_ratio крайности).
   - `build_report(conn, user_id, period, *, llm_url, timeout=120) -> dict` — prompt из
     `quarterly_v001.txt` (`PROMPT_VERSION_QREPORT = "qreport-v1"`), данные JSON-ом в user message
     (клип 7000), memoization по (user_id, period, prompt_version) + prompt_hash в строке;
     HTTP-паттерн age_estimate. Ответ = markdown, сохраняется в insight_reports + файл
     `C:\calls\reports\{user_id}-{period}.md` (mkdir parents).
   - Промпт (файл):
     ```
     Ты пишешь владельцу телефонного архива квартальный отчёт о состоянии его круга общения.
     Только факты из данных ниже; каждый факт привязывай к имени. Никаких выдуманных деталей,
     никакой морали и советов «как жить». Тон — спокойный, наблюдательный, слегка ироничный.
     5-7 абзацев markdown, без заголовков-секций, по-русски. Данные:
     {data_json}
     ```
2. CLI `quarterly-report --user X --quarter 2026-Q2 [--force]` (`--force` = игнор кэша: удалить строку и пересчитать).
3. **Тесты:** gather на синт-БД (2 квартала звонков) → risers/fallers верные по знаку; mock LLM →
   body_md сохранён в таблицу и файл; второй вызов без --force → HTTP не зовётся; llama down → RuntimeError exit 2 в CLI.

**DoD:** тесты зелёные. Commit: `feat(insight): quarterly social-universe report over aggregates (D3)`.

---

## Финализация (после последней задачи)

- [ ] **Сверка целей:** пройти по STRATEGIC_PLAN_v5 §5 таблицам — каждая строка A1-A6/B1-B8/C1,C3/D1-D3
  имеет коммит (C2 — задокументированный пропуск). §6: слои/Admiralty/tensions — A7. §7: петля 0.2,
  спот-чек 0.3, UNKNOWN-гейт 0.4, synth-тесты в каждой B-задаче. Расхождение → доделать, не рационализировать.
- [ ] **Kill-criteria (§7.6):** в `.claude/rules/dashboard.md` добавить абзац: «замер использования =
  grep access-лога uvicorn по endpoint'ам (/api/mirror, /api/insight/lifeline, /api/person) раз в 4 недели;
  фича без обращений удаляется». Кода не писать — лог уже есть.
- [ ] **Память:** CONTINUITY.md — State: портфель исполнен, что на боксе не прогнано (LLM-пассы A2/B3/D3,
  calibrate-risk, mirror-build, mentions-build — все требуют реальной БД/LLM-окна; перечислить командами).
  decisions.md — записи: «BS v2 отклонён (инвариант graph.md), специфичность display-level»,
  «C2 отложен до T3». CHANGELOG — уже писался по задачам.
- [ ] Финальный полный `pytest tests/ -q` + `git push origin main`.

## Чего в этом плане НЕТ намеренно

SER/просодика из аудио, эмбеддинги, Big5/MBTI в UI, детектор лжи, real-time подсказки,
health-трекер контактов, авто-слияние контактов, C2-эхо — отвергнуто STRATEGIC_PLAN §5 или T3-гейт.
Просить их = менять STRATEGIC_PLAN, не этот файл.
