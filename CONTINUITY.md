# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history preserved in git. Overwrite each session; append-only logs live in CHANGELOG.md.

**Goal (incl. success criteria):**
- Рабочий локальный pipeline `C:\calls\in` → текст (GigaAM v3) → БД → LLM-анализ (Qwen) → дашборд/Telegram.
- **Доктрина дашборда (юзер, 2026-06-11): 2 функции** — ход обработки + полный психопортрет личности
  («нажал имя — знаешь всё»: risk, BS-index, архетип, возраст (fusion: маркеры+kin+стиль), паттерны, факты).

**Workflow (durable):**
- Claude **коммитит и пушит в `main` БЕЗ пер-действенного согласования** (2026-06-04).
- **Каждый значимый шаг сперва в файлы памяти**, **потом** `commit`+`push origin main`.
- **Кратко, по делу, без воды** (2026-06-05). Карты `.claude/rules/*` вместо перечитывания кода.
- **Model Routing v2 (2026-06-10):** тир = blast radius; T0/T1 без субагентов; объявлять тир.

**Constraints/Assumptions:**
- 100% local. Windows. LLM = llama-server @127.0.0.1:8080 (Qwen3.5-9B Q8_0). SQLite, no ORM,
  каждый запрос `user_id`. Код пишем ЗДЕСЬ (без GPU/моделей/данных), запускаем на боксе.
- `data_dir = C:\calls\data`. Лог: `C:\calls\callprofiler.log`.
- **GPU sequential (Hard Constraint):** ASR+pyannote и LLM НИКОГДА одновременно (12GB RTX 3060).

**State (2026-08-21) — облачный routine, первый реальный запуск: extras-баг + WAL-restore баг:**

☁ **Первый реальный автономный прогон в облаке нашёл, что предпосылка «облако дёшево, без
ML-стека» (2026-08-08) была измерена НЕВЕРНО.** `pip install -e ".[cloud]"` реально ставил
ПОЛНЫЙ ML-стек (torch/pyannote.audio/faster-whisper/soundfile/librosa) — extras в pip только
добавляют пакеты к `dependencies`, не могут их исключить, а ML-стек жил в безусловных
`dependencies`. Прежнее «1415 passed, 0 failed» было измерено симуляцией отсутствия torch, не
реальной командой — расхождение никогда не всплывало. Заодно нашёлся реальный дефект в уже
закрытом T-20: `restore_backup()` не чистил `-wal`/`-shm` sidecar-файлы перезаписываемого
назначения → после restore счётчики строк молча откатывались к состоянию ДО restore (реплей
чужого WAL). Оба фикса + путь-санитайзер (`_resolve_incoming_dst`, платформозависимый traversal
на POSIX) + отсутствующий `pytest-asyncio` — детали `CHANGELOG.md` 2026-08-21, `bugs.md`.

**Обе базовые линии перепроверены РЕАЛЬНОЙ установкой в чистый venv (не симуляцией):**
`.[cloud]` → **1415 passed, 7 skipped, 0 failed**. `.[dev,full]` → **1459 passed, 3 skipped,
0 failed**. Числа не изменились относительно заявленных 2026-08-08, но теперь действительно
верны — раньше были недоказаны.

**PR #18 ВЛИТ в `main` 2026-08-21 (`b17629c`), PR #17 закрыт как superseded** (две облачные
сессии в один день сделали один и тот же WAL-sidecar фикс; #18 — строгое надмножество #17:
+ extra `full`, + `tools.py` traversal-нормализация). Ветка `claude/adoring-mendel-b281nh`
больше не нужна. CI `test (3.10)`/`test (3.11)` красные НЕ из-за диффа:
`.github/workflows/ci.yml:27` `apt-get install -y ffmpeg ffprobe` — `ffprobe` не apt-пакет,
идёт внутри `ffmpeg`; сломано для любого PR/push. Однострочный фикс ещё не запушен (owner
decision: починить или удалить workflow, если его заменил routine).

**Аудит статуса плана 2026-08-21 (16 агентов по коду, не по ledger; T-01/T-02/T-10/T-13 —
ручная сверка):** 11/26 закрыты подтверждено (42%), 15 осталось. Три «закрытых» с дырками:
- **T-18:** `dashboard/tools.py::_reprocess_sync` → `repo.get_error_calls(max_retries)` БЕЗ
  `user_id` + `Orchestrator.retry_errors()` без user-scope → кнопка «Reprocess» в дашборде
  ретраит error-звонки ВСЕХ профилей. На одно-профильном боксе безвредно, DoD T-18 («только
  выбранный call/user») нарушен. Маленький фикс: прокинуть `user_id` в оба.
