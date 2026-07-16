# -*- coding: utf-8 -*-
"""test_dashboard_role_unknown.py — задача 0.4: role-UNKNOWN% master-gate (System tab)."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.db.repository import Repository


def _seed(tmp_path):
    data_dir = tmp_path / "data"
    db_dir = data_dir / "db"
    db_dir.mkdir(parents=True)
    repo = Repository(str(db_dir / "callprofiler.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir=str(tmp_path), sync_dir=str(tmp_path), ref_audio=str(tmp_path / "r.wav"))
    conn = repo._get_conn()
    cur = conn.execute(
        "INSERT INTO calls(user_id, direction, source_filename, source_md5, status) "
        "VALUES ('me', 'IN', 'f.mp3', 'md5z', 'done')"
    )
    call_id = cur.lastrowid
    for speaker in ("UNKNOWN", "UNKNOWN", "UNKNOWN", "OWNER"):
        conn.execute(
            "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) VALUES (?,0,100,'x',?)",
            (call_id, speaker),
        )
    conn.commit()
    repo.close()
    return data_dir


def test_get_role_unknown_share_reader(tmp_path):
    data_dir = _seed(tmp_path)
    reader = DashboardDBReader(str(data_dir))
    result = reader.get_role_unknown_share("me", days=30)
    assert result["share"] == 0.75
    assert result["n"] == 4
    reader.close()


def test_get_role_unknown_share_cached_within_ttl(tmp_path):
    import sqlite3

    data_dir = _seed(tmp_path)
    reader = DashboardDBReader(str(data_dir))
    first = reader.get_role_unknown_share("me", days=30)

    # Добавить ещё сегменты через ОТДЕЛЬНЫЙ writer-коннект (reader сам query_only=ON) —
    # без TTL-протухания повторный вызов должен вернуть КЭШ (старое значение).
    writer = sqlite3.connect(reader.db_path)
    writer.execute(
        "INSERT INTO calls(user_id, direction, source_filename, source_md5, status) "
        "VALUES ('me', 'IN', 'g.mp3', 'md5w', 'done')"
    )
    writer.commit()
    writer.close()

    second = reader.get_role_unknown_share("me", days=30)
    assert second == first  # кэш ещё жив (TTL 60s)
    reader.close()


def test_get_role_unknown_share_isolation(tmp_path):
    data_dir = _seed(tmp_path)
    reader = DashboardDBReader(str(data_dir))
    other = reader.get_role_unknown_share("someone_else", days=30)
    assert other["n"] == 0
    reader.close()


def test_api_system_includes_role_unknown_share(tmp_path):
    import callprofiler.dashboard.server as server_mod

    data_dir = _seed(tmp_path)
    saved_config, saved_user = server_mod._CONFIG, server_mod._USER_ID
    server_mod._CONFIG = SimpleNamespace(data_dir=str(data_dir))
    server_mod._USER_ID = "me"
    try:
        with TestClient(server_mod.app) as tc:
            resp = tc.get("/api/system")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role_unknown_share"]["share"] == 0.75
        assert data["role_unknown_share"]["n"] == 4
    finally:
        server_mod._CONFIG = saved_config
        server_mod._USER_ID = saved_user
