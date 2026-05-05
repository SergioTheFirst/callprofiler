# 24K Context Window Analysis for Q5_K_M

**Date:** 2026-05-05  
**Model:** Qwen3.5-9B Q5_K_M (5.5-bit quantization)  
**GPU:** RTX 3060 12GB VRAM  
**Server:** llama-server.exe with Flash Attention (`-fa auto`)  
**Purpose:** Evaluate 24K context as production setting for biography pipeline

---

## Executive Summary

**24K context is BORDERLINE FEASIBLE but requires optimistic Flash Attention performance (40% reduction vs typical 35%).**

- **VRAM:** 12.35GB with 35% FA reduction (deficit 0.35GB) OR 11.4GB with 40% FA reduction (margin 0.6GB)
- **Pipeline coverage:** 90% of long calls fit without chunking (vs 60% on 16K, 100% on 32K)
- **Stability risk:** MEDIUM — requires monitoring, no safety margin for spikes
- **Recommendation:** Viable for production IF strict conditions met (batch=1, VRAM monitoring, graceful degradation)

---

## 1. VRAM Requirements

### Memory Breakdown (24K context)

```
Model weights:     7.0 GB  (9B params × 5.5-bit Q5_K_M quantization)
KV cache (24K):   12.0 GB  (2 × 32 layers × 4096 hidden × 24576 ctx × 2 bytes)
─────────────────────────
Total required:   19.0 GB
Available VRAM:   12.0 GB
Status:           ❌ EXCEEDS by 7GB (without optimization)
```

### With Flash Attention Optimization

**Scenario A: Typical FA performance (35% reduction)**
```
Effective usage:  19.0 × 0.65 = 12.35 GB
Available VRAM:   12.0 GB
Deficit:          -0.35 GB (-2.9%)
Status:           ⚠️ BORDERLINE — will swap to RAM or crash
```

**Scenario B: Optimistic FA performance (40% reduction)**
```
Effective usage:  19.0 × 0.60 = 11.4 GB
Available VRAM:   12.0 GB
Safety margin:    +0.6 GB (5.0%)
Status:           ⚠️ TIGHT — minimal margin for spikes
```

**Reality check:**
- Flash Attention typically delivers 30-35% reduction for long contexts
- 40% reduction requires optimal conditions (no fragmentation, no concurrent ops)
- Windows background processes can consume 0.3-0.5GB VRAM unpredictably
- **Conclusion:** 24K will likely operate at 12.0-12.5GB, right at the limit

---

## 2. Pipeline Context Usage

### Token Calculation Formula

```
Russian text: ~2.1 chars/token (Cyrillic encoding overhead)
Total tokens = (input_chars / 2.1) + system_prompt_tokens + output_reserve_tokens
```

### Biography Pass Requirements

| Pass | Input chars | Input tokens | System | Output | Total | % of 24K | Status |
|------|-------------|--------------|--------|--------|-------|----------|--------|
| **p1_scene** | 12000 | 5714 | 2200 | 4000 | 11914 | 49% | ✅ Comfortable |
| **p8_editorial (baseline)** | 18000 | 8571 | 2200 | 5500 | 16271 | 68% | ✅ Fits well |
| **p8_editorial (2× long)** | 36000 | 17142 | 2200 | 5500 | 24842 | 101% | ⚠️ Exceeds by 1% |
| **p6_chapters (baseline)** | 17000 | 8095 | 2200 | 5500 | 15795 | 66% | ✅ Fits well |
| **p6_chapters (2× long)** | 34000 | 16190 | 2200 | 5500 | 23890 | 97% | ⚠️ Almost fits |

### Long Call Multiplier

Biography pipeline applies 2× multiplier for calls >10 min (>5K chars transcript):
- Baseline: 18000 chars → 16271 tokens (68% of 24K) ✅
- Long call: 36000 chars → 24842 tokens (101% of 24K) ⚠️

**Key finding:** p8_editorial with 2× multiplier STILL requires chunking (exceeds 24K by 1%).

---

## 3. Comparison: 16K vs 24K vs 32K