- **T-08:** `deliver/card_generator.py:332` пишет карточку `Path.write_text` напрямую, мимо
  `artifacts.atomic_write_text` — частичный артефакт виден при краше; теста нет.
- **T-20/T-04 (ledger сам признаёт):** чек backup в `doctor` не добавлен; ~60 безусловных
  `commit()` вне `repository.py`.
Частичная подложка у «незакрытых» (не ноль): T-06 `purge_user` покрывает 12 таблиц, но нет
манифеста артефактов/удаления файлов, `llm_calls`/`ask_log`/`reminders` не чистятся; T-07
`retry_errors` = immediate retry, нет `next_retry_at`/backoff; T-12 только `_unload_models()`,
нет координатора/state machine; T-14 `prompt_budget.py` клип есть, нет `PromptInput`/envelope/
owner-alias из профиля; T-15 парсер tolerant-repair (обратное strict-схеме). T-11/T-16/T-17/
T-19/T-21/T-22/T-23/T-24/T-25 ≈ ноль.

**Следующий шаг: T-07** (durable jobs/attempts/retry-backoff, P0, зависимости T-04/T-05 закрыты;
брать вертикальным срезом — transition table + `next_retry_at`/backoff+jitter в `retry_errors()`),
попутно закрыть T-18 `user_id` в reprocess (тот же `retry_errors`). Альтернатива — T-06.

**State (2026-08-08) — ИСПОЛНЕНИЕ `docs/sintezdiharea.md`, оркестрация:**

🚀 **Новая входная точка исполнения — `docs/sintezdiharea.md`** (доказательная спецификация
доведения до production-ready; ревизии 2 и 3 сверены с кодом). Она **не отменяет** `opsus5.md`
как каталог продуктовых задач, но идёт ПЕРЕД ним: сначала фундамент correctness/recovery
(T-00…T-25), продуктовые и психологические фичи — после CP-5.

- **CP-0 пройден.** C-01…C-05 приняты и записаны в `docs/decisions/CP-0-contracts.md`
  (делегация владельца 2026-08-08): GigaAM primary + Whisper fallback · карточка 512 UTF-8 байт ·
  pyannote = модель 3.1 + runtime 4.0.4 (решение владельца 2026-08-07 зафиксировано, не
  переоткрывается) · Telegram opt-in с whitelist полей · прямой push в `main`.
  **`CONSTITUTION.md` приведена в соответствие 2026-08-08** по распоряжению владельца
  (Ст. 16 не задействована — исправлены только фактические ярлыки, Ст. 19.1). `AGENTS.md`
  приведён ранее в T-02. Расхождений документов с кодом по CP-0 больше нет — автономный
  прогон в них не упрётся.
- **Закрыты:** T-10 (S0 — утечка reference embedding между профилями, `bugs.md` 2026-08-08),
  T-01 (torch убран из package init → `doctor` живёт без ML-стека; typed config preflight),
  T-00 (пины/dev-группа/`python -m pytest` без `PYTHONPATH`/baseline-отчёт),
  T-02 (`AGENTS.md` под CP-0; расхождения `CONSTITUTION.md` — приложением в CP-0-документе,
  сам файл не тронут — ждёт владельца), T-03 (ownership во всех мутаторах + `identity.py` +
  inventory-тест по интроспекции), T-04 (`db/connection.py` + `db/uow.py`, границы транзакций
  в сценариях, `busy_timeout` на writer), T-08 (`artifacts.py` — атомарная публикация;
  транскрипты больше не перезаписываются между профилями).
- **T-05 закрыт:** `db/migrations.py` — 9 миграций с журналом и контрольными суммами, ни одного
  `except: pass`; FTS починен (убран `user_id` из индекса, `rebuild` работает); межвладельческие
  ссылки отвергает сама БД (триггеры, не composite FK — SQLite потребовал бы пересборки
  центральных таблиц). Гейт бэкапа переделан на самовзводящийся — как параметр он был мёртв.
- **T-18 закрыт:** профиль резолвится на запрос из валидированной cookie (`_USER_ID` больше не
  мутируется), жёсткий loopback, CSRF+Origin на мутациях, потоковый upload, lifespan вместо
  `on_event`. Значение cookie ВАЛИДИРУЕТСЯ по таблице `users` — без этого клиент назначал бы
  себе tenant-идентичность сам.
- **T-13 закрыт:** конструктор `LLMClient` не ходит в сеть (liveness/readiness разведены),
  `user_id` и `model_fingerprint` в ключе кэша, `ask_log` уникален по паре, усечённые ответы
  больше не кэшируются. Карта `llm.md` обновлена.
