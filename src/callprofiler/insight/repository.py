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


def load_contact_archetypes(conn, user_id):
    rows = conn.execute(
        "SELECT contact_id, cluster_idx, archetype_label, membership, confidence "
        "FROM contact_archetypes WHERE user_id = ? ORDER BY contact_id", (user_id,)
    ).fetchall()
    return [dict(zip(("contact_id", "cluster_idx", "label", "membership", "confidence"), r))
            for r in rows]
