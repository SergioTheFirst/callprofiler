-- schema.sql — CallProfiler SQLite schema

CREATE TABLE IF NOT EXISTS users (
    user_id        TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL,
    telegram_chat_id TEXT,
    incoming_dir   TEXT NOT NULL,
    sync_dir       TEXT NOT NULL,
    ref_audio      TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
    contact_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          TEXT NOT NULL REFERENCES users(user_id),
    phone_e164       TEXT,
    display_name     TEXT,
    guessed_name     TEXT,
    guessed_company  TEXT,
    guess_source     TEXT,
    guess_call_id    INTEGER REFERENCES calls(call_id),
    guess_confidence TEXT,
    name_confirmed   INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, phone_e164)
);

CREATE TABLE IF NOT EXISTS calls (
    call_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    contact_id     INTEGER REFERENCES contacts(contact_id),
    direction      TEXT NOT NULL DEFAULT 'UNKNOWN',
    call_datetime  TEXT,
    source_filename TEXT NOT NULL,
    source_md5     TEXT NOT NULL,
    audio_path     TEXT,
    norm_path      TEXT,
    duration_sec   INTEGER,
    status         TEXT NOT NULL DEFAULT 'new',
    retry_count    INTEGER NOT NULL DEFAULT 0,
    error_message  TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transcripts (
    segment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id        INTEGER NOT NULL REFERENCES calls(call_id),
    start_ms       INTEGER NOT NULL,
    end_ms         INTEGER NOT NULL,
    text           TEXT NOT NULL,
    speaker        TEXT NOT NULL DEFAULT 'UNKNOWN'
);

CREATE TABLE IF NOT EXISTS analyses (
    analysis_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id        INTEGER NOT NULL UNIQUE REFERENCES calls(call_id),
    priority       INTEGER NOT NULL DEFAULT 0,
    risk_score     INTEGER NOT NULL DEFAULT 0,
    summary        TEXT NOT NULL DEFAULT '',
    action_items   TEXT NOT NULL DEFAULT '[]',
    flags          TEXT NOT NULL DEFAULT '{}',
    key_topics     TEXT NOT NULL DEFAULT '[]',
    raw_response   TEXT NOT NULL DEFAULT '',
    model          TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    feedback       TEXT,
    call_type      TEXT DEFAULT 'unknown',
    hook           TEXT,
    parse_status   TEXT DEFAULT 'unknown',
    profanity_count   INTEGER DEFAULT 0,
    profanity_density REAL DEFAULT 0,
    -- schema_version added via migration in graph/repository.py:apply_graph_schema()
    -- 'v1' = legacy (no entities/structured_facts), 'v2' = graph-enabled
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS promises (
    promise_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    contact_id     INTEGER REFERENCES contacts(contact_id),
    call_id        INTEGER NOT NULL REFERENCES calls(call_id),
    who            TEXT NOT NULL,
    what           TEXT NOT NULL,
    due            TEXT,
    status         TEXT NOT NULL DEFAULT 'open',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
    text,
    speaker,
    call_id UNINDEXED,
    user_id UNINDEXED,
    content='transcripts',
    content_rowid='segment_id'
);

CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
    INSERT INTO transcripts_fts(rowid, text, speaker, call_id, user_id)
    SELECT NEW.segment_id, NEW.text, NEW.speaker, NEW.call_id,
           (SELECT user_id FROM calls WHERE call_id = NEW.call_id);
END;

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL REFERENCES users(user_id),
    contact_id    INTEGER REFERENCES contacts(contact_id),
    call_id       INTEGER NOT NULL REFERENCES calls(call_id),
    event_type    TEXT NOT NULL CHECK(event_type IN (
        'promise','debt','contradiction','risk','task','fact','smalltalk'
    )),
    who           TEXT CHECK(who IN ('OWNER','OTHER','UNKNOWN')),
    payload       TEXT NOT NULL,
    source_quote  TEXT,
    confidence    REAL DEFAULT 1.0,
    deadline      TEXT,
    status        TEXT DEFAULT 'open' CHECK(status IN ('open','fulfilled','broken','expired','resolved')),
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_contact ON events(user_id, contact_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(user_id, status);
-- Graph extension columns added via migration in graph/repository.py:apply_graph_schema()
--   entity_id INTEGER REFERENCES entities(id)
--   fact_id   TEXT   (sha256 hash, 16 chars, for dedup)
--   quote     TEXT
--   start_ms  INTEGER
--   end_ms    INTEGER
--   polarity  INTEGER  (-1/0/+1)
--   intensity REAL     (0..1)
-- Unique index on fact_id and index on entity_id added via migration as well.

-- ── Knowledge Graph ────────────────────────────────────────────────────────
-- Entities extracted by LLM from analyses (schema_version='v2').
-- normalized_key is generated by the LLM (transliterated, lowercase, underscores).
CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    entity_type     TEXT    NOT NULL,   -- person|org|topic|trait|place|product|deal|event
    canonical_name  TEXT    NOT NULL,
    normalized_key  TEXT    NOT NULL,   -- LLM-generated: ivan_petrov
    aliases         TEXT,               -- JSON array of strings
    attributes      TEXT,               -- JSON: type-specific fields
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, entity_type, normalized_key)
);
CREATE INDEX IF NOT EXISTS idx_entities_user_type ON entities(user_id, entity_type);

-- Directed relations between entities (time-decayed weight).
CREATE TABLE IF NOT EXISTS relations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT    NOT NULL REFERENCES users(user_id),
    src_entity_id       INTEGER NOT NULL REFERENCES entities(id),
    dst_entity_id       INTEGER NOT NULL REFERENCES entities(id),
    relation_type       TEXT    NOT NULL,
    weight              REAL    DEFAULT 1.0,
    confidence          REAL    DEFAULT 1.0,
    first_seen_call_id  INTEGER REFERENCES calls(call_id),
    last_seen_call_id   INTEGER REFERENCES calls(call_id),
    call_count          INTEGER DEFAULT 1,
    created_at          TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, src_entity_id, dst_entity_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_relations_src ON relations(src_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_dst ON relations(dst_entity_id);

-- Aggregated behavioural metrics per entity (deterministic, recalculated from events).
CREATE TABLE IF NOT EXISTS entity_metrics (
    entity_id           INTEGER PRIMARY KEY REFERENCES entities(id),
    user_id             TEXT    NOT NULL,
    total_calls         INTEGER DEFAULT 0,
    total_promises      INTEGER DEFAULT 0,
    fulfilled_promises  INTEGER DEFAULT 0,
    broken_promises     INTEGER DEFAULT 0,
    overdue_promises    INTEGER DEFAULT 0,
    contradictions      INTEGER DEFAULT 0,
    vagueness_count     INTEGER DEFAULT 0,
    blame_shift_count   INTEGER DEFAULT 0,
    emotional_spikes    INTEGER DEFAULT 0,
    avg_risk            REAL    DEFAULT 0,
    bs_index            REAL    DEFAULT 0,
    bs_formula_version  TEXT    DEFAULT 'v1_linear',
    emotional_pattern   TEXT,
    last_interaction    TEXT,
    updated_at          TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_summaries (
    contact_id    INTEGER PRIMARY KEY REFERENCES contacts(contact_id),
    user_id       TEXT NOT NULL REFERENCES users(user_id),
    total_calls   INTEGER DEFAULT 0,
    last_call_date TEXT,
    global_risk   INTEGER DEFAULT 0,
    avg_bs_score  INTEGER DEFAULT 0,
    top_hook      TEXT,
    open_promises TEXT,
    open_debts    TEXT,
    personal_facts TEXT,
    contact_role  TEXT,
    advice        TEXT,
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