- **T-20 закрыт** (`ops/backup.py` + CLI `backup`/`verify-backup`/`restore`): снимок только через
  SQLite online backup API, обязательная верификация ДО публикации, манифест с SHA-256,
  retention по манифесту. **Это гейт: T-05 на боевых данных без него не запускать.**
  Осталось: добавить чек backup в `doctor.py` (файл был занят другим агентом).
- **Остаток T-04 (осознанный, не потерян):** ~60 мест вне `repository.py` коммитят безусловно
  (`biography/repo.py`, `insight/*`, `graph/repository.py` ×3, `deliver/reminders.py`, `ask.py`,
  `llm_cache.py`, `dashboard/tools.py`, CLI) — не на пер-звонковом пути, список в CHANGELOG.
- **Правки оркестратора поверх агентов (все — реальные дефекты, повторяющийся класс fail-open):**
  сторож отпечатка в `_diarize_batch` был `getattr(..., expected_fp)`; `torch>=2.9.1` в
  `pyproject.toml` исключал боевой бокс (torch 2.6.0+cu124) — floor снят у torch и numpy;
  `delete_calls` имел `user_id=None` **дефолтом** — кросс-тенантное удаление по умолчанию,
  теперь параметр обязателен. Отдельно: агент T-02 отчитался о правках `AGENTS.md`, которых
  на диске не было (`git diff` пуст) — сделано вручную. **Вывод для будущих сессий: отчёт
  субагента не доказательство; проверять `git diff` и пересчитывать метрику самому.**
- Тесты: **1317 passed, 3 skipped** (3-й скип — нет ffmpeg на dev-машине, штатно).
  `ruff`: 163 замечания зафиксированы как known-fail ledger, не исправлялись.

☁ **Готово к автономному облачному прогону (2026-08-08).** Routine раз в 6 часов при выключенной
машине владельца; промпт и подготовка — `docs/routines/continue-sintezdiharea.md`.
- Установка в облаке: `pip install -e ".[cloud]"` (~40МБ, без ML-стека).
- **Две базовые линии:** облако — `1415 passed, 7 skipped`; локально с ML — `1459 passed, 3 skipped`.
  Разница — три файла ML-тестов, которые в облаке не собираются (`pytest.importorskip`). Это норма.
- Для этого убраны три eager-импорта ML: `WhisperRunner` на верхнем уровне `orchestrator`,
  создание ASR-runner в `Orchestrator.__init__` (теперь ленивое свойство), `_ref_fingerprint`
  вынесен в `artifacts.py`. Мерилось заглушкой torch, а не предполагалось: до правок было
  5 несобираемых файлов и 57 падений.
- **Ограничение:** S0-регресс утечки reference-эмбеддинга в облаке покрыт частично — сторож
  в `_diarize_batch` проверяется, сам runner нет.

**Следующие по критическому пути:** T-02 (документные ревизии под CP-0) → T-03 (tenant identity
и ownership API) → T-04 (SQLite UoW) → T-20 (verified backup) → T-05 (versioned schema).
Порядок обязателен: T-05 не запускать на боевых данных до рабочего T-20.

---

**State (2026-08-07):**

✅ **Диаризация: решение — остаёмся на pyannote 3.1** (задача `/gaol`, T1, без субагентов).
Исследован лучший вариант под бокс (Win 10, RTX 3060 12GB, Python 3.10+torch 2.6):
`pyannote/speaker-diarization-community-1` (4.0) выигрывает DER на 6 из 7 датасетов
(AliMeeting 20.3 vs 24.5, CALLHOME 26.7 vs 28.5, DIHARD3 20.2 vs 21.4, AMI IHM 17.0 vs 18.8,
MSDWild 22.8 vs 25.4, REPERE хуже 8.9 vs 7.9). NeMo — несовместим (Python 3.12+/torch 2.7+/
Linux), pyannoteAI Precision-2/Live-1 — только облако (Статья 4), WhisperX запрещён.
**Юзер: «Оставить 3.1, ничего не менять».** Подробности: CHANGELOG 2026-08-07.

✅ **Интерактивная схема архитектуры v5** (`ARCHITECTURE_SCHEMA.html`, T1, без субагентов).
Статичная устаревшая схема (пути D:\calls, биография «8 проходов») переписана на месте:
самодостаточная SVG-диаграмма (инлайн CSS/JS) по `ARCHITECTURE_v5.md` — 6 слоёв, 21 узел
(тултипы, клик → описание + его потоки), 24 ребра, 7 потоков данных в панели справа
(pipeline, bulk-load/enrich, граф/BS-index, возраст Ф0–Ф3, биография 11 фаз, дашборд/SSE,
CLI); выбор потока подсвечивает весь маршрут. JS провалидирован (`node --check`), найдены и
исправлены 2 дефекта (дубль "e" в id рёбер; `f.edges` отсутствовал — считаем из EDGES).
Коммит: `main` (доктрина: коммит+push без согласования).