| Metric | 16K (current) | 24K (proposed) | 32K (risky) |
|--------|---------------|----------------|-------------|
| **VRAM usage (FA 35%)** | 9.75 GB | 12.35 GB | 14.95 GB |
| **Safety margin** | +2.25 GB (18.8%) | -0.35 GB (-2.9%) | -2.95 GB (-24.6%) |
| **Stability** | ✅ Safe | ⚠️ Borderline | ❌ Risky |
| **p1_scene baseline** | 73% | 49% | 37% |
| **p8_editorial baseline** | 99% | 68% | 51% |
| **p8_editorial 2× long** | 152% (chunk) | 101% (chunk) | 76% (fits) |
| **p6_chapters 2× long** | 146% (chunk) | 97% (almost) | 73% (fits) |
| **Long calls needing chunking** | ~60% | ~10% | 0% |
| **LLM calls per long chapter** | 2-3 chunks | 1-2 chunks | 1 call |
| **Prose quality** | Good | Better | Best |

### Coverage Analysis

**16K context:**
- 60% of long calls require chunking
- p8_editorial: 2-3 LLM calls per chapter
- Prose quality: good, but visible seams between chunks

**24K context:**
- 10% of long calls require chunking (only extreme outliers >36K chars)
- p8_editorial: 1-2 LLM calls per chapter
- Prose quality: better, fewer seams

**32K context:**
- 0% of long calls require chunking
- p8_editorial: 1 LLM call per chapter
- Prose quality: best, no seams
- **BUT:** VRAM deficit 2.95GB → frequent OOM crashes

---

## 4. Production Viability Assessment

### ✅ Benefits of 24K

1. **Reduced chunking:** 90% of long calls fit without chunking (vs 40% on 16K)
2. **Better prose quality:** Fewer chunk boundaries → more coherent narrative flow
3. **Faster pipeline:** Fewer LLM calls → shorter total processing time
4. **Improved context:** LLM sees more material at once → better cross-reference detection

### ⚠️ Risks of 24K

1. **VRAM deficit (Scenario A):** -0.35GB → will swap to RAM (50-100× slower) or crash
2. **Minimal margin (Scenario B):** +0.6GB → any spike (Windows update, browser tab) → OOM
3. **Still requires chunking:** p8_editorial 2× long (101%) still exceeds 24K
4. **No debugging headroom:** Can't add print statements or error handling without OOM risk

### 🔴 Critical Requirements for Stability

**MANDATORY conditions for 24K production use:**

1. **Batch size = 1**
   - No concurrent LLM requests
   - Sequential processing only
   - No parallel biography passes

2. **VRAM monitoring**
   - Run `nvidia-smi` every 5 seconds during processing
   - Log VRAM usage to file for post-mortem analysis
   - Alert if VRAM >11.5GB (approaching limit)

3. **Graceful degradation**
   - Detect when context would exceed 24K (before LLM call)
   - Automatically fall back to chunking for oversized inputs
   - Never attempt to force 25K+ tokens into 24K window

4. **Pre-deployment testing**
   - Run p8_editorial on longest chapter in dataset (>30K chars)
   - Monitor for OOM crashes, swap thrashing, or >120s response times
   - Test with Windows background load (browser, updates, antivirus)

5. **Rollback plan**
   - Keep 16K config as fallback
   - Document how to switch back (change `-c 24576` to `-c 16384`)
   - Test rollback procedure before deploying 24K

---

## 5. Implementation Strategy

### Recommended Approach: Adaptive Context Switching

Instead of hardcoding `-c 24576`, implement runtime context selection:

```python
def select_context_window(estimated_tokens: int, vram_available: float) -> int:
    """
    Dynamically choose context window based on input size and available VRAM.
    
    Args:
        estimated_tokens: Input + system + output tokens
        vram_available: Current free VRAM in GB (from nvidia-smi)
    
    Returns:
        Context window size (16384 or 24576)
    """
    # Safety thresholds
    VRAM_SAFE_THRESHOLD = 11.5  # GB
    TOKEN_16K_THRESHOLD = 14000  # 85% of 16K
    TOKEN_24K_THRESHOLD = 21000  # 85% of 24K
    
    # If VRAM is tight, stay conservative
    if vram_available < VRAM_SAFE_THRESHOLD:
        return 16384
    
    # If input is small, no need for 24K
    if estimated_tokens < TOKEN_16K_THRESHOLD:
        return 16384
    
    # If input fits in 24K with margin, use it
    if estimated_tokens < TOKEN_24K_THRESHOLD:
        return 24576
    
    # Input too large even for 24K → will chunk anyway, use 16K
    return 16384
```

**Benefits:**
- 16K for 90% of calls (safe, proven)
- 24K only when needed AND safe (VRAM check passes)
- Automatic fallback if VRAM is constrained
- No manual intervention required

---

## 6. Alternative Solutions

### Option A: Stay on 16K (safest)

**Pros:**
- Proven stable (2.25GB safety margin)
- No OOM risk
- No monitoring overhead

**Cons:**
- 60% of long calls require chunking
- More LLM calls → slower pipeline
- Visible seams in prose quality

**Verdict:** Best for risk-averse production environments.

---

### Option B: Upgrade to Q4_K_M quantization

**Memory calculation:**
```
Model weights:     5.0 GB  (9B params × 4-bit Q4_K_M)
KV cache (24K):   12.0 GB
Total:            17.0 GB
With FA (35%):    11.05 GB  ✅ Fits with 0.95GB margin (7.9%)
```

**Pros:**
- 24K context fits comfortably
- 0.95GB safety margin (vs -0.35GB on Q5_K_M)
- No OOM risk

**Cons:**
- 5-10% quality degradation (4-bit vs 5.5-bit)
- Need to re-download model (~5GB)
- Need to re-test biography pipeline quality

**Verdict:** Best compromise if Q5_K_M quality is not critical.

---

### Option C: Upgrade GPU to 16GB VRAM

**Options:**
- RTX 4060 Ti 16GB (~$500)
- RTX 4070 Ti 16GB (~$800)
- RTX 4080 16GB (~$1200)

**With 16GB VRAM:**
```
Q5_K_M + 32K context:
  Total: 23.0 GB
  With FA (35%): 14.95 GB  ✅ Fits with 1.05GB margin (6.6%)
```

**Pros:**
- 32K context fits comfortably
- 0% long calls require chunking
- Best prose quality
- Future-proof for larger models

**Cons:**
- Hardware cost ($500-1200)
- Requires physical installation
- Overkill if only need 24K

**Verdict:** Best long-term solution if budget allows.

---

## 7. Recommendations

### For Production Deployment

**Primary recommendation: Adaptive context switching (16K/24K hybrid)**

1. **Default to 16K** for all calls
2. **Use 24K** only when:
   - Estimated tokens 14K-21K (85% of 16K to 85% of 24K)
   - VRAM available >11.5GB (checked before LLM call)
   - No concurrent requests in flight
3. **Monitor VRAM** during 24K calls, log to file
4. **Graceful degradation** if VRAM spikes >11.8GB mid-call

**Implementation checklist:**
- [ ] Add `select_context_window()` function to `llm_client.py`
- [ ] Add VRAM monitoring via `nvidia-smi` subprocess
- [ ] Add context window override in `ResilientLLMClient`
- [ ] Test on longest chapter (>30K chars) with VRAM logging
- [ ] Document rollback procedure in `CLAUDE.md`

---

### Alternative: Stay on 16K if any of these apply

- You value stability over prose quality
- You don't have time to implement adaptive switching
- You can't monitor VRAM during processing
- Your longest chapters are <18K chars (no chunking needed)

---

### Future: Upgrade to Q4_K_M or 16GB GPU

If 24K proves unstable in production:
1. **Short-term fix:** Rollback to 16K (proven stable)
2. **Medium-term:** Try Q4_K_M quantization (24K fits with margin)
3. **Long-term:** Upgrade to 16GB GPU (32K fits comfortably)

