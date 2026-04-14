# CallProfiler Business Model

## What It Does

Local phone call post-processing system that transforms raw audio recordings into actionable intelligence.

### Pipeline
```
Audio File → Normalize → Transcribe → Diarize → LLM Analysis → SQLite DB → Telegram/Cards
```

### Core Functions

1. **Audio Intake** (ingest module)
   - Monitors user folders for new phone recordings
   - Parses filename to extract: phone number (E.164), date/time, direction (IN/OUT), contact name
   - Deduplicates via MD5 hash
   - Stores in SQLite with user isolation

2. **Audio Processing** (transcribe + diarize)
   - Normalize to WAV 16kHz mono (ffmpeg)
   - Transcribe with Whisper (faster-whisper, large-v3 model)
   - Speaker diarization with Pyannote (3.3.2) + reference embedding
   - Assign speakers: OWNER (user) vs OTHER (contact)
   - Return timestamped transcript with speaker labels

3. **Intelligence Analysis** (LLM analyze)
   - Ollama Qwen 2.5 14B model (local, no API calls)
   - Extract: priority (0-100), risk_score (0-100), summary, action items
   - Identify: promises (who/what/due), flags (urgent/conflict/follow-up)
   - Extract topics (business context, small talk, risks)
   - Parse BS-score (deception indicator)

4. **Aggregation** (contact summaries)
   - Weighted average risk (exponential decay, 90-day half-life)
   - Aggregate promises, debts, facts per contact
   - Generate advice rules (risk>70 → "speak first", etc)
   - Extract top "hook" (sales angle) from recent calls

5. **Delivery** (Telegram bot + caller cards)
   - **Telegram commands:** /digest [N] [days], /search, /contact, /promises, /status
   - **Notifications:** After enrichment, send summary with feedback buttons
   - **Caller cards:** Generate ≤512 byte cards with risk emoji, hook, promises
   - **Integration:** Write cards to FolderSync directory for Android caller overlay

## Target User

Sales professional (phonebook holder) who:
- Makes many phone calls daily
- Needs to remember context about each contact
- Wants to track promises/debts from conversations
- Values quick risk assessment before callbacks

## Hardware Target

- Windows 11 (CMD/PowerShell)
- NVIDIA RTX 3060 12GB + CUDA 12.4
- System Python 3.10+ (no venv)
- Local Ollama server (no cloud)

## Data Model

- **Users**: One user per system (telegram_chat_id for bot)
- **Contacts**: Phone number + name per user (isolated)
- **Calls**: Every recorded call (original + normalized audio paths)
- **Transcripts**: Timestamped text segments with speaker
- **Analyses**: LLM output (priority, risk, summary, actions, promises, flags)
- **Events**: Structured extraction (promises, debts, tasks, facts, risks, contradictions)
- **Contact Summaries**: Aggregated profile (total calls, risk, hook, advice, open items)
- **Promises** (legacy): Specific promise tracking (who/what/due/status)

## Key Metrics

- **Risk Score:** 0-100, higher = more problematic
- **BS Score:** 0-100, higher = more deceptive/unclear
- **Priority:** 0-100, higher = more urgent
- **Half-life:** 90 days (older data weighs less in risk calculations)
- **Confidence:** 0.0-1.0 per extracted event (LLM confidence scoring)