**Прежние сессии (сжато):** Age Ensemble v2 (2026-07-03, 810 passed) · age_style Ф0-Ф5 +
marker-vs-style фикс (2026-07-01/02) · STRATEGIC_PLAN_v5 + ozalupennieStrategic5.md
(2026-07-02) · прогон на боксе стартовал, 2 краша закрыты (psutil, no such column — bugs.md
2026-07-02) · русификация характеристики · досье Ф0-Ф4.

**Next:**
1. **Бокс:** pull → задать `owner_birth_year` в base.yaml (иначе реляционные якоря и часть kin
   мертвы) → полный пересчёт возраста: `age-estimate --user me` + `age-style --user me`
   (TABLE/RULES v2 = кэш-строки перезапишутся) — или кнопкой из досье.
2. Спот-чек 10 знакомых контактов: fused-возраст в интервале? топ-вклады осмысленны? kin-сигналы
   не мусорят? (таблицы v2 — экспертные приоры, ждать грубую точность, vozrast.md §13).
3. В LLM-окне: `age-estimate --user me --llm` (LLM-пасс поверх, memoized).
4. Продолжить прогон бокса (make-characteristics/дашборд) + визуально проверить блок возраста
   (fused-строка, кнопка, hints).
5. После стабилизации: `ozalupennieStrategic5.md` (Ф0 → Ф-A → …).
- ОТЛОЖЕНО: калибровка вероятностных таблиц на реальных данных (§15); kin_child словесные
  числительные («сыну тридцать» — сейчас только цифры); per-conversation ось B (темпер. байес,
  contact_age_evidence); age_band как ось кластеризации; Ф4-dominance; Stage-2 биография.

**Open questions (UNCONFIRMED):**
- Сохраняет ли GigaAM филлеры («типа/значит») в транскрипте — от этого зависит ось discourse
  (проверить на боксе: плотность хитов discourse в реальных строках contact_age_style).
