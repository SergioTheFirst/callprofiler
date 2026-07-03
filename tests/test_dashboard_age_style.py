# -*- coding: utf-8 -*-
"""test_dashboard_age_style.py — Ф5.5 плана age.md: dossier read + action endpoint."""
from datetime import date
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.db.repository import Repository
from callprofiler.insight import repository as insight_repo


def _seed_contact(tmp_path, apply_insight=True):
    db = tmp_path / "age_style.db"
    repo = Repository(str(db))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )
    conn = repo._get_conn()
    if apply_insight:
        insight_repo.apply_insight_schema(conn)
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) "
        "VALUES ('me', '+79001112233', 'Игорь')"
    )
    cid = cur.lastrowid
    conn.commit()
    repo.close()
    return str(db), cid


def _reader(db):
    r = DashboardDBReader(db)
    r.connect()
    return r


def test_dossier_age_style_guarded_no_table(tmp_path):
    """Свежая БД без insight-схемы: age_style=None, не 500 (bugs.md-класс)."""
    db, cid = _seed_contact(tmp_path, apply_insight=False)
    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()
    assert d is not None
    assert d["age_style"] is None


def test_dossier_reads_style_row(tmp_path):
    db, cid = _seed_contact(tmp_path)
    repo = Repository(db)
    conn = repo._get_conn()
    insight_repo.save_contact_age_style(
        conn, "me", contact_id=cid, group_code="G4",
        group_dist={"G1": 0.0, "G2": 0.03, "G3": 0.19, "G4": 0.46, "G5": 0.24, "G6": 0.08},
        birth_low=1975, birth_high=1985, birth_point=1980,
        confidence=62, confidence_level=3, n_conversations=47, total_tokens=3000,
        top=[["life_stage", 0.31], ["ch6", 0.18]], warnings=[],
        table_version="age-style-v1+age-rules-v1",
    )
    conn.commit()
    repo.close()

    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()

    yr = date.today().year
    st = d["age_style"]
    assert st is not None
    assert st["group_code"] == "G4"
    assert st["birth_year_point"] == 1980
    assert st["age_point"] == yr - 1980
    assert st["confidence"] == 62 and st["confidence_level"] == 3
    assert st["n_conversations"] == 47
    assert st["top_features"][0] == ["life_stage", 0.31]
    assert st["group_distribution"]["G4"] == 0.46


def test_people_age_falls_back_to_style_when_no_marker(tmp_path):
    """get_people: без явного маркера/LLM возраст берётся из age_style (для
    этого он и строился — покрывает контакты БЕЗ явного упоминания возраста)."""
    db, cid = _seed_contact(tmp_path)
    repo = Repository(db)
    conn = repo._get_conn()
    insight_repo.save_contact_age_style(
        conn, "me", contact_id=cid, group_code="G4",
        group_dist={"G1": 0.0, "G2": 0.03, "G3": 0.19, "G4": 0.46, "G5": 0.24, "G6": 0.08},
        birth_low=1975, birth_high=1985, birth_point=1980,
        confidence=55, confidence_level=3, n_conversations=10, total_tokens=800,
        top=[], warnings=[], table_version="age-style-v1+age-rules-v1",
    )
    conn.commit()
    repo.close()

    r = _reader(db)
    people = r.get_people("me")
    r.close()

    yr = date.today().year
    p = people[0]
    assert p["age_point"] == yr - 1980
    assert p["age_confidence"] == 55
    assert p["age_source"] == "style"


def test_people_age_prefers_marker_over_style(tmp_path):
    """Явный маркер (contact_age_estimates) СИЛЬНЕЕ стиля — побеждает в списке,
    даже если стиль посчитан на другой год рождения."""
    db, cid = _seed_contact(tmp_path)
    repo = Repository(db)
    conn = repo._get_conn()
    insight_repo.save_contact_age_estimate(
        conn, "me", contact_id=cid, age_low=49, age_high=51, age_point=50,
        birth_year_low=1975, birth_year_high=1976, birth_year_point=1976,
        confidence=80, method="marker", evidence=[],
    )
    insight_repo.save_contact_age_style(
        conn, "me", contact_id=cid, group_code="G2",
        group_dist={"G1": 0.0, "G2": 0.7, "G3": 0.2, "G4": 0.1, "G5": 0.0, "G6": 0.0},
        birth_low=1998, birth_high=2002, birth_point=2000,
        confidence=40, confidence_level=2, n_conversations=5, total_tokens=300,
        top=[], warnings=["расходится с явным маркером"], table_version="age-style-v1+age-rules-v1",
    )
    conn.commit()
    repo.close()

    r = _reader(db)
    people = r.get_people("me")
    r.close()

    yr = date.today().year
    p = people[0]
    assert p["age_point"] == yr - 1976  # маркер, не стиль (2000)
    # C2: fusion возвращает маркер но с конфликтом (интервалы не пересекаются),
    # поэтому confidence = marker_conf - 10 = 80 - 10 = 70
    assert p["age_confidence"] == 70
    assert p["age_source"] == "marker"


def test_age_recompute_endpoint_writes_and_returns():
    import callprofiler.dashboard.server as server_mod

    saved_t, saved_u = server_mod._TOOLS, server_mod._USER_ID
    server_mod._TOOLS = MagicMock()
    server_mod._USER_ID = "me"
    try:
        server_mod._TOOLS.run_age_recompute.return_value = {
            "status": "ok", "stats": {"estimated": 1}, "age_style": {"group_code": "G4"}}
        with TestClient(server_mod.app) as tc:
            resp = tc.post("/api/tools/age-recompute?contact_id=5")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["age_style"]["group_code"] == "G4"
        server_mod._TOOLS.run_age_recompute.assert_called_once_with(5)
    finally:
        server_mod._TOOLS = saved_t
        server_mod._USER_ID = saved_u


