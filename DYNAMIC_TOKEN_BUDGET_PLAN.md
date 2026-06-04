# Dynamic Output Token Budget — Plan

**Scope:** Main call-analysis path (the 17k production run). Replace the static
`max_tokens=1500` with a value-scaled, hardware-bounded budget so long/rich
conversations get the output room they deserve and short calls stop reserving
room they never use.

**Status:** Design. Code written here, run on the GPU box.
**Author note:** mirrors the pattern already proven in `biography/prompts.py`
(`calculate_dynamic_budget` + CRS multiplier) and reuses `analyze/prompt_budget.py`.

---

## 1. Current state (facts from code)

| Where | Value | Notes |
|-------|-------|-------|
| `bulk/enricher.py:398` | `max_tokens=1500` | hardcoded — the 17k run uses this |
| `analyze/service.py:43` | default `1500` | service-level default |
| `analyze/llm_client.py:81` | default `1500` | client-level default |
| `analyze/prompt_budget.py` | `clip_transcript_for_llm()` | input clip util **(verify it is wired into enricher — enricher currently passes `transcript_text` raw)** |
| `pipeline.md` | `parse_status="output_truncated"` | contract exists, but `finish_reason` is **not** read today |
| `_SHORT_CALL_THRESHOLD` | skip-LLM | very short calls already bypass the LLM |

**Problem:** a long, high-value call hits the 1500 ceiling → JSON truncated →
lost promises/facts. Per `decisions.md` blast-radius, that corrupts `events.quote`
→ Knowledge Graph → biography `bio_scenes.key_quote` downstream. Truncation on the
valuable tail is the real cost, not the short calls.

---

## 2. Mental model (the part that makes this correct, not cargo-cult)

Two independent ceilings. Respect both:

1. **Hardware / context ceiling** — `prompt_tokens + max_tokens ≤ n_ctx`.
   With llama-server, the KV cache for the full `n_ctx` is **allocated once at
   launch** (`-c 16384`). Therefore **per-request `max_tokens` does NOT change
   VRAM** — it only costs *decode time* and must fit under what the prompt leaves
   free. → 12 GB VRAM constrains the *launch* `n_ctx` (and quant), not the per-call
   budget.

2. **Policy ceiling** — an absolute cap (e.g. 4096) + a length gate so a single
   2-hour call can't balloon the 17k-run wall-clock.

**Consequence:** raising the ceiling is *near-free* — it only spends time on calls
that genuinely emit more tokens (the valuable ones). Short calls are unaffected
because the model stops at the natural end of the JSON regardless of the ceiling.

So the layered picture the request asked for:

```
12 GB VRAM ──sets──▶ launch n_ctx + quant  (one-time, governs INPUT capacity too)
                         │
                         ▼
   per-call max_tokens = clamp( value_budget(call),
                                floor,
                                min(n_ctx − prompt_tokens − margin,   ← hardware
                                    ABS_MAX) )                         ← policy
```

---

## 3. VRAM → n_ctx table (pin this first — it's the master knob)

Model per `CLAUDE.md`: Qwen3.5-9B. There is **doc drift** on the real `n_ctx`:
`CLAUDE.md` launch cmd says `-c 16384`; `biography/prompts.py` assumes 24576/32768.
**Decision required: confirm the launch line on the box.**

| n_ctx | quant | ~VRAM (9B, +KV) | input transcript cap | verdict on 12 GB |
|------:|-------|----------------:|---------------------:|------------------|
| 16384 | Q8_0  | ~11 GB          | ~10K tok (~24K ch)   | **safe, current** |
| 24576 | Q5_K_M + FA | ~11.4 GB  | ~18K tok (~38K ch)   | biography's prod setting; needs flash-attn |
| 32768 | Q5_K_M + FA | ~15 GB    | ~28K tok             | **OOM risk on 12 GB** — avoid |

Bigger budgets for long calls ultimately come from raising `n_ctx` (lower quant +
flash-attention), because input *and* output both draw from the same window. The
per-call formula below works at any `n_ctx` via one constant.

Recommended start: **`n_ctx = 16384, Q8_0`** (quality-preserving), tune up only if
input clipping proves lossy on real long calls.

---

## 4. The budget function

