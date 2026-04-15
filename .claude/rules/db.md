# DB Rules

- SQLite only. No ORM. Use `sqlite3` directly.
- Every SELECT/UPDATE/DELETE MUST have `WHERE user_id = ?`.
- contact_id can be NULL (unknown callers) — handle gracefully, no FK crash.
- Schema changes: ALTER TABLE, never recreate. Update schema.sql to match.
- Transactions for batch operations (bulk-load, bulk-enrich).
- FTS5 index on transcripts for full-text search.
- Integer milliseconds for all timestamps in segments.
- MD5 hash for deduplication (per user_id).
