"""Phase 7 — Insight Engine dashboard visualizations.

Two layers:
  1. DashboardDBReader read methods, exercised offline against a schema-accurate
     SyntheticCorpus (numpy-only, no GPU/real DB) with archetypes actually fit.
  2. FastAPI endpoints, exercised with a mocked reader (shape + uninitialized).
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight import cli_ops
from callprofiler.dashboard.db_reader import DashboardDBReader


# ── Reader layer (offline, real archetype fit) ──────────────────────────────

def _build_db(tmp_path, fit=True):
    """Schema-accurate file DB with features built and (optionally) archetypes fit."""
    db = tmp_path / "insight.db"
    conn = SyntheticCorpus(seed=0).build(path=str(db), n_per=10)
    cli_ops.run_features_build(conn, "me")
    if fit:
        cli_ops.run_archetypes_fit(conn, "me")
    conn.commit()
    conn.close()
    return db


class TestInsightReader:
    def test_pca_returns_points_and_centroids(self, tmp_path):
        reader = DashboardDBReader(str(_build_db(tmp_path)))
        out = reader.get_insight_pca("me")
        reader.close()
        assert out["points"], "expected projected points after fit"
        assert all("x" in p and "y" in p and "cluster" in p for p in out["points"])
        assert out["k"] >= 2 and out["silhouette"] is not None
        assert out["clusters"] and all("cx" in c and "cy" in c for c in out["clusters"])

    def test_pca_is_user_scoped(self, tmp_path):
        reader = DashboardDBReader(str(_build_db(tmp_path)))
        out = reader.get_insight_pca("other")
        reader.close()
        assert out["points"] == []  # no cross-user leakage

    def test_network_star_from_call_volume(self, tmp_path):
        reader = DashboardDBReader(str(_build_db(tmp_path)))
        out = reader.get_insight_network("me", limit=15)
        reader.close()
        assert out["owner_label"]
        assert 0 < len(out["nodes"]) <= 15
        n = out["nodes"][0]
        assert "contact_id" in n and "calls" in n and "cluster" in n
        # ordered by call volume desc
        calls = [x["calls"] for x in out["nodes"]]
        assert calls == sorted(calls, reverse=True)

    def test_circadian_matrix_bounds(self, tmp_path):
        reader = DashboardDBReader(str(_build_db(tmp_path)))
        out = reader.get_insight_circadian("me")
        reader.close()
        assert out["max"] > 0 and out["cells"]
        for hr, wd, cnt in out["cells"]:
            assert 0 <= hr <= 23 and 0 <= wd <= 6 and cnt >= 1
        assert out["days"] == ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    def test_ecg_monthly_series_global_and_per_contact(self, tmp_path):
        reader = DashboardDBReader(str(_build_db(tmp_path)))
        all_series = reader.get_insight_ecg("me")
        cid = reader._conn.execute(
            "SELECT contact_id FROM contacts WHERE user_id='me' LIMIT 1"
        ).fetchone()[0]
        one = reader.get_insight_ecg("me", contact_id=cid)
        reader.close()
        assert all_series["series"]
        assert all("period" in s and "calls" in s for s in all_series["series"])
        assert one["contact_id"] == cid
        # a single contact cannot have more calls than the whole user
        assert sum(s["calls"] for s in one["series"]) <= sum(s["calls"] for s in all_series["series"])

    def test_reads_degrade_when_not_fit(self, tmp_path):
        """Archetype tables exist but empty → PCA empty, network still works."""
        reader = DashboardDBReader(str(_build_db(tmp_path, fit=False)))
        pca = reader.get_insight_pca("me")
        net = reader.get_insight_network("me")
        reader.close()
        assert pca["points"] == [] and pca["clusters"] == [] and pca["k"] == 0
        assert net["nodes"]  # derived from call metadata, independent of fit

    def test_reads_guard_missing_archetype_tables(self, tmp_path):
        """contact_archetypes table absent entirely → guarded, never raises."""
        db = tmp_path / "raw.db"
        conn = sqlite3.connect(str(db))
        conn.executescript(
            "CREATE TABLE users(user_id TEXT PRIMARY KEY);"
            "CREATE TABLE contacts(contact_id INTEGER PRIMARY KEY, user_id TEXT,"
            " display_name TEXT, guessed_name TEXT, phone_e164 TEXT);"
            "CREATE TABLE calls(call_id INTEGER PRIMARY KEY, user_id TEXT, contact_id INTEGER,"
            " direction TEXT, call_datetime TEXT, duration_sec INTEGER, created_at TEXT);"
            "CREATE TABLE analyses(analysis_id INTEGER PRIMARY KEY, call_id INTEGER, risk_score REAL);"
        )
        conn.execute("INSERT INTO contacts VALUES (1,'me','X',NULL,'+7')")
        conn.execute("INSERT INTO calls VALUES (1,'me',1,'IN','2026-05-04 10:30:00',60,'2026-05-04 10:30:00')")
        conn.execute("INSERT INTO analyses VALUES (1,1,42.0)")
        conn.commit()
        conn.close()

        reader = DashboardDBReader(str(db))
        pca = reader.get_insight_pca("me")        # no contact_archetypes → guarded empty
        net = reader.get_insight_network("me")    # _archetype_map guarded → cluster None
        circ = reader.get_insight_circadian("me")
        ecg = reader.get_insight_ecg("me")
        reader.close()
        assert pca["points"] == [] and pca["k"] == 0
        assert net["nodes"] and net["nodes"][0]["cluster"] is None
        assert circ["cells"][0] == [10, 0, 1]  # 2026-05-04 = Monday, hour 10
        assert ecg["series"][0]["period"] == "2026-05"


# ── Endpoint layer (mocked reader) ──────────────────────────────────────────

@pytest.fixture
def client():
    import callprofiler.dashboard.server as server_mod
    from unittest.mock import MagicMock

    saved_reader = server_mod._DB_READER
    saved_user = server_mod._USER_ID
    server_mod._DB_READER = MagicMock()
    server_mod._USER_ID = "me"
    with TestClient(server_mod.app) as tc:
        yield tc, server_mod
    server_mod._DB_READER = saved_reader
    server_mod._USER_ID = saved_user


class TestInsightEndpoints:
    def test_pca_endpoint(self, client):
        tc, server_mod = client
        server_mod._DB_READER.get_insight_pca.return_value = {
            "points": [{"x": 1.0, "y": 2.0, "cluster": 0, "name": "A"}],
            "clusters": [{"idx": 0, "label": "L", "cx": 0.0, "cy": 0.0, "size": 1}],
            "k": 1, "silhouette": 0.5, "version": "arch-v1",
        }
        resp = tc.get("/api/insight/pca")
        assert resp.status_code == 200
        assert resp.json()["k"] == 1 and resp.json()["points"]

    def test_network_endpoint(self, client):
        tc, server_mod = client
        server_mod._DB_READER.get_insight_network.return_value = {
            "owner_label": "Ты",
            "nodes": [{"contact_id": 1, "name": "A", "calls": 5, "risk": 30, "cluster": 0, "label": "L"}],
        }
        resp = tc.get("/api/insight/network?limit=10")
        assert resp.status_code == 200
        assert resp.json()["nodes"][0]["contact_id"] == 1

    def test_circadian_endpoint(self, client):
        tc, server_mod = client
        server_mod._DB_READER.get_insight_circadian.return_value = {
            "cells": [[10, 0, 3]], "max": 3, "days": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]}
        resp = tc.get("/api/insight/circadian")
        assert resp.status_code == 200
        assert resp.json()["max"] == 3

    def test_ecg_endpoint_passes_contact_filter(self, client):
        tc, server_mod = client
        server_mod._DB_READER.get_insight_ecg.return_value = {
            "series": [{"period": "2026-05", "calls": 4, "risk": 33.0}], "contact_id": 7}
        resp = tc.get("/api/insight/ecg?contact_id=7")
        assert resp.status_code == 200
        assert resp.json()["series"][0]["period"] == "2026-05"
        server_mod._DB_READER.get_insight_ecg.assert_called_with("me", 7)

    def test_contacts_picker_endpoint(self, client):
        tc, server_mod = client
        server_mod._DB_READER.get_contacts.return_value = [
            {"contact_id": 1, "display_name": "A", "call_count": 9}]
        resp = tc.get("/api/insight/contacts")
        assert resp.status_code == 200
        assert resp.json()["contacts"][0]["contact_id"] == 1


class TestInsightEndpointsUninitialized:
    def test_pca_empty_without_reader(self, client):
        tc, server_mod = client
        saved = server_mod._DB_READER
        server_mod._DB_READER = None
        try:
            resp = tc.get("/api/insight/pca")
            assert resp.status_code == 200
            assert resp.json()["points"] == [] and resp.json()["k"] == 0
        finally:
            server_mod._DB_READER = saved

    def test_network_empty_without_reader(self, client):
        tc, server_mod = client
        saved = server_mod._DB_READER
        server_mod._DB_READER = None
        try:
            resp = tc.get("/api/insight/network")
            assert resp.status_code == 200
            assert resp.json()["nodes"] == []
        finally:
            server_mod._DB_READER = saved
