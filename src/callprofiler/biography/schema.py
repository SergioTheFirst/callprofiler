# -*- coding: utf-8 -*-
"""
schema.py — DDL for biography tables.

All tables are idempotent (CREATE TABLE IF NOT EXISTS) and user_id-scoped.
No foreign-key cascades: we only soft-link; sources (calls, transcripts,
analyses) are never modified by biography passes.
"""

from __future__ import annotations

BIOGRAPHY_SCHEMA_SQL = r"""
-- Per-call scene: narrative unit distilled from one call.
CREATE TABLE IF NOT EXISTS bio_scenes (
    scene_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    call_id         INTEGER NOT NULL REFERENCES calls(call_id),
    call_datetime   TEXT,
    importance      INTEGER NOT NULL DEFAULT 0,    -- 0-100 narrative weight
    scene_type      TEXT,                          -- business|personal|conflict|joy|routine|transition
    setting         TEXT,                          -- short context phrase
    synopsis        TEXT NOT NULL DEFAULT '',      -- 1-3 sentence narrative summary
    key_quote       TEXT,                          -- one telling quote (<=200 chars)
    emotional_tone  TEXT,                          -- tense|warm|neutral|worried|celebratory|angry
    named_entities  TEXT NOT NULL DEFAULT '[]',    -- JSON [{name, type, mention}]
    themes          TEXT NOT NULL DEFAULT '[]',    -- JSON [theme1, theme2]
    insight         TEXT NOT NULL DEFAULT '',      -- LLM: narrative/psychological significance
    raw_llm         TEXT,                          -- full LLM response (debug)
    model           TEXT,
    prompt_version  TEXT,
    status          TEXT NOT NULL DEFAULT 'ok',    -- ok|partial|skipped|failed
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(call_id)
);

CREATE INDEX IF NOT EXISTS idx_bio_scenes_user ON bio_scenes(user_id, call_datetime);
CREATE INDEX IF NOT EXISTS idx_bio_scenes_importance ON bio_scenes(user_id, importance DESC);

-- Canonical entity: person / place / company / project / event.
CREATE TABLE IF NOT EXISTS bio_entities (
    entity_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    canonical_name  TEXT    NOT NULL,
    entity_type     TEXT    NOT NULL,              -- PERSON|PLACE|COMPANY|PROJECT|EVENT
    aliases         TEXT    NOT NULL DEFAULT '[]', -- JSON list of strings
    contact_id      INTEGER REFERENCES contacts(contact_id),  -- if linkable to phone contact
    first_seen      TEXT,
    last_seen       TEXT,
    mention_count   INTEGER NOT NULL DEFAULT 0,
    description     TEXT,                          -- 1-2 sentence description from LLM
    role            TEXT,                          -- colleague|client|supplier|friend|family
    importance      INTEGER NOT NULL DEFAULT 0,    -- derived: sum(scene.importance) capped
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, entity_type, canonical_name)
);

CREATE INDEX IF NOT EXISTS idx_bio_entities_user ON bio_entities(user_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_bio_entities_importance ON bio_entities(user_id, importance DESC);

-- Link: scene <-> entity (many-to-many).
CREATE TABLE IF NOT EXISTS bio_scene_entities (
    scene_id        INTEGER NOT NULL REFERENCES bio_scenes(scene_id),
    entity_id       INTEGER NOT NULL REFERENCES bio_entities(entity_id),
    mention_text    TEXT,                          -- surface form in this scene
    PRIMARY KEY(scene_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_bio_scene_entities_entity ON bio_scene_entities(entity_id);

-- Thread: chronological chain of scenes about one entity.
CREATE TABLE IF NOT EXISTS bio_threads (
    thread_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    entity_id       INTEGER REFERENCES bio_entities(entity_id),
    title           TEXT,
    scene_ids       TEXT NOT NULL DEFAULT '[]',    -- JSON [scene_id,...] chronological
    start_date      TEXT,
    end_date        TEXT,
    summary         TEXT,                          -- LLM-written arc of the thread
    tension_curve   TEXT NOT NULL DEFAULT '[]',    -- JSON [importance per scene]
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, entity_id)
);

-- Arc: multi-scene problem/story/project resolution.
CREATE TABLE IF NOT EXISTS bio_arcs (
    arc_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    title           TEXT,
    arc_type        TEXT,                          -- problem|project|relationship|life_event
    start_date      TEXT,
    end_date        TEXT,
    status          TEXT,                          -- ongoing|resolved|abandoned
    synopsis        TEXT,                          -- 1-paragraph narrative
    scene_ids       TEXT NOT NULL DEFAULT '[]',    -- JSON
    entity_ids      TEXT NOT NULL DEFAULT '[]',    -- JSON
    outcome         TEXT,
    importance      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bio_arcs_user ON bio_arcs(user_id, importance DESC);

-- Portrait: deep character sketch for a recurring entity.
CREATE TABLE IF NOT EXISTS bio_portraits (
    portrait_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    entity_id       INTEGER NOT NULL REFERENCES bio_entities(entity_id),
    prose           TEXT,                          -- 1-3 paragraphs
    traits          TEXT NOT NULL DEFAULT '[]',    -- JSON
    relationship    TEXT,
    pivotal_scenes  TEXT NOT NULL DEFAULT '[]',    -- JSON
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, entity_id)
);

-- Chapter: thematic / temporal prose chunk.
CREATE TABLE IF NOT EXISTS bio_chapters (
    chapter_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    chapter_num     INTEGER NOT NULL,
    title           TEXT,
    period_start    TEXT,
    period_end      TEXT,
    theme           TEXT,
    prose           TEXT,                          -- markdown
    scene_ids       TEXT NOT NULL DEFAULT '[]',    -- JSON
    arc_ids         TEXT NOT NULL DEFAULT '[]',    -- JSON
    entity_ids      TEXT NOT NULL DEFAULT '[]',    -- JSON
    word_count      INTEGER NOT NULL DEFAULT 0,
    model           TEXT,
    status          TEXT NOT NULL DEFAULT 'draft', -- draft|edited|final
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, chapter_num)
);

-- Book: full assembled volume (one row per "version").
CREATE TABLE IF NOT EXISTS bio_books (
    book_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    title           TEXT,
    subtitle        TEXT,
    epigraph        TEXT,
    prologue        TEXT,
    epilogue        TEXT,
    toc             TEXT NOT NULL DEFAULT '[]',    -- JSON
    prose_full      TEXT,                          -- final markdown
    word_count      INTEGER NOT NULL DEFAULT 0,
    period_start    TEXT,
    period_end      TEXT,
    model           TEXT,
    version_label   TEXT,                          -- "draft-1" / "final"
    book_type       TEXT NOT NULL DEFAULT 'main',  -- main|yearly_summary
    generated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Checkpoint: per-pass resumable state.
CREATE TABLE IF NOT EXISTS bio_checkpoints (
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    pass_name       TEXT    NOT NULL,
    last_item_key   TEXT,                          -- last processed (e.g. "call_id:12345")
    total_items     INTEGER NOT NULL DEFAULT 0,
    processed_items INTEGER NOT NULL DEFAULT 0,
    failed_items    INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running', -- running|done|failed|paused
    notes           TEXT,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(user_id, pass_name)
);

-- Memoized LLM calls: every prompt + response, keyed by hash.
-- A re-run that issues the same prompt returns the cached response — key to
-- multi-day runs that survive restarts, crashes, model swaps.
CREATE TABLE IF NOT EXISTS bio_llm_calls (
    llm_call_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    pass_name       TEXT,
    context_key     TEXT,                          -- e.g. "scene:12345" or "portrait:entity:42"
    prompt_hash     TEXT NOT NULL,                 -- MD5(prompt + temp + max_tokens + model)
    prompt_preview  TEXT,                          -- first 400 chars (debugging)
    response        TEXT,
    duration_sec    REAL,
    status          TEXT NOT NULL DEFAULT 'ok',    -- ok|retry|failed|cached
    error           TEXT,
    model           TEXT,
    temperature     REAL,
    max_tokens      INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bio_llm_hash    ON bio_llm_calls(prompt_hash);
CREATE INDEX IF NOT EXISTS idx_bio_llm_context ON bio_llm_calls(user_id, pass_name, context_key);
"""


def _add_column_if_missing(conn, table: str, column: str, definition: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def apply_biography_schema(conn) -> None:
    """Apply biography schema to an existing sqlite3 connection."""
    conn.executescript(BIOGRAPHY_SCHEMA_SQL)
    # Migrations for columns added after initial schema deployment.
    _add_column_if_missing(conn, "bio_scenes", "insight",
                           "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "bio_books", "book_type",
                           "TEXT NOT NULL DEFAULT 'main'")
    conn.commit()
