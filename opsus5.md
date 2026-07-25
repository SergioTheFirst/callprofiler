# opsus5.md — сводный план исправления и развития callprofiler

> **Для кого:** Claude Code (Sonnet), исполняющий агент. Входная точка исполнения.
> Заменяет `OzaluplivanieFable2.md` / `OzaluplivanieFable.md` / `ozalup2.md` / `NeErrorsGR.md`
> как рабочий список. Тела задач здесь самодостаточны — в старые файлы ходить не нужно.
>
> **Правило исполнения.** Задачи строго по номерам. Не додумывать сверх написанного.
> Якорь «Grep …» — обязательная проверка перед правкой. После КАЖДОЙ задачи:
> `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q` зелёный →
> строка в `CHANGELOG.md` → карта в `.claude/rules/*` (если указано) → `git commit` →
> `git push origin main`. Одна задача = один коммит.
>
> **Состояние на старте:** 1294 passed / 2 skipped. Все номера строк ниже сверены с деревом
> `C:\pro\callprofiler` на 2026-07-25 — если строка уехала, ищи по имени символа.

---

## 0. Инварианты (нарушение = откат задачи)

1. Каждый SELECT/UPDATE/DELETE по `calls/contacts/events/promises/analyses/transcripts` и
   insight-таблицам несёт `WHERE user_id = ?`.
2. GPU последовательно: ASR+pyannote и LLM никогда одновременно. Дашборд не зовёт LLM никогда.
3. Ошибки логируются. `except: pass` запрещён везде, где есть побочный эффект (VRAM, файлы, БД).
4. Нарратив (портрет, архетип, возраст, стиль, биография) не попадает на caller card, в
   напоминания и в тексты кнопок. Исключение — одна BS-строка (задача 26).
5. Плановых Telegram-пушей ровно два: вечерний отчёт (F5) и doctor (F6). Событийно разрешены:
   напоминания F2, ack голосовой заметки F4, вопрос-имя (задача 15, ≤1/час).
6. Любой показанный агрегат несёт `n=`. Сигнал ниже гейта НЕ СУЩЕСТВУЕТ (не ноль, не «⚪»).
7. Черта контакта видна только `stable=1` (задача 24). Нестабильное не покидает дашборд:
   ни digest, ни отчёты, ни экспорт.
8. Firewall синтеза: в промпт портрета подаются только числа, структуры и готовые улики.
   Сырые транскрипты — никогда. Каждая строка портрета несёт теги сигналов.
9. Никаких Big5/MBTI/соционики/эннеаграммы/диагнозов. Оси — наблюдаемые и счётные.
10. Модель зафиксирована: `C:\models\Qwen3.5-9B.Q8_0.gguf`. Смена — только по явной команде
    юзера, в этом плане такой задачи нет.
11. Возраст: ровно одно видимое число на всех поверхностях (задача 14).
12. Недоверенный текст (цитаты, словечки, имена из ASR) подаётся в промпт только внутри
    XML-тегов с явной инструкцией игнорировать инструкции внутри.
13. Запрещено: ORM, Ollama, cloud LLM, Docker, Redis, python-multipart, новые ML-стеки,
    авто-слияние контактов.

**Общие хелперы, которые уже есть — переиспользовать, не писать заново:**
`textnorm.norm_quote` · `insight/features/base.py::tokenize` · `insight/risk_calibration.py` ·
`insight/repository.py::apply_insight_schema` + `_MIGRATIONS` · `dashboard/db_reader.py::_has_table`
/ `_has_column` · `insight/tiers.py::_percentile` · `deliver/telegram_sender.py` ·
`analyze/llm_client.py::LLMClient(cache_conn=…)` (мемоизация M3).

---

# ЧАСТЬ I — Дефекты (задачи 1-13)

Каждая задача части I — отдельный коммит, максимум ~1 файл кода + тест.

---

## Задача 1 — Ключи леджера: `payload` → `what`, `deadline` → `due` *(T1)*

**Дефект:** `aggregate/summary_builder.py` пишет в `contact_summaries.open_promises` JSON с
ключами `payload`/`deadline`; `dashboard/static/app.js::promiseItemHtml` и досье читают
`what`/`due` → в UI текст обещания рендерится как `?`.

**Якоря:** `summary_builder.py:421 _extract_open_promises`, `:437 _extract_open_debts`,
`:453 _extract_personal_facts` (ключи `payload`/`deadline` в dict-литералах),
`db_reader.py:507` (цикл `for field in ("open_promises","open_debts","personal_facts")`),
`db_reader.py:364/425` (`get_contact_profile`), `app.js` (Grep `promiseItemHtml`).

**Шаги**

1. `summary_builder.py`, все три экстрактора — писать оба ключа:
   ```python
   {
       "id": e.get("id"),
       "who": e.get("who"),
       "what": e.get("payload") or e.get("what") or "",
       "payload": e.get("payload"),          # legacy, не удалять
       "due": e.get("deadline") or e.get("due"),
       "deadline": e.get("deadline"),        # legacy
   }
   ```
   Для `_extract_personal_facts` — ключи `what`/`payload` (без due).
2. `db_reader.py` — модульная функция (одна точка нормализации для всех ридеров):
   ```python
   def _norm_ledger_item(d: dict) -> dict:
       d.setdefault("what", d.get("payload") or "")
       d.setdefault("due", d.get("deadline"))
       return d
   ```
   Применить в цикле `:507` (`items = [_norm_ledger_item(x) for x in json.loads(...)]`) и в
   `get_contact_profile` там, где грузятся те же три поля. Старые строки БД чинятся на чтении —
   миграция данных не нужна.
3. `app.js::promiseItemHtml` — защита: `escapeHtml(p.what || p.payload || '?')`,
   дедлайн `p.due || p.deadline`.
4. Тесты `tests/test_summary_builder_promises.py`:
   `test_extract_open_promises_writes_what_and_payload`,
   `test_dossier_normalizes_legacy_payload_only_row` (сеять строку только с `payload` →
   `dossier["promises"]["open"][0]["what"]` непустой).

**Commit:** `fix(aggregate): ledger items carry what/due keys, dossier normalizes legacy rows`

---

## Задача 2 — `run_coro`: отправка Telegram без ambient event loop *(T1)*

**Дефект:** `pipeline/orchestrator.py:558` (`_finalize_note`) зовёт
`asyncio.get_event_loop().run_until_complete(...)` без fallback; при закрытом/отсутствующем loop
уведомление о голосовой заметке теряется в общем `except`. На `:978` fallback есть — код
расходится.

**Шаги**

1. Создать `src/callprofiler/deliver/notify.py`:
   ```python
   """Синхронный запуск корутины из не-async кода пайплайна."""
   import asyncio

   def run_coro(coro) -> None:
       """Выполнить корутину из синхронного потока. Свой loop, если ambient нет/закрыт."""
       try:
           loop = asyncio.get_event_loop()
           if loop.is_closed():
               raise RuntimeError("closed")
       except RuntimeError:
           loop = asyncio.new_event_loop()
           try:
               asyncio.set_event_loop(loop)
               loop.run_until_complete(coro)
           finally:
               loop.close()
               asyncio.set_event_loop(None)
           return
       loop.run_until_complete(coro)
   ```
2. `orchestrator.py` — заменить ОБА места (`:558` и `:978-989`) на
   `from callprofiler.deliver.notify import run_coro` + `run_coro(self.telegram.send_...(...))`.
   Ручной блок `new_event_loop` на `:983` удалить.
3. Тест `tests/test_orchestrator_notify.py::test_finalize_note_notify_without_ambient_loop`:
   в потоке выполнить `asyncio.run(asyncio.sleep(0))` (обнуляет loop), затем `_finalize_note`
   с mock-telegram → `send_note_ready.call_count == 1`.

**Commit:** `fix(pipeline): loop-safe telegram notify helper for note + summary paths`

---

## Задача 3 — Единый источник risk-порогов (карточка · summary · дашборд) *(T2)*

**Дефект:** три несогласованные шкалы. `summary_builder.py:80 _risk_emoji_with_calibration`
красит **risk_score** порогами `BSCalibrator` (обучен на bs_index). `db_reader.py:311/313`
использует 60/30, `db_reader.py:452/454` — 70/40, `app.js:963` и `:1136` — 60/30.
`card_generator.py:122` уже на калиброванных `risk_thresholds`.

**Шаги**

1. `insight/risk_calibration.py` — добавить единственный публичный хелпер:
   ```python
   DEFAULT_BANDS = (30, 70)

   def risk_bands(conn, user_id: str) -> tuple[int, int]:
       """(green_max, yellow_max) из risk_thresholds; таблицы/строки нет → DEFAULT_BANDS."""
   ```
   Реализация: `get_latest_risk_thresholds` в try/except (нет таблицы → default).
2. `card_generator.py:122` — переписать тело `_risk_emoji_with_calibration` на `risk_bands`
   (внешнее поведение и тесты карточки не меняются).
3. `summary_builder.py` — удалить `_get_calibrator`, `self._calibrator`, импорт
   `graph.calibration.BSCalibrator` (строки 27, 58-77); `_risk_emoji_with_calibration` →
   `green, yellow = risk_bands(conn, user_id)`; эмодзи `🟢/🟡/🔴` по `risk <= green`,
   `risk <= yellow`, иначе красный.
