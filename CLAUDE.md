# CallProfiler

**Mission:** audio → transcript → local LLM → Telegram/Android. Think a lot, show little.

## Communication (user-authorized 2026-06-05)
- Отвечать пользователю **кратко, по делу, без воды**. Без преамбул/пересказа/«могу ещё».
- Не перечитывать весь код на простой вопрос. Ответы про pipeline/db/graph/llm брать из
  `.claude/rules/*` карт; код читать ТОЛЬКО если карта не покрывает (и тогда обновить карту).
- В конце задачи: обновить память → `commit` + `push origin main`. Затем короткий итог.

## Hard Constraints
- 100% local. No cloud / Docker / Redis / Celery / ORM / Ollama.
- LLM: `llama-server.exe -m "C:\models\Qwen3.5-9B.Q8_0.gguf" -ngl 99 -c 16384` → `http://127.0.0.1:8080/v1/chat/completions`
- GPU sequential: Whisper+pyannote (4.5GB) → unload → LLM (10GB). Never concurrent.
- Every SQL: `WHERE user_id = ?`. Tokens: `os.environ.get()`. Errors: log+DB+continue.
- Push to `main` only. No feature branches.
- **Git autonomy (user-authorized 2026-06-04):** commit+push to `main` WITHOUT per-action confirmation. Rule: record every significant step in memory files (CONTINUITY/CHANGELOG/.claude/rules/*) FIRST, then commit+push.

## Paths & Commands
```
Project: C:\pro\callprofiler\          DB: C:\calls\data\db\callprofiler.db
Data:    C:\calls\data                 Audio: …\users\{uid}\audio\{originals,normalized}\
Ref:     C:\pro\mbot\ref\manager.wav
PYTHONPATH=C:\pro\callprofiler\src | python -m callprofiler <cmd> | pytest tests/ -v
dashboard: python -m callprofiler dashboard --user UID [--port 8765]
```

## Python Hacks
```python
import torch; _o=torch.load; torch.load=lambda *a,**k:_o(*a,**{**k,'weights_only':k.get('weights_only',False)})  # torch 2.6
# pyannote 3.3.2: use_auth_token=  NOT  token=
```

## Model Routing (enforce strictly)
| Task | Model | Effort |
|------|-------|--------|
| Q&A, format, 1-file patch | Haiku 4.5 | low |
| Routine dev, CRUD, tests, refactor | Opus (Fast Mode) | medium |
| New feature, complex bug, module design | Opus | high |
| Architecture, research, genuinely novel | Opus | max |

## Session Start (every session)
1. `.codegraph/` exists? → `codegraph_search` affected symbols before any Read.
2. Read `CONTINUITY.md` + last 5 lines `CHANGELOG.md` → print "State: … / Next: …"
3. Match task to model tier above.

## .codegraph (mandatory)
`codegraph_search` / `codegraph_callers` / `codegraph_impact` **before every edit**.
For multi-file questions: spawn Explore subagent with codegraph as primary tool.
If `.codegraph/` missing → `codegraph init -i` first.

## Subagents (always, never optional)
- **Explore**: any question spanning >1 file.
- **planner**: feature touching >2 files.
- **tdd-guide**: every bug fix + new feature (RED→GREEN→REFACTOR).
- **code-reviewer**: after every code write.
- **security-reviewer**: any auth / DB / input / API / file change.

## Skills (invoke before writing code)
| Trigger | Skill |
|---------|-------|
| DB schema / SQL | `sql-pro` + `database-optimizer` + `.claude/skills/db-migration` |
| Python module | `python-pro` + `python-patterns` |
| LLM prompt | `prompt-engineer` |
| Bug | `.claude/skills/fix-bug` + `systematic-debugging` |
| Architecture | `architecture-patterns` |
| Security | `007` |

## Memory Protocol (обновлять ПОСТОЯННО, не в конце — по ходу работы)
- `CONTINUITY.md` — current state + next step only. **Overwrite** each session (not append).
- `CHANGELOG.md` — one line per logical change. Append only.
- `.claude/rules/pipeline.md` → **Pipeline Map** — стадии/статусы/файлы. Менять при смене конвейера.
- `.claude/rules/bugs.md` — non-obvious root cause + regression test ref + **способ решения**. One block per bug.
- `.claude/rules/decisions.md` — architectural WHY + **планы**. One paragraph per decision.
- Хуки/способы решения проблем → в профильный `.claude/rules/*` (pipeline/db/graph/llm), не в код-комменты.
- **Rule: add only non-obvious facts. Never duplicate what's already in code or rules.**
- **Каждый значимый шаг: сперва в память (эти файлы), потом `commit`+`push origin main`.**

## Domain
- `[me]` = Сергей Медведев (always owner). `[s2]` = other. Roles may be swapped — LLM determines.
- Output: ≤300 chars/item, ≤3 facts/item. Never show counts/durations to user.

## Prohibited
ORM · Ollama · cloud LLM · auto-merge contacts · verbose output (>300 chars) · features outside current phase · premature abstraction

## Reference Files (load on demand — NOT at session start)
`@ARCHITECTURE_v5.md` `@CONSTITUTION.md` `@AGENTS.md` `@configs/prompts/analyze_v001.txt`
`@.claude/rules/db.md` `@.claude/rules/pipeline.md` `@.claude/rules/llm.md` `@.claude/rules/graph.md`
`@.claude/rules/biography-*.md` `@.claude/rules/bugs.md` `@.claude/rules/decisions.md`
`@src/callprofiler/biography/CLAUDE.md` `@.claude/skills/fix-bug.md` `@.claude/skills/db-migration.md`
