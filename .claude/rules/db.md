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

## Idempotency

All operations must be idempotent:
- **bulk-load:** skip files with existing MD5 hash (per user_id)
- **bulk-enrich:** skip calls that already have analysis
- **extract-names:** skip contacts that already have guessed_name
- **save_events:** check for duplicate (call_id + event_type + payload) before insert

Repeated runs must never duplicate data.