4. `db_reader.py` — заменить литералы на `risk_bands(self._conn, user_id)` в обоих местах
   (`:311`, `:452`); добавить в ответ `/api/overview` и `/api/person` ключ
   `risk_thresholds: {"green_max": g, "yellow_max": y}`.
5. `app.js` — одна функция рядом с существующей BS-раскраской (Grep `thr.green_max`, ~`:1076`):
   ```js
   function riskClass(n, thr) {
     if (n === null || n === undefined) return '';
     var g = (thr && thr.green_max != null) ? thr.green_max : 30;
     var y = (thr && thr.yellow_max != null) ? thr.yellow_max : 70;
     return n <= g ? 'risk-low' : (n <= y ? 'risk-med' : 'risk-high');
   }
   ```
   Заменить оба литеральных выражения (`:963`, `:1136`) на `riskClass(risk, state.riskThr)`;
   `state.riskThr` заполняется из `/api/overview` и из ответа досье.
6. Тесты `tests/test_risk_bands.py`: `risk_bands` без таблицы → (30,70); с сеяной строкой
   p50=20/p85=50 → (20,50); `test_summary_risk_emoji_uses_risk_thresholds_not_bs` — файловый
   `Repository` + отдельный коннект к тому же файлу (WAL), risk=45 при (20,50) → 🟡.

**Commit:** `fix(risk): single calibrated threshold source for card, summary and dashboard`

---

## Задача 4 — Выгрузка моделей: логировать сбой *(T1)*

**Дефект:** `orchestrator.py:611 _unload_models` — два `except Exception: pass` (`:621`, `:625`).
Молчаливый сбой выгрузки = VRAM не освобождена перед LLM-фазой = OOM.

**Шаги**

1. Оба блока:
   ```python
   except Exception as exc:
       logger.warning("unload %s failed: %s", "pyannote", exc, exc_info=True)
   ```
   (второй — `"asr"`). Не поднимать исключение.
2. Тест `tests/test_orchestrator_roles.py::test_unload_models_logs_failure`: mock unload кидает →
   `caplog` содержит `unload pyannote failed`, выполнение продолжается, второй unload вызван.

**Commit:** `fix(pipeline): log GPU unload failures instead of swallowing`

---

## Задача 5 — `doctor`: чеки в границах user_id *(T2)*

**Дефект:** `doctor.py:253 _check_queue_stuck`, `:270 _check_error_burst`, `:298
_check_reminders_stale`, `:317 _check_input_silence` считают по всем профилям.

**Шаги**

1. Сигнатуры: `run_checks(config, conn=None, user_id: str | None = None)`; перечисленные четыре
   чека принимают `user_id` и при непустом значении добавляют `AND user_id = ?` во все запросы к
   `calls` / `reminders`. `user_id is None` → прежнее поведение (глобально), заголовок чека
   получает суффикс ` [все профили]`.
2. Call sites (Grep `run_checks(`): `pipeline/watcher.py::_maybe_send_doctor_report` → передать
   `uid` цикла; `dashboard/server.py` `/api/health-report` → `self.user_id` ридера;
   `cli` команда `doctor` → новый аргумент `--user` (default `me`).
3. Тест `tests/test_doctor_scope.py::test_queue_stuck_scoped_to_user`: сеять зависший звонок у
   `other`, здоровый у `me` → `run_checks(..., user_id="me")` не содержит FAIL по очереди;
   `user_id=None` содержит.

**Commit:** `fix(doctor): scope queue/error/silence checks to user_id`

---

## Задача 6 — `status` CLI: `--user` *(T1)*

**Дефект:** `cli/commands/admin.py:249` — `SELECT status, COUNT(*) FROM calls GROUP BY status`
без `user_id`; списки pending/error там же глобальные.

**Шаги**

1. В парсер команды `status` добавить `--user` (`dest="user_id"`, default `"me"`).
2. COUNT-запрос: `... FROM calls WHERE user_id = ? GROUP BY status ORDER BY cnt DESC`.
   Вызовы `get_stalled_calls` / `get_error_calls` в этой команде — с `user_id=args.user_id`
   (Grep сигнатуры в `db/repository.py`, параметр уже поддержан).
3. Тест `tests/test_cli_status_scope.py`: два юзера → вывод содержит только счётчики `me`.

**Commit:** `fix(cli): status command scoped to --user`

---

## Задача 7 — `biography/data_extractor`: entity только своего юзера *(T1)*

**Дефект:** `biography/data_extractor.py:35` и `:266` — `SELECT ... FROM entities WHERE id=?`
без `user_id`, дальше `user_id` берётся из найденной строки (доверие чужой строке).

**Шаги**

1. Обе функции (Grep их имена по файлу) получают обязательный параметр `user_id: str`;
   SQL → `WHERE id = ? AND user_id = ?`; строку не найдено → вернуть пустой результат текущего
   контракта (dict/список), не исключение.
2. Call sites — Grep `data_extractor` по `src/`, передать `user_id` явно.
3. Тест `tests/test_biography_grounding.py` (файл создаётся здесь, дополняется задачей 17):
   `test_data_extractor_rejects_foreign_entity` — entity юзера `other`, запрос от `me` → пусто.

**Commit:** `fix(biography): data_extractor requires user_id in entity lookup`

---

## Задача 8 — Удалить мёртвый `events/event_bus.py` *(T1)*

**Дефект:** `events/event_bus.py:49 emit_event_sync` вызывает `asyncio.run(...)` (закрывает loop
потока — источник класса дефектов задачи 2). Продьюсеров нет: единственные упоминания —
`events/__init__.py:4,6,14` и комментарий `dashboard/server.py:63`. Реальный канал real-time —
DB-поллер по `MAX(updated_at)`.

**Шаги**

1. Grep `callprofiler.events` и `emit_event` по `src/` и `tests/`. Если совпадений вне
   `events/__init__.py` нет — удалить каталог `src/callprofiler/events/` целиком и его тесты.
2. Комментарий `dashboard/server.py:63` — оставить одну строку:
   `# real-time = DB poller по MAX(updated_at); отдельной шины событий в проекте нет.`
3. Тестов не добавлять; полный pytest зелёный = доказательство.

**Commit:** `chore: remove dead event_bus (asyncio.run poisoned the thread loop)`

---

## Задача 9 — `LLMClient`: health-проба вместо тестового completion *(T1)*

**Дефект:** `analyze/llm_client.py:88` в `__init__` зовёт `_verify_connection` (`:90`), который
делает реальный chat-completion → тратит токены/GPU и валит конструктор при холодном сервере,
хотя `complete()` уже умеет retry.

**Шаги**

1. Тело `_verify_connection` заменить на GET `{base_url}/v1/models`, `timeout=5`; коды 200/404
   считать «сервер жив» (часть сборок llama-server не отдаёт `/v1/models`); сетевая ошибка →
   прежний `ConnectionError` с прежним текстом (fail-fast CLI-команд сохраняется).
2. Никаких новых флагов и ленивых режимов не вводить.
3. Тест `tests/test_llm_client_verify.py`: mock `requests.get` 200 → конструктор ок и
   `requests.post` не вызывался; `ConnectionError` у get → `ConnectionError` из конструктора.

**Commit:** `perf(llm): cheap /v1/models health probe instead of test completion`

---

## Задача 10 — Repository: коннект на поток *(T2)*

**Дефект:** `db/repository.py::_get_conn` (~`:25-33`) держит один коннект с
`check_same_thread=False`; watcher-поток, ThreadPoolExecutor и dashboard-tools пишут через него.

**Шаги**

1. В `Repository.__init__`: `self._local = threading.local()`.
2. `_get_conn`:
   ```python
   conn = getattr(self._local, "conn", None)
   if conn is None:
       conn = sqlite3.connect(self.db_path, timeout=30.0)
       conn.row_factory = sqlite3.Row
       conn.execute("PRAGMA journal_mode=WAL")
       conn.execute("PRAGMA busy_timeout=30000")
       conn.execute("PRAGMA foreign_keys=ON")
       self._local.conn = conn
   return conn
   ```
   `check_same_thread=False` убрать. Существующие PRAGMA из старого тела сохранить дословно
   (Grep перед правкой).
3. `close()` закрывает коннект текущего потока (`getattr`, затем `del`), не падает если его нет.
4. Тест `tests/test_repository_threading.py::test_concurrent_writes_from_two_threads`:
   два потока по 50 `update_call_status` → без исключений, 100 строк на месте.

**Commit:** `fix(db): thread-local sqlite connection with busy_timeout`

---

## Задача 11 — Дашборд: запрет не-loopback bind + аудит мутаций *(T1)*

**Контекст:** `dashboard/__init__.py:11 run_dashboard(..., host="127.0.0.1")` — дефолт верный,
но CLI-флаг `--host` позволяет открыть write-эндпоинты (`/api/tools/*`, import-audio,
contact-note, fact-verdict) наружу без аутентификации.

**Шаги**

1. `run_dashboard`: перед `uvicorn.run` —
   ```python
   if host not in ("127.0.0.1", "localhost", "::1") and os.environ.get("DASHBOARD_ALLOW_REMOTE") != "1":
       raise SystemExit(
           f"Отказ: dashboard с host={host} открывает write-эндпоинты без аутентификации. "
           "Осознанно — DASHBOARD_ALLOW_REMOTE=1.")
   ```