- Валидность tempo на реальных таймстампах (fixed-window сегменты vs pyannote-turn'ы).
- VRAM-footprint Qwen 9B Q8_0. Калибровка `bs_thresholds`.

**Working set:**
- `ARCHITECTURE_SCHEMA.html` (интерактивная схема v5) · `ARCHITECTURE_v5.md` ·
  `docs/superpowers/plans/2026-07-03-age-ensemble-v2.md` · `fixager.md` (исполнен) ·
  `.claude/rules/insight.md` · `vozrast.md`
**State (2026-07-17) — прежняя сессия (remote, сохранено при merge):**

✅ **Портфель `ozalupennieStrategic5.md` (A1-A7/B1-B8/C1,C3/D1-D3) исполнен** — каждая строка
имеет коммит (сверено по `git log`, 2026-07-17); C2 — единственный задокументированный пропуск
(T3-гейт, decisions.md). Код-side финализация закрыта (kill-criteria в dashboard.md, decisions.md
покрывает BS-v2/C2). **Не прогнано на боксе** (нужна реальная БД + LLM-окно, команды):
`age-estimate --user me --llm` · `deep-extract --user me` · `promise-outcomes --user me --llm` ·
`quarterly-report --user me --quarter YYYY-Qn` · `calibrate-risk --user me` ·
`mirror-build --user me` · `mentions-build --user me` (последние 3 — numpy/SQL-only, не LLM, но
нужны на реальных данных). См. также «Бокс» ниже (age-style v2, canary M4).

✅ **`OzaluplivanieFable2.md` — мастер-план (Fable-ревизия 3), входная точка исполнения**
(scheduled replan, Fable/max). Supersedes `OzaluplivanieFable.md` (ревизия 2, F1-F27 + инварианты
16-25 + §8 транспорт — действуют по ссылке), который supersedes `ozalup2.md`. Новое в ревизии 3:
- **Qwythos-9B-Claude-Mythos-5-1M ОТКЛОНЁН** (§9.2): self-reported бенчи с базой 0.232 MMLU
  (ниже случайного = сломанный харнесс), greedy-decoding деградация vs наш temp 0.0-0.3 JSON-режим,
  ноль RU-заявлений, 1M ctx бесполезен, blast radius смены HIGH. Инвариант 27: модель зафиксирована;
  пересмотр только через canary-протокол §9.3 (задача 59a, ТОЛЬКО по команде юзера).
- **F28 единый возраст** (инвариант 26): fuse_age = единственное видимое число на всех поверхностях;
  маркер/стиль → свёрнутые «детали расчёта»; AGE_DISPLAY_MIN_CONF=30.
- **F29-F32 психоглубина**: стресс-контраст (high-risk vs baseline дельты), зеркальная динамика
  (OWNER-дельты — единственный легальный OWNER-слой), лонгитюд по годам, портрет v2 (5 секций,
  критик-пасс, петля ✓/✗ строк, portrait_quality в F13). «Уровень психоаналитика»
  операционализирован в §10 (5 доменов, фальсифицируемость, ✓-rate ≥0.8).
- Вставки в порядок Fable §2 суффиксами: 19a, 56a-56d, 59a — старые номера/кросс-ссылки не ломаются.

**Прежняя State-запись (2026-07-05, сжато):** `ozalup2.md` — слияние
`ozalupennieStrategic5.md` (портфель Ф0→A→B→C→D, тела задач остаются там) с аудитом
https://github.com/Zackriya-Solutions/meetily (клонирован, изучены backend/Rust-ядро/фронт).
ozalup2.md = входная точка исполнения для Sonnet, supersedes oz5. Состав:
- **Новые задачи M1-M8** (полные спеки в §3, якоря проверены по коду 2026-07-05):
  M1 `doctor` (преполёт env/schema — класс бокс-крашей из bugs.md), M2 аудио-плеер в дашборде
  (`calls.audio_path` schema.sql:36 + seek по `start_ms`), M3 мемоизация analyze-пути
  (llm_cache; retry УЖЕ есть — llm_client.py:119; реализует decisions.md 2026-06-04 #1),
  M4 `response_format: json_object` + canary-харнесс (флаг default OFF, решение юзера на боксе),
  M5 drag&drop импорт аудио → C:\calls\in (без python-multipart, raw body; security-review
  обязателен), M6 заметка владельца (contact_notes, tools-канал), M7 error_message в UI,
  M8 deep-extract map-reduce длинных звонков (СВОЯ таблица deep_facts, НЕ events/graph —
  replay-инвариант; прецедент B2).
- Единый порядок §2 (M-задачи вплетены в Ф0+/Ф-A/Ф-B), поправки к oz5-задачам §4 (A2/B3/D3 —
  инъекция-гард + json_mode; 0.3 — audio_path), новые инварианты 12-15, карта «взято из meetily»
  §5, отвергнутое §6 (их LLM-стек — по указанию юзера; VAD/confidence — T3-кандидаты).
- Meetily-клон в scratchpad (временный, можно удалить).

**Прежние сессии (сжато):** Age Ensemble v2 реализован (fixager P1-P9 + маркеры/kin v2 + стиль-оси
v2 + fusion, 810 passed; 2026-07-03) · age_style Ф0-Ф5 (2026-07-01/02) · STRATEGIC_PLAN_v5 +
ozalupennieStrategic5.md (2026-07-02) · бокс-прогон стартовал, 2 краша закрыты (psutil, no such
column — bugs.md 2026-07-02) · досье Ф0-Ф4 · русификация.

✅ **`opsus5.md` — сводный план исполнения (2026-07-25), НОВАЯ входная точка.** Supersedes
`OzaluplivanieFable2.md`/`OzaluplivanieFable.md`/`ozalup2.md`/`NeErrorsGR.md` как рабочий список:
36 самодостаточных задач, тела внутри файла (в старые планы ходить не нужно). Состав: часть I —
13 дефектов (все якоря сверены по коду 2026-07-25: `payload`/`what` в summary_builder:421-459,
`get_event_loop` без fallback orchestrator:558, BSCalibrator на risk summary_builder:80,
`except: pass` orchestrator:621/625, doctor:253-317 без user_id, admin.py:249 глобальный COUNT,
data_extractor.py:35/266 без user_id, risk-литералы db_reader:311/452 + app.js:963/1136,
мёртвый event_bus, LLMClient._verify_connection тратит токены, общий коннект
`check_same_thread=False`, dashboard bind, 512-байт усечение карточки); часть II — F28 единый
возраст; III — F22/F23/F11/F9; IV — реестр психосигналов и производители (F14-F20, F29-F31);
V — F10 стабильность/портрет/F25/F27; VI — F12 vault, F13 метрики, финализация + бокс-очередь.
Отличия от прежних планов: единый источник risk-порогов на все 3 поверхности вместо трёх шкал ·
`call_ids=` в производителях сигналов с рождения (не ретрофит) · стабильность считается ОДИН раз
после всех производителей · портрет собирается сразу секционным с критиком и петлёй (v1-итерация
не создаётся) · имена модулей без коллизий с `insight/features/*`.

**Next:**
1. **Исполнение `opsus5.md` по номерам задач 1→36** (Sonnet). Каждая задача: pytest зелёный →
   CHANGELOG → карта `.claude/rules/*` (где указано) → commit+push.
2. *(историческая справка)* Прежняя входная точка — `OzaluplivanieFable2.md` (порядок Fable §2:
   0.1 → 0.2 → M1 → … → 19a(F28) → … → 56a-56d → …). Каждая задача: pytest зелёный →
   CHANGELOG → commit+push. 59a (canary смены LLM) — НЕ исполнять автономно.
   **В процессе (автономный прогон начат 2026-07-16, юзер авторизовал полную автономию
   2026-07-17 — не останавливаться, не спрашивать):** сделаны 1-21 (0.1 гейт · 0.2 feedback-петля
   · M1 doctor · 0.3 spotcheck-sample · M2 аудио-плеер · 0.4 role-UNKNOWN% · role-fragile флаг
   (инлайн №7) · M3 llm_cache · M4 json_mode+canary-analyze · A1 obligations-digest — БЕЗ
   Telegram-пуша, см. decisions.md · A2 `ask` по архиву + инъекция-гард §4.1 · A4 risk_thresholds
   — фикс BS-index-подмены, dashboard-очистка отложена, см. decisions.md · A6 карточка v2 —
   due/grade/call/freshness-штамп, канон имени файла, интерпретации в decisions.md · M5
   drag&drop импорт аудио — security-reviewed, 1 HIGH исправлен (Windows reserved names) · M6
   заметка владельца — contact_notes, tools-канал, секция досье · M7 error_message на виду,
   без retry-кнопки — YAGNI · F24 fresh-first очередь watcher · A3 «Зеркало» владельца —
   insight/mirror.py, mirror-build CLI, /api/mirror · **A7 досье 5 слоёв + Admiralty в шапке +
   напряжения** — insight/tension.py (5 детерминированных правил), db_reader ключи
   admiralty/layers/tensions/pivotal_scenes, app.js 5 заголовков-групп + 2 новые секции;
   поворотные сцены резолвятся через junction `bio_scene_entities` — НЕ через
   `bio_portraits.pivotal_scenes` (эфемерные LLM-индексы, баг пойман до коммита verify-граппом
   по schema.py, см. CHANGELOG) · **F1 ✓/✗ пофактовое подтверждение** — `fact_feedback`
   (insight/repository.py), bot `/promises` с per-item кнопками + `handle_fact_verdict`,
   dashboard `/api/tools/fact-verdict` (2 промис-поверхности: event-JSON досье + live
   promises-таблица граф-модалки), digest.py rejected-фильтр/confirmed-метка. Security-reviewed,
   0 CRITICAL/HIGH. Побочная находка (не фикшена) — bugs.md идея #9 (payload/what naming) ·
   **F2 напоминания по подтверждённым обещаниям** — `deliver/reminders.py` (RU-парсер дат,
   self-disabling), bot «🔔 Напомнить»/date-capture/тикер-asyncio (НЕ job_queue),
   `reminders-due` CLI. Security-reviewed — **1 CRITICAL исправлен** (snooze без
   user_id-гейта — чужой reminder_id переносился; фикс на уровне бота И SQL, regression-тесты
   на обоих уровнях). ⚠ `insight/mirror.py` (A3) будет расширен ПОЗЖЕ задачей F30 (56b,
   зеркальная динамика) — при её исполнении дополнять файл, не переписывать ·
   **F3 `ask` через Telegram-бот** — свободный текст без pending-напоминания падает в
   `_handle_ask` (реюз A2 `answer_question`/`retrieve` целиком, инъекция-гард не тронут);
   `llm_available()` health-проба (паттерн M1); HTML-ответ с источниками, cap вопроса 500 /
   ответа 4096 символов; `ask_log.answered` аддитивная колонка (F13 её переиспользует).
   Security-review не запускался (T1, внешний ввод — уже прорецензированный A2-путь,
   новых SQL write-path нет).
   **F4 голосовая заметка владельца → конвейер** — voicenote_* парсер, спец-контакт self:notes,
   note-ветка orchestrator (без диаризации/analyze), caption `@Имя` → contact_notes, bot
   handle_voice_note (allowlist/cap 50MB/атомарная запись), дашборд-фильтр «🎙 Заметки».
   **F5 вечерний отчёт дня** — daily_report.py (5 секций, reuse digest A1/F1/F2), telegram_sender.py
   (новый голый sync HTTP-sender — TelegramNotifier не годится вне bot-процесса, self.app=None),
   watcher._maybe_send_daily_report (21:00-триггер, report_state дедуп), CLI daily-report.
   **F6 heartbeat + плановый doctor** — watcher._write_heartbeat (каждый цикл), doctor.py +6 чеков
   (heartbeat/queue-stuck/error-burst/disk/reminders-stale/input-silence), build_doctor_message
   (🟢/🔴 заголовок), watcher._maybe_send_doctor_report (9:00-триггер, report_state.last_doctor_date
   — независимый столбец той же таблицы что F5), CLI `doctor --send`. Оба плановых пуша инварианта
   25 теперь реализованы (F5 вечер + F6 doctor) — новый пуш-на-событие впредь = нарушение.
   **F7 панель «Здоровье» в дашборде** — GET /api/health-report (doctor.run_checks напрямую,
   threadpool, read-only), collapsible-панель overview + 🔴-бейдж в шапке при FAIL.
   **F8 Эббингауз-тиры контактов** — `insight/tiers.py` (score=retention·log1p(minutes),
   перцентильные тиры core/active/warm/cold/archive, `contact_tiers` UPSERT+prev_tier).
   Реальный ночной триггер — watcher `_run_insight_fit` (не только `bulk_enrich()`/
   `obligations-digest`, оба тоже вызывают); потребители: `enricher.select_pending_calls`
   (ORDER BY тир) + дашборд `get_people`/`get_person_dossier` (бейдж+сортировка). Biography
   per-entity очередь сознательно не тронута — предмет будущей F21 (entity_contact_map).
   **M8 Deep-extract длинных звонков** — `insight/deep_extract.py`, map-reduce чанкинг (9000/800,
   word-boundary) + `LLMClient(cache_conn=conn)` per-chunk (реюз M3 llm_calls, НЕ свой кэш),
   `deep_facts`/`deep_scans` (дисплей-слой, НЕ events/graph). CLI `deep-extract`; digest получил
   `extra_sections`; досье — секция «Из длинных разговоров».
   **§4.1 фикс (ретроактивно к M8) + F26 заметки-осторожно** — `textnorm.py::norm_quote()`
   (пропущенная поправка Fable §4.1, теперь и в M8-гейте); `call_type='note'` РЕВЕРС —
   входят по умолчанию (`NOTE_MIN_DURATION=30`), гейты жёстче (who=OWNER only,
   type⊂{promise,fact}, числовой гейт `extract_numbers`); 🎙 в digest, досье self:notes
   подавлено.
   **B1 темп/ритм из таймстампов** — `insight/features/tempo.py` (tempo_cps/reply_latency_ms/
   tempo_accel), роутер `feature_store.py` SELECT расширен на call_id/start_ms/end_ms (полный
   регресс tests/insight зелёный — обратная совместимость подтверждена).
   **B2 специфичность vs вода** — `insight/features/specificity.py` (числа/даты/деньги/время на
   whitespace-токенах); BS-index v2 подтверждённо НЕ делается; entity-хиты не считаются в v1
   (decisions.md новая запись).
   **B4 эмоциональная палитра** — `insight/features/emotion_palette.py` (emo_anger/anxiety/joy/
   contempt, лексиконная плотность на речи контакта), лексиконы в `age_style/lexicons/emo_*.txt`
   (переиспользован существующий loader, НЕ спека-путь `features/lexicons/`); досье-секция
   «Эмоциональная палитра» (4 мини-бара, слой «Речь»).
   **B5 баланс просьб** — `linguistic.py::compute_request_balance` (req_other−req_owner)/сумма,
   обе стороны раздельно, UNKNOWN не считается, гейт сумма≥3; отдельной досье-секции нет —
   питает A7 tension-правило 5.
   **B6 лексическая аккомодация** — `insight/features/accommodation.py` (медиана per-call
   align_contact−align_owner по множествам контентных слов, гейт |A|,|B|≥20).
   **B7 финансовая экспозиция** — `insight/finance.py` (единственный insight-модуль, сам
   ходящий в БД: `events` promise/debt → `{currency:[low,high]}`, max-не-сумма на событие);
   досье-секция «Финансовая экспозиция» (слой «Место в сети»); digest overdue-строки
   получают суффикс суммы из своего what+quote.
   **B8 дрейф стиля по годам** — `insight/age_style/drift.py` (реюз slang_density/
   mean_syllables_per_word/vy_ratio, polyfit deg1, FRAGILE-gated по UNKNOWN>40%); досье-ключ
   `drift` был заранее зарезервирован в A7 `layers.dynamic`. **B-серия (B1-B8) завершена.**
   **C3 спящие ценные связи** — `insight/dormancy.py` (личный ритм: 3×median_gap, не общий
   порог); digest-секция «😴 Спящие ценные связи» через `cli/commands/deliver.py` (не
   digest.py — тот уже generic); досье-флаг `dormant` в шапке «Что делать».
   **C1 граф упоминаний** — `mention_edges`/`insight/mentions.py` (DERIVED, паттерн
   entity_contact_map; строится в graph-replay СРАЗУ ПОСЛЕ неё); CLI `mentions-build`; досье
   «Через упоминания» (о нём говорят top-3 + исходящий счётчик; «общие люди» — YAGNI v1, не
   делается). **Портфель C завершён** (C2 пропущена — T3-гейт, `decisions.md`).
   **D1 «В этот день»** — `digest.py::on_this_day` (bio_scenes годовщины, importance>70,
   RU-склонение год/года/лет); `build_digest` зовёт сам (не extra_sections); CLI
   `on-this-day --user X [--send]` для отдельного Task Scheduler.
   **D2 линия жизни** — `get_lifeline`/`/api/insight/lifeline`, 5-й вид вкладки «Архетипы»
   (Gantt-стиль ECharts custom-серия из `bio_arcs`); тестом пойман нюанс —
   `DashboardDBReader` read-only (`query_only=ON`), seed тестовых данных требует отдельный
   r/w-коннект.
   **D3 квартальный отчёт** — `insight/quarterly.py` (gather_aggregates только числа/имена/даты,
   build_report кэш по user_id+period+prompt_version в `insight_reports`, LLM-сбой →
   `RuntimeError` не глотается, `quarterly-report` CLI). **Портфель D (D1-D3) завершён.**
   **B3 поведенческая надёжность обещаний** (закрывает находку из D3-сессии, decisions.md) —
   `insight/promise_outcomes.py`: det-эвристика (content-word overlap + `_RE_DONE`/`_RE_FAIL`
   по ё-нормализованному тексту, первый резолвящий сегмент побеждает, due+2дн grace→late) +
   LLM-донасыщение unknown (memoized, verbatim-гейт и парсер переиспользованы из
   `age_estimate.py`, LLM-сбой graceful НЕ RuntimeError); `contact_reliability` (side=contact
   only, kept_ratio, фраза с русским склонением опоздания). Потребители: досье-секция
   «Надёжность обещаний», A6/A7 `admiralty.source_grade` теперь получает реальные kept_ratio/n
   (было None), digest A1 contact-side suffix. CLI `promise-outcomes --user X [--llm]`.
   **Портфель B (B1-B8) теперь фактически полон.**
   Финализация портфеля (`ozalupennieStrategic5.md` строки 902-914) — следующий шаг: сверка
   коммитов A1-A6/B1-B8/C1,C3/D1-D3 · kill-criteria параграф в dashboard.md (grep uvicorn
   access log каждые 4 недели, без кода) · State-обновление (бокс-очередь LLM-пассов:
   `age-estimate --llm`, `deep-extract`, `promise-outcomes --llm`, `quarterly-report`,
   `calibrate-risk`, `mirror-build`, `mentions-build`) · финальный pytest+push.
   Детали каждой готовой задачи — CHANGELOG.md (запись по задаче, не здесь). 1294 passed/2 skipped.
2. **Бокс (не блокирует исполнение):** pull → `owner_birth_year` в base.yaml → пересчёт возраста
   (`age-estimate --user me` + `age-style --user me`, TABLE/RULES v2) → спот-чек 10 контактов →
   LLM-окно: `age-estimate --user me --llm`.
3. После M1: `python -m callprofiler doctor` — преполёт перед каждым бокс-прогоном.
4. Бокс-чеклист после портфеля — ozalup2.md §7 (canary → решение про llm_json_mode → deep-extract →
   LLM-пассы A2/B3/D3 → спот-чек с прослушиванием M2).

**Open questions (UNCONFIRMED):**
- Поддерживает ли текущая сборка llama-server на боксе `response_format: json_object` (canary M4 покажет;
  старые сборки игнорируют поле молча — fallback-парсер вечен, инвариант 15).
- Сохраняет ли GigaAM филлеры («типа/значит») — ось discourse (проверить на боксе).
- Валидность tempo на реальных таймстампах. VRAM-footprint Qwen 9B Q8_0. Калибровка `bs_thresholds`.

**Working set:**
- `ozalup2.md` (мастер-план) · `ozalupennieStrategic5.md` (тела задач A/B/C/D) ·
  `STRATEGIC_PLAN_v5.md` · `.claude/rules/{insight,dashboard,llm,graph}.md`
- Tests: `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`