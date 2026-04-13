# CallProfiler

Local multi-user phone call processing system. Records → transcripts → LLM analysis → Telegram digest + Android caller overlay.

## Tech Stack

- Python 3.10+, no venv, system-wide pip
- SQLite + FTS5 (single DB, user_id isolation)
- faster-whisper large-v3 (ASR, GPU)
- pyannote 3.3.2 (diarization, GPU)
- LLM: llama-server + Qwen3.5-9B via OpenAI-compatible API
- Windows 10/11, cmd (NOT WSL, NOT bash)

## Commands

```bash
# Run any CLI command
set PYTHONPATH=C:\pro\callprofiler\src
python -m callprofiler <command>

# Key commands
python -m callprofiler bulk-load "D:\calls\out" --user serhio
python -m callprofiler extract-names --user serhio
python -m callprofiler bulk-enrich --user serhio --limit 100
python -m callprofiler add-user <id> --display-name <name> --incoming <dir> --ref-audio <wav> --sync-dir <dir>

# Tests
python -m pytest tests/ -v

# Git
git add . && git commit -m "description" && git push origin main
```

## LLM Server (CRITICAL — not Ollama)

```bash
llama-server.exe -m "C:\models\Qwen3.5-9B.Q5_K_M.gguf" -ngl 99 -c 16384 --host 127.0.0.1 --port 8080
```

API: `POST http://127.0.0.1:8080/v1/chat/completions` (OpenAI format).
Do NOT use Ollama API. Do NOT import openai SDK. Use `requests.post()` directly.

## Project Structure

```
src/callprofiler/
├── config.py              # YAML config loader
├── models.py              # Dataclasses: CallMetadata, Segment, Analysis
├── db/
│   ├── schema.sql         # All tables (users, contacts, calls, transcripts, analyses, promises)
│   └── repository.py      # CRUD — EVERY query MUST filter by user_id
├── ingest/
│   ├── filename_parser.py # 5 filename formats → CallMetadata
│   └── ingester.py        # File intake, MD5 dedup, contact creation
├── audio/normalizer.py    # ffmpeg → WAV 16kHz mono
├── transcribe/whisper_runner.py  # faster-whisper wrapper
├── diarize/
│   ├── pyannote_runner.py # Diarization + ref embedding
│   └── role_assigner.py   # Segment → speaker assignment
├── analyze/
│   ├── llm_client.py      # HTTP to llama-server (NOT Ollama)
│   ├── prompt_builder.py  # Template from configs/prompts/
│   └── response_parser.py # Robust JSON extraction from LLM output
├── bulk/
│   ├── loader.py          # Mass import .txt transcripts
│   ├── enricher.py        # Mass LLM analysis
│   └── name_extractor.py  # Regex name extraction from transcripts
├── deliver/
│   ├── telegram_bot.py
│   └── card_generator.py  # {phone}.txt for Android overlay
├── pipeline/
│   ├── orchestrator.py    # Sequential pipeline for new files
│   └── watcher.py         # Watchdog for incoming/
└── cli/main.py            # CLI entry point
```

## Key Paths

```
Project:        C:\pro\callprofiler\
Audio:          D:\calls\audio (with subfolders)
Transcripts:    D:\calls\out (18,000 .txt files)
Database:       D:\calls\data\db\callprofiler.db
Ref voice:      C:\pro\mbot\ref\manager.wav
Prototype:      C:\pro\callprofiler\reference_batch_asr.py
```

## MUST Rules

- EVERY DB query filters by `user_id` — no exceptions
- NEVER hardcode tokens — use `os.environ.get("HF_TOKEN")` etc.
- NEVER modify ASR/diarize logic from reference_batch_asr.py without measurement
- NEVER load two GPU models that exceed 12GB VRAM together
- NEVER use Ollama API — only llama-server OpenAI-compatible endpoint
- ALWAYS handle errors per-file: log, save to DB, continue to next
- ALWAYS use `--break-system-packages` with pip
- ALWAYS commit after completing a step

## Required Hacks

```python
# torch 2.6 weights_only fix — put in any module loading pyannote
import torch as _torch
_original_load = _torch.load
def _patched_load(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _original_load(*args, **kwargs)
_torch.load = _patched_load

# pyannote 3.3.2 — use_auth_token, NOT token=
Model.from_pretrained("pyannote/embedding", use_auth_token=HF_TOKEN)
```

## Transcript Format

Files contain dialogs with speaker labels. Roles may be swapped due to recognition errors:
```
[me]: владелец телефона (Сергей Медведев)
[s2]: собеседник (speaker 2)
```
"Сергей", "Серёжа", "Серёж", "Медведев" = ALWAYS the owner, regardless of label.

## JSON Parsing from LLM

LLM output is unreliable. Parser MUST:
1. Strip markdown fences (```json```)
2. Extract text between first `{` and last `}`
3. Fix truncated JSON (close unclosed quotes, brackets, braces)
4. Remove trailing commas before `}` and `]`
5. Use `dict.get(key, default)` for every field — never KeyError
6. If all parsing fails — save raw response, return Analysis with defaults

## Reference Documents

Read these when working on specific areas:

- Architecture decisions: @ARCHITECTURE_v4.md
- Project constitution and constraints: @CONSTITUTION.md
- Agent coding rules and style guide: @AGENTS.md
- Strategic plan and phases: @STRATEGIC_PLAN_v4.md
- Working ASR/diarize prototype: @reference_batch_asr.py
- LLM analysis prompt: @configs/prompts/analyze_v001.txt
