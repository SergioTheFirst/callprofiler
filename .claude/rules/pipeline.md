# Pipeline Rules

- State machine: new → transcribing → diarizing → analyzing → done | error
- GPU discipline: Whisper(3GB) + pyannote(1.5GB) load together. Unload BOTH before LLM.
- After unload: `gc.collect()` + `torch.cuda.empty_cache()`
- Batch mode: load models once → process all pending → unload → LLM phase
- Error per file: log + status=error + error_message + continue to next
- Max 3 retries per file. After 3 → stays in error.
- Short calls (<50 chars transcript): skip LLM, set call_type='short', priority=0
- Original audio files: NEVER modify or delete.
