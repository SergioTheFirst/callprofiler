# Knowledge Graph Rules

Architecture and constraints for the graph layer (Этап 1 + 2).
Graph entities are SEPARATE from biography entities (`bio_entities`).

---

## Three-Layer Separation

1. **Extraction** — LLM writes `entities`, `relations`, `structured_facts`
   into `analyses.raw_response` (JSON, schema_version='v2').
2. **Aggregation** — Python deterministically reads raw_response and writes
   `entities`, `relations`, `events` tables. No LLM involved.
3. **Interpretation** — Future LLM passes receive structured aggregates
   (entity_metrics, BS-index) as context, not raw transcripts.

Never skip a layer. Aggregation Python must stay deterministic so the
BS-index formula can be versioned and upgraded without re-running LLM.

---

## Layer Contract (Architectural Invariants)

**events table = DERIVED (read-only source of truth for graph aggregation).**

- events.entity_id, fact_id, quote, polarity, intensity, speaker_attribution
  are **puresly computed** from analyses.raw_response (schema_version='v2')
- events.entity_id/fact_id/quote/speaker_attribution may be **safely recreated**
  by running `graph-replay --user X --limit N`
- events WHERE schema_version='v1' OR entity_id IS NULL are **never touched** by replay
  (legacy events from pre-graph pipeline)

**graph (entities/relations/entity_metrics) = DERIVED from events (schema_version='v2').**

