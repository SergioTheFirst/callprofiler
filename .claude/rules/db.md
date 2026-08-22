# DB Rules

- SQLite only. No ORM. Use `sqlite3` directly.
- Every SELECT/UPDATE/DELETE MUST have `WHERE user_id = ?`.
- contact_id can be NULL (unknown callers) — handle gracefully, no FK crash.
- Schema changes (T-05, 2026-08-08): новая запись в `db/migrations.py::ALL_MIGRATIONS`
  (ordered, checksummed, журнал в БД; `Repository._migrate()` зовёт `apply_migrations`). Применённую
  миграцию НЕ править — checksum-mismatch падает громко намеренно. `schema.sql` держать в sync
  (свежая БД = schema.sql + все миграции no-op). Recreate таблиц запрещён.
  Restore боевой БД — только `backup`/`verify-backup`/`restore` (`ops/backup.py`, T-20).
- Transactions for batch operations (bulk-load, bulk-enrich).
- FTS5 index on transcripts for full-text search.
- Integer milliseconds for all timestamps in segments.
- MD5 hash for deduplication (per user_id).

## Purge (T-06, 2026-08-22)

- `Repository.purge_user(user_id, apply)` — **introspection, не список**: каждая таблица `sqlite_master`
  (кроме `schema_migrations`, `transcripts_fts*`) обязана иметь правило: колонка `user_id` → `user_id=?`;
  без неё → `CHILD_RULES` (`transcripts`/`analyses` по `call_id IN (calls юзера)`, `bio_scene_entities`
  по `scene_id IN (bio_scenes юзера)`); иначе `RuntimeError` (fail-loud, тест
  `test_purge_user_introspection_classifies_all_tables` собирает ПОЛНУЮ схему всех `apply_*_schema`).
  Новая таблица без `user_id` → добавить правило в `CHILD_RULES`, иначе purge громко падает.
- `apply=True`: `PRAGMA foreign_keys=OFF` на время транзакции (RESTRICT/порядок не важны), порядок
  DELETE: CHILD_RULES → OWNED → `users`; перед commit `PRAGMA foreign_key_check` обязан быть пустым
  (иначе rollback + RuntimeError — сироты невозможны). Нельзя звать внутри открытой транзакции/UoW.
- Файлы: `ops/purge_files.py::purge_user_files(config, user_id, apply)` — ОДИН `shutil.move` корня
  (`data_dir/users/{uid}`, `text_export_dir/users/{uid}`, `sync_dir/{uid}`) в
  `data_dir/trash/{uid}-{ts}/{i}-{parent}/{uid}` (восстановление = move обратно; rmtree нигде);
  гарды: `validate_user_id` (нет `..`/разделителей), корень строго внутри своей базы, корень-симлинк
  пропускается, назначение внутри trash. `cleanup.py purge-user|keep-only --apply` зовёт после DB-purge
  (`--config` для путей; `load_config(validate=False)`).

## Idempotency

All operations must be idempotent:
- **bulk-load:** skip files with existing MD5 hash (per user_id)
- **bulk-enrich:** skip calls that already have analysis
- **extract-names:** skip contacts that already have guessed_name
- **save_events:** check for duplicate (call_id + event_type + payload) before insert

Repeated runs must never duplicate data.
