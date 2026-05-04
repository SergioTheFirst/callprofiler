# Architecture Decisions

## Core Stack Decisions

### Why SQLite (not PostgreSQL/cloud)?
- **CONSTITUTION Rule 4:** Local-only, no external dependencies
- Single-file database fits Windows deployment
- User isolation via schema design (all queries filter by user_id)
- Fast enough for single-user 100+ calls/week

### Why Ollama (not OpenAI/cloud)?
- **CONSTITUTION Rule 4:** Local inference, full privacy
- Qwen 2.5 14B fits RTX 3060 12GB (float16)
- No API calls = no latency, no costs, no rate limits
- Can swap models without code changes

### Why Whisper (not WhisperX)?
- Simpler pipeline, fewer dependencies
- Good enough accuracy for business context extraction
- No speaker clustering (use Pyannote separately)
- faster-whisper = fast inference on GPU

### Why Pyannote 3.3.2 (not 4.0)?
- 3.3.2 stable with GPU support
- 4.0 requires complex setup
- Reference embedding approach (compare user's voice) works well
- use_auth_token= pattern is proven

### Why exponential decay for risk (not average)?
- Recent calls more relevant than old ones
- 90-day half-life matches human memory (3 months = half-weight)
- Recent context = better decision-making
- Avoids "one bad call 6 months ago" blocking all trust

### Why user_id isolation (not multi-tenant)?
- Simpler model (one user per Windows machine)
- CONSTITUTION Rule 2.5: "Every query filters by user_id"
- Future: can add multiple users to same machine if needed
- Zero data leakage between users

## Data Model Decisions

### Why separate Events + Promises tables?
- **Events:** 7 types (promise, debt, task, fact, risk, contradiction, smalltalk) with confidence
- **Promises:** Legacy table, keeps backward compatibility
- Events = structured extraction; Promises = specific caller debts
- Allows flexible query patterns (open promises ≠ open debts)

### Why contact_summaries (not compute on-read)?
- Telegram commands need fast response (/<1 sec)
- Computing risk from 50+ calls each time = too slow
- Rebuild on call enrichment = O(1) lookup
- Risk calculation is expensive (exponential decay)

### Why JSON fields for arrays (not separate tables)?
- Simpler queries for readonly data (promises, debts, facts)
- No joins needed for UI display
- Bounded size (max 10 promises per contact)
- Trade: harder to search/filter, but acceptable

### Why risk_score 0-100 (not continuous)?
- Easy to understand (>70 = red flag)
- Matches emoji system (🟢 <30, 🟡 30-70, 🔴 >70)
- Simple advice rules (if risk>70 → "speak first")
- Granular enough for business decisions

## Delivery Strategy Decisions

### Why Telegram (not SMS/email)?
- Instant notifications (bot runs in background)
- Rich formatting (HTML, inline buttons)
- Feedback loop (click [OK] / [Wrong])
- User has control (enable/disable per contact)

### Why caller cards (not just Telegram)?
- Android overlay (caller ID screen integration)
- FolderSync = automatic sync to phone
- Offline access (no internet needed)
- Visual risk indicator (emoji at a glance)

### Why inline feedback buttons (not separate message)?
- One-click feedback (no conversation)
- Saved to analyses.feedback field
- Trains LLM for next session (could improve prompts)
- Respects user's time

### Why FastAPI + SSE for dashboard (not WebSockets/polling)?
- **SSE (Server-Sent Events):** One-way real-time push from server to browser
- Simpler than WebSockets (no bidirectional complexity)
- Automatic reconnection built into EventSource API
- Graceful degradation: fallback to 5-second polling after 5 reconnect failures
- Read-only DB access via `file:path?mode=ro` URI = no locks, no interference with pipeline
- FastAPI = async, automatic OpenAPI docs, Pydantic validation
- Polling-based change detection: check MAX(updated_at) every 2 seconds
- No Redis/message queue needed (SQLite timestamp is the event source)

## Process Decisions

### Why Memory Protocol (CONTINUITY.md + CHANGELOG.md)?
- AI context resets between sessions
- Only way to ensure continuity = written logs
- Every change must be recorded immediately
- Prevents "context loss" spirals

### Why direct push to main (no PR)?
- Single developer (you) making decisions
- PR overhead not worth it for 1 person
- CLAUDE.md documents the decision
- Easier to experiment and iterate

### Why .bat automation files?
- Windows-native (no WSL, no bash)
- new-session.bat = reproducible briefing
- save-session.bat = safe commit (runs tests first)
- emergency-save.bat = untested quick save

## Known Trade-offs

| Decision | Benefit | Cost |
|----------|---------|------|
| SQLite | Simple, local | Limited to 1 machine |
| Ollama local | No API calls | Must have GPU |
| Exponential decay | Recent bias | Old context fades |
| JSON arrays | Simple | Hard to search |
| No multi-tenant | Simpler code | Can't scale easily |
| Memory Protocol | Continuity | Must update journals |

## Future Flexibility

- **Model swap:** Ollama model can change (Llama, Mistral, etc)
- **Database migration:** Could move to PostgreSQL if needed
- **Multi-user:** Can add user_id branching logic later
- **Cloud option:** Could add cloud fallback if needed
- **Telegram alternative:** Could add Discord/Slack later
