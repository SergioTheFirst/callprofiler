# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history preserved in git. Overwrite each session; append-only logs live in CHANGELOG.md.

**Goal (incl. success criteria):**
- Рабочий локальный pipeline `C:\calls\in` → текст (GigaAM v3) → БД → LLM-анализ (Qwen) → дашборд/Telegram.
- **Доктрина дашборда (юзер, 2026-06-11): 2 функции** — ход обработки + полный психопортрет личности
  («нажал имя — знаешь всё»: risk, BS-index, архетип, возраст, паттерны, факты-цитаты; без лирики).

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

**State (2026-06-13):**

✅ **Фикс: entity-слой дашборда падал 500 на graph-only БД** (bugs.md 2026-06-13). guard'ы
`_has_table`/`_has_column` были только в досье-функциях; `get_stats`/`get_entity_profile`/
`get_all_characters`/`get_character_profile` не защищены от отсутствия bio_* + от того, что
trust_score/volatility/conflict_count нет в entity_metrics (они в bio_behavior_patterns).
Regress `test_entity_layer_graph_only_db_no_bio_tables`, 692 passed. Латентный (вне фикса):
get_character_profile грузит bio_behavior_patterns с несуществующими колонками name/severity/
ratio/label — проявится на БД с biography, чинить там же.

✅ **«Возраст контакта» РЕАЛИЗОВАН (Ф0-Ф3 плана age-estimation), 691 passed/2 skipped, JS OK.**
План: `docs/superpowers/plans/2026-06-11-age-estimation.md`; карты: `.claude/rules/insight.md`
(секция «Возраст»), `.claude/rules/dashboard.md`; WHY: decisions.md (birth-year-space, stale_only).
- Ф0/Ф1: `insight/age_markers.py`+`age_estimate.py` — маркеры (мне N лет / словесные / год рождения /
  юбилей / этапные) + направленные якоря (гейт `owner_birth_year`, в base.yaml = 0 → ВЫКЛ).
- Ф2: LLM-пасс под Qwen3.5 (`configs/prompts/age_v001.txt`, age-v1): <think>/fences-парсер,
  verbatim-гейт, memoization per-row; det-пересчёты реюзают оплаченный LLM-результат.
- Ф3: досье — секция «Возраст» + колонка в списке людей (динамический возраст из birth_year_point).
- Динамика: det-часть в watcher-autofit (stale_only инкрементально); LLM только CLI в LLM-окне.
- Ревью: security clean; ложные CRITICAL/HIGH code-ревьюера отклонены пересчётом (см. CHANGELOG).
✅ Досье «Личности» (Ф0-Ф4 плана dossier) — в main ранее (208e5c1).

**Next:**
1. **ПРОГОН НА БОКСЕ:** pull → задать `owner_birth_year` в base.yaml (иначе якоря выкл) →
   reset/startprocess как планировалось. autofit сам построит архетипы+возраст (инкрементально).
2. В LLM-окне (llama-server жив, ASR не идёт): `profile-all --user me` +
   `age-estimate --user me --llm`.
3. Чеклист плана: спот-чек 10 знакомых контактов (возраст в реальном диапазоне? цитаты настоящие?).
4. Визуальная проверка UI (колонка «Возраст», секция в досье) — на боксе.
- ОТЛОЖЕНО: age_band как FRAGILE-ось кластеризации; калибровка confidence; Ф4-dominance;
  LLM-имена кластеров; Stage-2 биография; resilience-порт.

**Open questions (UNCONFIRMED):**
- VRAM-footprint Qwen 9B Q8_0 на боксе. Калибровка `bs_thresholds`.
- Качество age-LLM-пасса на реальной лексике (промпт age-v1 — первая версия; бамп = пересчёт кэша).

**Working set:**
- `docs/superpowers/plans/2026-06-11-age-estimation.md` · `.claude/rules/insight.md` ·
  `.claude/rules/dashboard.md`
- Tests: `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
