# Dashboard Live Update Testing

## Overview

Dashboard uses **Server-Sent Events (SSE)** for real-time updates. When call processing happens (transcription, LLM analysis), the dashboard automatically shows new events without page refresh.

## Architecture

```
Pipeline (enricher.py)
  ↓ updates calls.updated_at
Database (SQLite)
  ↓ polled every 2 seconds
SSE Stream (/events/stream)
  ↓ pushes events
Browser (EventSource API)
  ↓ updates UI
Dashboard (Live Events panel)
```

## Key Components

### Backend (FastAPI + SSE)

- **`server.py`**: FastAPI app with SSE endpoint `/events/stream`
- **`db_reader.py`**: Read-only SQLite queries (mode=ro, no locks)
- **Polling**: Checks `MAX(updated_at)` every 2 seconds
- **Change detection**: Compares timestamps, emits events for new/updated calls
- **Keepalive**: Sends comment every 30 seconds to prevent timeout

### Frontend (JavaScript + EventSource)

- **`app.js`**: Connects to SSE stream via `EventSource('/events/stream')`
- **Auto-reconnect**: Up to 5 attempts with exponential backoff
- **Fallback**: Switches to 5-second polling after max reconnect failures
- **Event types**:
  - `call_created` — New call added (status=pending)
  - `transcription_complete` — Transcript ready (status=transcribed)
  - `analysis_complete` — LLM analysis done (status=analyzed, includes risk_score)

## Testing

### 1. Start Dashboard

```bash
start-dashboard.bat
```

Opens http://127.0.0.1:8765 in browser.

### 2. Run Test Scripts

#### Simple Status Update Test

```bash
python test_dashboard_live.py
```

- Finds a pending call (or creates one)
- Updates status: `pending` → `transcribed` → `analyzed`
- Verifies `updated_at` timestamp changes

**Expected dashboard behavior:**
- 2 events appear in "Live Events" panel
- History refreshes automatically
- Stats update (total calls counter)

#### Full Pipeline Simulation Test

```bash
python test_dashboard_with_analysis.py
```

- Creates new call with realistic data
- Adds transcript segments
- Adds LLM analysis (risk_score=45, summary, promises)
- Updates status through all stages

**Expected dashboard behavior:**
- 3 events appear in "Live Events" panel:
  1. 📞 Новый звонок
  2. 📝 Транскрипция готова
  3. 🧠 Анализ завершён (with risk score badge)
- New call appears in history with risk_score=45
- Stats update (total_calls, avg_risk)

### 3. Real Pipeline Test

Run actual call processing:

```bash
set PYTHONPATH=C:\pro\callprofiler\src
python -m callprofiler bulk-enrich --user serhio --limit 1
```

Dashboard should show live updates as the call is processed.

## Troubleshooting

### Events not appearing

1. **Check SSE connection**: Open browser DevTools → Network → Filter "stream" → Should see `/events/stream` with status 200
2. **Check console**: Look for "SSE connected" message
3. **Check polling**: Server logs should show "Client disconnected from SSE stream" when you close browser

### Timestamp not updating

```sql
-- Check if updated_at is being set
SELECT call_id, status, created_at, updated_at
FROM calls
WHERE user_id = 'serhio'
ORDER BY updated_at DESC
LIMIT 5;
```

If `updated_at` is NULL or not changing, check `db/repository.py:set_status()` — it should include `updated_at=datetime('now')`.

### SSE connection drops

- **Symptom**: "SSE connection error" in console, auto-reconnect attempts
- **Cause**: Server restart, network issue, or browser tab suspended
- **Fix**: Automatic (up to 5 reconnects), then falls back to polling

### No events after reconnect

- **Symptom**: SSE reconnects but no events appear
- **Cause**: `_LAST_TIMESTAMP` is stale (server restarted)
- **Fix**: Refresh page to reset client state

## Implementation Details

### Why SSE (not WebSockets)?

- **Simpler**: One-way push (server → client), no bidirectional complexity
- **Auto-reconnect**: Built into EventSource API
- **HTTP-friendly**: Works through proxies, no special server config
- **Graceful degradation**: Falls back to polling if SSE fails

### Why polling (not triggers)?

- **SQLite limitation**: No LISTEN/NOTIFY like PostgreSQL
- **Read-only mode**: Dashboard uses `file:path?mode=ro` to avoid locks
- **Low overhead**: 2-second poll interval, only checks MAX(updated_at)
- **Simple**: No message queue (Redis/RabbitMQ) needed

### Why timestamp comparison (not event log)?

- **Idempotent**: Re-running enricher doesn't duplicate events
- **Stateless**: No event_id sequence to maintain
- **Efficient**: Single query gets latest timestamp across all tables
- **Reliable**: Survives server restarts (timestamp persists in DB)

## Performance

- **Polling overhead**: ~1ms per poll (single MAX() query)
- **SSE bandwidth**: ~50 bytes per keepalive (every 30s)
- **Event latency**: 0-2 seconds (depends on poll timing)
- **Concurrent clients**: Tested with 10+ browsers, no issues

## Future Improvements

1. **WebSocket upgrade**: For sub-second latency (if needed)
2. **Event batching**: Group rapid updates (e.g., bulk-enrich)
3. **Selective updates**: Only send events for visible calls (pagination)
4. **Push notifications**: Browser Notification API for background tabs
5. **Event replay**: Store last N events in memory for late-joining clients

## Related Files

- `src/callprofiler/dashboard/server.py` — SSE endpoint
- `src/callprofiler/dashboard/db_reader.py` — Database queries
- `src/callprofiler/dashboard/static/app.js` — Frontend SSE client
- `src/callprofiler/dashboard/config.py` — Polling intervals
- `src/callprofiler/db/repository.py` — `set_status()` updates `updated_at`
- `test_dashboard_live.py` — Simple status update test
- `test_dashboard_with_analysis.py` — Full pipeline simulation test
