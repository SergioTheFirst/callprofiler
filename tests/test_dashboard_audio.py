# -*- coding: utf-8 -*-
"""test_dashboard_audio.py — M2: call audio playback + transcript seek."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.db.repository import Repository


def _seed(tmp_path, audio_rel="audio.mp3", audio_dir=None):
    """Настроить data_dir/db/callprofiler.db + один звонок с audio_path."""
    data_dir = tmp_path / "data"
    db_dir = data_dir / "db"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "callprofiler.db"

    repo = Repository(str(db_path))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir=str(tmp_path), sync_dir=str(tmp_path), ref_audio=str(tmp_path / "r.wav"))
    conn = repo._get_conn()

    audio_root = audio_dir if audio_dir is not None else data_dir
    audio_root.mkdir(parents=True, exist_ok=True)
    audio_path = audio_root / audio_rel
    audio_path.write_bytes(b"ID3fake")

    cur = conn.execute(
        "INSERT INTO calls(user_id, direction, source_filename, source_md5, status, audio_path) "
        "VALUES ('me', 'IN', 'f.mp3', 'md5x', 'done', ?)",
        (str(audio_path),),
    )
    call_id = cur.lastrowid
    conn.commit()
    repo.close()
    return data_dir, call_id, audio_path


@pytest.fixture
def client_with_config(tmp_path):
    import callprofiler.dashboard.server as server_mod

    data_dir, call_id, audio_path = _seed(tmp_path)
    saved_config, saved_user = server_mod._CONFIG, server_mod._USER_ID
    server_mod._CONFIG = SimpleNamespace(data_dir=str(data_dir))
    server_mod._USER_ID = "me"
    try:
        with TestClient(server_mod.app) as tc:
            yield tc, call_id, audio_path
    finally:
        server_mod._CONFIG = saved_config
        server_mod._USER_ID = saved_user


def test_audio_endpoint_returns_file_bytes(client_with_config):
    tc, call_id, audio_path = client_with_config
    resp = tc.get(f"/api/audio/{call_id}")
    assert resp.status_code == 200
    assert resp.content == audio_path.read_bytes()
    assert resp.headers["content-type"] == "audio/mpeg"


def test_audio_endpoint_wrong_user_404(tmp_path):
    import callprofiler.dashboard.server as server_mod

    data_dir, call_id, _ = _seed(tmp_path)
    saved_config, saved_user = server_mod._CONFIG, server_mod._USER_ID
    server_mod._CONFIG = SimpleNamespace(data_dir=str(data_dir))
    server_mod._USER_ID = "someone_else"
    try:
        with TestClient(server_mod.app) as tc:
            resp = tc.get(f"/api/audio/{call_id}")
        assert resp.status_code == 404
    finally:
        server_mod._CONFIG = saved_config
        server_mod._USER_ID = saved_user


def test_audio_endpoint_null_audio_path_404(tmp_path):
    import callprofiler.dashboard.server as server_mod

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
        "VALUES ('me', 'IN', 'f.mp3', 'md5y', 'done')"
    )
    call_id = cur.lastrowid
    conn.commit()
    repo.close()

    saved_config, saved_user = server_mod._CONFIG, server_mod._USER_ID
    server_mod._CONFIG = SimpleNamespace(data_dir=str(data_dir))
    server_mod._USER_ID = "me"
    try:
        with TestClient(server_mod.app) as tc:
            resp = tc.get(f"/api/audio/{call_id}")
        assert resp.status_code == 404
    finally:
        server_mod._CONFIG = saved_config
        server_mod._USER_ID = saved_user


def test_audio_endpoint_path_outside_data_dir_404(tmp_path):
    import callprofiler.dashboard.server as server_mod

    outside_dir = tmp_path / "outside"
    data_dir, call_id, _ = _seed(tmp_path, audio_dir=outside_dir)
    saved_config, saved_user = server_mod._CONFIG, server_mod._USER_ID
    server_mod._CONFIG = SimpleNamespace(data_dir=str(data_dir))
    server_mod._USER_ID = "me"
    try:
        with TestClient(server_mod.app) as tc:
            resp = tc.get(f"/api/audio/{call_id}")
        assert resp.status_code == 404
    finally:
        server_mod._CONFIG = saved_config
        server_mod._USER_ID = saved_user


def test_audio_endpoint_missing_file_on_disk_404(tmp_path):
    data_dir, call_id, audio_path = _seed(tmp_path)
    audio_path.unlink()
    import callprofiler.dashboard.server as server_mod
    saved_config, saved_user = server_mod._CONFIG, server_mod._USER_ID
    server_mod._CONFIG = SimpleNamespace(data_dir=str(data_dir))
    server_mod._USER_ID = "me"
    try:
        with TestClient(server_mod.app) as tc:
            resp = tc.get(f"/api/audio/{call_id}")
        assert resp.status_code == 404
    finally:
        server_mod._CONFIG = saved_config
        server_mod._USER_ID = saved_user


def test_get_call_audio_path_reader_directly(tmp_path):
    data_dir, call_id, audio_path = _seed(tmp_path)
    reader = DashboardDBReader(str(data_dir))
    reader.connect()
    assert reader.get_call_audio_path(call_id, "me") == str(audio_path)
    assert reader.get_call_audio_path(call_id, "nobody") is None
    assert reader.get_call_audio_path(99999, "me") is None
    reader.close()
