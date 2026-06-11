# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history preserved in git. Overwrite each session; append-only logs live in CHANGELOG.md.

**Goal (incl. success criteria):**
- Рабочий локальный pipeline `C:\calls\in` → текст (GigaAM v3) → БД → LLM-анализ (Qwen) → дашборд/Telegram.
- **Доктрина дашборда (юзер, 2026-06-11): 2 функции** — ход обработки + полный психопортрет личности
  («нажал имя — знаешь всё»: risk, BS-index, архетип, паттерны, факты-цитаты; без лирики).

**Workflow (durable):**
- Claude **коммитит и пушит в `main` БЕЗ пер-действенного согласования** (2026-06-04).
- **Каждый значимый шаг сперва в файлы памяти**, **потом** `commit`+`push origin main`.
- **Кратко, по делу, без воды** (2026-06-05). Карты `.claude/rules/*` вместо перечитывания кода.
- **Model Routing v2 (2026-06-10):** тир = blast radius; T0/T1 без субагентов; объявлять тир.

**Constraints/Assumptions:**
- 100% local. Windows. LLM = llama-server @127.0.0.1:8080. SQLite, no ORM, каждый запрос `user_id`.
- **Код пишем ЗДЕСЬ (без GPU/моделей/данных), запускаем на боксе.** БД здесь пустая.
- `data_dir = C:\calls\data`. Лог: `C:\calls\callprofiler.log`.
- **GPU sequential (Hard Constraint):** ASR+pyannote и LLM НИКОГДА одновременно (12GB RTX 3060).

**State (2026-06-11):**

✅ **Досье «Личности» РЕАЛИЗОВАНО (Ф0-Ф4 плана), в main, 658 passed/2 skipped.**
План: `docs/superpowers/plans/2026-06-11-dashboard-person-dossier.md`; карта: `.claude/rules/dashboard.md`.
- Ф0 autofit в watcher (insight_autofit*, baseline, non-fatal) — вкладка наполняется сама.
- Ф1 `entity_contact_map` (name 0.95 / cooccur ≥0.6∧≥3 PERSON, owner-excl), rebuild в
  archetypes-fit + graph-replay Step 9; CLI `person-link [--dry-run]`. Security-review clean.
- Ф2 `get_person_dossier`/`get_people` + `/api/person/{id}`,`/api/people`; реюз
  `PsychologyProfiler(include_llm=False)`. **Багфикс:** модалка дёргала LLM (120s/клик) и писала
  на query_only → include_llm=False (bugs.md 2026-06-11).
- Ф3 вкладка «Личности» (поиск; риск/BS/архетип) + модал-досье (индексы→черты→паттерны→психотип→
  ритм→цитаты→противоречия→обещания→связи→динамика→интерпретация→совет→звонки) + клик из
  PCA-точки/узла сети → досье. node --check OK.
- Ф4 = ноль кода: `profile-all` УЖЕ персистит интерпретации в entity_profiles (досье читает).
- Всё ЗАПУШЕНО: 0ffb3dd (Ф0) → ccd3f04 (Ф1) → 803c02c (Ф2) → 208e5c1 (Ф3) на origin/main.

**Next:**
1. **ПРОГОН НА БОКСЕ:** pull → reset.bat --apply → llama-server+роли → startprocess. После прогона
   архетипы/связки построятся сами (autofit). Вкладка «Личности»: список+досье, клики из PCA/сети.
2. Интерпретации: `python -m callprofiler profile-all --user me` (llama-server жив, ASR не идёт).
3. Визуальная проверка UI досье — на боксе (здесь нет данных).
- ЖДЁТ ОТМАШКИ: план «Возраст контакта» (`docs/superpowers/plans/2026-06-11-age-estimation.md`,
  4 фазы: маркеры → якоря → LLM-пасс → UI; перед боксом задать `owner_birth_year`).
- ОТЛОЖЕНО: Ф4-dominance insight; LLM-имена кластеров; Stage-2 биография; resilience-порт.

**Open questions (UNCONFIRMED):**
- VRAM-footprint Qwen 9B Q8_0 на боксе. Калибровка `bs_thresholds` (досье красит BS если есть).
- Форма строки `bs_thresholds` (green_max/yellow_max?) — UI деградирует к статичным 30/60.

**Working set:**
- `docs/superpowers/plans/2026-06-11-dashboard-person-dossier.md` · `.claude/rules/dashboard.md`
- Tests: `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
