"""Insight engine persistence. All queries filter by user_id."""
import json
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contact_features (
    contact_id   INTEGER NOT NULL,
    user_id      TEXT    NOT NULL,
    feature_set  TEXT    NOT NULL,
    feature_name TEXT    NOT NULL,
    value        REAL,
    support_n    INTEGER NOT NULL DEFAULT 0,
    tier         TEXT    NOT NULL,
    computed_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (contact_id, feature_name)
);
CREATE INDEX IF NOT EXISTS idx_cfeat_user_set ON contact_features(user_id, feature_set);

CREATE TABLE IF NOT EXISTS archetype_models (
    model_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL,
    version      TEXT    NOT NULL,
    k            INTEGER NOT NULL,
    silhouette   REAL,
    n_contacts   INTEGER,
    feature_list TEXT,
    centroids    TEXT,
    labels       TEXT,
    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_archetypes (
    contact_id       INTEGER PRIMARY KEY,
    user_id          TEXT    NOT NULL,
    model_id         INTEGER,
    cluster_idx      INTEGER NOT NULL,
    archetype_label  TEXT,
    membership       REAL,
    distinctive_dims TEXT,
    confidence       TEXT,
    evidence         TEXT,
    pca_x            REAL,
    pca_y            REAL,
    computed_at      TEXT    DEFAULT CURRENT_TIMESTAMP
);

-- Мягкая связка graph-entity ↔ contact (Ф1 плана досье). DERIVED:
-- полностью перестраивается (person_link.build_entity_contact_map),
-- entity_id живут до ближайшего graph-replay. НЕ слияние контактов.
CREATE TABLE IF NOT EXISTS entity_contact_map (
    user_id    TEXT    NOT NULL,
    entity_id  INTEGER NOT NULL,
    contact_id INTEGER NOT NULL,
    method     TEXT    NOT NULL CHECK (method IN ('name', 'cooccur')),
    confidence REAL    NOT NULL,
    built_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, entity_id, contact_id)
);
CREATE INDEX IF NOT EXISTS idx_ecmap_contact ON entity_contact_map(user_id, contact_id);

-- Оценка возраста контакта (план 2026-06-11-age-estimation). Возраст храним
-- двояко: age_* (срез на computed_at) и birth_year_* (инвариант) — дашборд
-- выводит «возраст сейчас» из birth_year_point без пересчёта при ежедневном
-- притоке звонков. llm_prompt_hash/llm_result — memoization LLM-пасса
-- (паттерн сигнатуры психопрофайлера): det-пересчёты не платят токенами.
CREATE TABLE IF NOT EXISTS contact_age_estimates (
    contact_id       INTEGER PRIMARY KEY,
    user_id          TEXT    NOT NULL,
    age_low          INTEGER,
    age_high         INTEGER,
    age_point        INTEGER,
    birth_year_low   INTEGER,
    birth_year_high  INTEGER,
    birth_year_point INTEGER,
    confidence       INTEGER NOT NULL CHECK (confidence BETWEEN 1 AND 100),
    method           TEXT    NOT NULL,      -- 'marker'|'relation'|'llm'|'combined'
    evidence         TEXT,                  -- JSON [{quote, signal, weight, dt}]
    prompt_version   TEXT,                  -- версия age-промпта (llm-метод)
    llm_prompt_hash  TEXT,                  -- sha1(prompt+версия) — кэш LLM
    llm_result       TEXT,                  -- валидированный LLM-ответ (кэш/аудит)
    computed_at      TEXT    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cage_user ON contact_age_estimates(user_id);
"""

# Колонки, добавленные после первого релиза схемы. ALTER, не recreate (db.md).
# Имена таблиц/колонок — литералы кода, не пользовательский ввод (безопасно в f-string).
_MIGRATIONS = {
    "contact_archetypes": {"pca_x": "REAL", "pca_y": "REAL"},
}


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict) -> None:
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, decl in columns.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def apply_insight_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    for table, cols in _MIGRATIONS.items():
        _ensure_columns(conn, table, cols)
    conn.commit()


def save_archetype_model(conn, user_id, *, version, k, silhouette, n_contacts,
                         feature_list, centroids, labels):
    cur = conn.execute(
        "INSERT INTO archetype_models(user_id, version, k, silhouette, n_contacts, "
        "feature_list, centroids, labels) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, version, k, silhouette, n_contacts,
         json.dumps(feature_list), json.dumps(centroids), json.dumps(labels)),
    )
    conn.commit()
    return cur.lastrowid


def save_contact_archetype(conn, user_id, *, contact_id, model_id, cluster_idx,
                           label, membership, distinctive_dims, confidence, evidence,
                           pca_x=None, pca_y=None):
    conn.execute(
        "INSERT INTO contact_archetypes(contact_id, user_id, model_id, cluster_idx, "
        "archetype_label, membership, distinctive_dims, confidence, evidence, pca_x, pca_y) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(contact_id) DO UPDATE SET model_id=excluded.model_id, "
        "cluster_idx=excluded.cluster_idx, archetype_label=excluded.archetype_label, "
        "membership=excluded.membership, distinctive_dims=excluded.distinctive_dims, "
        "confidence=excluded.confidence, evidence=excluded.evidence, "
        "pca_x=excluded.pca_x, pca_y=excluded.pca_y, "
        "computed_at=CURRENT_TIMESTAMP "
        "WHERE contact_archetypes.user_id = excluded.user_id",  # user-scoped guard
        (contact_id, user_id, model_id, cluster_idx, label, membership,
         json.dumps(distinctive_dims), confidence, json.dumps(evidence), pca_x, pca_y),
    )
    conn.commit()


def save_contact_age_estimate(conn, user_id, *, contact_id, age_low, age_high,
                              age_point, birth_year_low, birth_year_high,
                              birth_year_point, confidence, method, evidence,
                              prompt_version=None, llm_prompt_hash=None,
                              llm_result=None):
    conn.execute(
        "INSERT INTO contact_age_estimates(contact_id, user_id, age_low, age_high, "
        "age_point, birth_year_low, birth_year_high, birth_year_point, confidence, "
        "method, evidence, prompt_version, llm_prompt_hash, llm_result) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(contact_id) DO UPDATE SET "
        "age_low=excluded.age_low, age_high=excluded.age_high, "
        "age_point=excluded.age_point, birth_year_low=excluded.birth_year_low, "
        "birth_year_high=excluded.birth_year_high, "
        "birth_year_point=excluded.birth_year_point, "
        "confidence=excluded.confidence, method=excluded.method, "
        "evidence=excluded.evidence, prompt_version=excluded.prompt_version, "
        "llm_prompt_hash=excluded.llm_prompt_hash, llm_result=excluded.llm_result, "
        "computed_at=CURRENT_TIMESTAMP "
        "WHERE contact_age_estimates.user_id = excluded.user_id",  # user-scoped guard
        (contact_id, user_id, age_low, age_high, age_point, birth_year_low,
         birth_year_high, birth_year_point, confidence, method,
         json.dumps(evidence, ensure_ascii=False), prompt_version,
         llm_prompt_hash, llm_result),
    )


def load_contact_archetypes(conn, user_id):
    rows = conn.execute(
        "SELECT contact_id, cluster_idx, archetype_label, membership, confidence "
        "FROM contact_archetypes WHERE user_id = ? ORDER BY contact_id", (user_id,)
    ).fetchall()
    return [dict(zip(("contact_id", "cluster_idx", "label", "membership", "confidence"), r))
            for r in rows]
