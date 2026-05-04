# Dynamic Resource Allocation Design

**Date:** 2026-05-04  
**Author:** AI Assistant  
**Status:** Approved for implementation

---

## Problem Statement

Current biography pipeline uses **fixed token budgets** per pass (e.g., p6_chapters always gets 17,000 chars input). This wastes resources on thin material and under-utilizes GPU on rich material.

**Critical issue:** Long calls (>10 min, >5K chars transcript) contain deepest psychological insights but get truncated to fit fixed 12K char limit in p1_scene.

**Goal:** Adaptive budget allocation based on content richness + special priority for long calls.

---

## Design Principles

1. **Budget follows content richness, not fixed limits**
2. **Long calls = quality priority over speed** (never truncate)
3. **Thin months get honest brevity** (500-1000 words, no padding)
4. **Rich material gets maximum safe GPU allocation**
5. **Psychology depth scales with available budget**
6. **Adaptive feedback loop** (adjust budgets based on output quality)

---

## Architecture

### 1. Content Richness Score (CRS)

**Multi-factor formula:**
```python
CRS = (importance_avg × 0.4) + (entity_density × 0.3) + (arc_density × 0.3)

where:
  importance_avg = mean(scene.importance) / 100  # 0.0-1.0
  entity_density = unique_entities / max(scenes, 1)
  arc_density = arc_count / max(scenes, 1)
```

**Interpretation:**
- `CRS < 0.3` → thin material (reduce budget 50%)
- `CRS 0.3-0.7` → normal (baseline budget)
- `CRS > 0.7` → rich material (expand to safe max)

---

### 2. Long Call Priority Rule

**Detection:**
```python
def is_long_call(duration_sec: int, transcript_length: int) -> bool:
    return duration_sec > 600 or transcript_length > 5000
```

**Special handling:**
- **Budget multiplier:** 2.0× (double baseline)
- **Clipping mode:** "smart" (extract key fragments, not head+tail)
- **Processing:** Chunked if needed (preserve all content)
- **Psychology:** Prioritize participants for deep profiles

**Rationale:** Long calls reveal current state, mood, detailed facts. Must never truncate for speed.

---

### 3. Dynamic Budget Calculation

**Per-pass formula:**
```python
def calculate_dynamic_budget(
    pass_name: str,
    crs: float,
    is_long_call: bool = False,
    context_window: int = 16384
) -> int:
    # Safe reserves
    system_tokens = 2200
    output_tokens = PASS_OUTPUT_RESERVES[pass_name]
    available_tokens = context_window - system_tokens - output_tokens
    
    # Baseline (current BUDGETS values)
    baseline_chars = BASELINE_BUDGETS[pass_name]
    
    # CRS multiplier
    if is_long_call:
        multiplier = 2.0  # Long call priority
    elif crs < 0.3:
        multiplier = 0.5  # Thin material
    elif crs > 0.7:
        multiplier = 1.5  # Rich material
    else:
        multiplier = 1.0  # Normal
    
    dynamic_chars = int(baseline_chars * multiplier)
    
    # Safety cap
    max_safe_chars = int(available_tokens * 2.1)  # 2.1 chars/token
    return min(dynamic_chars, max_safe_chars)
```

**Constants:**
```python
BASELINE_BUDGETS = {
    "p1_scene": 12000,
    "p2_entities": 10000,
    "p3_threads": 12000,
    "p4_arcs": 14000,
    "p5_portraits": 12000,
    "p6_chapters": 17000,
    "p7_book": 9000,
    "p8_editorial": 18000,  # REDUCED from 32000 (was overflowing)
    "p9_yearly": 9500,
}

PASS_OUTPUT_RESERVES = {
    "p1_scene": 1800,
    "p2_entities": 3800,
    "p3_threads": 2500,
    "p4_arcs": 4200,
    "p5_portraits": 2500,
    "p6_chapters": 5500,
    "p7_book": 3500,
    "p8_editorial": 5500,
    "p9_yearly": 4000,
}
```

