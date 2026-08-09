# -*- coding: utf-8 -*-
"""test_tiers.py — F8: Эббингауз-тиры контактов (core/active/warm/cold/archive)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from callprofiler.bulk.enricher import select_pending_calls
from callprofiler.db.repository import Repository
from callprofiler.insight.tiers import (
    TIER_ORDER,
    apply_tiers_schema,
    classify_tier,
    compute_score,
    recompute_tiers,
)


def _repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def _user(repo: Repository, user_id: str = "me") -> None:
    repo.add_user(
        user_id=user_id, display_name="Test", telegram_chat_id="555",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/ref.wav",
    )


def _call(repo, user_id, contact_id, dt, duration=600, status="done"):
    call_id = repo.create_call(
        user_id, contact_id, "incoming", dt, f"f{dt.isoformat()}-{contact_id}.mp3",
        f"md5-{dt.isoformat()}-{contact_id}", f"/audio/{contact_id}-{dt.isoformat()}.mp3",
    )
    repo.update_call_paths(user_id, call_id, f"/norm/{call_id}.wav", duration)
    repo.update_call_status(user_id, call_id, status)
    return call_id


# ── Формула (чистые функции) ────────────────────────────────────────────

def test_score_zero_for_no_calls():
    assert compute_score(0, 100.0, 0.0) == 0.0


def test_score_more_calls_slower_decay():
    # тот же talk-объём, тот же возраст последнего звонка, но больше касаний -> выше score
    low = compute_score(call_count=1, days_since_last_call=60, total_talk_minutes=30)
    high = compute_score(call_count=15, days_since_last_call=60, total_talk_minutes=30)
    assert high > low


def test_score_fresh_call_raises_score():
    fresh = compute_score(call_count=5, days_since_last_call=1, total_talk_minutes=20)
    stale = compute_score(call_count=5, days_since_last_call=200, total_talk_minutes=20)
    assert fresh > stale


def test_classify_tier_zero_score_is_archive():
    thresholds = {"p95": 5.0, "p75": 3.0, "p40": 1.0, "p10": 0.1}
    assert classify_tier(0.0, thresholds) == "archive"


def test_classify_tier_ordering_monotonic():
    thresholds = {"p95": 5.0, "p75": 3.0, "p40": 1.0, "p10": 0.1}
    rank = {t: i for i, t in enumerate(TIER_ORDER)}
    scores = [10.0, 4.0, 2.0, 0.5, 0.05]  # descending
    tiers = [classify_tier(s, thresholds) for s in scores]
    ranks = [rank[t] for t in tiers]
    assert ranks == sorted(ranks)  # non-decreasing rank as score decreases


# ── recompute_tiers (integration, sqlite) ───────────────────────────────

def test_percentile_boundaries_on_20_contacts():
    repo = _repo()
    _user(repo)
    today = date(2026, 7, 17)
    for i in range(20):
        cid = repo.get_or_create_contact("me", f"+7000000{i:04d}", f"C{i}")
        # differing call volume/recency -> differing scores
        n_calls = i + 1
        for k in range(n_calls):
            dt = datetime(2026, 7, 17) - timedelta(days=k * 5)
            _call(repo, "me", cid, dt, duration=300 + i * 20)

    conn = repo._get_conn()
    res = recompute_tiers(conn, "me", today=today)
    assert res["ok"] is True
    assert res["n_contacts"] == 20

    rows = conn.execute("SELECT contact_id, tier, score FROM contact_tiers WHERE user_id='me'").fetchall()
    rank = {t: i for i, t in enumerate(TIER_ORDER)}
    by_score = sorted(rows, key=lambda r: r["score"], reverse=True)
    ranks = [rank[r["tier"]] for r in by_score]
    assert ranks == sorted(ranks)  # higher score -> better-or-equal tier
    # top scorer should land in the best tier present
    assert by_score[0]["tier"] in ("core", "active")


def test_prev_tier_captures_transition():
    repo = _repo()
    _user(repo)
    cid = repo.get_or_create_contact("me", "+70000000001", "Вася")
    conn = repo._get_conn()

    # First run: contact has no calls at all -> archive
    res1 = recompute_tiers(conn, "me", today=date(2026, 7, 17))
    assert res1["transitions"] == []
    row = conn.execute(
        "SELECT tier, prev_tier FROM contact_tiers WHERE user_id='me' AND contact_id=?", (cid,)
    ).fetchone()
    assert row["tier"] == "archive"
    assert row["prev_tier"] is None

    # Add strong recent activity for this contact
    for k in range(10):
        dt = datetime(2026, 7, 17) - timedelta(days=k)
        _call(repo, "me", cid, dt, duration=1200)

    res2 = recompute_tiers(conn, "me", today=date(2026, 7, 17))
    row2 = conn.execute(
        "SELECT tier, prev_tier FROM contact_tiers WHERE user_id='me' AND contact_id=?", (cid,)
    ).fetchone()
    assert row2["prev_tier"] == "archive"
    assert row2["tier"] != "archive"
    assert any(t["contact_id"] == cid and t["from"] == "archive" for t in res2["transitions"])


def test_recompute_tiers_isolated_by_user():
    repo = _repo()
    _user(repo, "me")
    _user(repo, "other")
    cid_me = repo.get_or_create_contact("me", "+70000000001", "A")
    cid_other = repo.get_or_create_contact("other", "+70000000002", "B")
    conn = repo._get_conn()
    for k in range(5):
        dt = datetime(2026, 7, 17) - timedelta(days=k)
        _call(repo, "other", cid_other, dt, duration=600)

    recompute_tiers(conn, "me", today=date(2026, 7, 17))

    rows_me = conn.execute("SELECT * FROM contact_tiers WHERE user_id='me'").fetchall()
    rows_other = conn.execute("SELECT * FROM contact_tiers WHERE user_id='other'").fetchall()
    assert len(rows_me) == 1  # only cid_me, isolated from other's calls
    assert len(rows_other) == 0  # recompute wasn't called for 'other'


def test_apply_tiers_schema_idempotent():
    repo = _repo()
    conn = repo._get_conn()
    apply_tiers_schema(conn)
    apply_tiers_schema(conn)  # second call must not raise


# ── Потребитель: enricher queue ──────────────────────────────────────────

def test_enricher_queue_sorted_by_tier_when_tiers_computed():
    repo = _repo()
    _user(repo)
    cid_core = repo.get_or_create_contact("me", "+70000000001", "Core")
    cid_cold = repo.get_or_create_contact("me", "+70000000002", "Cold")
    conn = repo._get_conn()

    # cold contact's call is OLDER (would sort first chronologically)
    call_cold = _call(repo, "me", cid_cold, datetime(2026, 1, 1, 10, 0))
    call_core = _call(repo, "me", cid_core, datetime(2026, 7, 1, 10, 0))

    apply_tiers_schema(conn)
    conn.execute(
        "INSERT INTO contact_tiers(user_id,contact_id,tier,score) VALUES ('me',?,?,?)",
        (cid_core, "core", 10.0),
    )
    conn.execute(
        "INSERT INTO contact_tiers(user_id,contact_id,tier,score) VALUES ('me',?,?,?)",
        (cid_cold, "cold", 0.5),
    )
    conn.commit()

    calls = select_pending_calls(conn, "me")
    call_ids = [c["call_id"] for c in calls]
    assert call_ids.index(call_core) < call_ids.index(call_cold)


def test_enricher_queue_falls_back_to_chronological_without_tiers_table():
    repo = _repo()
    _user(repo)
    cid = repo.get_or_create_contact("me", "+70000000001", "A")
    conn = repo._get_conn()
    call_old = _call(repo, "me", cid, datetime(2026, 1, 1, 10, 0))
    call_new = _call(repo, "me", cid, datetime(2026, 7, 1, 10, 0))

    calls = select_pending_calls(conn, "me")  # no contact_tiers table yet
    call_ids = [c["call_id"] for c in calls]
    assert call_ids.index(call_old) < call_ids.index(call_new)


# ── Потребители: дашборд (get_people / get_person_dossier) ──────────────

def test_get_people_exposes_tier_and_label(tmp_path):
    from callprofiler.dashboard.db_reader import DashboardDBReader

    db = tmp_path / "cp.db"
    repo = Repository(str(db))
    repo.init_db()
    _user(repo)
    cid = repo.get_or_create_contact("me", "+70000000001", "Вася")
    conn = repo._get_conn()
    apply_tiers_schema(conn)
    conn.execute(
        "INSERT INTO contact_tiers(user_id,contact_id,tier,score) VALUES ('me',?,?,?)",
        (cid, "core", 5.0),
    )
    conn.commit()
    repo.close()

    reader = DashboardDBReader(str(db))
    reader.connect()
    people = reader.get_people("me")
    reader.close()

    row = next(p for p in people if p["contact_id"] == cid)
    assert row["tier"] == "core"
    assert row["tier_label"] == "ядро"


def test_get_people_tier_none_without_table(tmp_path):
    from callprofiler.dashboard.db_reader import DashboardDBReader

    db = tmp_path / "cp2.db"
    repo = Repository(str(db))
    repo.init_db()
    _user(repo)
    repo.get_or_create_contact("me", "+70000000001", "Вася")
    repo.close()

    reader = DashboardDBReader(str(db))
    reader.connect()
    people = reader.get_people("me")
    reader.close()

    assert people[0]["tier"] is None
    assert people[0]["tier_label"] is None


def test_get_person_dossier_exposes_tier(tmp_path):
    from callprofiler.dashboard.db_reader import DashboardDBReader

    db = tmp_path / "cp3.db"
    repo = Repository(str(db))
    repo.init_db()
    _user(repo)
    cid = repo.get_or_create_contact("me", "+70000000001", "Вася")
    conn = repo._get_conn()
    apply_tiers_schema(conn)
    conn.execute(
        "INSERT INTO contact_tiers(user_id,contact_id,tier,score) VALUES ('me',?,?,?)",
        (cid, "warm", 1.5),
    )
    conn.commit()
    repo.close()

    reader = DashboardDBReader(str(db))
    reader.connect()
    dossier = reader.get_person_dossier(cid, "me")
    reader.close()

    assert dossier["tier"] == {"code": "warm", "label": "тёплые"}
