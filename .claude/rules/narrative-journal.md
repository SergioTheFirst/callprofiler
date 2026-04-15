# Narrative Journal Architecture

**Purpose:** Generate book-like narratives from call transcripts and metadata. Instead of statistics ("47 calls to Vasya"), extract life events, discoveries, and connections into a flowing story.

---

## The Problem We're Solving

Current system: "You called John 3 times (2h total), mostly about Project X"  
Desired: "This month you reconnected with John after 6 weeks. First call: he mentioned the Moscow opportunity. Second call: you both realized the supplier issue was traceable to the new contractor. By third call, you had a plan. Meanwhile, Katya (not spoken to in 2 months) reached out with a similar problem."

**Why this matters:**
- Life is about narratives, not aggregates
- Insights emerge from patterns and connections, not totals
- User wants to *remember* the month, not *measure* it
- Boring calls (routine checkups, confirmations) should fade into background

---

## Architecture: Three Layers

### Layer 1: Event Extraction (Database Side)

**Source:** `analyses` + `events` + `promises` tables  
**Task:** Distill 2,000 calls down to ~50 *narrative events* per month

**Event Types (prioritized):**
1. **NEW_CONTACT** — First mention of a person's name
2. **RECONNECTION** — Haven't spoken to this person in >X weeks
3. **DECISION** — Call led to a committed action/promise
4. **DISCOVERY** — New fact, problem, or opportunity mentioned
5. **LOCATION_MENTION** — Geographic reference (travel, client visit)
6. **PROBLEM_SOLVED** — Promise fulfilled or issue resolved
7. **CONTRADICTION** — Conflicting information (red flag)
8. **MILESTONE** — Deal closed, project ended, major achievement

**Extraction Logic:**
```
FOR each call IN period:
  IF risk_score > 70 AND call_type != "smalltalk":
    → Likely important conversation
  
  FROM transcripts:
    - Extract promises (who, what, when)
    - Extract named entities (people, places, companies)
    - Extract first-mention entities → NEW_CONTACT
  
  FROM events table:
    - Use existing event_type: promise, debt, risk, task, fact
    - Use confidence score to filter noise
  
  FROM contact_summaries:
    - Track last_call_date for each contact
    - Calculate days_since_last_call
    - IF days > 30 AND called again → RECONNECTION
```

**Output:** Event log with `(call_id, date, type, who, summary, confidence, text_snippet)`

---

### Layer 2: Narrative Clustering (Intelligence Layer)

**Task:** Group related events into story arcs

**Algorithms:**

1. **Contact Threads** — All mentions of person X across multiple calls
   - Track: first mention, last mention, sentiment trend, key topics
   - Example: "Vasya (3 calls, 2 weeks): Mentioned Moscow opportunity → problem with supplier → solution agreed"

2. **Problem Arcs** — Multi-call problem resolution
   - Detect: same issue mentioned in call N and call N+5
   - Track: problem → investigation → solution
   - Example: "Supplier issue surfaced in call #1047 (with Vasya), appeared again in #1053 (with Katya), resolved in #1061"

3. **Temporal Clustering** — Group events by time and topic
   - Within same week: calls about "project X" likely related
   - Sequence matters: "First you heard about, then you investigated, finally you decided"

4. **Entity Graphs** — Build knowledge graph
   - Node: person/place/company
   - Edge: interaction type (discussed, agreed with, visited, hired, etc.)
   - Query: "Who did I meet about the Moscow opportunity?" → path traversal

---

### Layer 3: Prose Generation (LLM)

**Approach:** Hierarchical prompting to maintain coherence

**Stage 1: Contact Portraits** (1-2 sentences per person)
```
INPUT: Vasya's thread:
  - Call 1: discussed Moscow expansion
  - Call 2: mentioned supplier problem
  - Call 3: agreed on new contractor
PROMPT: "Summarize Vasya's role in this month's narrative (1 sentence)"
OUTPUT: "Vasya, your Moscow contact, evolved the expansion plan through three calls and identified a supplier bottleneck you both committed to fixing."
```

**Stage 2: Chapter Outline** (3-5 sections per week)
```
Chapters:
  1. New Connections (who you met)
  2. Problem Solving (what you worked on)
  3. Achievements (what got decided)
  4. Serendipities (unexpected connections or insights)
  5. Loose Ends (open promises, follow-ups needed)
```

