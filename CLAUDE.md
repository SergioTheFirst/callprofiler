# CallProfiler

Local multi-user phone call analysis system. Records → transcripts → LLM structured analysis → Telegram + Android overlay.

## Mission

**System thinks a lot — shows little.** Heavy analysis offline, user sees only short actionable digests.

## Constraints (never violate)

- 100% local. No cloud LLM, no SaaS, no subscriptions.
- Windows + system Python. No Docker/Redis/Celery.
- LLM: `llama-server.exe -m "C:\models\Qwen3.5-9B.Q5_K_M.gguf" -ngl 99 -c 16384 --host 127.0.0.1 --port 8080` — OpenAI-compatible API at `http://127.0.0.1:8080/v1/chat/completions`. NOT Ollama.
- GPU sequential: Whisper+pyannote together (4.5GB), unload before LLM (10GB).
- Every DB query MUST filter by `user_id`.
- Never hardcode tokens — `os.environ.get()` only.
- Never swallow errors — log + save to DB + continue.

## Session Protocol

```
IF session_start:
  → read CONTINUITY.md + CHANGELOG.md
  → output: "Last state: … / Next: …"

IF code_generated OR schema_changed:
  → update CONTINUITY.md immediately
  → update CHANGELOG.md
  → run tests

IF bug_fixed:
  → write to .claude/rules/bugs.md
  → add regression test

IF architectural_decision:
  → write to .claude/rules/decisions.md
```

## Before Writing Code

THINK (what files affected, what depends on them) → PLAN (3-5 steps) → IMPLEMENT → VERIFY (run tests) → LOG (update CONTINUITY.md)

## Commands

```bash
set PYTHONPATH=C:\pro\callprofiler\src
python -m callprofiler <command>          # CLI entry point
python -m callprofiler dashboard --user USER_ID [--port 8765] [--host 127.0.0.1]  # Real-time web dashboard
python -m pytest tests/ -v               # Tests
git add . && git commit -m "msg" && git push origin main
```

## Required Hacks

```python
# torch 2.6 — in any module loading pyannote
import torch; _orig = torch.load
torch.load = lambda *a, **kw: _orig(*a, **{**kw, "weights_only": kw.get("weights_only", False)})

# pyannote 3.3.2 — use_auth_token=, NOT token=
```

## Key Paths

```
Project:     C:\pro\callprofiler\          DB:    D:\calls\data\db\callprofiler.db
Audio:       D:\calls\audio                Transcripts: D:\calls\out (18K .txt)
Ref voice:   C:\pro\mbot\ref\manager.wav   Prototype:   reference_batch_asr.py
```

## Transcript Format

`[me]` = owner (Сергей Медведев), `[s2]` = other speaker. Roles may be swapped — LLM determines by context. "Сергей/Серёжа/Медведев" = ALWAYS owner.

## Working Style

- Vertical slice first (end-to-end before broad scaffolding).
- Reuse `reference_batch_asr.py` logic — refactor, don't rewrite.
- Events + aggregates, not ad-hoc queries.
- Precompute after each call (contact_summary → card → ready for next incoming).
- Small testable steps. One commit per logical change.

## Progressive Disclosure

IF referenced @file does not exist → ignore, do not infer its contents.

```
Architecture & pipeline:       @ARCHITECTURE_v4.md
Strategy & phases:             @STRATEGIC_PLAN_v4.md
Constitution & constraints:    @CONSTITUTION.md
Agent coding rules:            @AGENTS.md
LLM prompt template:           @configs/prompts/analyze_v001.txt
Working prototype:             @reference_batch_asr.py
DB rules:                      @.claude/rules/db.md
Pipeline rules:                @.claude/rules/pipeline.md
LLM analysis rules:            @.claude/rules/llm.md
Known bugs & fixes:            @.claude/rules/bugs.md
Architectural decisions log:   @.claude/rules/decisions.md
Narrative journal architecture:@.claude/rules/narrative-journal.md
Biography module overview:     @src/callprofiler/biography/CLAUDE.md
Biography data rules:          @.claude/rules/biography-data.md
Biography style canon:         @.claude/rules/biography-style.md
Biography prompt contracts:    @.claude/rules/biography-prompts.md
Knowledge graph rules:         @.claude/rules/graph.md
```

## Prohibited

- Cloud/SaaS dependencies
- ORM (use sqlite3 directly)
- Ollama API (use llama-server)
- Auto-merge contacts
- Verbose user-facing output
- User-facing output longer than 300 chars or more than 3 facts per item
- Adding components not in current phase plan

## Git Push Authorization

**Push to: `main` branch (not feature branches)**

All commits and pushes should go directly to `main`. Feature branches are not used for this repository.

```bash
git push origin main
```
