# Known Bugs & Fixes

## Fixed

- **FOREIGN KEY constraint failed on promises** (2026-04-08): contact_id was NULL for unknown callers. Fix: skip promises save when contact_id is NULL.
- **JSON truncation from LLM** (2026-04-08): max_tokens too low (1024). Fix: increased to 1500, added truncated JSON repair in parser.
- **SQL binding mismatch in enricher** (2026-04-08): query had 1 placeholder, 0 params. Fix: corrected parameter tuple.
- **HF token in git** (2026-04-07): hardcoded token blocked push. Fix: moved to os.environ.get("HF_TOKEN").

## Known Issues

- Events table may be empty if enrichment ran before events extraction was added. Fix: run `backfill-events`.
- Some analyses have raw_llm but no parsed fields (partial parse). These count as partial successes.
