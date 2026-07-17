# -*- coding: utf-8 -*-
"""test_dashboard_dossier.py — Ф2 плана досье.

Слои:
  1. PsychologyProfiler.build_profile(include_llm=False) — без LLM и без записи
     (безопасно на query_only-коннекте дашборда).
  2. DashboardDBReader.get_person_dossier / get_people — агрегатор всех слоёв,
     каждая секция guarded (слоя нет → None/[], не 500).
  3. Эндпоинты /api/people и /api/person/{id} (mocked reader).
"""
import json
from unittest import mock

from fastapi.testclient import TestClient

from callprofiler.biography.psychology_profiler import PsychologyProfiler
from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.db.repository import Repository
from callprofiler.graph.repository import apply_graph_schema
from callprofiler.insight import repository as insight_repo
from callprofiler.insight.person_link import build_entity_contact_map


def _seed_db(tmp_path, with_entity=True, with_archetype=True):
    """Файловая БД: контакт + звонки + сводка (+ entity/метрики/факты/архетип)."""
    db = tmp_path / "dossier.db"
    repo = Repository(str(db))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )
    conn = repo._get_conn()
    apply_graph_schema(conn)
    insight_repo.apply_insight_schema(conn)

    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) "
        "VALUES ('me', '+79001112233', 'Дмитрий Бердников')"
    )
    cid = cur.lastrowid
    call_ids = []
    for i in range(4):
        cur = conn.execute(
            "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
            "source_filename, source_md5, status) VALUES ('me', ?, 'IN', ?, ?, ?, 'done')",
            (cid, f"2026-0{i + 1}-15T12:00:00", f"f{i}.mp3", f"md5{i}"),
        )
        call_ids.append(cur.lastrowid)
    conn.execute(
        "INSERT INTO contact_summaries(contact_id, user_id, total_calls, last_call_date, "
        "global_risk, avg_bs_score, open_promises, open_debts, personal_facts, advice) "
        "VALUES (?, 'me', 4, '2026-04-15', 62, 41, ?, '[]', '[]', 'осторожно')",
        (cid, json.dumps([{"what": "вернуть долг"}], ensure_ascii=False)),
    )

    eid = None
    if with_entity:
        cur = conn.execute(
            "INSERT INTO entities(user_id, entity_type, canonical_name, normalized_key, "
            "aliases, archived) VALUES ('me', 'PERSON', 'Дмитрий Бердников', "
            "'дмитрий бердников', '[]', 0)"
        )
        eid = cur.lastrowid
        # trust_score намеренно не сидируем: колонку добавляет только
        # biography-схема, на graph-only БД (бокс до биографии) её нет
        conn.execute(
            "INSERT INTO entity_metrics(entity_id, user_id, total_calls, total_promises, "
            "broken_promises, contradictions, vagueness_count, blame_shift_count, "
            "emotional_spikes, avg_risk, bs_index) "
            "VALUES (?, 'me', 4, 5, 3, 2, 1, 1, 1, 55.0, 64.0)",
            (eid,),
        )
        for i, call_id in enumerate(call_ids):
            conn.execute(
                "INSERT INTO events(user_id, contact_id, call_id, event_type, payload, "
                "entity_id, fact_id, quote, confidence) "
                "VALUES ('me', ?, ?, 'fact', 'обещал документы', ?, ?, ?, 0.9)",
                (cid, call_id, eid, f"fid{i}", f"«сделаю завтра» №{i}"),
            )
        build_entity_contact_map(conn, "me")  # name-match → link

    if with_archetype:
        insight_repo.save_contact_archetype(
            conn, "me", contact_id=cid, model_id=1, cluster_idx=0,
            label="ночной зависимый", membership=0.83,
            distinctive_dims=[{"dim": "night_ratio", "z": 2.1,
                               "phrase": "часто звонит ночью"}],
            confidence="medium", evidence=[], pca_x=0.5, pca_y=-1.2,
        )
    conn.commit()
    repo.close()
    return str(db), cid, eid


# ── 1. PsychologyProfiler include_llm=False ──────────────────────────────

