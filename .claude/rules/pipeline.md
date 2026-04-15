# Pipeline Rules & Error Handling

## Diarization Failure Handling

**Rule:** IF diarization fails OR returns 0 segments:

1. **Mark all transcript segments** with `speaker=UNKNOWN`
2. **Set call metadata** `diarization_failed=true`
3. **Continue pipeline** — DO NOT stop or mark call as error
4. **LLM will still extract meaning** from undiarized text (analyses still run normally)

**Rationale:**
- Audio might be corrupted but still transcribable
- LLM can extract context even without speaker attribution
- User gets partial result instead of complete failure
- Diarization is "nice to have", not "must have" for analysis

**Implementation:**
```python
# In diarize/pyannote_runner.py
try:
    diarization = pyannote_runner.diarize(wav_path)
except Exception as e:
    logger.warning("Diarization failed: %s", e)
    diarization = []

# In role_assigner.py
if not diarization:
    for segment in segments:
        segment.speaker = "UNKNOWN"
    call_metadata["diarization_failed"] = True
    # Continue to LLM analysis
```

**Test case:** Call with corrupted audio (Whisper can still transcribe but Pyannote fails)
- Expected: Card generated with speaker=UNKNOWN but analysis still present
- Risk/summary/action items should be extracted from text alone

---

## Short Call Handling (< 50 chars)

**Rule:** If `len(transcript_text.strip()) < 50`:
- Skip LLM analysis entirely
- Create stub Analysis with:
  - `call_type="short"`
  - `priority=0`
  - `risk_score=0`
  - `summary=""`
  - No promises, flags, actions
- Mark in database as "analyzed" (don't retry)

**Rationale:** Avoids unnecessary LLM calls for noise/silence

---

## LLM Response Validation

**Rule:** After LLM response parsing:
1. Check `parse_status` value (see response_parser.py)
2. Log parse_status to database (`analyses.parse_status`)
3. If `parse_status="output_truncated"` → flag for manual review
4. If `parse_status="parse_failed"` → keep raw_response for debugging

---

## Enricher Progress Reporting

**Rule:** Enricher must log:
- Total calls to process
- Current call_id being processed
- Stage (transcribe/diarize/analyze/save)
- parse_status for each analysis (after parsing)
- Errors with full exception trace

This helps user monitor long-running batches and diagnose failures.

---

## Fallback Strategy

**Rule:** One file failure must NEVER block the entire batch.

| Stage | Failure | Action |
|-------|---------|--------|
| Audio normalization | Any exception | status=error, skip file, continue |
| Whisper | Any exception | status=error, skip file, continue |
| Diarization | Exception OR 0 segments | mark all segments speaker=UNKNOWN, continue pipeline |
| LLM request | Timeout / HTTP error | retry once; if still fails → save transcript without analysis, status=error |
| LLM JSON parse | parse_status=parse_failed | save raw_response, set parse_status=parse_failed, continue |

**Implementation pattern:**
```python
for call in calls:
    try:
        process_call(call)
    except Exception as e:
        logger.error("Call %s failed: %s", call.call_id, e, exc_info=True)
        repo.set_status(call.call_id, "error", error_message=str(e))
        continue  # never raise, never break
```