---

### 4. Chunked Processing

**For long chapters (p8_editorial) or long calls (p1_scene):**

```python
def chunk_content(content: str, max_chunk_chars: int = 18000) -> list[str]:
    """Split on semantic boundaries (## headers or speaker turns)."""
    # Implementation: split on \n## for chapters, on speaker changes for transcripts
    pass

def process_chunked(chunks: list[str], prompt_builder, prev_context: str = "") -> str:
    """Process chunks sequentially, preserve continuity."""
    results = []
    for i, chunk in enumerate(chunks):
        prompt = prompt_builder(
            chunk=chunk,
            prev_context=prev_context,
            is_first=(i == 0),
            is_last=(i == len(chunks) - 1)
        )
        result = call_llm(prompt)
        results.append(result)
        prev_context = result[-500:]  # Last 500 chars for continuity
    return "\n\n".join(results)
```

**Triggers:**
- p1_scene: if `is_long_call()` and `len(transcript) > 24000` (2× baseline)
- p8_editorial: if `len(chapter_prose) > 18000`

---

### 5. Psychology Depth Allocation

**Budget-aware profile expansion:**

```python
def allocate_psychology_budget(
    entity_ids: list[int],
    available_tokens: int,
    crs: float
) -> dict:
    if crs > 0.7:
        # Rich material: top-10 entities, deep profiles
        profile_count = min(10, len(entity_ids))
        profile_depth = "deep"  # All OCEAN + motivation + network + evolution
    elif crs < 0.3:
        # Thin material: top-3 entities, basic profiles
        profile_count = min(3, len(entity_ids))
        profile_depth = "basic"  # Temperament + top 2 OCEAN traits
    else:
        # Normal: top-6 entities, standard profiles
        profile_count = 6
        profile_depth = "standard"  # Current behavior
    
    return {
        "profile_count": profile_count,
        "profile_depth": profile_depth,
        "tokens_per_profile": available_tokens // profile_count
    }
```

**Profile depth modes:**
- **basic:** Temperament + 2 OCEAN traits (500 tokens)
- **standard:** Temperament + 5 OCEAN + motivation (1000 tokens)
- **deep:** Full OCEAN + motivation + network + temporal evolution + top facts (2000 tokens)

---

### 6. Adaptive Feedback Loop

**After each pass, assess output quality:**

```python
def assess_output_quality(pass_name: str, output: str, input_crs: float) -> dict:
    metrics = {
        "output_length": len(output),
        "expected_length": EXPECTED_LENGTHS[pass_name],
        "truncation_detected": "..." in output[-100:],
        "json_valid": validate_json(output) if pass_name in JSON_PASSES else None,
        "crs_utilization": len(output) / (input_crs * EXPECTED_LENGTHS[pass_name])
    }
    
    # Adjustment signal for next run
    if metrics["truncation_detected"]:
        adjustment = -0.1  # Budget was too high
    elif metrics["crs_utilization"] < 0.6:
        adjustment = +0.1  # Material was thinner than predicted
    else:
        adjustment = 0.0
    
    return {"metrics": metrics, "adjustment": adjustment}
```

**Store adjustments in `bio_checkpoints.metadata` JSON field.**

---

### 7. Thin Month Handling

**When month CRS < 0.3:**
- Generate short chapter (500-1000 words)
- Prompt hint: "Материал скудный — пиши честно и кратко, без воды."
- Mark `bio_chapters.status = 'sparse'`
- User can filter sparse chapters in final book assembly

**No artificial padding. Honest brevity > fake detail.**

---

## Implementation Plan

### Phase 1: Core Infrastructure (Tasks #8, #3)

**Files:**
- `src/callprofiler/biography/prompts.py`
- `src/callprofiler/biography/orchestrator.py`

