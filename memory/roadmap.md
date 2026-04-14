# Project Roadmap

## Phase Overview

```
Phase 0: Foundation (DONE 2026-04-09)
    ↓
Phase 1: Core Pipeline (DONE 2026-04-09)
    ↓
Phase 2: Intelligence (DONE 2026-04-10)
    ↓
Phase 3: Delivery (DONE 2026-04-11)
    ↓
Phase 4: Aggregation (DONE 2026-04-11)
    ↓
Phase 5: Automation & Memory (DONE 2026-04-14) ← CURRENT
    ↓
Phase 6: Optimization (NEXT)
    ↓
Phase 7: Scale & Distribute
```

## Current Phase: Phase 5 - Automation & Memory (✅ COMPLETE)

### Completed in Phase 5 (2026-04-14)

**Memory Protocol (CLAUDE.md)**
- 6 binding rules for AI session continuity
- Mandatory journal updates (CONTINUITY.md + CHANGELOG.md)
- Context limit protection
- Session briefing requirement

**Audit & Fixes (2026-04-14)**
- Audited memory system: found gaps (no Memory Protocol in CLAUDE.md)
- Fixed: Added memory.bat files (new-session, save-session, emergency-save)
- Fixed: Added start-prompt.txt for session initialization
- Verified: All journals tracked in git, .gitignore correct

**Git Permissions (2026-04-14)**
- Permission granted: Claude can push directly to main (no PR)
- Updated CLAUDE.md with Git Branch Policy
- Merged all 5 commits from feature branch to main
- Tested: All 90 tests pass

**Status:** ✅ PHASE COMPLETE

---

## Next Phase: Phase 6 - Optimization

### Goals

Improve performance and user experience for production use.

### Planned Tasks (Priority Order)

1. **GPU Memory Management**
   - Profiling: measure peak GPU usage during full call processing
   - Optimize: batch transcription + diarization (load models once, process N calls)
   - Implement: clear CUDA cache between LLM calls
   - Target: < 6GB peak usage (leave headroom for other apps)

2. **Database Optimization**
   - Add indexes on frequently queried columns (user_id, contact_id, status)
   - Profile slow queries (Telegram /search command)
   - Consider: contact_summaries cache invalidation strategy
   - Benchmark: 1000+ call processing time

3. **Telegram Bot Reliability**
   - Add retry logic for failed notifications
   - Implement: message queue (if bot offline, buffer messages)
   - Add: rate limiting (don't spam user with notifications)
   - Monitor: long-polling stability (handle network disconnects)

4. **UI/UX Polish**
   - Caller card format: test on real Android phones
   - Risk emoji: validate users understand 🟢/🟡/🔴 scale
   - Telegram command help: make discoverable
   - Error messages: make actionable

5. **Logging & Monitoring**
   - Add structured logging (JSON format for analysis)
   - Track: processing times per call (bottleneck identification)
   - Monitor: error rates by component
   - Dashboard: simple status page (calls processed, errors, queue depth)

### Success Criteria
- Peak GPU usage < 6GB
- Telegram commands respond < 2 seconds
- No lost messages if bot restarts
- Database query times < 100ms for common operations

---

## Future Phases

### Phase 7 - Scale & Distribute
- Multi-machine deployment (network SQLite replication)
- Load balancing for multiple Ollama instances
- Distributed call processing
- Redundancy for production reliability

### Phase 8 - Analytics & Insights
- Contact relationship graphs (who knows whom)
- Trend analysis (risk over time per contact)
- Conversation patterns (frequency, duration, outcomes)
- Sales performance correlation

### Phase 9 - Integration & Ecosystem
- CRM integration (Salesforce, HubSpot)
- Slack/Discord instead of Telegram
- Email digest reports
- API for third-party integrations

### Phase 10 - Intelligence Enhancement
- Fine-tune LLM on user's past calls
- Custom extraction rules per user
- Competitive intelligence (inferred from conversations)
- Relationship health scoring

---

## Velocity & Timeline

| Phase | Start | End | Duration | Type |
|-------|-------|-----|----------|------|
| 0 | 2026-04-09 | 2026-04-09 | 1 day | Foundation |
| 1 | 2026-04-09 | 2026-04-09 | 1 day | Pipeline |
| 2 | 2026-04-10 | 2026-04-10 | 1 day | Intelligence |
| 3 | 2026-04-11 | 2026-04-11 | 1 day | Delivery |
| 4 | 2026-04-11 | 2026-04-14 | 4 days | Aggregation |
| 5 | 2026-04-14 | 2026-04-14 | 1 day | Automation |
| 6 | **2026-04-15** | TBD | Est. 3-5 days | Optimization |

**Note:** Phases 0-5 moved fast because spec was clear and no external dependencies. Phase 6 (optimization) is more exploratory = longer.

---

## Git Commit History

```
Phase 5 commits (merged to main):
- 8d62300: Audit: Memory Protocol + Automation fixes
- 1d165bd: Implement Telegram bot (6 commands + notifications)
- bc4fd6f: Contact summaries infrastructure (weighted risk)
- 80c3b57: Event extraction refinement
- fd862d3: Events table and extraction infrastructure
```

All phases combined: **~50 commits** to main, **90 tests**, **100%** coverage of core pipeline.
