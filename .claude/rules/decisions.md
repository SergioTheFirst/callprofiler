# Architectural Decisions

## 2026-04 Decisions

- **llama-server over Ollama**: direct control, OpenAI-compatible API, no extra process.
- **pyannote over NeMo**: already working in batch_asr.py, no measured reason to change.
- **No LLM Role Correction**: doubles processing time. Implement only if role error >15%.
- **No Event Store pattern**: SQLite events table is sufficient. No CQRS needed.
- **Overlay over CardDAV**: MacroDroid + .txt files. No phone book pollution.
- **One DB for all users**: isolation via user_id, simpler backup/migration.
- **contact_summaries as materialized aggregate**: precomputed after each call, not on-the-fly.
