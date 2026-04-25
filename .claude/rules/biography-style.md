# Biography Style Rules

## General

- Prose output ≤ 300 chars per paragraph.
- No statistics in user-facing text (no call counts, no durations).
- Language: match the contact's language (Russian if quotes are Russian).
- Never speculate beyond extracted data.
- Always cite source calls with dates when making factual claims.

---

## Psychology Profile Output Contract

**Source:** `PsychologyProfiler.build_profile()` in `biography/psychology_profiler.py`

**Structure (returned dict):**

| Key              | Type           | Content |
|------------------|----------------|---------|
| `entity_id`      | int            | Graph entity id |
| `canonical_name` | str            | Primary name |
| `entity_type`    | str            | person / org / project |
| `aliases`        | list[str]      | Known name variants |
| `metrics`        | dict           | Raw entity_metrics row |
| `patterns`       | list[dict]     | Behavioral patterns with severity |
| `temporal`       | dict           | Activity timing stats |
| `social`         | dict           | Org links, open_promises, conflict_count, centrality |
| `evolution`      | list[dict]     | Year-by-year avg_risk buckets |
| `top_facts`      | list[dict]     | Up to 5 verbatim quotes (confidence ≥ 0.6) |
| `interpretation` | str or None    | 3-paragraph LLM prose |

**Interpretation field format (3 paragraphs, ≤ 250 words total):**
1. **Communication style** — how this person communicates (direct/evasive, reliable/volatile)
2. **Trust signals** — key risk indicators or trust factors
3. **Interaction recommendation** — one actionable suggestion for next conversation

**When `interpretation` is None:**
- LLM was unreachable or timed out
- The structured data (metrics, patterns, temporal, social) is still valid
- CLI displays "(LLM interpretation unavailable)"
- Never block the caller — None is always a valid return

**Pattern severity levels:**
- `positive` — reliable, low risk
- `low` — neutral / insufficient data
- `medium` — pattern above threshold but below 1.5× threshold
- `high` — pattern at or above 1.5× threshold

**Temporal frequency_trend values:**
- `increasing` — second half of calls per day > first half × 1.2
- `decreasing` — second half < first half × 0.8
- `stable` — within 20% of first-half rate
- `insufficient_data` — fewer than 4 calls total
- `unknown` — no call timestamps

---

## CLI Output Contract

`person-profile` default (non-JSON) output:
```
=== Psychology Profile: <name> ===
Type: <type>  |  Aliases: <aliases>
BS-index: <n>  |  avg_risk: <n>
Temporal: <n> calls/week  |  trend: <trend>

Patterns:
  [<severity>] <name>: <label>

Social: centrality=<n>, open_promises=<n>, conflicts=<n>

--- Interpretation ---
<3 paragraph prose>
```

`person-profile --json` → full dict as pretty JSON.

`profile-all` → one line per entity: `[ok|no-llm|skip] <id>: <name>`, then summary.

---

## Integration with book-chapter pipeline

`PsychologyProfiler` is **independent** of the 8-pass biography orchestrator.
It does not read biography checkpoints and does not write to bio_* tables.

To use psychology profiles inside biography passes:
1. Run `graph-health --user X` (exit 0 required)
2. Call `PsychologyProfiler(conn).build_profile(entity_id, user_id)`
3. Pass `profile["interpretation"]` as context to the relevant biography pass
4. Never pass `profile["metrics"]` raw to LLM — format it first