def test_profiler_include_llm_false_no_llm_no_write(tmp_path):
    db, _cid, eid = _seed_db(tmp_path)
    repo = Repository(db)
    conn = repo._get_conn()
    with mock.patch("requests.post") as mp:
        prof = PsychologyProfiler(conn).build_profile(eid, "me", include_llm=False)
    mp.assert_not_called()
    assert prof and prof["interpretation"] is None
    assert prof["metrics"]["bs_index"] == 64.0
    assert prof["metrics"].get("trust_score") is None
    n = conn.execute(
        "SELECT COUNT(*) FROM entity_profiles WHERE user_id = 'me'"
    ).fetchone()[0]
    assert n == 0  # без LLM профиль НЕ сохраняется (read-only путь дашборда)
    repo.close()


# ── 2. get_person_dossier / get_people ───────────────────────────────────

def _reader(db):
    r = DashboardDBReader(db)
    r.connect()
    return r


def test_dossier_full(tmp_path):
    db, cid, eid = _seed_db(tmp_path)
    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()

    assert d["contact"]["display_name"] == "Дмитрий Бердников"
    assert d["indices"]["global_risk"] == 62
    assert d["indices"]["avg_bs_score"] == 41
    assert d["indices"]["bs_index"] == 64.0          # entity-слой через map
    assert d["indices"]["trust_score"] is None       # колонка только у biography-схемы
    assert d["indices"]["avg_risk"] == 55.0
    assert d["entity"]["entity_id"] == eid
    assert d["entity"]["link_method"] == "name"
    assert d["archetype"]["label"] == "ночной зависимый"
    assert d["archetype"]["traits"] == ["часто звонит ночью"]
    assert isinstance(d["patterns"], list)
    assert d["temporal"]["avg_calls_per_week"] > 0
    assert len(d["facts"]) == 4 and all(f["quote"] for f in d["facts"])
    assert d["promises"]["open"][0]["what"] == "вернуть долг"
    assert d["advice"] == "осторожно"
    assert d["interpretation"] is None  # LLM не зван и не сохранён
    assert d["recent_calls"]
    # A7: Admiralty-грейд + 5-слойная группировка + напряжения (пусто без bio-схемы).
    assert d["admiralty"] == "F2 — данных мало, информация вероятно верна"
    assert set(d["layers"]) == {"behavioral", "speech", "relational", "dynamic", "practical"}
    assert d["tensions"] == []
    assert "pivotal_scenes" not in d  # biography-схема не сидировалась в этом фикстуре


def test_dossier_pivotal_scenes_via_bio_scene_entities_junction(tmp_path):
    """A7 regress: bio_scenes has NO entity_id column and bio_portraits.pivotal_scenes
    holds LLM-time positional indices (unreliable, id-space precedent bugs.md
    2026-07-02) — real resolution is the bio_scene_entities junction, top-importance
    first, capped at _MAX_PIVOTAL_SCENES."""
    from callprofiler.biography.schema import apply_biography_schema
    from callprofiler.dashboard.db_reader import _MAX_PIVOTAL_SCENES

    db, cid, eid = _seed_db(tmp_path)
    repo = Repository(db)
    conn = repo._get_conn()
    apply_biography_schema(conn)
    conn.execute(
        "INSERT INTO bio_entities(entity_id, user_id, canonical_name, entity_type) "
        "VALUES (?, 'me', 'Дмитрий Бердников', 'person')", (eid,))
    call_ids = [r[0] for r in conn.execute(
        "SELECT call_id FROM calls WHERE contact_id = ? ORDER BY call_id", (cid,)
    ).fetchall()]
    assert len(call_ids) >= 4
    importances = [10, 90, 50, 70]
    for call_id, importance in zip(call_ids, importances):
        cur = conn.execute(
            "INSERT INTO bio_scenes(user_id, call_id, importance, synopsis) "
            "VALUES ('me', ?, ?, ?)",
            (call_id, importance, f"синопсис звонка {call_id}" + "x" * 310),
        )
        conn.execute(
            "INSERT INTO bio_scene_entities(scene_id, entity_id) VALUES (?, ?)",
            (cur.lastrowid, eid),
        )
    conn.commit()
    repo.close()

    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()

    scenes = d["pivotal_scenes"]
    assert len(scenes) <= _MAX_PIVOTAL_SCENES
    # top-importance first (90, 70, 50, 10, ...) — не порядок вставки/call_id
    assert [s["call_id"] for s in scenes] == [
        cid_ for _, cid_ in sorted(zip(importances, call_ids), reverse=True)
    ]
    assert all(len(s["synopsis"]) <= 300 for s in scenes)