Inputs available at the call site **with zero extra LLM cost**:
- `transcript_chars` (primary — the request's instinct: longer = more valuable)
- `duration_sec` (from `calls`) — fallback/corroborating signal
- `profanity['density']` (already computed) — conflict signal
- contact `priority` / prior `risk_score` (already pulled into the context block)
- segment / speaker-turn count — dialogue density

**Tiered v1 (KISS, testable):**

```python
# analyze/output_budget.py  (new, ~40 lines)
SAFETY_MARGIN = 512        # tokens of headroom under n_ctx
ABS_MAX       = 4096       # policy ceiling for the 17k run
FLOOR         = 400

def output_budget(transcript_chars: int, prompt_tokens: int, n_ctx: int,
                  *, priority: int = 0) -> int:
    if   transcript_chars <  800:  base = 700    # routine / sub-1-min
    elif transcript_chars < 3000:  base = 1500   # today's default
    elif transcript_chars < 8000:  base = 2600   # substantive
    else:                          base = 3600   # long / high-value tail

    if priority >= 70:             base = int(base * 1.2)   # known-important contact

    hardware_ceiling = n_ctx - prompt_tokens - SAFETY_MARGIN
    return max(FLOOR, min(base, hardware_ceiling, ABS_MAX))
```

**Continuous v2 (optional, smoother):**
`base = 700 + 0.5 * transcript_chars ** 0.85`, then same clamps. Prefer tiered for
v1 — easier to unit-test and reason about; revisit after telemetry.

`prompt_tokens` estimate reuses `prompt_budget.estimate_tokens()` on the assembled
system+user message (don't guess — measure the actual strings).

Keep input and output drawing from the *same* `n_ctx` so `input+output ≤ n_ctx` is
provable: clip transcript via `clip_transcript_for_llm(t, max_chars)` where
`max_chars` is derived from `n_ctx − reserved_output − system`.

---

## 5. Telemetry & safety loop (closes "don't lose valuable calls")

1. **Read `finish_reason`.** llama-server returns `choices[0].finish_reason`:
   `"stop"` = complete, `"length"` = hit the ceiling = truncated. Today the code
   only checks `llm_response is None`. Add the check.
2. On `"length"`: set `parse_status="output_truncated"` (contract already in
   `pipeline.md`), log it, and **optionally one retry** at `min(budget*1.5, hardware,
   ABS_MAX)`. Bounded — never loops.
3. **Per-call log line:** `transcript_chars, prompt_tok_est, budget, out_tokens,
   finish_reason, tps`. This is the calibration dataset.
4. After ~500 real calls: percentile-tune the tier thresholds from actual
   `out_tokens` distribution (same spirit as `bs_thresholds` calibration). Most
   calls will sit well under 1500 → confirms short calls were over-provisioned and
   the long tail was being clipped.

---

## 6. Throughput impact on the 17k run

- Cost = `actual_decoded_tokens × time_per_token`. Ceiling raises cost **only**
  when the model truly emits more (the valuable calls).
- Rough mix: ~70% short/normal (≤ today's cost), ~25% substantive (modest +),
  ~5% long tail (now complete instead of truncated). Expected net decode increase
  **~5–10%**, in exchange for eliminating truncation on the exact calls that matter.
- Guardrail: global CLI knob `--max-output-cap N` (lowers `ABS_MAX`) for time-boxed
  runs. Default `ABS_MAX=4096`.

---

## 7. Integration points (minimal diff)

1. **New** `analyze/output_budget.py` — `output_budget()` + `estimate_prompt_tokens()`.
   Pure functions, fully unit-tested. No I/O.
2. `analyze/llm_client.py` — read & return `finish_reason` alongside text
   (or expose via a small result dataclass). Keep `max_tokens` a param (already is).
3. `analyze/service.py` — accept `n_ctx` (from config) + `priority`; compute budget;
   pass through. Replace the `1500` default with the computed value.
4. `bulk/enricher.py:392` — call `output_budget(...)` instead of literal `1500`;
   wire clip; record telemetry; honor `--max-output-cap`.
5. **Config** — add `models.llm_n_ctx` (default 16384) + `analysis.output_abs_max`
   (default 4096) to YAML so the box can tune without code edits. Single source of
   truth for the master knob from §3.
6. `graph/llm_disambiguator.py` (800) and biography passes already set their own
   budgets — **leave them**; this change is scoped to the call-analysis path only.

---

## 8. Rollout (TDD, per project rules)

- **P0 — pin reality:** confirm launch `-c` and quant on the box; set config.
- **P1 — pure function:** `output_budget()` + tests (boundaries: 799/800/2999/3000/
  7999/8000 chars; priority bump; hardware-ceiling clamp when prompt is huge; floor;
  ABS_MAX). RED→GREEN.
- **P2 — finish_reason:** plumb through `llm_client`; test truncation→`output_truncated`
  + bounded single retry.
- **P3 — wire enricher:** swap literal, add telemetry log, `--max-output-cap`.
- **P4 — shadow run:** 200–500 real calls, collect the log, eyeball truncation rate
  before/after, percentile-tune tiers.
- **P5 — full 17k.** Then `graph-replay` + biography p1/p2 rebuild only if truncation
  was materially reduced (blast-radius per `decisions.md`).

---

## 9. Open decisions (need owner input)

1. **`n_ctx` on the box** — 16384/Q8 (quality, recommended) vs 24576/Q5_K_M+FA
   (room for full long-call input, but quant-quality + flash-attn dependency).
   *Master knob — everything scales from it.*
2. **Priority of the 17k run** — quality (let long calls run to 3600–4096) vs
   wall-clock (cap `ABS_MAX` lower, e.g. 2600). Knob exists either way; just sets
   the default.
3. **Value signal** — length-only (simple, recommended v1) vs composite
   (length + duration + contact priority). Composite is a one-line change once the
   telemetry says length alone mis-ranks some calls.
4. **Truncation retry** — on by default (one bounded retry) or log-only?
```
