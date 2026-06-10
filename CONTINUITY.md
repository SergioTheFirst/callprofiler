# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history preserved in git. Overwrite each session; append-only logs live in CHANGELOG.md.

**Goal (incl. success criteria):**
- Рабочий локальный pipeline `C:\calls\in` → текст (GigaAM v3) → БД → LLM-анализ (Qwen) → дашборд/Telegram.
- Полный путь: pyannote-роли → GigaAM(GPU ASR) → Qwen 9B Q8_0(GPU LLM). Unattended-прогон ~4.6k+ файлов.

**Workflow (durable):**
- Claude **коммитит и пушит в `main` БЕЗ пер-действенного согласования** (2026-06-04).
- **Каждый значимый шаг сперва в файлы памяти** (CONTINUITY/CHANGELOG/.claude/rules/*), **потом** `commit`+`push origin main`.
- **Отвечать кратко, по делу, без воды** (2026-06-05). Не перечитывать код на простой вопрос — брать из `.claude/rules/*` карт.
- **Model Routing v2 (2026-06-10, CLAUDE.md):** тир = blast radius. T0 Haiku/low → T1 Opus fast/medium →
  T2 Opus/high → **T3 Fable/max** (Hard Constraints, удаление данных, статусы/resume, decisions-уровень).
  T0/T1 — без субагентов; объявлять тир в начале задачи; эскалация только по гейту.

**Constraints/Assumptions:**
- 100% local. Windows. LLM = llama-server @127.0.0.1:8080. SQLite, no ORM, каждый запрос фильтрует `user_id`.
- **Код пишем на ЭТОЙ машине (без GPU/моделей/данных), запускаем на ДРУГОЙ (бокс с GPU).** БД здесь пустая.
- `data_dir = C:\calls\data`. Лог запуска: `C:\calls\callprofiler.log`.
- **GPU sequential (Hard Constraint):** ASR+pyannote и LLM НИКОГДА одновременно в VRAM (12GB RTX 3060).

**State (2026-06-10):**

📋 **CLAUDE.md переработан — Model Routing v2** (запрос юзера: умная экономия токенов без потери
качества). Тиры T0-T3 по blast radius, жёсткие гейты (история OOM/data-loss), субагенты тиризованы
(Explore=haiku, planner/reviewer/security/tdd=sonnet, T0/T1 без них), Skills ≤2/задачу. Актуализация:
GigaAM вместо Whisper, dev/run split, pyannote in-memory hack, insight-команды/карта в references.
WHY: `decisions.md` 2026-06-10. Код НЕ менялся.

🧠 **Insight Engine — Фазы 0-7 СОБРАНЫ, в main** (Ф4 dominance отложена). Карта: `.claude/rules/insight.md`.
**634 passed, 2 skipped** локально. Конвейер: `features-build`→`archetypes-fit` (пишет имена/membership/
pca_x,pca_y)→`person-archetype` (карточка). Дашборд: вкладка «Архетипы» (PCA-карта/эго-сеть/циркад/ЭКГ),
5 эндпоинтов `/api/insight/*`. Доказано на синте: META 0.71 → +TEXT 1.0 → +AFFECTIVE twin @true-k.

🟢 **Пайплайн готов к прогону:** параллельный ffmpeg, ко-резидентность Фазы 2, выгрузка ДО LLM (OOM-фикс),
process_pending каждый цикл, sweep сирот-wav, дашборд real-time, reset.bat чистый лист.
Конфиг: `enable_llm_analysis:true`, `enable_diarization:true` (роли обязательны).

**Next — ПРОГОН НА БОКСЕ** (этот ПК всё закоммичено; см. план в истории CONTINUITY @086c3b2):
1. `git pull origin main` → 2. остановить watch/dashboard → `reset.bat --apply` → 3. llama-server +
   роли (`install-roles.bat`, HF_TOKEN, gated pyannote, ref manager.wav) + аудио в `C:\calls\in` →
   `startprocess.bat`. Мониторить `C:\calls\callprofiler.log`: нет OOM, дашборд live, wav не копятся.
4. Insight на реальных ~16k: `features-build --user me` → `archetypes-fit --user me` → вкладка
   «Архетипы» + `person-archetype`. **Визуальная проверка Ф7 — на боксе.**
- ОТЛОЖЕНО: Ф4 dominance; LLM-имена кластеров (детерм. есть). ПОТОМ: Stage-2 graph/биография; resilience.

**Open questions (UNCONFIRMED):**
- Реальный VRAM-footprint llama-server Qwen 9B Q8_0 на боксе (ко-резидентность с LLM — только после замера).
- Дальнейшие perf (`-np 4`, skip-LLM коротких, in-memory audio) — за флагом, с замером.

**Working set (files/commands):**
- Эта сессия: `CLAUDE.md` (routing v2), `CHANGELOG.md`, `.claude/rules/decisions.md`, `CONTINUITY.md`.
- Tests (бокс): `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
