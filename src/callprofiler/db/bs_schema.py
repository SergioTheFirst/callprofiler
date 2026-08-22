# -*- coding: utf-8 -*-
"""
db/bs_schema.py — BS-v2 (T-26) canonical DDL, single-sourced.

Три DDL-владельца (``db/schema.sql``, ``graph/repository.py::_GRAPH_DDL``,
``insight/repository.py::_SCHEMA``) исторически расходились (RISK-15). Текст
таблиц BS-v2 объявлен ЗДЕСЬ один раз; migration 12 и оба применителя схемы
исполняют одну и ту же строку, поэтому ``sqlite_master`` не зависит от порядка
``init_db``/``apply_graph_schema``/``apply_insight_schema``.

``db/schema.sql`` держит байтовую копию этих же операторов (файл не может
импортировать Python) — равенство доказывает
``tests/test_db_migrations.py::test_migration_12_bs_v2_full_contract``.
"""

from __future__ import annotations

import sqlite3

# ── Canonical tables (§6 плана 100bsindex) ──────────────────────────────────
# contact_bs_metrics — canonical пара BS/уверенность на КОНТАКТЕ (единственный
# канон; entity_metrics/contact_summaries получают versioned projection).
CONTACT_BS_METRICS_DDL = """
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
"""

# bs_legacy_snapshots — байтовый снимок v1-значений ДО первой v2-проекции.
# Immutable (триггеры), кроме удаления внутри purge (users.purge_started_at).
BS_LEGACY_SNAPSHOTS_DDL = """
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
"""

# relation_evidence — per-call ledger отношений: заменяет wall-clock decay
# (upsert_relation_with_decay) детерминированной проекцией из леджера.
RELATION_EVIDENCE_DDL = """
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
"""

# Ownership/immutability триггеры (стиль m009: работают и при foreign_keys=OFF).
# trg_bls_immutable_del условный: безусловный ABORT сломал бы purge_user (T-06,
# privacy-контракт) — внутри purge флаг users.purge_started_at снимает запрет.
BS_V2_TRIGGERS_DDL = """
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
"""

BS_V2_TABLES_DDL = CONTACT_BS_METRICS_DDL + BS_LEGACY_SNAPSHOTS_DDL + RELATION_EVIDENCE_DDL

# ── Additive columns on pre-existing tables (§6 п.6-12) ─────────────────────
# Один источник для migration 12 и для fresh-DDL: fresh-схема объявляет их
# инлайн, upgrade добавляет ALTER'ом — контракт колонок совпадает.
BS_V2_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "users": [("purge_started_at", "TEXT")],
    "contacts": [("placeholder_key", "TEXT")],
    "promises": [
        ("vague", "INTEGER CHECK(vague IN (0,1))"),
        ("source_quote", "TEXT"),
        ("quote_match", "REAL CHECK(quote_match BETWEEN 0 AND 1)"),
        ("status_updated_at", "TEXT"),
        (
            "status_method",
            "TEXT NOT NULL DEFAULT 'legacy' "
            "CHECK(status_method IN ('det','system','llm','legacy'))",
        ),
    ],
    "events": [
        ("normalized_entity_key", "TEXT"),
        ("quote_match", "REAL CHECK(quote_match BETWEEN 0 AND 1)"),
        ("quote_verified", "INTEGER NOT NULL DEFAULT 0 CHECK(quote_verified IN (0,1))"),
        (
            "producer",
            "TEXT NOT NULL DEFAULT 'legacy' "
            "CHECK(producer IN ('legacy','graph_v1','graph_v2'))",
        ),
    ],
    "contact_summaries": [
        ("bs_index", "REAL"),
        ("bs_confidence", "INTEGER NOT NULL DEFAULT 1 CHECK(bs_confidence BETWEEN 1 AND 100)"),
        ("bs_formula_version", "TEXT NOT NULL DEFAULT 'legacy'"),
        ("bs_confidence_version", "TEXT NOT NULL DEFAULT 'legacy'"),
        ("bs_as_of", "TEXT"),
    ],
    "entity_metrics": [
        ("bs_confidence", "INTEGER NOT NULL DEFAULT 1 CHECK(bs_confidence BETWEEN 1 AND 100)"),
        ("bs_confidence_version", "TEXT NOT NULL DEFAULT 'legacy'"),
        ("bs_components_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("bs_source_signature", "TEXT NOT NULL DEFAULT ''"),
        ("bs_as_of", "TEXT"),
        (
            "bs_projection_status",
            "TEXT NOT NULL DEFAULT 'legacy' "
            "CHECK(bs_projection_status IN ('contact','unmapped','ambiguous','legacy'))",
        ),
    ],
    "bs_thresholds": [
        ("bs_formula_version", "TEXT NOT NULL DEFAULT 'legacy'"),
        ("policy_version", "TEXT NOT NULL DEFAULT 'legacy'"),
    ],
    "graph_replay_runs": [("run_signature", "TEXT"), ("as_of", "TEXT")],
    "relations": [
        (
            "producer",
            "TEXT NOT NULL DEFAULT 'graph_v1' CHECK(producer IN ('graph_v1','graph_v2'))",
        ),
        ("source_signature", "TEXT NOT NULL DEFAULT ''"),
    ],
}

