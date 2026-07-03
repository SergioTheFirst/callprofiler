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

**State (2026-07-03):**

✅ **Полная ревизия системы возраста → Age Ensemble v2 РЕАЛИЗОВАН** (T3-ревизия по запросу юзера;
план: `docs/superpowers/plans/2026-07-03-age-ensemble-v2.md`; карта: `.claude/rules/insight.md`
секции «Возраст v2 / Возраст-стиль v2 / Возраст-FUSION»). Исполнение: 3 Sonnet-задачи (A=fixager
Ф1-Ф6, B=маркеры/kin/стиль-оси, C=fusion/дашборд) + архитекторские до-фиксы (агенты дважды
упирались в session limit — B5/B8 и часть аудит-фиксов докатаны в основной сессии). Состав:
- **fixager P1-P9 закрыты**: `=`-точный матч лексиконов (омонимы), support=хиты (везде, вкл.
  slang/archaism), z по полной популяции при stale_only, честная ширина интервала, pension/ЕГЭ-гарды,
  мягкий конфликт в `_aggregate` (−10/сигнал вместо обвала), кнопка всегда + маркер-пасс из UI,
  hint при owner_birth_year=0, hint_diarization при 0 OTHER-реплик.
- **Маркеры-v2**: born_in/since_year/age_slangnum/age_approx (класс 3), год-якорные события
  школа/вуз/армия (класс 2), KIN-арифметика (у дочки ЕГЭ → контакту 36-58 и т.п.) — «третье лицо»
  теперь сигнал, а не мусор. `_PRIORITY` покрывает все новые сигналы.
- **Стиль-v2** (`TABLE_VERSION=age-style-v2`, `RULES_VERSION=age-rules-v2`): новые оси discourse
  (филлеры-репертуар)/kancelyarit/morphosyntax (М3+С3 одним голосом)/tempo (слов/сек из
  таймстампов)/популяционный prior (0.25, гасит ложные G1/G2); биграммы в лексиконах; реалии
  пере-датированы (reminiscence bump) + пересечение эпох одиночных хитов; синт-G4 очищен от
  советизмов (был подгон под v1).
- **FUSION** (`age_fusion.py`, fuse-v1, чистая функция на чтении): маркер ∩ стиль → conf+5;
  конфликт → маркер побеждает + warning; только стиль → cap 70. Потребители: get_people,
  get_person_dossier (`age_fused` — первая строка досье), age-recompute.
- **Кнопка «Пересчитать возраст ↻»** в досье: полный пересчёт (маркеры контакта + стилометрия
  всей популяции), без LLM, всегда видна.
- Верификация: 810 passed / 2 skipped (полный `tests/`); гейт восстановления когорт
  (`test_recovery_groups` ARI) зелёный; пул/kin-арифметика пересчитаны вручную (урок 2026-06-06).
- Отступление от процесса: финальный code-reviewer-субагент НЕ запускался (двое агентов подряд
  упёрлись в session limit) — заменён построчным аудитом архитектора (найдено и исправлено 8
  дефектов агентов: латинские c/s в «классе», discourse/kancelyarit не доходили до scorer,
  prior ломал marker_conflict, _PRIORITY без новых сигналов, kin-regex ловил «мне 30» и др.).

**Прежние сессии (сжато):** age_style Ф0-Ф5 + marker-vs-style фикс (2026-07-01/02) ·
STRATEGIC_PLAN_v5 + ozalupennieStrategic5.md (2026-07-02) · прогон на боксе стартовал, 2 краша
закрыты (psutil, no such column — bugs.md 2026-07-02) · русификация характеристики · досье Ф0-Ф4.

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
- `docs/superpowers/plans/2026-07-03-age-ensemble-v2.md` · `fixager.md` (исполнен) ·
  `.claude/rules/insight.md` · `vozrast.md`
- Tests: `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