def test_dossier_promise_verdicts_hide_rejected_mark_confirmed(tmp_path):
    """F1: get_person_dossier промисы несут id (events.id, summary_builder.py) —
    rejected скрыт, confirmed помечен, item_kind='event' (JSON-блок contact_summaries,
    не live promises-таблица — get_character_profile ниже покрывает второй путь)."""
    db, cid, _eid = _seed_db(tmp_path, with_entity=False, with_archetype=False)
    repo = Repository(db)
    conn = repo._get_conn()
    conn.execute(
        "UPDATE contact_summaries SET open_promises = ? WHERE contact_id = ? AND user_id = 'me'",
        (json.dumps([
            {"id": 101, "who": "OWNER", "what": "вернуть долг", "deadline": "2020-01-05"},
            {"id": 102, "who": "OTHER", "what": "прислать документы", "deadline": "2020-02-01"},
        ], ensure_ascii=False), cid),
    )
    from callprofiler.insight.repository import set_fact_verdict
    set_fact_verdict(conn, "me", item_kind="event", item_key="101", verdict="rejected")
    set_fact_verdict(conn, "me", item_kind="event", item_key="102", verdict="confirmed")
    conn.commit()
    repo.close()

    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()

    opens = d["promises"]["open"]
    assert len(opens) == 1
    assert opens[0]["id"] == 102
    assert opens[0]["confirmed"] is True
    assert opens[0]["item_kind"] == "event"