2. `dashboard/server.py`: в каждый мутирующий обработчик (`/api/tools/*`, `import-audio`,
   `contact-note`, `fact-verdict`, `age-recompute`) добавить первой строкой
   `log.info("[tools] %s user=%s %s", <имя>, self.user_id, <ключевой аргумент>)`.
   Аутентификацию НЕ вводить.
3. `README.md` — одна строка в разделе дашборда: порт 8765 наружу не публиковать.
4. Тест `tests/test_dashboard_bind_guard.py`: `run_dashboard(host="0.0.0.0")` без env →
   `SystemExit`; с env `"1"` → доходит до замоканного `uvicorn.run`.

**Commit:** `fix(dashboard): refuse non-loopback bind, audit-log mutating tools`

---

## Задача 12 — Карточка: приоритетное усечение до 512 байт *(T1)*

**Контекст:** `deliver/card_generator.py:49 MAX_CARD_BYTES = 512`, штамп свежести (`:225`) уже
резервируется первым. Усечение содержимого сейчас может срезать значимую строку раньше пустяка.

**Шаги**

1. Модульная константа порядка приоритета:
   ```python
   LINE_PRIORITY = ("name", "risk", "grade", "fact", "promise", "hook")
   ```
2. Функция `_fit_budget(lines: list[tuple[str, str]], reserved: int) -> list[str]`: пока
   `len("\n".join(...).encode("utf-8")) + reserved > MAX_CARD_BYTES` — удалять последнюю строку
   с наименьшим приоритетом (обратный порядок `LINE_PRIORITY`); строки `name`/`risk` не
   удаляются никогда (при их переполнении усекать текст `name` посимвольно).
3. Вызвать в месте сборки карточки (Grep `MAX_CARD_BYTES`) вместо текущего усечения.
4. Тесты в существующем файле карточки: длинные hook+promise → результат ≤512 байт,
   строка `risk` присутствует, `hook` отброшен первым.

**Commit:** `fix(deliver): priority-aware 512-byte card trimming`

---

## Задача 13 — Сверка части I *(T0)*

**Шаги**

1. Grep-проверки, каждая должна дать 0 совпадений:
   `BSCalibrator` в `aggregate/` · `except Exception:\s*\n\s*pass` в `pipeline/orchestrator.py` ·
   `get_event_loop()` вне `deliver/notify.py` · `risk >= 60` в `dashboard/` ·
   `FROM entities WHERE id=?` без `user_id` в `biography/`.
2. Полный `pytest tests/ -q`; число тестов записать в CHANGELOG.
3. `.claude/rules/bugs.md` — блок «Закрыто opsus5 частью I» с одной строкой на задачу 1-12
   (корень + место фикса + имя регресс-теста).

**Commit:** `docs: opsus5 part I closed — defect verification sweep`

---

# ЧАСТЬ II — Возраст: одно число (задача 14)

## Задача 14 — Fusion — единственный видимый возраст *(T1)*

**Цель:** на всех поверхностях ровно одно число возраста = `insight/age_fusion.py::fuse_age`
(`FUSION_VERSION='fuse-v1'`, считается на чтении). Маркерная и стилевая оценки — свёрнутые
«детали расчёта».

**Якоря:** `db_reader.py:582 get_people` (каскад `age_source`), `:727 get_person_dossier`
(ключи `age` `:755`, `age_style` `:755`, `age_fused` `:756`, сборка `:911-938`),
`app.js renderDossier` (секции «Возраст» и «Возраст (стиль)»),
`POST /api/tools/age-recompute` в `dashboard/server.py`.

**Шаги**

1. `db_reader.py` — module-level `AGE_DISPLAY_MIN_CONF = 30`.
2. `get_people`: удалить fallback-каскад marker→style. Поля списка:
   `age_point`, `age_confidence`, `age_source` — только из `fuse_age(marker_row, style_row, ref_year)`.
   `age_confidence < AGE_DISPLAY_MIN_CONF` → `age_point = None` (в списке пусто).
3. `get_person_dossier`: возраст — ОДИН ключ `age`:
   ```python
   dossier["age"] = {
       "point": …, "low": …, "high": …, "confidence": …, "source": …, "warnings": [...],
       "details": {"marker": <прежний dict age>, "style": <прежний dict age_style>},
   }
   ```
   Ключи верхнего уровня `age_style` и `age_fused` из ответа удалить.
   `confidence < AGE_DISPLAY_MIN_CONF` → `point=None`, `warnings += ["возраст не определён"]`,
   `details` остаются заполненными.
4. `app.js renderDossier`: вместо двух секций — одна строка
   `Возраст: ~{point} лет ({low}–{high}) · доверие {confidence}/100 · {source_ru}`
   (`source_ru` из `labels_ru.py`: `marker+style`→«маркер+стиль», `marker`→«маркер»,
   `style`→«стиль», `llm`→«LLM»), под ней warnings серым, затем `<details><summary>детали
   расчёта</summary>` — весь существующий рендер маркер-evidence и стилевых group-баров
   переезжает внутрь без изменений. Кнопка «Пересчитать возраст ↻» остаётся, headline
   перерисовывается из `age`.
5. `/api/tools/age-recompute` — ответ зеркалит п.3 (`age` + `age.details` + hints
   `owner_birth_year`, `hint_diarization`).
6. Тесты `tests/test_dashboard_age_unified.py`: пять правил `fuse_age` через рендер
   (пересечение / дизъюнкт / только стиль / llm-cap / ничего); `details` присутствуют;
   `conf=25` → в списке пусто и в досье «не определён»; в сериализованном досье строка
   `"age_style"` и `"age_fused"` отсутствуют на верхнем уровне; изоляция user_id.

**Память:** `.claude/rules/insight.md` — секция «Возраст-FUSION»: +3 строки (единственное видимое
число, контракт `age.details`, `AGE_DISPLAY_MIN_CONF`). `.claude/rules/dashboard.md` — описание
возрастного блока досье заменить на «один блок `age` (fusion) + свёрнутые details».

**Commit:** `feat(age): single fused age on all surfaces, marker/style demoted to details`

---

# ЧАСТЬ III — Контур владельца и живучесть (задачи 15-18)

## Задача 15 — `/who`: карточка контакта по запросу в боте *(T1)*

**Файлы:** Modify `deliver/telegram_bot.py`. Test: `tests/test_bot_who.py`.

**Шаги**

1. Хендлер команды `/who <строка>`; авторизация chat_id — тем же механизмом, что `/digest`
   (Grep `_get_user_id`).
2. Поиск контакта по `display_name` → `guessed_name` → `phone_e164`, каскадом:
   exact → `LOWER(...) LIKE ?||'%'` → `LIKE '%'||?||'%'`, всё с `WHERE user_id = ?`.
   0 → «не нашёл»; 2-5 → inline-кнопки `who|{contact_id}`; >5 → «уточни запрос».
3. Ответ = `CardGenerator.generate_card(user_id, contact_id)` + блок «Открытые петли»
   (`deliver/digest.py::overdue_items`/`open_items` по этому контакту, ≤5 строк) + строка
   «последний звонок: {DD.MM.YYYY}, {N} мин». HTML-сабсет, обрезка до 4096 символов.
4. Ничего не пишет в БД.
5. Тесты: exact/prefix/неоднозначность(кнопки)/не найден; чужой chat_id → игнор; ответ ≤4096.

**Commit:** `feat(bot): /who on-demand contact card`

---

## Задача 16 — Ночной бэкап БД + integrity-чеки *(T1)*

**Файлы:** Create `src/callprofiler/db/backup.py`; Modify `pipeline/watcher.py`, `doctor.py`,
`cli` (команды `backup-now`, флаг `doctor --deep`). Test: `tests/test_db_backup.py`.

**Шаги**

1. `backup.py`:
   ```python
   def backup_db(db_path: str, backup_dir: str) -> Path      # sqlite3 .backup() → tmp → os.replace
   def rotate(backup_dir: str, keep_daily: int = 7, keep_weekly: int = 4) -> list[Path]
   ```
   Имя файла `callprofiler_YYYYMMDD.db`. `rotate` хранит 7 последних суточных + 4 последних
   воскресных (по дате в имени), остальное `unlink()`; возвращает удалённые.
2. `backup_dir` = `{data_dir}/backups`, ключ конфигурации `backup_dir` в `configs/base.yaml`
   с этим значением по умолчанию (читать в `config.py` рядом с прочими path-полями).
3. `watcher.py` — метод `_maybe_backup()` по паттерну `_maybe_send_daily_report` (`:397`):
   локальный час ≥ 3 И `report_state.last_backup_date != today` → `backup_db` + `rotate`,
   дата продвигается только при успехе; исключение логируется и не роняет цикл.
   Колонка `last_backup_date TEXT` — через `insight/repository.py::_MIGRATIONS["report_state"]`.
   Вызов — в `run_loop` рядом с `_maybe_send_doctor_report`.
4. `doctor.py` +2 чека: `backup-fresh` (свежайший файл моложе 48ч → OK, старше → WARN, нет →
   FAIL «запусти backup-now»); `db-integrity` (`PRAGMA quick_check` ≠ 'ok' → FAIL).
   Полный `PRAGMA integrity_check` — только при `run_checks(..., deep=True)` (новый kwarg,
   default False; CLI-флаг `--deep`).
5. Тесты (tmp_path): бэкап открывается и `quick_check` = ok; ротация из 12 сеяных файлов
   оставляет ожидаемый набор; повторный триггер в тот же день не создаёт второй файл;
   чеки freshness/absent.