BS_V2_INDEXES: list[str] = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_user_contact ON contacts(user_id, contact_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_placeholder ON contacts(user_id, placeholder_key) WHERE placeholder_key IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_replay_runs_sig ON graph_replay_runs(user_id, run_signature) WHERE run_signature IS NOT NULL",
]


# ── Frozen version/signature constants ─────────────────────────────────────
# ЗАМОРОЖЕНЫ: migration 12 и insight/bs_recompute.py считают одни и те же
# подписи. Изменение формата = новая formula version + новая миграция.
BS_FORMULA_VERSION_V2 = "v2_roc_observed_1"
CONFIDENCE_FORMULA_VERSION_V1 = "c1_effective_evidence_1"
BS_DETAILS_SCHEMA = "bs-details-1"
BS_INPUT_SCHEMA = "bs-input-1"
BS_CALLSET_SCHEMA = "bs-callset-1"

EMPTY_DETAILS_JSON = (
    '{"schema":"bs-details-1","as_of":null,'
    '"components":{"behavior":null,"contradiction":null,"promise_vague":null,'
    '"language":null,"model":null},'
    '"available":{"behavior":false,"contradiction":false,"promise_vague":false,'
    '"language":false,"model":false},'
    '"confidence":{"potential_mass":0.0,"qualified_mass":0.0,"quality":0.0,'
    '"agreement":0.0,"stability":0.0,"k":3,"undated_excluded":0,'
    '"rejection_reasons":[]},'
    '"evidence_refs":[]}'
)


def _canonical_json(payload) -> str:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def source_signature(payload) -> str:
    """SHA-256 канонического ``bs-input-1`` (без computed_at/UI-флагов)."""
    import hashlib

    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def callset_signature(call_tuples) -> str:
    """SHA-256 ``bs-callset-1``: (source_md5, domain_date) видимых звонков контакта."""
    import hashlib

    payload = {
        "schema": BS_CALLSET_SCHEMA,
        "calls": [[str(md5 or ""), str(date or "")] for md5, date in sorted(call_tuples)],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def empty_source_signature(user_id: str, contact_id: int, as_of: str) -> str:
    """Подпись контакта без пригодных строк (первый звонок, baseline 0/1)."""
    return source_signature(
        {
            "schema": BS_INPUT_SCHEMA,
            "user_id": user_id,
            "contact_id": int(contact_id),
            "as_of": as_of,
            "bs_formula_version": BS_FORMULA_VERSION_V2,
            "confidence_formula_version": CONFIDENCE_FORMULA_VERSION_V1,
            "rows": [],
        }
    )


def bs_v2_columns_for(table: str) -> list[tuple[str, str]]:
    return BS_V2_COLUMNS.get(table, [])


def apply_bs_v2_tables(conn: sqlite3.Connection) -> None:
    """Идемпотентно создать canonical BS-v2 таблицы и триггеры.

    Вызывается migration 12 и обоими применителями схемы. Триггеры ссылаются
    на ``users``/``contacts``/``calls`` — при отсутствии этих таблиц (порядок
    ``apply_graph_schema`` до ``init_db``) создание триггера всё равно проходит
    (SQLite резолвит имена при срабатывании), но сами таблицы BS создаются
    только когда есть на что ссылаться, поэтому порядок безопасен.
    """
    conn.executescript(BS_V2_TABLES_DDL)
    conn.executescript(BS_V2_TRIGGERS_DDL)