**Stage 3: Full Narrative** (2-3 paragraphs per section)
```
PROMPT: "Write 2-3 paragraphs about 'Problem Solving this month' using these facts:
  - Supplier issue with Moscow expansion
  - Multiple people mentioned it (Vasya, Katya)
  - Led to decision about new contractor
  Tone: journalistic, factual, no statistics"
```

**Safety Safeguards:**
- Never mention call count/duration (violates user-output brevity rule)
- Never generate fiction — use only extracted facts
- Flag low-confidence events (don't include if confidence < 0.6)
- Include source citations: "(From call with Vasya, Mar 15)"

---

## Data Model: Narrative Tables

**Create two new tables:**

```sql
CREATE TABLE narrative_events (
  event_id INTEGER PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  period_start TEXT,
  period_end TEXT,
  call_id INTEGER REFERENCES calls(call_id),
  event_type TEXT,        -- NEW_CONTACT, RECONNECTION, DECISION, DISCOVERY, etc.
  entity_type TEXT,       -- PERSON, PLACE, COMPANY, PROMISE
  entity_name TEXT,       -- "Vasya", "Moscow", "Supplier X"
  summary TEXT,           -- Extracted fact (one sentence)
  confidence REAL,        -- 0.0-1.0
  text_snippet TEXT,      -- Quoted from transcript
  source_quote TEXT,      -- "[me]: so we're going with the new contractor?"
  created_at TEXT
);

CREATE TABLE narrative_journals (
  journal_id INTEGER PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  period_start TEXT,
  period_end TEXT,
  title TEXT,            -- "March 2026: Moscow, Connections & Decisions"
  prose TEXT,            -- Full narrative (markdown)
  event_count INTEGER,   -- How many events synthesized
  model_version TEXT,    -- Which LLM version generated this
  generated_at TEXT
);
```

---

## Workflow: Week-to-Book Pipeline

### Step 1: Extract Events (Daily/Weekly)
```
FOR each call added since last run:
  → Extract entities, promises, risks
  → Classify as narrative_event
  → Calculate confidence
  → Store in DB
```

### Step 2: Cluster into Arcs (Weekly)
```
FOR each user:
  FOR each event type:
    → Group by entity (who/what)
    → Detect problem arcs (same issue across calls)
    → Build contact threads
```

### Step 3: Generate Prose (On-Demand)
```
USER REQUESTS: /journal --period "March 2026"
  1. Query narrative_events WHERE period matches
  2. Build contact portraits (LLM)
  3. Generate chapter outline
  4. Write full prose (LLM)
  5. Save to narrative_journals table
  6. Output as markdown/PDF
```

---

## CLI Commands

```bash
python -m callprofiler narrative-extract --period "2026-03-01:2026-03-31"
  → Extract events from calls in this period
  → Save to narrative_events table

python -m callprofiler narrative-generate --period "2026-03" --output journal.md
  → Generate narrative prose
  → Save to file + DB

python -m callprofiler narrative-list --user USER_ID
  → Show all generated narratives for this user
```

---

## Phase Integration

**Phase 5 (Current: Audit & Rules)** → No changes  
**Phase 6 (Next: Optimization)** → Add narrative extraction as post-processing  
**Phase 7 (Future: Intelligence)** → Full narrative generation + entity graph  
**Phase 9 (Future: Integration)** → Sync narratives to Telegram, weekly digest

---

## Key Constraints (From CLAUDE.md)

✅ 100% local (no cloud LLM)  
✅ Use existing llama-server for narrative generation  
✅ Filter by user_id (multi-user safe)  
✅ Never swallow errors — log failures  
✅ Output ≤300 chars per fact (summary field)  
✅ Use sqlite3 directly (no ORM)  

---

## Competitive Advantage

This goes beyond CRM tools (Salesforce stores contacts) and calendar apps (Google Calendar shows meetings).

**What narrative journals enable:**
- Understand your month by reading it, not viewing charts
- Discover unexpected connections (two separate "problems" are actually the same)
- Prepare for next meeting by reviewing last 3 calls with that person
- Export life story to paper book (monthly retrospectives)
- Find patterns: "Every Q1 I reconnect with these three people"

---

## Success Metrics

1. **Accuracy:** Narrative events match user's actual call content (validation by user)
2. **Relevance:** Generated prose includes ≥80% of high-confidence events
3. **Brevity:** Month narrative fits in 3-5 pages (≤1500 words)
4. **Coherence:** Reader can follow thread without re-listening to calls
5. **Serendipity:** At least one non-obvious connection per narrative

