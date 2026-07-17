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

-- Стилометрическая (no-ML) оценка возраста — план age.md, доп. к маркерам/
-- якорям/LLM в contact_age_estimates. Отдельная таблица: contact_id там уже
-- PRIMARY KEY (одна строка на контакт), второй method='stylometric' не вписать
-- (vozrast.md §9.3 это упускает). Слияние в 'combined' — отложено.
CREATE TABLE IF NOT EXISTS contact_age_style (
    contact_id      INTEGER PRIMARY KEY,
    user_id         TEXT    NOT NULL,
    group_code      TEXT,                 -- argmax группа: 'G1'..'G6'
    group_json      TEXT,                 -- {"G1":0.0,...,"G6":0.08} сумма=1
    birth_year_low  INTEGER,
    birth_year_high INTEGER,
    birth_year_point INTEGER,
    confidence      INTEGER NOT NULL CHECK (confidence BETWEEN 1 AND 100),
    confidence_level INTEGER NOT NULL CHECK (confidence_level BETWEEN 1 AND 5),
    n_conversations INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    top_json        TEXT,                 -- [["Т1 карьера",0.31],["Ч6",0.18],...]
    warnings_json   TEXT,                 -- ["мало данных","специфичный регистр"]
    table_version   TEXT,                 -- TABLE_VERSION+RULES_VERSION
    computed_at     TEXT    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cage_style_user ON contact_age_style(user_id);

-- Заметка владельца на контакте (M6): свободное ручное поле, НЕ правка
-- автогенерата (raw_response неприкосновенен). tools-канал, dashboard/tools.py.
CREATE TABLE IF NOT EXISTS contact_notes (
    contact_id INTEGER PRIMARY KEY,
    user_id    TEXT NOT NULL,
    note       TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- «Зеркало» владельца (A3): один агрегат-JSON на юзера, PK=user_id.
CREATE TABLE IF NOT EXISTS owner_mirror (
    user_id     TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    computed_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Пофактовое ✓/✗ подтверждение владельцем (F1). item_key всегда TEXT (str(rowid)
-- для promise/event; готовый sha1[:16] для будущего deep_fact, M8). user_id —
-- часть составного PK, поэтому кросс-юзерная коллизия по (kind,key) невозможна
-- в принципе (не нужен доп. guard как у contact_id-only таблиц).
CREATE TABLE IF NOT EXISTS fact_feedback (
    user_id    TEXT NOT NULL,
    item_kind  TEXT NOT NULL CHECK(item_kind IN ('promise','event','deep_fact')),
    item_key   TEXT NOT NULL,
    verdict    TEXT NOT NULL CHECK(verdict IN ('confirmed','rejected')),
    source     TEXT NOT NULL DEFAULT 'telegram',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, item_kind, item_key)
);

-- Напоминания по подтверждённым обещаниям (F2) — только по явному действию
-- владельца (инвариант 18), self-disabling после 5 ошибок отправки подряд.
CREATE TABLE IF NOT EXISTS reminders (
    reminder_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT NOT NULL,
    item_kind           TEXT NOT NULL,
    item_key            TEXT NOT NULL,
    text                TEXT NOT NULL,
    due_at              TEXT NOT NULL,
    chat_id             INTEGER NOT NULL,
    sent_at             TEXT,
    enabled             INTEGER NOT NULL DEFAULT 1,
    consecutive_errors  INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(user_id, enabled, sent_at, due_at);

-- Дедуп 21:00-триггера вечернего отчёта (F5): один отчёт в день на юзера.
CREATE TABLE IF NOT EXISTS report_state (
    user_id           TEXT PRIMARY KEY,
    last_report_date  TEXT
);

-- M8: map-reduce deep-extract по ПОЛНОМУ транскрипту длинных звонков. Дисплей-слой
-- (НЕ events/graph — replay-инвариант, graph.md layer contract). item_key дедупит
-- перекрытия соседних чанков одного звонка. deep_scans — "звонок X уже пройден
-- версией промпта Y", гейт повторного прогона без --force.
CREATE TABLE IF NOT EXISTS deep_facts (
    user_id        TEXT NOT NULL,
    item_key       TEXT NOT NULL,
    call_id        INTEGER NOT NULL,
    contact_id     INTEGER,
    type           TEXT NOT NULL CHECK(type IN ('promise','debt','fact','date')),
    who            TEXT NOT NULL CHECK(who IN ('OWNER','OTHER')),
    what           TEXT NOT NULL,
    quote          TEXT NOT NULL,
    deadline_raw   TEXT,
    chunk_idx      INTEGER,
    prompt_version TEXT NOT NULL,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, item_key)
);
CREATE INDEX IF NOT EXISTS idx_deepfacts_contact ON deep_facts(user_id, contact_id);

CREATE TABLE IF NOT EXISTS deep_scans (
    user_id        TEXT NOT NULL,
    call_id        INTEGER NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, call_id, prompt_version)
);

-- C1: граф упоминаний contact->contact через entity_contact_map. DERIVED,
-- полный rebuild per user (паттерн entity_contact_map) — не трогать вручную.
CREATE TABLE IF NOT EXISTS mention_edges (
    user_id        TEXT NOT NULL,
    src_contact_id INTEGER NOT NULL,
    dst_contact_id INTEGER NOT NULL,
    mention_count  INTEGER NOT NULL,
    last_date      TEXT,
    sample_quote   TEXT,
    PRIMARY KEY (user_id, src_contact_id, dst_contact_id)
);

-- D3: квартальный LLM-отчёт о социальной вселенной, кэш по (user,period,версия промпта).
CREATE TABLE IF NOT EXISTS insight_reports (
    user_id        TEXT NOT NULL,
    period         TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_hash    TEXT NOT NULL,
    body_md        TEXT NOT NULL,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, period, prompt_version)
);
"""

# Колонки, добавленные после первого релиза схемы. ALTER, не recreate (db.md).
# Имена таблиц/колонок — литералы кода, не пользовательский ввод (безопасно в f-string).
_MIGRATIONS = {
    "contact_archetypes": {"pca_x": "REAL", "pca_y": "REAL"},
    "report_state": {"last_doctor_date": "TEXT"},  # F6: доктор — второй плановый пуш (инвариант 25)
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


_NOTE_MAX_CHARS = 2000  # держать в синхроне с dashboard/tools.py::_CONTACT_NOTE_MAX_CHARS


def append_contact_note(conn: sqlite3.Connection, user_id: str, contact_id: int, line: str) -> None:
    """Дописать строку в contact_notes (F4: caption-привязка голосовой заметки).

    В отличие от dashboard/tools.py::set_contact_note (полная замена из UI),
    здесь ДОПИСЫВАЕМ — при превышении cap старое обрезается С ГОЛОВЫ (хвост важнее).
    """
    apply_insight_schema(conn)
    row = conn.execute(
        "SELECT note FROM contact_notes WHERE contact_id = ? AND user_id = ?",
        (contact_id, user_id),
    ).fetchone()
    old = (row["note"] if row else "") or ""
    combined = f"{old}\n{line}" if old else line
    combined = combined[-_NOTE_MAX_CHARS:]
    conn.execute(
        "INSERT INTO contact_notes(contact_id, user_id, note, updated_at) "
        "VALUES (?,?,?,CURRENT_TIMESTAMP) "
        "ON CONFLICT(contact_id) DO UPDATE SET note=excluded.note, "
        "updated_at=CURRENT_TIMESTAMP "
        "WHERE contact_notes.user_id = excluded.user_id",
        (contact_id, user_id, combined),
    )
    conn.commit()


def get_report_state(conn: sqlite3.Connection, user_id: str) -> str | None:
    """F5: дата последнего отправленного вечернего отчёта (или None)."""
    apply_insight_schema(conn)
    row = conn.execute(
        "SELECT last_report_date FROM report_state WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["last_report_date"] if row else None


def set_report_state(conn: sqlite3.Connection, user_id: str, date_str: str) -> None:
    apply_insight_schema(conn)
    conn.execute(
        "INSERT INTO report_state(user_id, last_report_date) VALUES (?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET last_report_date=excluded.last_report_date",
        (user_id, date_str),
    )
    conn.commit()


def get_doctor_state(conn: sqlite3.Connection, user_id: str) -> str | None:
    """F6: дата последнего отправленного doctor-отчёта (или None)."""
    apply_insight_schema(conn)
    row = conn.execute(
        "SELECT last_doctor_date FROM report_state WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["last_doctor_date"] if row else None


def set_doctor_state(conn: sqlite3.Connection, user_id: str, date_str: str) -> None:
    apply_insight_schema(conn)
    conn.execute(
        "INSERT INTO report_state(user_id, last_doctor_date) VALUES (?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET last_doctor_date=excluded.last_doctor_date",
        (user_id, date_str),
    )
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


def save_contact_age_style(conn, user_id, *, contact_id, group_code, group_dist,
                           birth_low, birth_high, birth_point, confidence,
                           confidence_level, n_conversations, total_tokens,
                           top, warnings, table_version):
    conn.execute(
        "INSERT INTO contact_age_style(contact_id, user_id, group_code, group_json, "
        "birth_year_low, birth_year_high, birth_year_point, confidence, "
        "confidence_level, n_conversations, total_tokens, top_json, warnings_json, "
        "table_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(contact_id) DO UPDATE SET "
        "group_code=excluded.group_code, group_json=excluded.group_json, "
        "birth_year_low=excluded.birth_year_low, birth_year_high=excluded.birth_year_high, "
        "birth_year_point=excluded.birth_year_point, confidence=excluded.confidence, "
        "confidence_level=excluded.confidence_level, "
        "n_conversations=excluded.n_conversations, total_tokens=excluded.total_tokens, "
        "top_json=excluded.top_json, warnings_json=excluded.warnings_json, "
        "table_version=excluded.table_version, computed_at=CURRENT_TIMESTAMP "
        "WHERE contact_age_style.user_id = excluded.user_id",  # user-scoped guard
        (contact_id, user_id, group_code, json.dumps(group_dist, ensure_ascii=False),
         birth_low, birth_high, birth_point, confidence, confidence_level,
         n_conversations, total_tokens, json.dumps(top, ensure_ascii=False),
         json.dumps(warnings, ensure_ascii=False), table_version),
    )
    conn.commit()


def load_contact_age_style(conn, user_id, contact_id=None):
    sql = ("SELECT contact_id, group_code, group_json, birth_year_low, birth_year_high, "
           "birth_year_point, confidence, confidence_level, n_conversations, "
           "total_tokens, top_json, warnings_json, table_version, computed_at "
           "FROM contact_age_style WHERE user_id = ?")
    params = [user_id]
    if contact_id is not None:
        sql += " AND contact_id = ?"
        params.append(contact_id)
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


FACT_KINDS = ("promise", "event", "deep_fact")


def set_fact_verdict(conn, user_id, *, item_kind, item_key, verdict, source="telegram"):
    """UPSERT ✓/✗ вердикт владельца по одному факту/обещанию (F1). Повторный тап
    меняет вердикт (не копит историю — источник истины = последнее решение)."""
    if item_kind not in FACT_KINDS:
        raise ValueError(f"unknown item_kind: {item_kind!r}")
    if verdict not in ("confirmed", "rejected"):
        raise ValueError(f"unknown verdict: {verdict!r}")
    conn.execute(
        "INSERT INTO fact_feedback(user_id, item_kind, item_key, verdict, source, created_at) "
        "VALUES (?,?,?,?,?,CURRENT_TIMESTAMP) "
        "ON CONFLICT(user_id, item_kind, item_key) DO UPDATE SET "
        "verdict=excluded.verdict, source=excluded.source, created_at=CURRENT_TIMESTAMP",
        (user_id, item_kind, str(item_key), verdict, source),
    )
    conn.commit()


def get_verdicts(conn, user_id, item_kind, keys):
    """Вердикты для батча ключей одного kind. Возврат: {item_key: verdict}, ключи
    без вердикта отсутствуют в словаре (не 'unknown'-заглушка)."""
    keys = [str(k) for k in keys]
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    rows = conn.execute(
        f"SELECT item_key, verdict FROM fact_feedback "
        f"WHERE user_id = ? AND item_kind = ? AND item_key IN ({placeholders})",
        (user_id, item_kind, *keys),
    ).fetchall()
    return {r[0]: r[1] for r in rows}
