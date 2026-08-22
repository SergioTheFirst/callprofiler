# T-25 — Канареечный прогон на боксе (RTX 3060, Windows) после серии 2026-08-22

> Код этой серии (T-07/T-06/T-08/T-12/T-11/T-14/T-15/T-16/T-17/T-21/T-22/T-23) написан и
> протестирован на dev-ноутбуке без GPU/БД. Ниже — порядок проверки на боксе. Каждый шаг: команда →
> ожидаемый результат → что делать при отклонении. Ничего не пропускать; при FAIL — стоп и rollback.

## 0. Подготовка (T-20 гейт)
1. Остановить `watch`, дашборд, бота.
2. `git pull` → `pip install -e ".[dev,full]"` → `python -m pytest -q` (ожидается 0 failed).
3. `python -m callprofiler backup` → `python -m callprofiler verify-backup <файл>` → запомнить путь.
4. `python -m callprofiler doctor` — чеки `backup` OK, `db-schema` OK; `dead-letters` — записать число.

## 1. Миграции 10–11 (next_retry_at, asr_coverage)
- Первый запуск любой команды применит миграции (журнал `schema_migrations`, `PRAGMA user_version=11`).
- Проверка: `sqlite3 C:\calls\data\db\callprofiler.db "PRAGMA user_version; SELECT COUNT(*) FROM calls WHERE next_retry_at IS NOT NULL;"` → `11`, `0`.
- Отклонение: checksum-mismatch → не править миграции; `restore` из п.0.3.

## 2. Промпт v002 (T-14) — канарейка ДО массового прогона
- `python -m callprofiler canary-analyze --user me --n 30` (llama-server в LLM-окне).
- Ожидание: `parse_fail%` и `truncated%` не хуже прежнего отчёта v001 (M4); в логе — `owner_name` из
  `users.display_name`, ни одного «Сергей Медведев» в системном промпте.
- Отклонение: parse_fail% вырос > 5 п.п. → откат `PROMPT_VERSION_ANALYZE='v001'` (одна строка,
  `analyze/service.py`), кэш v002 не мешает.

## 3. Строгий анализ (T-15) — наблюдать первые 50 звонков
- `python -m callprofiler watch` на 50 новых звонков → `doctor`: `dead-letters` не выросло более чем на
  5 % от числа звонков; в `calls.error_message` нет «LLM parse_failed» массово.
- Отклонение: массовые `LLM parsed_partial` → проверить, что llama-server отвечает полным JSON
  (json_mode флаг M4), не снижать строгость.

## 4. ASR-покрытие (T-11)
- `SELECT COUNT(*), AVG(asr_coverage) FROM calls WHERE asr_coverage IS NOT NULL;` → среднее ≥ 0.95;
  доля `error_message LIKE 'ASR partial coverage%'` < 2 %.
- Отклонение: > 10 % → временно `models.asr_min_coverage: 0.5` в base.yaml и завести задачу на окна GigaAM.

## 5. GPU-барьер (T-12)
- В логе после каждого батча нет `[gpu] VRAM-барьер … НЕ пройден`; `nvidia-smi` в LLM-фазе показывает
  только llama-server.
- Отклонение: барьер срабатывает ложно (фоновые процессы держат VRAM) → `models.gpu_unload_barrier_mb`
  поднять до измеренного фона + 256.

## 6. Retry/backoff (T-07) и карантин
- Искусственно: положить битый mp3 в `C:\calls\in` → через цикл watcher звонок `error`,
  `next_retry_at` в будущем (≈ `retry_interval_sec`); повторы не чаще интервала; после `max_retries` —
  в `doctor dead-letters`. `reprocess --user me` повторяет только свои.

## 7. Purge (T-06) — только на копии или тест-профиле
- `python cleanup.py purge-user --user testuser --db <копия>` (dry-run) → счётчики по ВСЕМ таблицам;
  `--apply` → строки нулевые, файлы в `data/trash/testuser-<ts>/`. Боевой профиль `me` не трогать.

## 8. Дашборд / карточка
- Деталь звонка с `asr_coverage<1` показывает «⚠ распознано частично»; досье не содержит
  темперамент/Big Five/мотивацию (T-23); карточка пишется атомарно (нет `.tmp` в sync).

## 9. Rollback
- Любой FAIL выше: остановить watch → `python -m callprofiler restore <бэкап из п.0.3>` → `git checkout
  <предыдущий тег/коммит>` → `pip install -e ".[dev,full]"`. Миграции 10–11 аддитивны (лишние колонки
  старому коду не мешают) — откат БД нужен только при порче данных.
