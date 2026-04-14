# Roadmap

## Phase 1 — End-to-end pipeline (CURRENT)
Goal: File → Telegram in 3-5 min, 10 files in a row without error
Status: Pipeline built, bulk-load done (18K files), bulk-enrich running
Completion: llama-server CUDA working + 10 files processed end-to-end

## Phase 2 — Stabilization + 2nd user
Goal: One week without manual intervention, user isolation verified
Key tasks:
- Fix any pipeline errors from Phase 1
- Add second user, verify data isolation
- Auto-start on Windows boot (Task Scheduler)

## Phase 3 — Context and quality
Goal: Promises tracked, FTS5 search working via Telegram
Key tasks:
- /promises command working
- /search returning good results
- Contact summaries populated

## Phase 4 — Web interface
Goal: FastAPI dashboard showing call history
Key tasks:
- REST API: /calls /contacts /search
- Simple HTML dashboard

## Phase 5 — Advanced (only with measurements)
Triggers required before starting:
- Vector search: only if FTS5 measured too slow
- ECAPA-TDNN: only if role error >15%
- Multi-agent LLM: only if single prompt <70% quality
- PostgreSQL: only if SQLite contention measured
