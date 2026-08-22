-- schema.sql — CallProfiler SQLite schema

CREATE TABLE IF NOT EXISTS users (
    user_id        TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL,
    telegram_chat_id TEXT,
    incoming_dir   TEXT NOT NULL,
    sync_dir       TEXT NOT NULL,
    ref_audio      TEXT NOT NULL,
    purge_started_at TEXT,          -- M12: снимает immutability bs_legacy_snapshots на время purge (T-06)
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
    placeholder_key  TEXT,           -- M12: контакт без телефона (md5-<source_md5>); НИКОГДА не merge'ится
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, phone_e164)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_user_contact ON contacts(user_id, contact_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_placeholder ON contacts(user_id, placeholder_key) WHERE placeholder_key IS NOT NULL;

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
    pipeline_stage INTEGER NOT NULL DEFAULT 0,
    role_fragile   INTEGER NOT NULL DEFAULT 0,
    asr_coverage   REAL,          -- T-07: доля успешных ASR окон (1 - failed/total), NULL = не вычислено
    call_type      TEXT,          -- NULL для обычных звонков, 'note' для голосовых заметок (F4)
    retry_count    INTEGER NOT NULL DEFAULT 0,
    error_message  TEXT,
    next_retry_at  TEXT,
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
    schema_version TEXT DEFAULT 'v1',   -- 'v1' legacy, 'v2' graph-enabled (writer всегда явный)
    canonical_json TEXT DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_analyses_schema ON analyses(schema_version, call_id);

CREATE TABLE IF NOT EXISTS promises (
    promise_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    contact_id     INTEGER REFERENCES contacts(contact_id),
    call_id        INTEGER NOT NULL REFERENCES calls(call_id),
    who            TEXT NOT NULL,
    what           TEXT NOT NULL,
    due            TEXT,
    status         TEXT NOT NULL DEFAULT 'open',
    vague          INTEGER CHECK(vague IN (0,1)),
    source_quote   TEXT,
    quote_match    REAL CHECK(quote_match BETWEEN 0 AND 1),
    status_updated_at TEXT,
    status_method  TEXT NOT NULL DEFAULT 'legacy' CHECK(status_method IN ('det','system','llm','legacy')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- NB: no user_id column here (P-DB-06, db/migrations.py::_m008_fts_drop_user_id).
-- content='transcripts' has no user_id column, so a rebuild ('rebuild' special
-- command) would fail looking for it. Ownership filtering is done via JOIN to
-- calls.user_id everywhere this is queried (search_transcripts, dashboard).
CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
    text,
    speaker,
    call_id UNINDEXED,
    content='transcripts',
    content_rowid='segment_id'
);

CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
    INSERT INTO transcripts_fts(rowid, text, speaker, call_id)
    VALUES (NEW.segment_id, NEW.text, NEW.speaker, NEW.call_id);
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
    entity_id     INTEGER,
    fact_id       TEXT,
    fact_type     TEXT,
    quote         TEXT,
    start_ms      INTEGER,
    end_ms        INTEGER,
    polarity      REAL,
    intensity     REAL,
    normalized_entity_key TEXT,
    quote_match   REAL CHECK(quote_match BETWEEN 0 AND 1),
    quote_verified INTEGER NOT NULL DEFAULT 0 CHECK(quote_verified IN (0,1)),
    producer      TEXT NOT NULL DEFAULT 'legacy' CHECK(producer IN ('legacy','graph_v1','graph_v2')),
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_factid ON events(fact_id) WHERE fact_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_id);

CREATE INDEX IF NOT EXISTS idx_events_contact ON events(user_id, contact_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(user_id, status);

-- Indexes для dashboard/poller (Фаза 2)
CREATE INDEX IF NOT EXISTS idx_calls_user_status ON calls(user_id, status);
CREATE INDEX IF NOT EXISTS idx_calls_updated_at ON calls(updated_at);
CREATE INDEX IF NOT EXISTS idx_calls_user_datetime ON calls(user_id, call_datetime);

-- Атомарная MD5-дедупликация (F2.5): один звонок на пользователя по source_md5
CREATE UNIQUE INDEX IF NOT EXISTS idx_calls_user_md5
    ON calls(user_id, source_md5)
    WHERE source_md5 IS NOT NULL;

-- Hot-path index для graph-replay (post-mortem 2026-06-30):
--   transcripts: get_transcript(call_id) ORDER BY start_ms — без индекса
--     на 660k+ строк = 17.5k полных сканов на каждый replay (~11.6B row visits).
-- NB: idx_analyses_schema создаётся в apply_graph_schema() — schema_version
--     добавляется ALTER-миграцией и в исходном DDL отсутствует.
CREATE INDEX IF NOT EXISTS idx_transcripts_call
    ON transcripts(call_id, start_ms);

-- Graph extension columns added via migration in graph/repository.py:apply_graph_schema()
--   entity_id INTEGER REFERENCES entities(id)
--   fact_id   TEXT   (sha256 hash, 16 chars, for dedup)
--   quote     TEXT
--   start_ms  INTEGER
--   end_ms    INTEGER
--   polarity  INTEGER  (-1/0/+1)
--   intensity REAL     (0..1)
-- Unique index on fact_id and index on entity_id added via migration as well.

-- ── Knowledge Graph ────────────────────────────────────
-- ВНИМАНИЕ: текст ниже — байтовая копия graph/repository.py::_GRAPH_DDL.
-- Расхождение = разные sqlite_master в зависимости от порядка применения
-- (init_db / apply_graph_schema) — RISK-15; ловится
-- tests/test_db_migrations.py::test_migration_12_bs_v2_full_contract.
CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    entity_type     TEXT    NOT NULL,
    canonical_name  TEXT    NOT NULL,
    normalized_key  TEXT    NOT NULL,
    aliases         TEXT,
    attributes      TEXT,
    archived        INTEGER DEFAULT 0,
    merged_into_id  INTEGER,
    is_owner        INTEGER DEFAULT 0,
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, entity_type, normalized_key)
);
CREATE INDEX IF NOT EXISTS idx_entities_user_type ON entities(user_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_user_archived ON entities(user_id, archived);
CREATE INDEX IF NOT EXISTS idx_entities_owner ON entities(user_id, is_owner);

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
    producer            TEXT NOT NULL DEFAULT 'graph_v1' CHECK(producer IN ('graph_v1','graph_v2')),
    source_signature    TEXT NOT NULL DEFAULT '',
    created_at          TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, src_entity_id, dst_entity_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_relations_src ON relations(src_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_dst ON relations(dst_entity_id);

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
    bs_confidence       INTEGER NOT NULL DEFAULT 1 CHECK(bs_confidence BETWEEN 1 AND 100),
    bs_confidence_version TEXT NOT NULL DEFAULT 'legacy',
    bs_components_json  TEXT NOT NULL DEFAULT '{}',
    bs_source_signature TEXT NOT NULL DEFAULT '',
    bs_as_of            TEXT,
    bs_projection_status TEXT NOT NULL DEFAULT 'legacy' CHECK(bs_projection_status IN ('contact','unmapped','ambiguous','legacy')),
    emotional_pattern   TEXT,
    last_interaction    TEXT,
    updated_at          TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entity_merges_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(user_id),
    canonical_id    INTEGER NOT NULL REFERENCES entities(id),
    duplicate_id    INTEGER NOT NULL REFERENCES entities(id),
    confidence      REAL,
    signals_json    TEXT,
    reason          TEXT,
    snapshot_json   TEXT,
    merged_by       TEXT,
    reversible      INTEGER DEFAULT 1,
    merged_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
    unmerged_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_entity_merges_user ON entity_merges_log(user_id);
CREATE INDEX IF NOT EXISTS idx_entity_merges_canonical ON entity_merges_log(canonical_id);

CREATE TABLE IF NOT EXISTS graph_replay_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL,
    calls_processed INTEGER DEFAULT 0,
    facts_total     INTEGER DEFAULT 0,
    facts_inserted  INTEGER DEFAULT 0,
    facts_rejected  INTEGER DEFAULT 0,
    rejection_rate  REAL    DEFAULT 0,
    entities_count  INTEGER DEFAULT 0,
    avg_bs_index    REAL,
    audit_critical  INTEGER DEFAULT 0,
    run_signature   TEXT,
    as_of           TEXT,
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_replay_runs_user ON graph_replay_runs(user_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_replay_runs_sig ON graph_replay_runs(user_id, run_signature) WHERE run_signature IS NOT NULL;

CREATE TABLE IF NOT EXISTS bs_thresholds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL,
    reliable_max    REAL    NOT NULL,
    noisy_max       REAL    NOT NULL,
    risky_max       REAL    NOT NULL,
    unreliable_max  REAL    NOT NULL,
    entity_count    INTEGER DEFAULT 0,
    std_dev         REAL,
    bs_formula_version TEXT NOT NULL DEFAULT 'legacy',
    policy_version  TEXT NOT NULL DEFAULT 'legacy',
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bs_thresholds_user ON bs_thresholds(user_id, created_at);

CREATE TABLE IF NOT EXISTS entity_profiles (
    profile_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          TEXT    NOT NULL REFERENCES users(user_id),
    entity_id        INTEGER NOT NULL REFERENCES entities(id),
    profile_type     TEXT    NOT NULL DEFAULT 'psychology',
    summary          TEXT,
    interpretation   TEXT,
    payload_json     TEXT    NOT NULL DEFAULT '{}',
    source_signature TEXT,
    model            TEXT,
    source           TEXT    NOT NULL DEFAULT 'llm',
    created_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, entity_id, profile_type)
);
CREATE INDEX IF NOT EXISTS idx_entity_profiles_user
    ON entity_profiles(user_id, profile_type, updated_at);

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
    bs_index      REAL,
    bs_confidence INTEGER NOT NULL DEFAULT 1 CHECK(bs_confidence BETWEEN 1 AND 100),
    bs_formula_version TEXT NOT NULL DEFAULT 'legacy',
    bs_confidence_version TEXT NOT NULL DEFAULT 'legacy',
    bs_as_of      TEXT,
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ── BS-v2 (T-26) ────────────────────────────────────────
-- Байтовая копия db/bs_schema.py (тот же текст исполняют migration 12,
-- apply_graph_schema и apply_insight_schema).
CREATE TABLE IF NOT EXISTS contact_bs_metrics (
  user_id TEXT NOT NULL,
  contact_id INTEGER NOT NULL,
  bs_index REAL NOT NULL CHECK(bs_index BETWEEN 0 AND 100),
  bs_confidence INTEGER NOT NULL CHECK(bs_confidence BETWEEN 1 AND 100),
  bs_formula_version TEXT NOT NULL,
  confidence_formula_version TEXT NOT NULL,
  behavior_score REAL CHECK(behavior_score BETWEEN 0 AND 1),
  linguistic_score REAL CHECK(linguistic_score BETWEEN 0 AND 1),
  model_score REAL CHECK(model_score BETWEEN 0 AND 1),
  potential_mass REAL NOT NULL CHECK(potential_mass >= 0),
  qualified_mass REAL NOT NULL CHECK(qualified_mass >= 0 AND qualified_mass <= potential_mass),
  quality_score REAL NOT NULL CHECK(quality_score BETWEEN 0 AND 1),
  agreement_score REAL NOT NULL CHECK(agreement_score BETWEEN 0 AND 1),
  stability_score REAL NOT NULL CHECK(stability_score BETWEEN 0 AND 1),
  no_evidence INTEGER NOT NULL CHECK(no_evidence IN (0,1)),
  details_json TEXT NOT NULL DEFAULT '{}',
  source_signature TEXT NOT NULL,
  callset_signature TEXT NOT NULL,
  computed_as_of TEXT NOT NULL,
  computed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, contact_id, bs_formula_version, confidence_formula_version),
  FOREIGN KEY(user_id, contact_id) REFERENCES contacts(user_id, contact_id)
);
CREATE INDEX IF NOT EXISTS idx_cbm_user_contact ON contact_bs_metrics(user_id, contact_id);

CREATE TABLE IF NOT EXISTS bs_legacy_snapshots (
  user_id TEXT NOT NULL,
  subject_kind TEXT NOT NULL CHECK(subject_kind IN ('entity','contact_fallback')),
  subject_key TEXT NOT NULL,
  contact_id INTEGER,
  bs_index REAL NOT NULL CHECK(bs_index BETWEEN 0 AND 100),
  bs_formula_version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, subject_kind, subject_key),
  CHECK(subject_kind='entity' OR contact_id IS NOT NULL),
  FOREIGN KEY(user_id, contact_id) REFERENCES contacts(user_id, contact_id)
);

