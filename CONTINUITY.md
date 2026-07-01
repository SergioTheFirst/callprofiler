# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history preserved in git. Overwrite each session; append-only logs live in CHANGELOG.md.

**Goal (incl. success criteria):**
- Рабочий локальный pipeline `C:\calls\in` → текст (GigaAM v3) → БД → LLM-анализ (Qwen) → дашборд/Telegram.
- **Доктрина дашборда (юзер, 2026-06-11): 2 функции** — ход обработки + полный психопортрет личности
  («нажал имя — знаешь всё»: risk, BS-index, архетип, возраст (маркеры+стиль), паттерны, факты; без лирики).

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

**State (2026-07-02):**

✅ **Стилометрическая оценка возраста (`age_style`) — план `age.md` (Ф0-Ф5) реализован целиком,
+ marker-vs-style конфликт исправлен по запросу юзера.** Методология `vozrast.md`. Карта:
`.claude/rules/insight.md` («Возраст-стиль»). 4-й сигнальный класс, ОТДЕЛЬНЫЙ от marker/
relation/LLM `age_estimate.py` (своя таблица `contact_age_style`, свой пайплайн
`insight/age_style/`; READ-ONLY заимствует `contact_age_estimates.method/birth_year_*` как
явный маркер — НЕ пишет туда). Поток: no-ML фичи → z внутри популяции юзера → 8 вероятностных
таблиц (vozrast.md §4.2, дословно) → взвешенный линейный пул по группам G1-G6 (деконфликт
коррелирующих измерений разнообразия) → год рождения (анкор — средний год звонков контакта) →
confidence (sigmoid). CLI `age-style --user X [--stale-only]`, watcher-autofit, дашборд-секция
«Возраст (стиль)» + `POST /api/tools/age-recompute?contact_id=`.
**Фикс 2026-07-02 (юзер спросил "не будет ли мешать" LLM-промпту age_v001.txt):** формула
доверия §7.2 реализовывала Conflict-член ТОЛЬКО наполовину (внутренняя бимодальность, без
marker-vs-style) → явный маркер мог противоречить стилю без штрафа/флага. Fix: маркер входит
в пул `score_contact` как узкая сильная посылка (вес ∝ его confidence, обычно перевешивает
style — vozrast.md §7.1 «маркер побеждает»), конфликт argmax детектируется явно → warning +
штраф доверия. Заодно: список «Личности» показывал возраст ТОЛЬКО из marker-системы — контакты
БЕЗ маркера (ради которых age_style строился) не получали возраст в списке; добавлен fallback
+ `age_source`. Security: read-only SQL, самопроверено (не T2-гейт — новых write-путей нет).
733 passed/2 skipped (полный `tests/`). **Не проверено на реальной БД/боксе.**

**Прежние сессии (сжато, детали — git log / CHANGELOG.md):** post-mortem
`make-characteristics.bat` (8-12ч зависание → ~3мин, 5 причин: CP866-кодировка, коррелированный
подзапрос, отсутствующие индексы, несуществующий метод, `goto` глотал предупреждения) ·
русификация характеристики личности (`dashboard/labels_ru.py`) · фикс entity-слоя дашборда на
graph-only БД (500 → guarded) · возраст-маркеры/LLM (Ф0-Ф3 age-estimation) · досье «Личности»
(Ф0-Ф4).

**Next:**
1. **ПРОГОН НА БОКСЕ:** pull → `make-characteristics.bat` (~3 мин) → визуально проверить секцию
   «Возраст (стиль)» в досье + кнопку «Определить возраст ↻» на живых данных.
2. `age-style --user me` на реальной БД — спот-чек 5-10 знакомых контактов (группа в разумном
   диапазоне? топ-вклады осмысленные?). Таблицы vozrast.md §4.2 — экспертные приоры, НЕ обучены;
   ожидать грубую точность, это стартовая калибровка (§15 vozrast.md).
3. Задать `owner_birth_year` в base.yaml (маркер-система, не стиль).
4. В LLM-окне: `profile-all --user me` + `age-estimate --user me --llm`.
- ОТЛОЖЕНО: калибровка вероятностных таблиц age_style на реальных данных; age_band/age_style как
  FRAGILE-ось кластеризации архетипов; Ф4-dominance; LLM-имена кластеров; Stage-2 биография.

**Open questions (UNCONFIRMED):**
- VRAM-footprint Qwen 9B Q8_0 на боксе. Калибровка `bs_thresholds`.
- Качество age-LLM-пасса и age_style на реальной лексике (обе системы — первые версии).

**Working set:**
- `age.md` (план) · `vozrast.md` (методология) · `.claude/rules/insight.md` · `.claude/rules/dashboard.md`
- Tests: `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