# C4 тесты — fusion + dashboard
def test_dossier_age_fused_present(tmp_path):
    """Если есть маркер и стиль — age_fused присутствует в dosiers."""
    db, cid = _seed_contact(tmp_path)
    repo = Repository(str(db))
    conn = repo._get_conn()

    # Добавить маркер
    conn.execute(
        "INSERT INTO contact_age_estimates(user_id, contact_id, age_point, "
        "birth_year_point, birth_year_low, birth_year_high, confidence, method) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("me", cid, 50, 1976, 1975, 1978, 80, "marker"),
    )
    # Добавить стиль
    conn.execute(
        "INSERT INTO contact_age_style(user_id, contact_id, group_code, "
        "birth_year_point, birth_year_low, birth_year_high, confidence, confidence_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("me", cid, "G4", 1975, 1970, 1980, 60, 2),
    )
    conn.commit()
    repo.close()

    r = _reader(db)
    d = r.get_person_dossier(cid, "me")
    r.close()

    assert d is not None
    assert d["age_fused"] is not None
    assert d["age_fused"]["source"] == "marker+style"  # пересечение


def test_people_age_from_fusion(tmp_path):
    """Список people использует fusion для age_point и age_source."""
    db, cid = _seed_contact(tmp_path)
    repo = Repository(str(db))
    conn = repo._get_conn()
    conn.execute(
        "INSERT INTO contact_age_estimates(user_id, contact_id, age_point, "
        "birth_year_point, birth_year_low, birth_year_high, confidence, method) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("me", cid, 45, 1980, 1979, 1981, 85, "marker"),
    )
    conn.commit()
    repo.close()

    r = _reader(db)
    people = r.get_people("me")
    r.close()

    p = people[0]
    assert p["age_source"] == "marker"  # fusion вернул маркер как source


def test_recompute_returns_fused(tmp_path):
    """Эндпоинт age-recompute возвращает age_fused в ответе."""
    import callprofiler.dashboard.server as server_mod

    saved_t, saved_u = server_mod._TOOLS, server_mod._USER_ID
    server_mod._TOOLS = MagicMock()
    server_mod._USER_ID = "me"
    try:
        server_mod._TOOLS.run_age_recompute.return_value = {
            "status": "ok", "stats": {"estimated": 1},
            "age_fused": {"age_point": 50, "source": "marker", "confidence": 80},
            "age": {"age_point": 50, "confidence": 80},
        }
        with TestClient(server_mod.app) as tc:
            resp = tc.post("/api/tools/age-recompute?contact_id=5")
            assert resp.status_code == 200
            body = resp.json()
            assert "age_fused" in body
            assert body["age_fused"]["source"] == "marker"
    finally:
        server_mod._TOOLS = saved_t
        server_mod._USER_ID = saved_u


def test_recompute_hint_diarization(tmp_path):
    """Если контакт не имеет OTHER-реплик — возвращается hint_diarization."""
    import callprofiler.dashboard.server as server_mod

    saved_t, saved_u = server_mod._TOOLS, server_mod._USER_ID
    server_mod._TOOLS = MagicMock()
    server_mod._USER_ID = "me"
    try:
        server_mod._TOOLS.run_age_recompute.return_value = {
            "status": "ok",
            "hint_diarization": "реплики контакта не размечены (UNKNOWN) — стилометрия невозможна",
        }
        with TestClient(server_mod.app) as tc:
            resp = tc.post("/api/tools/age-recompute?contact_id=5")
            assert resp.status_code == 200
            body = resp.json()
            assert "hint_diarization" in body
    finally:
        server_mod._TOOLS = saved_t
        server_mod._USER_ID = saved_u


def test_age_recompute_runs_marker_pass(tmp_path):
    """Кнопка запускает маркер-пасс (Ф6.1)."""
    import callprofiler.dashboard.server as server_mod

    saved_t, saved_u = server_mod._TOOLS, server_mod._USER_ID
    server_mod._TOOLS = MagicMock()
    server_mod._USER_ID = "me"
    try:
        server_mod._TOOLS.run_age_recompute.return_value = {
            "status": "ok", "marker_stats": {"estimated": 1},
            "stats": {"estimated": 1},
        }
        with TestClient(server_mod.app) as tc:
            resp = tc.post("/api/tools/age-recompute?contact_id=5")
            assert resp.status_code == 200
            body = resp.json()
            assert "marker_stats" in body
    finally:
        server_mod._TOOLS = saved_t
        server_mod._USER_ID = saved_u


def test_age_recompute_hint_when_no_owner_birth_year(tmp_path):
    """Диагностика: hint при owner_birth_year==0 (Ф6.4)."""
    import callprofiler.dashboard.server as server_mod

    saved_t, saved_u = server_mod._TOOLS, server_mod._USER_ID
    server_mod._TOOLS = MagicMock()
    server_mod._USER_ID = "me"
    try:
        server_mod._TOOLS.run_age_recompute.return_value = {
            "status": "ok",
            "hint": "owner_birth_year не задан в base.yaml — реляционные якоря выключены",
        }
        with TestClient(server_mod.app) as tc:
            resp = tc.post("/api/tools/age-recompute?contact_id=5")
            assert resp.status_code == 200
            body = resp.json()
            assert "hint" in body
    finally:
        server_mod._TOOLS = saved_t
        server_mod._USER_ID = saved_u