CREATE TABLE IF NOT EXISTS relation_evidence (
  user_id TEXT NOT NULL,
  evidence_key TEXT NOT NULL,
  source_call_id INTEGER NOT NULL,
  raw_src_type TEXT NOT NULL,
  raw_src_key TEXT NOT NULL,
  raw_dst_type TEXT NOT NULL,
  raw_dst_key TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  source_date TEXT NOT NULL,
  producer TEXT NOT NULL CHECK(producer IN ('graph_v1','graph_v2')),
  PRIMARY KEY(user_id,evidence_key),
  FOREIGN KEY(source_call_id) REFERENCES calls(call_id)
);
CREATE INDEX IF NOT EXISTS idx_relev_key ON relation_evidence(user_id,raw_src_type,raw_src_key,raw_dst_type,raw_dst_key,relation_type);
CREATE INDEX IF NOT EXISTS idx_relev_call ON relation_evidence(user_id,source_call_id);

CREATE TRIGGER IF NOT EXISTS trg_cbm_owner_ins
BEFORE INSERT ON contact_bs_metrics
BEGIN
    SELECT RAISE(ABORT, 'contact owner mismatch')
    WHERE NOT EXISTS (
        SELECT 1 FROM contacts WHERE contact_id = NEW.contact_id AND user_id = NEW.user_id
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_cbm_owner_upd
BEFORE UPDATE ON contact_bs_metrics
BEGIN
    SELECT RAISE(ABORT, 'contact owner mismatch')
    WHERE NOT EXISTS (
        SELECT 1 FROM contacts WHERE contact_id = NEW.contact_id AND user_id = NEW.user_id
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_bls_owner_ins
BEFORE INSERT ON bs_legacy_snapshots
WHEN NEW.contact_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'contact owner mismatch')
    WHERE NOT EXISTS (
        SELECT 1 FROM contacts WHERE contact_id = NEW.contact_id AND user_id = NEW.user_id
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_bls_immutable_upd
BEFORE UPDATE ON bs_legacy_snapshots
BEGIN
    SELECT RAISE(ABORT, 'immutable legacy snapshot');
END;

CREATE TRIGGER IF NOT EXISTS trg_bls_immutable_del
BEFORE DELETE ON bs_legacy_snapshots
WHEN NOT EXISTS (
    SELECT 1 FROM users WHERE user_id = OLD.user_id AND purge_started_at IS NOT NULL
)
BEGIN
    SELECT RAISE(ABORT, 'immutable legacy snapshot');
END;

CREATE TRIGGER IF NOT EXISTS trg_relev_owner_ins
BEFORE INSERT ON relation_evidence
BEGIN
    SELECT RAISE(ABORT, 'call owner mismatch')
    WHERE NOT EXISTS (
        SELECT 1 FROM calls WHERE call_id = NEW.source_call_id AND user_id = NEW.user_id
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_relev_owner_upd
BEFORE UPDATE ON relation_evidence
BEGIN
    SELECT RAISE(ABORT, 'call owner mismatch')
    WHERE NOT EXISTS (
        SELECT 1 FROM calls WHERE call_id = NEW.source_call_id AND user_id = NEW.user_id
    );
END;