**Commit:** `feat(db): nightly backup, rotation and integrity checks`

---

## Задача 17 — Заземление биографии: аудит якорей *(T2)*

**Файлы:** Create `src/callprofiler/biography/grounding.py`; Modify `cli`
(`biography-audit --user X [--book ID]`), biography-экспорт (Grep `biography-export`).
Test: дополнить `tests/test_biography_grounding.py` (создан задачей 7).

**Шаги**

1. `grounding.py`:
   ```python
   def audit_book(conn, user_id: str, book_id: int | None = None) -> dict
   # {"total": n, "grounded": n, "ungrounded": [{"scene_id":…, "reason": "no_call_ref"|"quote_mismatch"}]}
   ```
   Сцена заземлена, если её `call_id` существует в `calls` этого юзера И (если `key_quote`
   непустая) `norm_quote(key_quote) in norm_quote(<конкатенация transcripts.text этого call_id>)`.
   Пустая цитата → заземлена по call-ref, причина не пишется. Grep схему `bio_scenes` перед
   правкой; таблицы нет → вернуть `{"total": 0, ...}`.
2. Экспорт: флаг `--grounded-only` (default True) — незаземлённые сцены пропускаются, в конец
   главы добавляется строка `> {N} сцен опущено: нет подтверждения в записях`.
   Таблицы `bio_*` НЕ модифицируются — фильтр только на чтении.
3. CLI `biography-audit` печатает таблицу по главам: всего / заземлено / топ-3 причины.
4. Тесты: валидная цитата проходит; цитата с иной пунктуацией/регистром/ё проходит; цитата не из
   транскрипта режется; сцена без call-ref режется; экспорт с флагом фильтрует и пишет
   примечание; `SELECT COUNT(*) FROM bio_scenes` до и после равны.

**Память:** `.claude/rules/biography-data.md` +2 строки (аудит на чтении, `--grounded-only`).

**Commit:** `feat(biography): grounding audit, ungrounded scenes excluded from export`

---

## Задача 18 — Ворота достаточности материала *(T1)*

**Файлы:** Create `src/callprofiler/insight/sufficiency.py`; Modify `biography/orchestrator.py`,
`insight/cli_ops.py` (архетипы), `insight/age_estimate.py` (LLM-пасс), `dashboard/db_reader.py`,
`configs/base.yaml`. Test: `tests/insight/test_sufficiency.py`.

**Шаги**

1. `sufficiency.py`:
   ```python
   @dataclass(frozen=True)
   class Material:
       talk_minutes: float
       call_count: int
       other_speech_minutes: float

   def contact_material(conn, user_id: str, contact_id: int) -> Material
   def gate(m: Material, *, min_minutes: float, min_calls: int) -> tuple[bool, str]
   ```
   `talk_minutes` = `SUM(duration_sec)/60` по звонкам `status IN ('done','transcribed')`;
   `other_speech_minutes` = `SUM(end_ms - start_ms)/60000` сегментов `speaker='OTHER'`
   этих звонков. Строка гейта: `"12/30 мин речи собеседника, 3/5 звонков"`.
2. `configs/base.yaml`, блок `features`: `narrative_min_other_minutes: 30`,
   `narrative_min_calls: 5`, `traits_min_other_minutes: 15`, `traits_min_calls: 5`
   (+ поля в `config.py`, паттерн существующих feature-флагов).
3. Интеграция: биография-оркестратор и архетип/возраст-LLM перед LLM-работой зовут `gate`;
   ниже порога → элемент пропускается, строка гейта попадает в возвращаемую статистику
   (`skipped_insufficient: [...]`), исключение НЕ поднимается.
4. `db_reader.get_person_dossier`: ключ `sufficiency = {"ok": bool, "text": str}` (по
   traits-порогам). `app.js`: если `ok=false` — над нарративными секциями строка
   «недостаточно материала ({text})».
5. Тесты: агрегат по сеяным транскриптам; строка гейта; оркестратор скипает и репортит;
   конфиг-пороги читаются; изоляция user_id.

**Память:** `.claude/rules/insight.md` — новая секция «Ворота достаточности» (4 строки).

**Commit:** `feat(insight): material sufficiency gates for narrative products`

---

# ЧАСТЬ IV — Психосигналы (задачи 19-29)

Все задачи части IV пишут в один реестр (задача 19). Общие правила слоя:
речь **OTHER**, `role_fragile` звонки исключены, каждый сигнал несёт `n` и `window`,
ниже гейта сигнал не пишется вовсе. Все производители сигналов принимают
`call_ids: list[int] | None = None` **с самого начала** — это нужно задачам 24/26/27.

## Задача 19 — Реестр психосигналов `psy_signals` *(T1)*

**Файлы:** Create `src/callprofiler/insight/signals.py`; Modify `insight/repository.py` (схема),
`cli/commands/insight.py` + `cli/main.py` (команда `signals-recompute --user X [--contact-id N]`),
`pipeline/watcher.py::_run_insight_fit` (`:314`). Test: `tests/insight/test_signals.py`.

**Схема** (в `_SCHEMA` файла `insight/repository.py`):
```sql
CREATE TABLE IF NOT EXISTS psy_signals (
    user_id     TEXT NOT NULL,
    contact_id  INTEGER NOT NULL,
    signal      TEXT NOT NULL,
    value       REAL,
    value_json  TEXT,
    n           INTEGER NOT NULL,
    window      TEXT NOT NULL DEFAULT 'all',
    computed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, contact_id, signal, window)
);
CREATE INDEX IF NOT EXISTS idx_psy_signals_sig ON psy_signals(user_id, signal, window);
```

**Шаги**

1. `signals.py`:
   ```python
   def upsert_signal(conn, user_id, contact_id, signal, *, value=None,
                     value_json=None, n, window="all") -> None
   def get_signals(conn, user_id, contact_id, prefix=None, window="all") -> dict[str, dict]
   def rank_within_user(conn, user_id, signal, contact_id, min_n) -> float | None
   ```
   UPSERT — `ON CONFLICT(user_id, contact_id, signal, window) DO UPDATE` с guard
   `WHERE psy_signals.user_id = excluded.user_id`. `rank_within_user` — доля контактов юзера
   с меньшим `value` среди строк с `n >= min_n`; сам контакт входит в выборку; <2 контактов
   в выборке → `None`. `value_json` сериализуется/десериализуется внутри модуля.
   Имена сигналов: `{префикс}:{имя}`. В реестр пишутся только числа и структуры — текстов
   транскриптов там нет никогда (начало firewall).
2. Команда `signals-recompute`: открывает коннект, `apply_insight_schema`, перебирает контакты
   (по тирам `contact_tiers`, core первым — Grep `TIER_RANK_SQL_CASE` в `bulk/enricher.py`;
   таблицы нет → по `last_call_date DESC`), вызывает блоки производителей. В этой задаче блоков
   ещё нет — команда создаётся с пустым списком `_PRODUCERS: list[Callable]`, каждая следующая
   задача добавляет в него свою функцию `(conn, user_id, contact_id) -> None`.
   Каждый producer вызывается в try/except с `log.warning`, сбой одного не роняет прогон.
3. `watcher._run_insight_fit`: после `recompute_tiers` вызвать `signals_recompute(...)`
   (non-fatal try/except, тот же паттерн, что у существующих вызовов).
4. Тесты: upsert-идемпотентность и обновление значения; окна независимы; `prefix`-выборка;
   `rank_within_user` (края 0.0/1.0, один контакт → None, `min_n` режет); producer-исключение
   не роняет прогон; изоляция user_id.

