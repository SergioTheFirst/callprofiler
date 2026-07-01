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
