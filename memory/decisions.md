# Architecture Decisions Log

## Why llama-server instead of Ollama
- Ollama does not support qwen35 architecture in its embedded llama.cpp
- llama-server supports cutting-edge models directly
- Decision date: 2026-04

## Why SQLite instead of PostgreSQL
- Single machine, single process
- No measured contention at current scale
- Switch trigger: contention at >100K records
- Decision date: 2026-03

## Why pyannote + ref embedding instead of ECAPA-TDNN
- Already works in batch_asr.py (proven)
- Switch trigger: role error >15% on 100 calls
- Decision date: 2026-03

## Why no Docker
- Single PC, single process — zero benefit
- Adds complexity with no measured problem solved

## Why no ChromaDB/LangChain yet
- FTS5 covers 90% of search needs
- Add only when FTS5 measured too slow
- Planned: Phase 5 at earliest

## Why no real-time processing
- Task is post-processing of recordings
- Real-time adds complexity with no business need

## Why Windows cmd (not WSL)
- Target machine is Windows 11
- System Python, no venv
- All paths are Windows paths
