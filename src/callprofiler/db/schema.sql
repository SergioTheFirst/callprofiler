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