def test_character_profile_promise_verdicts(tmp_path):
    """F1: get_character_profile (граф-модалка, промисы из live `promises` table,
    item_kind='promise' — отдельное id-пространство от event/dossier-путь выше)."""
    db, cid, eid = _seed_db(tmp_path)
    repo = Repository(db)
    conn = repo._get_conn()
    call_id = conn.execute(
        "SELECT call_id FROM calls WHERE contact_id = ? LIMIT 1", (cid,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO promises(user_id, contact_id, call_id, who, what, due, status) "
        "VALUES ('me', ?, ?, 'OTHER', 'привезти документы', '2020-03-01', 'open')",
        (cid, call_id),
    )
    promise_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    from callprofiler.insight.repository import set_fact_verdict
    set_fact_verdict(conn, "me", item_kind="promise", item_key=str(promise_id), verdict="confirmed")
    conn.commit()
    repo.close()

    r = _reader(db)
    cp = r.get_character_profile(eid, "me")
    r.close()

    assert len(cp["open_promises"]) == 1
    assert cp["open_promises"][0]["confirmed"] is True
    assert cp["open_promises"][0]["item_kind"] == "promise"


def test_dossier_readonly_conn_not_written(tmp_path):
    """Построение досье на query_only-коннекте не пишет кэш профайлера."""
    db, cid, _eid = _seed_db(tmp_path)
    r = _reader(db)
    r.get_person_dossier(cid, "me")
    n = r._conn.execute(
        "SELECT COUNT(*) FROM entity_profiles WHERE user_id = 'me'"
    ).fetchone()[0]
    r.close()
    assert n == 0


def test_dossier_no_entity_link(tmp_path):
    db, cid, _ = _seed_db(tmp_path, with_entity=False, with_archetype=False)
    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()
    assert d is not None
    assert d["entity"] is None
    assert d["archetype"] is None
    assert d["age"] is None  # таблица есть (insight-схема), строки нет
    assert d["indices"]["bs_index"] is None
    assert d["patterns"] == [] and d["facts"] == []
    assert d["indices"]["global_risk"] == 62  # contact-слой живёт без entity


def _seed_age(db, cid):
    from datetime import date
    from callprofiler.db.repository import Repository as _R
    repo = _R(db)
    conn = repo._get_conn()
    insight_repo.save_contact_age_estimate(
        conn, "me", contact_id=cid, age_low=49, age_high=51, age_point=50,
        birth_year_low=1975, birth_year_high=1976, birth_year_point=1976,
        confidence=80, method="marker",
        evidence=[{"quote": "мне 45 лет", "signal": "direct_age",
                   "weight": 90, "dt": "2021-03-15"}],
    )
    conn.commit()
    repo.close()
    return date.today().year


def test_dossier_age_section(tmp_path):
    """Возраст в досье — динамический: из birth_year_point к текущему году."""
    db, cid, _eid = _seed_db(tmp_path)
    yr = _seed_age(db, cid)
    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()
    a = d["age"]
    assert a is not None
    assert a["age_point"] == yr - 1976
    assert a["age_low"] == yr - 1976 and a["age_high"] == yr - 1975
    assert a["confidence"] == 80 and a["method"] == "marker"
    assert a["evidence"][0]["quote"] == "мне 45 лет"


def test_people_age_column(tmp_path):
    db, cid, _eid = _seed_db(tmp_path)
    yr = _seed_age(db, cid)
    r = _reader(db)
    people = r.get_people("me")
    r.close()
    p = people[0]
    assert p["age_point"] == yr - 1976  # из birth_year, не из среза age_point
    assert p["age_confidence"] == 80


def test_dossier_feedback_badge_data(tmp_path):
    """A5/F0.2: feedback='inaccurate' на analyses контакта -> счётчик в досье."""
    db, cid, _eid = _seed_db(tmp_path, with_entity=False, with_archetype=False)
    repo = Repository(db)
    conn = repo._get_conn()
    call_id = conn.execute(
        "SELECT call_id FROM calls WHERE contact_id = ? LIMIT 1", (cid,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO analyses(call_id, prompt_version, feedback) VALUES (?, 'v1', 'inaccurate')",
        (call_id,),
    )
    conn.commit()
    repo.close()

    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()
    assert d["feedback"]["wrong_n"] == 1
    assert d["feedback"]["ok_n"] == 0
    assert d["feedback"]["last_wrong"]


def test_dossier_wrong_user(tmp_path):
    db, cid, _ = _seed_db(tmp_path)
    r = _reader(db)
    assert r.get_person_dossier(cid, "other") is None
    r.close()


def test_people_list(tmp_path):
    db, cid, eid = _seed_db(tmp_path)
    r = _reader(db)
    people = r.get_people("me")
    r.close()
    assert len(people) == 1
    p = people[0]
    assert p["contact_id"] == cid
    assert p["name"] == "Дмитрий Бердников"
    assert p["archetype_label"] == "ночной зависимый"
    assert p["bs_index"] == 64.0
    assert p["trust_score"] is None  # NULL AS trust_score без biography-колонки
    assert p["global_risk"] == 62
    assert p["total_calls"] == 4
    assert p["entity_id"] == eid


def test_people_empty_db_without_optional_layers(tmp_path):
    """Свежая БД без graph/insight таблиц: guarded, пусто, не 500."""
    db = tmp_path / "fresh.db"
    repo = Repository(str(db))
    repo.init_db()
    repo.close()
    r = _reader(str(db))
    assert r.get_people("me") == []
    r.close()


def test_entity_layer_graph_only_db_no_bio_tables(tmp_path):
    """Regress: entity-слой дашборда на graph-only БД (без bio_* и без
    колонки trust_score в entity_metrics) НЕ должен падать 500.

    Ловит 4 бага: get_stats/get_entity_profile (bio_portraits),
    get_all_characters (trust_score колонка + bio_portraits через
    _has_portrait), get_character_profile (trust_score/volatility/
    conflict_count колонки + bio_behavior_patterns + bio_contradictions).
    """
    db, _cid, eid = _seed_db(tmp_path)  # graph-схема есть, biography НЕТ
    r = _reader(db)
    assert not r._has_table("bio_portraits")          # предпосылка
    assert not r._has_column("entity_metrics", "trust_score")

    stats = r.get_stats("me")
    assert stats["total_portraits"] == 0              # bio нет → 0, не 500

    chars = r.get_all_characters("me")
    assert any(c["entity_id"] == eid for c in chars)
    assert all(c["has_portrait"] is False for c in chars)

    prof = r.get_entity_profile(eid, "me")
    assert prof and "prose" not in prof               # портрета нет, без падения

    cp = r.get_character_profile(eid, "me")
    assert cp is not None
    # patterns из PsychologyProfiler._extract_patterns (graph-only данные, не bio_*) —
    # НИКОГДА не пусто (fallback "neutral"), но severity — валидный enum, не сырое число
    # (регресс 2026-07-02: bio_behavior_patterns не имеет колонок name/severity/ratio/label).
    assert cp["patterns"]
    assert all(p.get("severity") in ("positive", "low", "medium", "high") for p in cp["patterns"])
    assert cp["contradictions"] == []
    assert cp["character_summary"]                    # построен из avg_risk/bs_index
    r.close()


def test_character_patterns_ignore_colliding_bio_behavior_patterns_row(tmp_path):
    """Regress (2026-07-02, реальный краш на боксе): bio_behavior_patterns.entity_id
    ссылается на bio_entities — ДРУГОЕ id-пространство, чем graph entities.id
    (dashboard.md «Id-пространства»). Старый запрос `SELECT name, severity, ratio,
    label FROM bio_behavior_patterns WHERE entity_id=?` падал (таких колонок нет);
    даже алиасом колонок он читал бы строку из ЧУЖОГО id-пространства при случайном
    численном совпадении id. Фикс: patterns берутся из PsychologyProfiler (graph-
    native, тот же источник, что и досье) — bio_behavior_patterns не участвует."""
    from callprofiler.biography.schema import apply_biography_schema

    db, _cid, eid = _seed_db(tmp_path)
    repo = Repository(db)
    conn = repo._get_conn()
    apply_biography_schema(conn)
    conn.execute(
        "INSERT INTO bio_entities(entity_id, user_id, canonical_name, entity_type) "
        "VALUES (?, 'me', 'Дмитрий Бердников', 'person')", (eid,))
    conn.execute(
        "INSERT INTO bio_behavior_patterns(entity_id, user_id, trust_score, volatility, "
        "dependency, role_type, call_count, conflict_count) "
        "VALUES (?, 'me', 12.0, 99.0, 0.9, 'mixed', 4, 9)", (eid,))
    conn.commit()
    repo.close()

    r = _reader(db)
    cp = r.get_character_profile(eid, "me")  # не должен упасть на "no such column"
    r.close()

    assert cp is not None
    assert cp["patterns"]
    assert all(p.get("severity") in ("positive", "low", "medium", "high") for p in cp["patterns"])
    # значения из bio_behavior_patterns не просочились как паттерн (чужое id-пространство)
    assert not any(p.get("name") == "mixed" for p in cp["patterns"])


# ── 3. Эндпоинты ─────────────────────────────────────────────────────────

def test_endpoints_people_and_person():
    import callprofiler.dashboard.server as server_mod
    from unittest.mock import MagicMock

    saved_r, saved_u = server_mod._DB_READER, server_mod._USER_ID
    server_mod._DB_READER = MagicMock()
    server_mod._USER_ID = "me"
    try:
        server_mod._DB_READER.get_people.return_value = [{"contact_id": 1, "name": "А"}]
        server_mod._DB_READER.get_person_dossier.return_value = {
            "contact": {"contact_id": 1}}
        with TestClient(server_mod.app) as tc:
            assert tc.get("/api/people").json()["people"][0]["name"] == "А"
            assert tc.get("/api/person/1").json()["contact"]["contact_id"] == 1
            server_mod._DB_READER.get_person_dossier.return_value = None
            assert tc.get("/api/person/999").json()["not_found"] is True
    finally:
        server_mod._DB_READER = saved_r
        server_mod._USER_ID = saved_u


# ── M6: owner note ────────────────────────────────────────────────────────

def test_dossier_owner_note_absent_by_default(tmp_path):
    db, cid, eid = _seed_db(tmp_path)
    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()

    assert d["owner_note"] is None


def test_dossier_owner_note_present_when_seeded(tmp_path):
    db, cid, eid = _seed_db(tmp_path)
    repo = Repository(db)
    conn = repo._get_conn()
    conn.execute(
        "INSERT INTO contact_notes(contact_id, user_id, note) VALUES (?, 'me', ?)",
        (cid, "любит звонить по вечерам"),
    )
    conn.commit()
    repo.close()

    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()

    assert d["owner_note"]["note"] == "любит звонить по вечерам"
    assert d["owner_note"]["updated_at"]
