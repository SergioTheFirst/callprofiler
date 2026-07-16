# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history preserved in git. Overwrite each session; append-only logs live in CHANGELOG.md.

**Goal (incl. success criteria):**
- Рабочий локальный pipeline `C:\calls\in` → текст (GigaAM v3) → БД → LLM-анализ (Qwen) → дашборд/Telegram.
- **Доктрина дашборда (юзер, 2026-06-11): 2 функции** — ход обработки + полный психопортрет личности
  («нажал имя — знаешь всё»: risk, BS-index, архетип, возраст (fusion), паттерны, факты).

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

**State (2026-07-16):**

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

**Next:**
1. **Исполнение `OzaluplivanieFable2.md`** (Sonnet, порядок = Fable §2 + вставки Fable2 §2:
   0.1 → 0.2 → M1 → … → 19a(F28) → … → 56a-56d → …). Каждая задача: pytest зелёный →
   CHANGELOG → commit+push. 59a (canary смены LLM) — НЕ исполнять автономно.
   **В процессе (автономный прогон начат 2026-07-16):** сделаны 1-12 (0.1 гейт · 0.2 feedback-петля
   · M1 doctor · 0.3 spotcheck-sample · M2 аудио-плеер · 0.4 role-UNKNOWN% · role-fragile флаг
   (инлайн №7) · M3 llm_cache · M4 json_mode+canary-analyze · A1 obligations-digest — БЕЗ
   Telegram-пуша, см. decisions.md · A2 `ask` по архиву + инъекция-гард §4.1 · A4 risk_thresholds
   — фикс BS-index-подмены, dashboard-очистка отложена, см. decisions.md). Следующая по порядку —
   **13. A6 карточка v2 (§4.3: freshness-штамп, без risk emoji до A4 — A4 сделан, порядок
   имён файлов)**.
   Детали каждой готовой задачи — CHANGELOG.md (запись по задаче, не здесь). 893 passed/2 skipped.
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