**Changes:**
1. Add `BASELINE_BUDGETS`, `PASS_OUTPUT_RESERVES` dicts
2. Add `calculate_dynamic_budget()` function
3. Add `assess_output_quality()` function
4. Modify `orchestrator.py` to compute CRS before each pass
5. Pass dynamic budget to prompt builders
6. Store quality metrics in checkpoint metadata

---

### Phase 2: Long Call Priority (Task #6)

**Files:**
- `src/callprofiler/biography/p1_scene.py` (new module, extract from orchestrator)

**Changes:**
1. Add `is_long_call()` detection
2. Implement smart clipping (extract key fragments, not head+tail)
3. Add chunked processing for transcripts >24K chars
4. Apply 2× budget multiplier for long calls

---

### Phase 3: Chunked Editorial (Task #5)

**Files:**
- `src/callprofiler/biography/p8_editorial.py` (new module)

**Changes:**
1. Extract editorial logic from orchestrator
2. Implement `chunk_chapter_prose()` (split on ## headers)
3. Implement `editorial_pass_chunked()` with continuity preservation
4. Add `build_editorial_prompt_chunked()` with prev_context parameter

---

### Phase 4: Psychology Depth (Task #7)

**Files:**
- `src/callprofiler/biography/p5_portraits.py` (new module)

**Changes:**
1. Add `allocate_psychology_budget()` logic
2. Implement "deep" profile prompt variant
3. Expand to top-10 entities when CRS > 0.7
4. Reduce to top-3 when CRS < 0.3

---

### Phase 5: Documentation (Task #4)

**Files:**
- `CONTINUITY.md`
- `CHANGELOG.md`
- `.claude/rules/biography-prompts.md`

**Changes:**
1. Document dynamic allocation system
2. Update context budget table with new p8_editorial limit (18K)
3. Add long call priority rule
4. Document CRS formula and thresholds

---

## Safety Guarantees

**Hard constraints:**
- `input_chars × 0.476 + system_tokens + output_tokens ≤ 16384` (always enforced)
- Chunked processing triggers automatically if overflow detected
- Fallback: retry with 20% smaller budget if LLM returns truncated output

**Monitoring:**
- Log CRS, dynamic_budget, actual_output_length per pass
- Track adjustment signals in checkpoint metadata
- Alert if >10% of passes trigger chunking

---

## Expected Outcomes

**Resource utilization:**
- Thin months: 50% token reduction → faster processing
- Rich months: 30-50% token expansion → deeper psychology
- Long calls: 100% content preservation (no truncation)
- Overall: 20-30% better GPU utilization

**Book quality:**
- No artificial padding in sparse periods
- Richer character portraits when material supports it
- Long calls fully analyzed (deepest psychological insights)
- Coherent narrative (chunked processing preserves continuity)
- Honest non-fiction standard maintained

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| CRS formula inaccurate | Adaptive feedback loop adjusts over time |
| Chunked processing breaks continuity | Pass prev_context between chunks |
| Long call processing too slow | Acceptable tradeoff (quality > speed) |
| p8_editorial still overflows | Hard cap at 18K chars (safe limit) |
| Psychology profiles too shallow | Expand to top-10 + deep mode for rich material |

---

## Future Enhancements

1. **LLM-based CRS:** Pre-scan pass to assess content richness (expensive but accurate)
2. **User-configurable priorities:** CLI flag `--priority psychology|chapters|balanced`
3. **Multi-model support:** Use smaller model for thin material, larger for rich
4. **Incremental psychology:** Update profiles after each call (not batch)

---

## Approval

**Design approved by user on 2026-05-04.**

Key requirements confirmed:
- ✅ Hybrid CRS (importance × entity_count × arc_density)
- ✅ Short chapters for thin months (500-1000 words, honest brevity)
- ✅ Maximize psychology depth (priority over chapter length)
- ✅ Adaptive feedback loop (adjust after each pass)
- ✅ Chunked processing (no truncation)
- ✅ **Long call priority (never truncate for speed)**

Ready for implementation.
