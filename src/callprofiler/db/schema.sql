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