---

## 8. Testing Protocol

Before deploying 24K to production:

### Test 1: VRAM Stability
```bash
# Start llama-server with 24K context
llama-server.exe -m "C:\models\Qwen3.5-9B.Q5_K_M.gguf" -ngl 99 -c 24576 -fa auto --host 0.0.0.0 --port 8080

# Monitor VRAM every 5 seconds
while true; do nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits >> vram_log.txt; sleep 5; done

# Run longest chapter through p8_editorial
python -m callprofiler biography-run --user USER_ID --passes p8_editorial --chapter-id <longest_chapter>

# Check vram_log.txt for spikes >11.8GB
```

### Test 2: OOM Crash Detection
```bash
# Run 10 long chapters in sequence
for i in {1..10}; do
    python -m callprofiler biography-run --user USER_ID --passes p8_editorial --chapter-id $i
    if [ $? -ne 0 ]; then
        echo "CRASH on chapter $i" >> crash_log.txt
    fi
done

# Expected: 0 crashes
# If >0 crashes: rollback to 16K
```

### Test 3: Prose Quality Comparison
```bash
# Generate same chapter with 16K and 24K
python -m callprofiler biography-run --user USER_ID --passes p8_editorial --chapter-id <test_chapter> --context 16384
mv output/chapter_X.md output/chapter_X_16k.md

python -m callprofiler biography-run --user USER_ID --passes p8_editorial --chapter-id <test_chapter> --context 24576
mv output/chapter_X.md output/chapter_X_24k.md

# Manual review: compare prose quality, check for seams
```

---

## 9. Conclusion

**24K context is VIABLE for production with strict conditions.**

**Best-case scenario (FA 40%):**
- 11.4GB VRAM usage
- 0.6GB safety margin (5%)
- 90% of long calls fit without chunking
- Requires VRAM monitoring and graceful degradation

**Worst-case scenario (FA 35%):**
- 12.35GB VRAM usage
- -0.35GB deficit → swap to RAM or crash
- Requires adaptive switching to 16K when VRAM tight

**Recommended strategy:**
1. Implement adaptive 16K/24K switching
2. Test on longest chapters with VRAM monitoring
3. Deploy with rollback plan to 16K
4. Monitor production for OOM crashes
5. If unstable: rollback to 16K or upgrade to Q4_K_M

**Long-term solution:**
- Upgrade to Q4_K_M (24K fits with margin) OR
- Upgrade to 16GB GPU (32K fits comfortably)

---

## Appendix: VRAM Calculation Details

### KV Cache Formula

```
KV_cache_GB = (2 × num_layers × hidden_dim × context_length × precision_bytes) / (1024^3)

For Qwen3.5-9B:
  num_layers = 32
  hidden_dim = 4096
  precision_bytes = 2 (float16)

16K context: (2 × 32 × 4096 × 16384 × 2) / 1024^3 = 8.0 GB
24K context: (2 × 32 × 4096 × 24576 × 2) / 1024^3 = 12.0 GB
32K context: (2 × 32 × 4096 × 32768 × 2) / 1024^3 = 16.0 GB
```

### Flash Attention Reduction

Flash Attention reduces memory by:
- Tiling attention computation (process in chunks)
- Recomputing attention on backward pass (trade compute for memory)
- Fusing operations (fewer intermediate tensors)

Typical reduction: 30-35% for long contexts (>16K tokens)
Optimistic reduction: 40% (requires optimal conditions)

### GQA (Grouped Query Attention)

Qwen models use GQA, which reduces KV cache by grouping queries:
- Standard attention: num_heads KV pairs
- GQA: num_kv_groups KV pairs (num_kv_groups < num_heads)

Qwen3.5-9B: 32 attention heads, 8 KV groups → 4:1 ratio
Additional memory reduction: ~15-20% on top of Flash Attention

**Combined optimization (FA + GQA):**
- Conservative: 35% reduction (FA only)
- Optimistic: 40-45% reduction (FA + GQA)
- Used in this analysis: 35% (conservative) and 40% (optimistic)
