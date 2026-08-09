# -*- coding: utf-8 -*-
"""test_role_fragile.py — инлайн-задача №7 (OzaluplivanieFable.md §4.2): role-fragile flag.

Роли иногда перепутаны (шум-доктрина) — звонки с высокой долей UNKNOWN-сегментов
помечаются role_fragile=1, чтобы who-критичные извлечения на них не опирались.
"""
import sqlite3

from callprofiler.db.repository import Repository
from callprofiler.diarize.role_assigner import (
    UNKNOWN_SHARE_THRESHOLD,
    is_role_fragile,
)
from callprofiler.models import Segment


def _seg(speaker):
    return Segment(0, 1000, "текст", speaker)


def test_is_role_fragile_over_threshold():
    # 4 из 10 UNKNOWN = 0.4 > 0.3
    segs = [_seg("UNKNOWN")] * 4 + [_seg("OWNER")] * 3 + [_seg("OTHER")] * 3
    assert is_role_fragile(segs) is True


def test_is_role_fragile_under_threshold():
    # 2 из 10 UNKNOWN = 0.2 <= 0.3
    segs = [_seg("UNKNOWN")] * 2 + [_seg("OWNER")] * 4 + [_seg("OTHER")] * 4
    assert is_role_fragile(segs) is False


def test_is_role_fragile_exactly_at_threshold_is_not_fragile():
    # ровно 0.3 — строгое ">", не ">="
    segs = [_seg("UNKNOWN")] * 3 + [_seg("OWNER")] * 7
    assert UNKNOWN_SHARE_THRESHOLD == 0.3
    assert is_role_fragile(segs) is False


def test_is_role_fragile_empty_segments_is_false():
    assert is_role_fragile([]) is False


def test_is_role_fragile_all_unknown():
    segs = [_seg("UNKNOWN")] * 5
    assert is_role_fragile(segs) is True


def test_set_role_fragile_writes_flag(tmp_path):
    repo = Repository(str(tmp_path / "cp.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    conn = repo._get_conn()
    cur = conn.execute(
        "INSERT INTO calls(user_id, direction, source_filename, source_md5, status) "
        "VALUES ('me', 'IN', 'f.mp3', 'md5a', 'done')"
    )
    call_id = cur.lastrowid
    conn.commit()

    row = conn.execute("SELECT role_fragile FROM calls WHERE call_id=?", (call_id,)).fetchone()
    assert row["role_fragile"] == 0  # default

    repo.set_role_fragile("me", call_id, True)
    row = conn.execute("SELECT role_fragile FROM calls WHERE call_id=?", (call_id,)).fetchone()
    assert row["role_fragile"] == 1

    repo.set_role_fragile("me", call_id, False)
    row = conn.execute("SELECT role_fragile FROM calls WHERE call_id=?", (call_id,)).fetchone()
    assert row["role_fragile"] == 0
    repo.close()


def test_schema_migration_adds_role_fragile_to_old_db(tmp_path):
    """Аддитивность схемы: старая БД без колонки role_fragile получает её через _migrate()."""
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    # Минимальная "старая" схема: calls БЕЗ role_fragile (и без pipeline_stage) +
    # прочие таблицы, которые _migrate() трогает без try/except (должны просто существовать).
    conn.execute(
        """CREATE TABLE calls (
            call_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
        )"""
    )
    conn.execute("CREATE TABLE contacts (contact_id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE analyses (analysis_id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE events (event_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    repo = Repository(str(db_path))
    conn = repo._get_conn()
    repo._migrate()

    cols = {row[1] for row in conn.execute("PRAGMA table_info(calls)").fetchall()}
    assert "role_fragile" in cols
    repo.close()


def test_schema_migration_idempotent(tmp_path):
    repo = Repository(str(tmp_path / "cp2.db"))
    repo.init_db()
    repo._migrate()  # второй прогон не должен упасть
    conn = repo._get_conn()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(calls)").fetchall()}
    assert "role_fragile" in cols
    repo.close()
