---
name: db-migration
description: Use when modifying database schema
---

# DB Migration Procedure

1. **ALTER TABLE** (never DROP+CREATE on tables with data)
   - Use `ALTER TABLE table_name ADD COLUMN ...` for new columns
   - Use `ALTER TABLE table_name RENAME COLUMN ...` for renames
   - SQLite doesn't support DROP COLUMN — work around with triggers
   - Plan: new column → backfill → verification

2. **Update schema.sql** to match new state
   - Modify the CREATE TABLE statement in `src/callprofiler/db/schema.sql`
   - This is the source of truth for schema documentation
   - Any future fresh installs use this schema
   - Add comments explaining new columns

3. **Update repository.py** with new methods if needed
   - Add migration logic to `_migrate()` method
   - Use PRAGMA table_info to detect missing columns (auto-migration)
   - Update save methods (save_analysis, save_batch, etc.) if columns changed
   - Use safe getattr() with defaults for backward compatibility

4. **Add index if new column will be queried**
   - If column is used in WHERE/JOIN → add `CREATE INDEX IF NOT EXISTS ...`
   - Full-text search columns → add to FTS5 virtual table
   - Reference in schema.sql under "CREATE INDEX" section

5. **Test:** Verify existing data survives migration
   - Run migration on existing test database
   - Verify row counts unchanged: `SELECT COUNT(*) FROM table_name`
   - Spot-check data integrity: query a few rows
   - Run full test suite: `pytest tests/ -v`

6. **Backward Compatible:** Old code must not break
   - New columns must have DEFAULT values
   - Old Analysis objects must work with getattr(obj, "new_field", default)
   - Don't require new fields in INSERT (use defaults)
   - Deploy migration before new code that uses the field

## PROHIBITED

- ORM (use sqlite3 directly, no SQLAlchemy/Peewee)
- Dropping existing columns (use nullable instead)
- Ignoring user_id in queries (breaks multi-user isolation)
- Schema changes without updating schema.sql
- Migration code that doesn't handle already-migrated databases
- Changes to primary keys or unique constraints without testing