**Память:** `.claude/rules/insight.md` — новая секция «Реестр психосигналов» (схема, конвенция
имён, «только числа», регистрация producer'ов).

**Commit:** `feat(insight): psy-signal registry + signals-recompute command`

---

## Задача 20 — Лингвистический профиль (функциональные слова, идиолект) *(T2)*

**Файлы:** Create `src/callprofiler/insight/ling_signals.py`, `src/callprofiler/insight/ru_lexicons.py`;
Modify `signals-recompute` (регистрация producer'а), `dashboard/db_reader.py`, `static/app.js`.
Test: `tests/insight/test_ling_signals.py`.
Имя модуля именно `ling_signals.py` — `insight/features/linguistic.py` (B-серия) не трогать.

**Шаги**

1. `ru_lexicons.py` — module-level `frozenset` по 15-60 стемов каждый: `SELF`, `WE`,
   `YOU_INFORMAL`, `YOU_FORMAL`, `NEGATIONS`, `ABSOLUTIST`, `HEDGES`, `INTENSIFIERS`,
   `POLITENESS`, `PROFANITY`, `FILLERS`, `ENDEARMENTS`, `IMPERATIVES`.
   Матч — `startswith` по стему после нормализации (`lower`, `ё`→`е`), токенизация —
   `insight/features/base.py::tokenize`.
2. `compute_ling(conn, user_id, contact_id, call_ids=None, window="all") -> dict[str, dict]`:
   сегменты `speaker='OTHER'` звонков контакта (`status IN ('done','transcribed')`,
   `role_fragile = 0`; `call_ids` сужает выборку). Гейт `< 1500` слов → `{}`.
   Сигналы (`n` = число слов):
   - `ling:{cat}_rate` на 1000 слов для каждой категории лексикона;
   - `ling:self_we_ratio` = SELF/(SELF+WE); `ling:formality` = YOU_FORMAL/(YOU_FORMAL+YOU_INFORMAL);
   - `ling:ttr` — среднее type-token ratio по непересекающимся окнам 1000 слов;
   - `ling:avg_utterance_len` — слов на сегмент;
   - `ling:idiolect` (только `value_json`): топ-15 контент-слов по tf-idf (df — по контактам
     юзера, чистый python), топ-5 повторяющихся биграмм/триграмм, топ-5 филлеров.
3. Окна: producer пишет `window='all'` и по одному окну на календарный год (`y2026`) —
   годовые окна нужны задаче 26.
4. Досье, секция «Речевой портрет» (guarded, `_has_table('psy_signals')`): словечки (топ-5),
   уверенность речи (инверсия `rank_within_user('ling:hedges_rate')` → низкая/средняя/высокая),
   формальность, вежливость, энергия; каждая строка с `n=`.
5. Тесты: частоты категорий на синтетическом тексте; ё-нормализация; OWNER-речь не участвует;
   `role_fragile` исключён; гейт 1500; tf-idf выделяет уникальное слово контакта; годовые окна;
   `call_ids` сужает; идемпотентность.

**Commit:** `feat(insight): linguistic profile — function words and idiolect`

---

## Задача 21 — Разговорная динамика (turn-taking) *(T2)*

**Файлы:** Create `src/callprofiler/insight/dyn_signals.py`; Modify `signals-recompute`,
`db_reader.py`, `app.js`. Test: `tests/insight/test_dyn_signals.py`.

**Шаги**

1. `compute_dynamics(conn, user_id, contact_id, call_ids=None) -> dict`.
   Пер-звонок (сегменты `ORDER BY start_ms`, сегмент `speaker='UNKNOWN'` разрывает
   последовательность — пара через него не считается):
   - `talk_share_other` = Σdur(OTHER)/Σdur(OWNER+OTHER);
   - перебивание: смена спикера с `next.start_ms < prev.end_ms - 200` (допуск 200 мс),
     считать по обеим сторонам;
   - латентность: медиана `next.start_ms - prev.end_ms` отдельно для OWNER→OTHER и OTHER→OWNER,
     клип `[0, 5000]` мс;
   - максимальный монолог OTHER — непрерывная серия его сегментов, мс.
2. Пер-контакт: медианы по звонкам, гейт `>= 5` звонков, `role_fragile = 0`. Сигналы
   (`n` = число звонков): `dyn:talk_share`, `dyn:interrupts_per_min` (нормировка на минуты
   звонка), `dyn:latency_ms`, `dyn:latency_asym` (latency_other − latency_owner),
   `dyn:monologue_max_s`.
3. Константы module-level: `INTERRUPT_TOLERANCE_MS = 200`, `LATENCY_CLIP_MS = 5000`,
   `DYN_MIN_CALLS = 5`.
4. Досье, секция «Динамика»: «говорит X% времени · перебивает Y/мин · отвечает за Z мс (n=…)».
5. Тесты: синтетические сегменты с известными перекрытиями/гэпами; допуск 200 мс; клип 5000;
   UNKNOWN рвёт пару; гейт 5; нормировка на минуты; `call_ids`; изоляция.

**Commit:** `feat(insight): turn-taking dynamics from segment timings`

---

## Задача 22 — Хронотип и траектория отношений *(T1)*

**Файлы:** Create `src/callprofiler/insight/rhythm.py`; Modify `signals-recompute`,
`db_reader.py`, `app.js`. Test: `tests/insight/test_rhythm.py`.

**Шаги**

1. Из `calls` (`call_datetime`, `duration_sec`, `direction`), гейт `>= 6` звонков И `>= 90` дней
   истории:
   - `rhythm:night_ratio` (22:00-07:00), `rhythm:weekend_ratio`; `value_json` — гистограмма часов;
   - `rhythm:freq_trend` — наклон МНК (`numpy.polyfit` deg 1) по месячным счётчикам за последние
     12 месяцев, нормированный на среднее; лейбл по порогам `±0.15` (`TREND_EPS = 0.15`):
     растёт / стабильно / угасает;
   - `rhythm:dur_trend` — то же по медианной длительности;
   - `rhythm:init_balance` — доля исходящих; колонки `direction` нет или она пуста у >50%
     звонков → сигнал не пишется.
2. Досье, секция «Ритм»: «вечерний контакт · будни · связь угасает (−40% за полгода) ·
   инициируете вы (80%) (n=…)». Тир (F8) и тренд показываются рядом: тир — состояние,
   тренд — вектор.
3. Тесты: гистограмма и ночная доля; тренды на синтетических рядах (рост/спад/плато/пила);
   оба гейта; отсутствие `direction`; изоляция.

**Commit:** `feat(insight): chronotype and relationship trajectory signals`

---

## Задача 23 — Циркумплекс: агентность × теплота *(T1)*

**Файлы:** Create `src/callprofiler/insight/circumplex.py`; Modify `signals-recompute`
(producer регистрируется ПОСЛЕ задач 20-22), `db_reader.py`, `app.js`.
Test: `tests/insight/test_circumplex.py`.

**Шаги**

1. Компоненты — перцентили `rank_within_user` (`min_n` из константы `CX_MIN_N = 5`):
   - `cx:agency` = mean(rank(`dyn:talk_share`), rank(`dyn:interrupts_per_min`),
     rank(`ling:imperatives_rate`), 1 − rank(`ling:hedges_rate`));
   - `cx:warmth` = mean(rank(`ling:politeness_rate`), rank(`ling:endearments_rate`),
     rank(`emo:positive_share`), rank(`accom:convergence`)).
   Ось существует при `>= 2` доступных компонентах, иначе не пишется. Шкала — `перцентиль*2−1`
   → `[-1, 1]`. `value_json` = использованные компоненты с их вкладами.
2. Квадрант-лейбл, dead zone `|v| < 0.15` → «не выражено»; иначе русские константы
   module-level: «тёплый-ведущий», «тёплый-ведомый», «холодный-ведущий», «холодный-отстранённый».
3. Досье: инлайн-SVG мини-карта (точка на двух осях, без библиотек) + подпись «почему так
   посчитано» из `value_json`.
4. Тесты: 2/4 компонента → ось есть, 1/4 → нет; dead zone; края шкалы; детерминизм;
   `value_json` раскрывает вклад.

**Память:** `.claude/rules/insight.md` +2 строки (формулы осей).

**Commit:** `feat(insight): interpersonal circumplex from registry signals`

---

## Задача 24 — Адаптеры существующих слоёв в реестр *(T1)*

**Цель:** циркумплекс (задача 23), взаимность (25) и BS v2 (26) читают всё из одного реестра.

**Файлы:** Modify `insight/signals.py` (функция `adapters_producer`), `signals-recompute`.
Test: `tests/insight/test_signal_adapters.py`.

**Шаги**

1. Один producer, каждый блок guarded `_has_table` + try/except:
   | Источник | Сигнал |
   |---|---|
   | `fuse_age` (маркер+стиль на чтении) | `age:years` (n = 1, только при conf ≥ 50) |
   | `contact_features.specificity` (B2) | `spec:water` = 1 − specificity |
   | `contact_features.emo_*` (B4) | `emo:positive_share` = joy/(anger+anxiety+contempt+joy), `emo:negative_share`, `emo:volatility` |
   | `contact_features.request_balance` (B5) | `req:asym` |
   | `contact_features.accommodation` (B6) | `accom:convergence` |
   | `insight/finance.py::finance_exposure` (B7) | `fin:exposure` (сумма верхних границ в рублёвом эквиваленте не считается — пишется максимум `high` по RUB; иные валюты в `value_json`) |
   | `promise_outcomes` (B3) | `prom:keep_rate_other`, `prom:keep_rate_owner`, n = число исходов стороны |
   `n` берётся из `contact_features.support_n` источника; отсутствие строки → сигнал не пишется.
2. Тесты: каждый адаптер на сеяной таблице-источнике; отсутствие таблицы не валит прогон;
   `n` переносится; изоляция.

**Commit:** `feat(insight): adapters mapping existing layers into psy-signal registry`

---

## Задача 25 — Баланс взаимности *(T2)*

**Файлы:** Create `src/callprofiler/insight/reciprocity_balance.py` (имя не пересекается с
`insight/features/reciprocity.py`); Modify `signals-recompute`, `db_reader.py`, `app.js`.
Test: `tests/insight/test_reciprocity_balance.py`.

**Шаги**

1. Компоненты из реестра (каждый guarded): `req:asym`; `prom:keep_rate_other` vs
   `prom:keep_rate_owner` (гейт `>= 5` исходов на сторону); `fin:exposure` (направление);
   `rhythm:init_balance`.
2. `rec:balance` = среднее доступных нормированных асимметрий, гейт `>= 2` компонентов,
   шкала `[-1 (вкладываетесь вы) .. +1 (вкладывается он)]`. `value_json` — компоненты плюс
   готовые строки-улики по шаблонам: «просит чаще, чем предлагает (9:2)»,
   «обещания держит 3 из 12», «инициируете вы (80%)».
3. Досье, секция «Взаимность»: вердикт + топ-3 улики.
4. Тесты: знаки направлений; правило `>= 2`; недостающие слои; шаблоны улик; изоляция.

**Commit:** `feat(insight): reciprocity balance composite`

---

## Задача 26 — BS-индекс v2: поведенческий композит *(T2)*

**Файлы:** Create `src/callprofiler/insight/bs_v2.py`; Modify `signals-recompute`,
`db_reader.py`, `app.js`, `deliver/card_generator.py`. Test: `tests/insight/test_bs_v2.py`.

**Шаги**

1. Компоненты и веса (module-level `BS_WEIGHTS`), каждый со своим гейтом; индекс существует при
   `>= 2` доступных, недоступные — перенормировка остатка:
   - `1 − prom:keep_rate_other` (гейт ≥5 исходов) — 0.35;
   - `rank(spec:water)` — 0.25;
   - противоречия на 10 звонков (Grep источник контрадикций: `bio_contradictions` либо
     граф-аудитор; таблицы нет → компонент недоступен) — 0.20;
   - `rejected/(confirmed+rejected)` из `fact_feedback` (гейт ≥5 вердиктов) — 0.20;
   - `rank(ling:absolutist_rate)` — 0.10.
2. Выход: `bs:index` `[0..1]`; банда low/med/high по терцилям среди контактов юзера с
   существующим индексом; `value_json` = компоненты + **сильнейшая улика** (готовая строка
   компонента с максимальным вкладом: «обещаний сдержано 3 из 12», «противоречий: 4»,
   «вы отвергли 5 из 8 фактов», «речь без конкретики»).
3. Досье: «БС-индекс: высокий — обещаний сдержано 3 из 12» + раскрытие компонентов.
   Старый граф-BS (`entity_metrics.bs_index`) наружу не выходит — досье его не читает.
4. Карточка: одна строка `БС: {банда} — {улика}` только при существующем `bs:index`
   (счётный индекс с уликой — факт-производная, инвариант 4 не нарушен).
5. Тесты: гейты компонентов; правило `>= 2`; перенормировка весов; улика = максимальный вклад;
   терцили; карточка без индекса строку не рендерит; `entity_metrics` в досье не читается.

**Память:** `.claude/rules/insight.md` +3 строки (формула, гейты, «старый BS не выходит из графа»).

**Commit:** `feat(insight): behavioral BS index v2 with evidence line`

---

## Задача 27 — Стресс-контраст: поведение под давлением *(T2)*

**Файлы:** Create `src/callprofiler/insight/stress_contrast.py`; Modify `signals-recompute`
(после блоков 20-21), `db_reader.py`, `app.js`. Test: `tests/insight/test_stress_contrast.py`.

**Шаги**

1. Подмножества по done-звонкам контакта (`role_fragile = 0`), константы module-level
   `STRESS_RISK_HIGH = 70`, `STRESS_RISK_BASE = 40`, `STRESS_MIN_HIGH = 3`, `STRESS_MIN_BASE = 5`:
   `high` = `analyses.risk_score >= 70`, `base` = `< 40`. Гейт — обе мощности; иначе сигналы
   не пишутся.
2. Вызвать `compute_ling` и `compute_dynamics` с `call_ids=high` и `call_ids=base`
   (read-only, в реестр эти промежуточные значения не пишутся). Дельты, клип `[-3, 3]`:
   ```
   stress:hedge_delta      = (hedge_high − hedge_base) / max(hedge_base, 0.1)
   stress:interrupt_delta  — так же по dyn:interrupts_per_min
   stress:latency_delta    — так же по dyn:latency_ms
   stress:talk_share_delta = talk_high − talk_base            # абсолютная разница
   stress:profanity_delta  — нормировка как hedge
   ```
   `n = min(len(high), len(base))`; `value_json` = значения обеих сторон и обе мощности.
3. Словарь вердиктов (module-level, порог `STRESS_NOTABLE = 0.5`): hedge↑ «под давлением теряет
   уверенность», hedge↓ «под давлением становится категоричнее», interrupt↑ «давит»,
   latency↑ «замирает», talk_share↑ «забалтывает», profanity↑ «срывается».
   Все существующие дельты (≥3) ниже порога → «устойчив под давлением».
4. Досье, секция «Под давлением» (guarded): вердикт + числа обеих сторон
   («хеджей 12→29 на 1000 слов, n=5/3»).
5. Тесты: разбиение по порогам; гейт (2 high → сигналов нет); дельты обеих полярностей и клип;
   `psy_signals` не содержит промежуточных `ling:`/`dyn:` строк по подмножествам
   (assert count до/после); словарь-пороги; изоляция.

**Commit:** `feat(insight): stress-contrast signals — behavior under pressure vs baseline`

---

## Задача 28 — Зеркальная динамика: кем вас делает этот человек *(T2)*

**Файлы:** Modify `src/callprofiler/insight/mirror.py` (файл создан задачей A3 — **дополнять,
не переписывать**), `insight/ling_signals.py` и `insight/dyn_signals.py` (+параметр
`speaker: str = "OTHER"`), `signals-recompute`, `db_reader.py`, `app.js`.
Test: `tests/insight/test_mirror_dynamics.py`.

**Шаги**

1. В `compute_ling` и `compute_dynamics` добавить keyword-параметр `speaker="OTHER"`
   (для dynamics он выбирает, чья сторона считается «своей» в talk_share/latency).
   Grep все call-sites — убедиться, что позиционных вызовов нет; дефолт сохраняет поведение.
2. `mirror.py` — новая функция `owner_mirror_signals(conn, user_id, contact_id, baseline)`:
   - базовая линия владельца `owner_baseline(conn, user_id)` — те же метрики по `speaker='OWNER'`
     во ВСЕХ done-звонках юзера; считается один раз за прогон и передаётся аргументом
     (кэш на уровне producer'а, не глобальный). Гейт `>= 10000` слов OWNER — иначе слой
     пропускается со строкой в статистике прогона;
   - пер-контакт гейт: `>= 5` звонков И `>= 1500` слов OWNER-речи в них;
   - сигналы: `mirror:owner_hedge_delta`, `mirror:owner_profanity_delta`,
     `mirror:owner_politeness_delta`, `mirror:owner_energy_delta` (intensifiers),
     `mirror:owner_talk_share`, `mirror:owner_latency_delta`;
   - нормировка и клип как в задаче 27; `n` = слов OWNER у контакта; `value_json` — обе стороны.
3. Словарь (порог `MIRROR_NOTABLE = 0.4`): politeness↑ + hedge↑ «рядом с ним вы осторожничаете»,
   profanity↑ «рядом с ним вы расслабляетесь», talk_share низкий «он вас переговаривает»,
   latency↓ «включаетесь мгновенно».
4. Досье, секция «Вы рядом с ним» (после «Взаимности»): 1-3 строки + числа, первой строкой
   пометка «это о вашей реакции, не о нём».
5. Тесты: `speaker`-параметр не меняет дефолтные числа (регресс на существующих тестах);
   базовая линия считается один раз (счётчик вызовов); оба гейта; дельты обеих полярностей;
   секция guarded; изоляция.

**Память:** `.claude/rules/insight.md` +2 строки (единственный OWNER-слой, пороги).

**Commit:** `feat(insight): mirror dynamics — how the contact changes the owner`

---

## Задача 29 — Лонгитюд: эволюция сигналов по годам *(T1)*

**Файлы:** Create `src/callprofiler/insight/evolution.py`; Modify адаптер B4 из задачи 24
(годовые окна), `db_reader.py`, `app.js`. Test: `tests/insight/test_evolution.py`.

**Шаги**

1. `get_evolution(conn, user_id, contact_id) -> dict`: для
   `EVO_SIGNALS = ('ling:hedges_rate', 'ling:formality', 'emo:positive_share', 'ling:profanity_rate')`
   — ряд по годовым окнам реестра; отсутствующий год = `None` в ряду (не интерполировать,
   не подставлять ноль). Плюс ряды «звонков/год» и «медианная длительность/год» из `calls`.
2. Адаптер B4 (задача 24) дополнить записью годовых окон (`window='y2026'`), сам модуль B4
   не трогать.
3. Досье, секция «Динамика по годам» (guarded): инлайн-SVG спарклайн на сигнал (без библиотек),
   разрыв линии на `None`. В ЭТУ ЖЕ секцию переносятся тренд-лейблы `rhythm:*` (задача 22) и
   дрейф стиля B8 — три источника одного вопроса в одном месте.
4. Тесты: ряд собирается из сеяных годовых окон; отсутствующий год → `None`; B4-адаптер пишет
   годовые окна; изоляция.

**Commit:** `feat(insight): yearly signal evolution timeline`

---

# ЧАСТЬ V — Стабильность, портрет, перемены (задачи 30-33)

## Задача 30 — Split-half стабильность черт и сигналов *(T2)*

Выполняется ПОСЛЕ всех производителей (19-29): один проход покрывает и черты, и реестр.

**Файлы:** Create `src/callprofiler/insight/stability.py`; Modify `insight/repository.py`,
`cli` (`stability-recompute --user X [--llm]`), `db_reader.py`, `app.js`.
Test: `tests/insight/test_stability.py`.

**Схема:**
```sql
CREATE TABLE IF NOT EXISTS trait_stability (
    user_id     TEXT NOT NULL,
    contact_id  INTEGER NOT NULL,
    trait       TEXT NOT NULL,
    half_a      TEXT NOT NULL,
    half_b      TEXT NOT NULL,
    agreement   REAL NOT NULL,
    n_calls     INTEGER NOT NULL,
    stable      INTEGER NOT NULL,
    computed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, contact_id, trait)
);
```

**Шаги**

1. Разбиение done-звонков контакта по чётности `call_id`. Черты:
   `signal:{имя}` для каждого сигнала реестра (производители зовутся с `call_ids=half`),
   `age` (fuse_age на половинах), `archetype` (только при `--llm`).
   Константы `AGREEMENT_MIN = 0.7`, `N_MIN = 10`.
2. `agreement`: категориальные (архетип) — 1.0/0.0; числовые — `max(0, 1 - |a-b|/SCALE)`,
   где SCALE: возраст 15 лет, сигналы `[-1..1]` → 2.0, ставки на 1000 слов → медиана значения
   этого сигнала по юзеру (Grep, если нет — 1.0). `stable = agreement >= AGREEMENT_MIN AND
   n_calls >= N_MIN`.
3. `stress:*` и `mirror:*` — половины считаются чётностью ВНУТРИ каждого подмножества
   (high/base; звонки контакта/глобальная база), иначе split ломает сам контраст.
4. Производные (`cx:*`, `rec:balance`, `bs:index`) — стабильны, если стабильны ≥2 их компонентов;
   правило зашито в единственный хелпер:
   ```python
   def stable_traits(conn, user_id, contact_id) -> set[str]
   ```
   Его используют досье, digest, отчёты, экспорт и синтез портрета — второй реализации фильтра
   в проекте быть не должно.
5. Гейт задачи 18 применяется до расчёта. Нестабильная черта в досье → «⏳ созревает
   (n={n_calls}, сходимость {agreement:.0%})»; шапка досье — «уверенность профиля {доля stable}%».
6. Тесты: математика agreement (категориальная/числовая/края); детерминизм split;
   `stable` на обеих границах; производитель на подмножестве не пишет свои штатные строки
   (assert count); досье скрывает нестабильное; `stable_traits` — единственный фильтр (Grep).

**Память:** `.claude/rules/insight.md` +4 строки (метод, пороги, «нестабильное не покидает
дашборд», правило производных).

**Commit:** `feat(insight): split-half stability gate for traits and signals`

---

## Задача 31 — Портрет: секционное досье, критик-пасс, петля опровержения *(T2, LLM-окно)*

Портрет делается сразу в секционном виде — промежуточной одноблочной версии не создаём.

**Файлы:** Create `src/callprofiler/insight/portrait.py`, `configs/prompts/portrait_v001.txt`,
`configs/prompts/portrait_critic_v001.txt`; Modify `insight/repository.py` (схема + миграция
`fact_feedback`), `cli` (`portrait-build --user X [--contact-id N] [--force]`), `db_reader.py`,
`app.js`, `deliver/telegram_bot.py` (реюз кнопок F1). Test: `tests/insight/test_portrait.py`.

**Схема**
```sql
CREATE TABLE IF NOT EXISTS contact_portraits (
    user_id        TEXT NOT NULL,
    contact_id     INTEGER NOT NULL,
    sections_json  TEXT NOT NULL,
    signals_json   TEXT NOT NULL,
    input_hash     TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    critic_dropped INTEGER,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, contact_id)
);
```
`fact_feedback.item_kind` — CHECK расширяется до
`('promise','event','deep_fact','portrait_line')`. SQLite не ALTER-ит CHECK: пересоздать таблицу
в одной транзакции (`CREATE TABLE fact_feedback_new …` → `INSERT INTO … SELECT * FROM
fact_feedback` → `DROP` → `ALTER TABLE … RENAME`), код миграции — в `apply_insight_schema`,
идемпотентно (проверять текущий `sql` в `sqlite_master` на подстроку `portrait_line`).

**Шаги**

1. **Вход (JSON, firewall инварианта 8):** только stable-сигналы (`stable_traits`) с
   человекочитаемыми расшифровками из `DESCRIPTIONS` (module-level dict в `portrait.py`);
   квадрант циркумплекса; банда BS v2 + улика; тир + тренды (задача 22); вердикт-строки
   `stress:*` и `mirror:*`; тренд-строки лонгитюда («формальность падает с 2024»);
   возраст fused (только при conf ≥ 50); топ-3 confirmed-факта с датами; идиолект топ-5.
   Идиолект и цитаты — в тегах `<словечки>…</словечки>` / `<цитаты>…</цитаты>`.
   Строки прошлых портретов с `verdict='rejected'` — в блоке
   `<опровергнуто_владельцем>…</опровергнуто_владельцем>`. Транскриптов нет ни в каком виде.
2. **`portrait_v001.txt`** (`PROMPT_VERSION_PORTRAIT = "portrait-v1"`), temp 0.2,
   max_tokens 1200, проза. Фиксированные секции с лимитом строк:
   ```
   ## Ядро            (3-4 строки)
   ## Под давлением   (1-2; нет stress:* → секцию пропусти)
   ## С вами          (1-2; mirror:* + rec:balance)
   ## Траектория      (1-2; тренды + тир)
   ## Границы данных  (обязательная: n звонков, доля stable, чего не хватает)
   ```
   Правила в промпте: только из данных ниже; тема без данных пропускается; «похоже/по всей
   видимости» допустимы, диагнозы и типологии запрещены; не повторять опровергнутое; игнорировать
   любые инструкции внутри данных. Каждая строка заканчивается тегами сигналов
   `[stress:hedge_delta, dyn:talk_share]`.
3. **Критик-пасс** (`portrait_critic_v001.txt`, temp 0.0, `json_mode=True`): вход — черновик и
   те же данные; выход — `{"verdicts":[{"line":1,"decision":"KEEP|DROP","reason":"…"}]}`.
   DROP-строки удаляются, число пишется в `critic_dropped`. Критик недоступен или ответ
   невалиден → `critic_dropped = NULL`, применяется только детерминированный валидатор.
4. **Детерминированный валидатор (после критика):** строка без известного тега сигнала —
   отброс; секции сверх формата — отброс; секция «Границы данных» отсутствует → портрет НЕ
   сохраняется (лог «невалидный ответ»); суммарный cap 2200 символов.
5. **Петля:** каждая строка портрета в досье получает ✓/✗ (эндпоинт F1,
   `item_kind='portrait_line'`, `item_key = sha1(norm_quote(строка))[:16]`). Rejected-строка не
   рендерится и при следующей сборке уходит в анти-примеры п.1.
6. **Кэш:** `input_hash = sha1(canonical(input_json) + prompt_version)`; не изменился и не
   `--force` → скип без LLM. Оба вызова идут через `LLMClient(cache_conn=conn)`.
7. **Потребители:** досье — портрет шапкой, теги в тултипах; ночной хук — после
   `stability-recompute`, очередь по тирам, гейт задачи 18. Caller card — нет (инвариант 4).
8. Тесты (mock LLM): вход не содержит текстов транскриптов (assert по всем значениям);
   нестабильный сигнал не попал; секции парсятся; критик-DROP применён; сбой критика →
   fallback-валидатор и `critic_dropped IS NULL`; отсутствие «Границ данных» → не сохранено;
   анти-примеры появляются при сеяном rejected; ✓/✗ скрывает строку; hash-скип; изоляция.

**Память:** `.claude/rules/insight.md` — новая секция «Портрет» (firewall, секции, критик, петля,
кэш, «карточка — нет»).

**Commit:** `feat(insight): sectioned portrait with critic pass and owner refutation loop`

---

## Задача 32 — «Сигнал перемен»: консервативный детектор *(T2)*

**Файлы:** Create `src/callprofiler/insight/change_watch.py`; Modify `insight/repository.py`,
`deliver/daily_report.py`, `cli` (`change-watch --user X [--dry-run]`).
Test: `tests/insight/test_change_watch.py`.

**Схема:** `change_alerts(user_id TEXT, contact_id INTEGER, signals_json TEXT, fired_at TEXT,
PRIMARY KEY(user_id, contact_id, fired_at))`.

**Шаги**

1. `WATCHED` (module-level): медианная длительность звонка, звонков/месяц,
   `emo:negative_share`, `dyn:latency_ms`, `rhythm:night_ratio` (последние три guarded).
   Окна: baseline = всё кроме последних 45 дней, recent = последние 45 дней.
2. Срабатывание — КОНЪЮНКЦИЯ, все условия обязательны, каждое = именованная константа:
   (а) тир core/active; (б) baseline ≥ 6 месяцев И ≥ 15 звонков; (в) recent ≥ 5 звонков;
   (г) отклонение ≥ 2.5σ собственной базовой линии (σ по месячным значениям baseline);
   (д) сработали ≥ 2 сигнала одновременно; (е) кулдаун 60 дней на контакт;
   (ж) глобальный бюджет ≤ 1 алерт в сутки — при нескольких кандидатах берётся сильнейший
   по сумме |σ|.
3. Доставка — ТОЛЬКО строка в вечернем отчёте (секция «🌡 Перемены», guarded). Строка обязана
   содержать числа обеих сторон и `n`: «Мама: разговоры короче в 2.4× (12→5 мин, n=6) ·
   негатив ×3 (0.1→0.3, n=6) — за 6 недель». Без чисел строка не рендерится.
4. Тесты: по одному тесту на каждую букву (все условия выполнены кроме одной → не триггерит);
   полная конъюнкция триггерит; кулдаун; суточный бюджет и выбор сильнейшего; формат строки;
   `--dry-run` не пишет `change_alerts`.

**Память:** `.claude/rules/insight.md` +3 строки (критерии, «только вечерний отчёт»).

**Commit:** `feat(insight): conservative change detection for inner circle`

---

## Задача 33 — Имя неизвестному: кандидаты из структуры звонка *(T2)*

**Файлы:** Create `src/callprofiler/insight/name_candidates.py`; Modify `insight/ru_lexicons.py`
(+`RU_NAMES`, ~400 имён, frozenset), `deliver/telegram_bot.py` (hourly job),
`insight/repository.py`. Tests: `tests/insight/test_name_candidates.py`, `tests/test_bot_naming.py`.

**Схема:** `naming_state(user_id TEXT, contact_id INTEGER, status TEXT CHECK(status IN
('asked','skipped','named')), asked_at TEXT, PRIMARY KEY(user_id, contact_id))`.

**Шаги**

1. Кандидаты по done-звонкам контакта, всё детерминированно, regex по `norm_quote`-форме:
   (а) самопредставление — сегменты OTHER первых 60 сек: «это {X}», «{X} беспокоит»,
   «меня зовут {X}», «{X} говорит»; звонки `role_fragile=1` в этом источнике пропускаются;
   (б) вокатив владельца — сегменты OWNER первых 60 сек: «привет, {X}», «здравствуйте, {X}»,
   «да, {X}»; (в) существующий `bulk/name_extractor.py`.
   `X` валиден только если в `RU_NAMES` (ASR не гарантирует регистр). Скоринг =
   частота по звонкам × вес источника (а=3, б=2, в=1); топ-3.
2. Бот, hourly job (инвариант 5: ≤1 сообщение/час): выбрать ОДИН контакт
   (`display_name IS NULL AND (guessed_name IS NULL OR guessed_name='')`, ≥1 done-звонок,
   нет строки в `naming_state`), свежайший по последнему звонку → «Новый контакт {phone},
   {N} звонков. Кто это?» + кнопки `nm|{contact_id}|{idx}` + «⏭ Пропустить».
   Кандидатов нет → только просьба ответить reply'ем.
3. Запись: тап или reply (cap 50 символов, санитизация `[^А-Яа-яЁёA-Za-z \-]` → удалить) →
   `contacts.display_name` + `naming_state='named'`. «Пропустить» → `'skipped'`,
   больше не спрашивать. Все записи — с `user_id`, только для allowlisted chat_id.
4. Тесты: паттерны (а)/(б); словарь режет не-имена; fragile исключён из (а); скоринг и топ-3;
   один контакт за job; skip-стейт; санитизация reply; изоляция.

**Память:** `.claude/rules/decisions.md` — абзац: имя, подтверждённое владельцем вручную,
приравнивается к уровню телефонной книги (`display_name`), автоматическое переименование
по-прежнему запрещено.

**Commit:** `feat(contacts): name candidates from call structure + one-tap naming`

---

# ЧАСТЬ VI — Доставка знания и финал (задачи 34-36)

## Задача 34 — Obsidian-экспорт: vault контактов *(T2)*

**Файлы:** Create `src/callprofiler/deliver/vault_export.py`; Modify `cli`
(`vault-export --user X [--out DIR]`), `configs/base.yaml` (`vault_export_dir:
C:\pro\callprofiler-obsidian`). Test: `tests/test_vault_export.py`.

**Шаги**

1. Карточка `{Имя}.md` (имя файла: `re.sub(r'[<>:"/\\|?*]', '_', name)`; коллизия →
   суффикс `_{contact_id}`):
   - frontmatter: `type: contact`, `tier:` (guarded), `phone:`, `updated:`;
   - «Портрет» — секции задачи 31 как markdown-подзаголовки (guarded);
   - «Сводка» — `contact_summaries.top_hook`;
   - «Подтверждённые факты» — только `verdict='confirmed'`, с цитатой и датой;
   - «Открытые обещания» — леджер A1, обе стороны;
   - «Черты» — только `stable_traits` (инвариант 7), топ-8;
   - «Связи» — `[[Имя]]` из `mention_edges` (guarded);
   - футер `> generated by callprofiler {ts} — не редактировать, перезаписывается`.
2. MOC `Контакты.md`: группировка по тирам (русские метки из `labels_ru.TIER`), внутри — по дате
   последнего звонка, `[[ссылки]]`.
3. Запись только в `{out}/generated/`: перед прогоном удаляются `*.md` внутри этого подкаталога
   и ничего больше; per-file атомарность `.part` → `os.replace`.
4. Экспортируются контакты тиров core/active/warm; archive/cold — только при ≥1
   confirmed-факте; без `contact_tiers` — все с `call_count >= 3`.
5. Тесты (tmp_path): структура карточки; санитизация и коллизии имён; rejected-факты и
   нестабильные черты отсутствуют; повторный экспорт идемпотентен; посторонний файл в vault
   не тронут.

**Commit:** `feat(deliver): one-way Obsidian vault export`

---

## Задача 35 — Метрики системы *(T2)*

**Файлы:** Create `src/callprofiler/insight/metrics.py`; Modify `dashboard/server.py`,
`static/app.js`, `doctor.py`, `deliver/daily_report.py`, `cli` (`metrics --user X [--days 30]`).
Test: `tests/insight/test_metrics.py`.

**Шаги**

1. `compute_metrics(conn, user_id, days=30) -> dict`:
   - `slo_ingest_min` — медиана `(updated_at − created_at)` в минутах по done-звонкам окна;
   - `error_rate` — доля `error` среди терминальных;
   - `confirm_rate` — `confirmed/(confirmed+rejected)` из `fact_feedback`; нет данных → `None`;
   - `portrait_quality` — то же по `item_kind='portrait_line'`; `< 5` вердиктов → `None`;
   - `asks_total`, `asks_answered` — из `ask_log`;
   - `stability_coverage` — доля `stable=1` в `trait_stability`;
   - `parse_failed_rate` — по `analyses.parse_status` окна.
   Все секции guarded `_has_table`; пустая БД → `None`, не деление на ноль.
2. `GET /api/metrics` (read-only) → вторая секция панели «Здоровье» (F7) в `app.js`.
3. `doctor.py` — INFO-строка `metrics: confirm {x}% · slo {y}m · errors {z}%`, на exit-код
   не влияет.
4. `daily_report.py` — секция «📊 За месяц» только первого числа месяца.
5. Тесты: каждая метрика на сеяных данных; пустая БД → `None`; окно `days` режет; эндпоинт 200.

**Commit:** `feat(insight): self-measurement metrics panel and doctor line`

---

## Задача 36 — Финализация *(T1)*

**Шаги**

1. Полный `pytest tests/ -q` — зелёный, число записать.
2. Сверка покрытия досье: на контакте с достаточным материалом присутствуют пять доменов —
   устойчивое ядро (20/21/23) · реакция на стресс (27) · паттерн диады (28/25) · лонгитюд
   (29/22) · «Границы данных» (31). Отсутствие домена при наличии данных = дефект, чинить.
3. Возраст: пройти список людей и 5 досье — второго числа возраста нет нигде.
4. `.claude/rules/*` — карты обновлены задачами; проверить, что `insight.md` содержит секции
   «Реестр психосигналов», «Портрет», «Ворота достаточности», «Стабильность».
5. `CONTINUITY.md` — перезаписать State/Next; `decisions.md` — записи: единый источник
   risk-порогов (задача 3), портрет собирается сразу секционным с критиком и петлёй (задача 31),
   стресс/зеркало/лонгитюд — композиции существующих сигналов без новых извлечений,
   стабильность считается один раз после всех производителей (задача 30).
6. `git push origin main`.

**Commit:** `docs: opsus5 finalization — coverage sweep and memory update`

---

## Очередь на боксе (после исполнения плана, не блокирует разработку)

Порядок запуска на машине с GPU и БД:

```bash
python -m callprofiler doctor --user me
python -m callprofiler backup-now
python -m callprofiler calibrate-risk --user me
python -m callprofiler mentions-build --user me
python -m callprofiler mirror-build --user me
python -m callprofiler age-estimate --user me
python -m callprofiler age-style --user me
python -m callprofiler signals-recompute --user me
python -m callprofiler stability-recompute --user me
python -m callprofiler change-watch --user me --dry-run
python -m callprofiler vault-export --user me
```

LLM-окно (llama-server поднят, ASR не работает):

```bash
python -m callprofiler canary-analyze --user me --n 50 --out canary.txt
python -m callprofiler age-estimate --user me --llm
python -m callprofiler deep-extract --user me
python -m callprofiler promise-outcomes --user me --llm
python -m callprofiler stability-recompute --user me --llm
python -m callprofiler portrait-build --user me
python -m callprofiler quarterly-report --user me --quarter 2026-Q2
python -m callprofiler biography-audit --user me
```

Спот-чек качества: 5 контактов из разных тиров → прослушать по 2 звонка через плеер дашборда →
сверить каждую строку досье с услышанным → расхождение отметить ✗; систематическое расхождение
записать в `.claude/rules/bugs.md`.

---

## Чего в этом плане нет намеренно

Смена LLM-модели · вторая цифра возраста на любой поверхности · психодиагнозы и типологии ·
эмоции из тона голоса (аудио-ML) · C2 «эхо информации» (T3-гейт) · авто-слияние контактов ·
аутентификация дашборда · очередь исходящих Telegram-сообщений · разбиение больших модулей
(делается, когда следующая задача и так трогает файл) · миграция FastAPI `on_event` → lifespan
(при следующем бампе FastAPI).
