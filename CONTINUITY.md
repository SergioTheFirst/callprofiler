# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history preserved in git. Overwrite each session; append-only logs live in CHANGELOG.md.

**Goal (incl. success criteria):**
- Рабочий локальный pipeline `C:\calls\in` → текст (GigaAM v3) → БД → LLM-анализ (Qwen) → дашборд/Telegram.
- **Доктрина дашборда (юзер, 2026-06-11): 2 функции** — ход обработки + полный психопортрет личности
  («нажал имя — знаешь всё»: risk, BS-index, архетип, паттерны, факты-цитаты; без лирики).

**Workflow (durable):**
- Claude **коммитит и пушит в `main` БЕЗ пер-действенного согласования** (2026-06-04).
- **Каждый значимый шаг сперва в файлы памяти** (CONTINUITY/CHANGELOG/.claude/rules/*), **потом** `commit`+`push origin main`.
- **Отвечать кратко, по делу, без воды** (2026-06-05). Карты `.claude/rules/*` вместо перечитывания кода.
- **Model Routing v2 (2026-06-10):** тир = blast radius; T0/T1 без субагентов; объявлять тир в начале.

**Constraints/Assumptions:**
- 100% local. Windows. LLM = llama-server @127.0.0.1:8080. SQLite, no ORM, каждый запрос фильтрует `user_id`.
- **Код пишем на ЭТОЙ машине (без GPU/моделей/данных), запускаем на ДРУГОЙ (бокс).** БД здесь пустая.
- `data_dir = C:\calls\data`. Лог: `C:\calls\callprofiler.log`.
- **GPU sequential (Hard Constraint):** ASR+pyannote и LLM НИКОГДА одновременно в VRAM (12GB RTX 3060).

**State (2026-06-11):**

📋 **План «Личности» (персональные досье в дашборде) — НАПИСАН, ждёт отмашки на реализацию.**
`docs/superpowers/plans/2026-06-11-dashboard-person-dossier.md`. 5 фаз: Ф0 autofit insight в watcher
(лечит «Нет модели архетипов») → Ф1 `entity_contact_map` (сшивка contact↔entity, derived/rebuild) →
Ф2 `get_person_dossier` + `/api/person` (реюз PsychologyProfiler `include_llm=False`; live-LLM в
дашборде запрещён) → Ф3 вкладка «Личности» (клик имени/PCA-точки/узла сети → досье) → Ф4
`profile-all --persist` (интерпретации, LLM-окно). Тиры: Ф0-Ф2,Ф4=T2; Ф3=T1.
Новая карта: `.claude/rules/dashboard.md`. WHY: `decisions.md` 2026-06-11. **Код НЕ менялся.**

🔎 Ключевые факты разбора: graph/BS наполняются в прогоне АВТОМАТИЧЕСКИ (`enable_graph_update=True`
дефолт; orchestrator:833, enricher:504); insight и психология — только ручные CLI → пустые вкладки =
операционный разрыв. `/api/characters`+модалка уже есть; дыры: `temporal`/`network`=None, архетип не
присоединён, contact↔entity по равенству имени, профайлер не персистит и к дашборду не подключён.

🧠 Insight Ф0-7 в main (634 passed, 2 skipped). 🟢 Пайплайн готов к прогону (см. @086c3b2).

**Next:**
1. **Реализация плана досье** по фазам (Ф0 → Ф4), каждая фаза = TDD + commit+push (см. план).
2. **ПРОГОН НА БОКСЕ** (не сделан): pull → reset.bat --apply → llama-server+роли → startprocess.
   После Ф0 архетипы строятся сами; до того — вручную `features-build`+`archetypes-fit --user me`.
3. После Ф4 на боксе: `profile-all --user me --persist` (llama-server жив, ASR не идёт).
- ОТЛОЖЕНО: Ф4-dominance (insight), LLM-имена кластеров, Stage-2 биография, resilience-порт.

**Open questions (UNCONFIRMED):**
- Реальный VRAM-footprint Qwen 9B Q8_0 на боксе.
- Калибровка `bs_thresholds` на реальных данных (досье показывает BS 🟢🟡🔴 только при наличии).

**Working set (files/commands):**
- План: `docs/superpowers/plans/2026-06-11-dashboard-person-dossier.md`; карта: `.claude/rules/dashboard.md`.
- Tests (бокс): `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