- graph is rebuilt by aggregating events WHERE user_id=? AND call_id IN (
  SELECT id FROM calls WHERE user_id=? AND id IN (SELECT DISTINCT call_id FROM events WHERE user_id=? AND schema_version='v2')
- Replay is idempotent:
  - DELETE entity_metrics, relations, entities (unarchived)
  - UPDATE events SET entity_id=NULL, fact_id=NULL, quote=NULL where v2
  - Re-run GraphBuilder → entities/relations/entity_metrics regenerate deterministically
  - Second replay on same data produces 0 new rows (dedup via fact_id)

**This enables:**
- Safe data fixing (fix raw_response, replay) without manual SQL
- Formula upgrades (new BS-formula, replay with new aggregator)
- Fact validation post-hoc (validator filters on replay)
- Transparency (every graph row traceable to analyses.raw_response + call_id)

---

## schema_version Contract

- `'v1'` — legacy analyses (raw_response has no graph fields). Skip silently.
- `'v2'` — graph-enabled: `raw_response` MUST contain `entities`, `relations`,
  `structured_facts` arrays. `GraphBuilder.update_from_call()` processes only v2.
- New LLM-analyzed calls get `schema_version='v2'` from the prompt.
- Existing rows keep `schema_version='v1'` (ALTER TABLE sets DEFAULT 'v1').
- To migrate old calls: `reenrich-v2 --user X --limit N` (deletes v1 analyses
  so enricher re-processes them with the new prompt).

---

## Anti-Noise Filters (in GraphBuilder)

All structured_facts go through two gates before upsert:

1. `confidence >= 0.6` (MIN_FACT_CONFIDENCE in graph/config.py)
2. `len(quote.strip()) >= 5` (MIN_QUOTE_LENGTH in graph/config.py)

Facts failing either gate are silently discarded. Do not lower these thresholds
without a measured experiment — lowering them floods the graph with noise.

Quotes MUST be verbatim transcript excerpts. `GraphBuilder` does not verify
verbatimness — that is the prompt's responsibility. `analyze_v001.txt` states
"quote — точная цитата из транскрипта, не перифраз".

---

## Fact Deduplication

`fact_id = sha256(f"{fact_type}|{entity_id}|{quote}")[:16]`

Upserted via `INSERT OR IGNORE` on `events(fact_id)` using partial unique index:
`CREATE UNIQUE INDEX IF NOT EXISTS idx_events_factid ON events(fact_id) WHERE fact_id IS NOT NULL`

Same quote from the same entity on the same fact_type = same fact. Running
`graph-backfill` twice on the same call must produce 0 new rows on second run.

---

## Relation Weight Decay

Half-life = 180 days (`RELATION_DECAY_DAYS` in graph/config.py).

```
new_weight = existing.weight * 0.5^(days_since_last_seen / 180) + confidence
```

Applied on every `upsert_relation_with_decay()` call. If no existing relation,
weight = confidence. Weight is clamped to [0.0, 1.0] implicitly by confidence range.

Do not change the formula without bumping the field name or adding a version column
so old weights can be identified.

---

## CLI Commands

### graph-replay (Идемпотентная пересборка)

```bash
python -m callprofiler graph-replay --user <USER_ID> [--limit N]
```

Перестраивает граф из v2 analyses (entities/relations/entity_metrics) с нуля.

**Логика:**
1. DELETE entity_metrics, relations, entities (unarchived)
2. UPDATE events SET entity_id/fact_id/quote/polarity/intensity = NULL (v2 only)
3. Получить все v2 analyses, передать в GraphBuilder.update_from_call()
4. Пересчитать metrics для всех entities через full_recalc_from_events()

**Assertions (exit code != 0):**
- facts_count > 0 если calls_processed > 0
- orphan_events == 0 (events с несуществующей entity_id)
- owner_contamination == 0 (owner entities с bs_index > 0)

**Используется:**
- После ручного исправления raw_response в analyses
- После смены formula версии BS-index
- Для тестирования детерминизма (вторая replay == первой replay)

---

## BS-Index Formula v1_linear

Deterministic. All raw counters saved to `entity_metrics` so future formula
versions can be applied without re-scanning events.

```python
bs_raw = (
    0.40 * broken_ratio          # promise_broken / total_facts
    + 0.20 * contradiction_dens  # contradictions / total_facts
    + 0.15 * vagueness_dens      # vagueness / total_facts
    + 0.15 * blame_shift_dens    # blame_shift / total_facts
    + 0.10 * emotional_dens      # emotion_spike / total_facts
)
bs_index = min(bs_raw * 100.0, 100.0)
```

`formula_version = "v1_linear"` stored per entity_metrics row.

To upgrade: add `BS_FORMULA_VERSION = "v2_..."` in `graph/config.py`,
add new formula in `aggregator.py`, re-run `graph-backfill`.

---

## events Table Extension

The `events` table serves dual purpose: original pipeline events + graph facts.
Event types `emotion_spike`, `vagueness`, `blame_shift`, `claim` map to `'fact'`
to satisfy the CHECK constraint on `event_type`.

Extended columns (added via ALTER TABLE in `apply_graph_schema()`):

| Column     | Type    | Purpose                          |
|------------|---------|----------------------------------|
| entity_id  | INTEGER | FK → entities.entity_id          |
| fact_id    | TEXT    | Dedup hash (sha256, 16 chars)    |
| quote      | TEXT    | Verbatim transcript excerpt      |
| start_ms   | INTEGER | Transcript segment start         |
| end_ms     | INTEGER | Transcript segment end           |
| polarity   | REAL    | Sentiment (-1.0 to +1.0)         |
| intensity  | REAL    | Signal strength (0.0 to 1.0)     |

Legacy events (from pipeline, before graph) have all graph columns = NULL.

---

## Module Structure

```
src/callprofiler/graph/
    __init__.py     GraphBuilder, EntityMetricsAggregator exports
    config.py       Thresholds and formula constants
    repository.py   GraphRepository + apply_graph_schema()
    builder.py      GraphBuilder.update_from_call()
    aggregator.py   EntityMetricsAggregator.recalc_for_entities()
```

`apply_graph_schema(conn)` — idempotent, safe to call on every startup.

---

## Integration Points

- **enricher.py**: `_update_graph()` called after each batch flush.
  Gated by `cfg.features.enable_graph_update`. Non-fatal (lazy import,
  wrapped in try/except).
- **orchestrator.py**: Graph update called after `save_promises()`.
  Same non-fatal pattern. `apply_graph_schema()` called before builder.
- **cli/main.py**: 3 commands — `graph-backfill`, `reenrich-v2`, `graph-stats`.

---

## Health Gate Rule

**`graph-health --user X` exit 0 is REQUIRED before running `book-chapter` or any
biography pass that reads entity_metrics.**

`graph-health` runs 4 checks (exit 0 = all pass, exit 1 = any fail):
1. Last `graph-replay` run: `rejection_rate < 0.90`
2. `graph-audit` → no CRITICAL issues
3. `entity_metrics` has at least 1 row for `user_id`
4. `bs_thresholds` has calibrated thresholds for `user_id`

If the gate fails, fix the indicated issue then re-run `graph-replay --user X`.

---

## CLI Commands

```bash
# Fill graph from existing v2 analyses (or all with --schema all)
python -m callprofiler graph-backfill --user USER_ID [--schema v2|all]

# Delete v1 analyses so enricher re-processes with new prompt
python -m callprofiler reenrich-v2 --user USER_ID [--limit N]

# Print graph stats (entity/relation/fact counts)
python -m callprofiler graph-stats --user USER_ID

# Run 4 stability checks (REQUIRED before book-chapter)
python -m callprofiler graph-health --user USER_ID
```

---

## Roadmap: Этапы 3-4 (NOT implemented yet)

### Этап 3 — EntityResolver (fuzzy merge, Python-only)

- Normalize all `normalized_key` values: strip accents, lower, collapse spaces.
- Build candidate pairs: Levenshtein distance ≤ 2 OR first-name prefix match.
- Merge if: same entity_type AND (same alias set OR distance ≤ 2 AND same user_id).
- Never auto-merge across entity_types (PERSON ≠ COMPANY).
- Merges are recorded in `entity_merges` table (merge_from, merge_into, reason,
  merged_at, merged_by='auto'). Auditable, reversible.
- CLI: `graph-resolve --user X --dry-run` (shows candidates without merging).

### Этап 4 — LLM-Assisted Merge

- For candidate pairs that EntityResolver can't decide (score 0.4-0.6):
  call llama-server with short prompt: "Are these the same entity? YES/NO + reason".
- Rate limit: max 50 LLM calls per resolve run.
- Merge recorded with `merged_by='llm'` in `entity_merges`.
- CLI: `graph-resolve --user X --llm-assist`.
- Never implement auto-merge without dry-run mode working first.

---

## What This Layer Is NOT

- Not a replacement for `biography/` — biography uses `bio_entities`, graph
  uses `entities`. They are separate schemas with separate purposes.
- Not a real-time query engine — graph is updated after call enrichment,
  not during.
- Not a trust score for humans — BS-index measures linguistic patterns
  (broken promises, contradictions, vagueness), not character judgments.
