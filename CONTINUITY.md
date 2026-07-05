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

**State (2026-07-05):**

✅ **`ozalup2.md` — единый мастер-план развития** (T3-сессия по запросу юзера): слияние
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
1. **Исполнение `ozalup2.md`** (Sonnet, задачи строго по §2: 0.1 → 0.2 → M1 → …). Каждая задача:
   pytest зелёный → CHANGELOG → commit+push.
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
