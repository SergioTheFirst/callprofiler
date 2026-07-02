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
733 passed/2 skipped (полный `tests/`). Прогон на боксе стартовал в этот же день — см. ниже.

✅ **STRATEGIC_PLAN_v5.md (2026-07-02)** — циничная ревизия «зачем система»/ценности + портфель
улучшений на существующих наработках (supersedes v4). Диагноз: извлечение перестроено, доставка
недостроена; рычаг = почти бесплатный переобход 16.6k-архива (мемоизация везде). Рамка: 4 момента
потребности владельца (звонок/решение/неделя/год) → Ф-A доставка добытого (леджер обязательств+
дайджест, `ask` к архиву, «Зеркало» владельца, калибровка порогов, замыкание feedback-петли) →
Ф-B новые сигнальные классы (надёжность обещаний, темп из таймстампов, специфичность, эмо-палитра,
аккомодация) → Ф-C реляционный интеллект (граф упоминаний, эхо информации, алерты затухания) →
Ф-D нарратив. Доктрина объёмного портрета = триангуляция 5 слоёв + Admiralty-грейд + противоречия
как контент. Отвергнуто: SER/эмбеддинги/Big5-ярлыки/детектор лжи/real-time. Kill-criteria 4 недели.

✅ **ozalupennieStrategic5.md (2026-07-02)** — атомарная Sonnet-декомпозиция STRATEGIC_PLAN_v5:
Ф0 (гейт fixager · A5-петля · спот-чек CLI · role-UNKNOWN% на System) → Ф-A (A1 дайджест, A2 ask,
A4 risk-калибровка, A6 карточка v2, A3 зеркало, A7 слои/Admiralty/tensions) → Ф-B (B3..B8) →
Ф-C (C3, C1; C2=T3-стоп) → Ф-D (D1-D3). Все якоря проверены по коду (§1 плана). Найдены 2 бага:
`handle_feedback` NameError `user_id` (feedback никогда не сохранялся — петля A5 разомкнута
буквально) и BS-пороги, применяемые к risk-шкале в `card_generator`. Решения — decisions.md
(BS-v2 отклонён, C2 за T3-гейтом).

**Прежние сессии (сжато, детали — git log / CHANGELOG.md):** post-mortem
`make-characteristics.bat` (8-12ч зависание → ~3мин, 5 причин: CP866-кодировка, коррелированный
подзапрос, отсутствующие индексы, несуществующий метод, `goto` глотал предупреждения) ·
русификация характеристики личности (`dashboard/labels_ru.py`) · фикс entity-слоя дашборда на
graph-only БД (500 → guarded) · возраст-маркеры/LLM (Ф0-Ф3 age-estimation) · досье «Личности»
(Ф0-Ф4).

**Прогон на боксе (2026-07-02) — СТАРТОВАЛ, 2 краша найдены+исправлены:**
✅ `ModuleNotFoundError: psutil` (не был в pyproject.toml — добавлен) + ✅ `sqlite3.
OperationalError: no such column: name` (`get_character_profile` слал запрос к
`bio_behavior_patterns` с несуществующими колонками; глубже — читал бы ЧУЖОЕ id-пространство
даже с алиасом колонок, bio_entities≠graph entities.id; fix: patterns из PsychologyProfiler,
не из bio_behavior_patterns). Детали: `bugs.md` (запись 2026-07-02). 734 passed/2 skipped.
Юзер прислал box-фиксы вручную — я их НЕ принял as-is (severity была бы сырым float вместо
enum, id-space баг остался бы), сделал корневой фикс вместо алиаса.

**Next:**
0. **Исполнить `fixager.md`** (Sonnet, 6 фаз) — аудит 2026-07-02 нашёл 9 препятствий возраста:
   P1 лексиконы-омонимы (startswith: «аккуратно»→архаизм, «диалог»→реалия 1980-90, «база»→сленг,
   «сериал»→внуки_пенсия) · P2 support_n=len(tokens) вместо хитов (1 ложный хит = полный вес) ·
   P3 stale_only считает z по подвыборке (watcher пишет мусорные группы) · P4 интервал ±1 год при
   conf 25 · P5 «выйду на пенсию»/«у дочки ЕГЭ» без гардов · P6 обвал conf до min+10 от мусорного
   низшего класса · P7 кнопка только при существующей строке стиля, только style-пасс · P8
   owner_birth_year=0 молча · P9 UNKNOWN-диаризация без объяснения в UI. После фиксов: бамп
   TABLE_VERSION/RULES_VERSION → v2, полный пересчёт на боксе.
1. **Продолжить прогон на боксе:** pull последний коммит → повторить `make-characteristics.bat`/
   запуск дашборда — оба известных краша закрыты, но прогон свежий, могут всплыть новые.
2. Визуально проверить секцию «Возраст (стиль)» в досье + кнопку «Определить возраст ↻» +
   старую entity-модалку (`/api/character/{id}`, теперь тоже через PsychologyProfiler) на живых данных.
3. `age-style --user me` на реальной БД — спот-чек 5-10 знакомых контактов (группа в разумном
   диапазоне? топ-вклады осмысленные?). Таблицы vozrast.md §4.2 — экспертные приоры, НЕ обучены;
   ожидать грубую точность, это стартовая калибровка (§15 vozrast.md).
4. Задать `owner_birth_year` в base.yaml (маркер-система, не стиль).
5. В LLM-окне: `profile-all --user me` + `age-estimate --user me --llm`.
6. После стабилизации бокса: исполнить `ozalupennieStrategic5.md` (Sonnet, задачи строго по
   порядку Ф0 → Ф-A → Ф-B → Ф-C → Ф-D; A5-петля/дайджест/спот-чек = задачи 0.2 / A1 / 0.3).
- ОТЛОЖЕНО: калибровка вероятностных таблиц age_style на реальных данных; age_band/age_style как
  FRAGILE-ось кластеризации архетипов; Ф4-dominance; LLM-имена кластеров; Stage-2 биография.

**Open questions (UNCONFIRMED):**
- VRAM-footprint Qwen 9B Q8_0 на боксе. Калибровка `bs_thresholds`.
- Качество age-LLM-пасса и age_style на реальной лексике (обе системы — первые версии).

**Working set:**
- `age.md` (план) · `vozrast.md` (методология) · `.claude/rules/insight.md` · `.claude/rules/dashboard.md`
- Tests: `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
