# -*- coding: utf-8 -*-
"""test_age_estimate.py — агрегатор возраста + UPSERT (Ф0/Ф1 плана).

Хранение в пространстве года рождения → возраст выводится к reference-дате
динамически: новые звонки лишь уточняют оценку, ничего не протухает.
"""
import json

from callprofiler.db.repository import Repository
from callprofiler.insight import repository as insight_repo
from callprofiler.insight.age_estimate import run_age_estimate


def _db(tmp_path, name="age.db"):
    repo = Repository(str(tmp_path / name))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )
    conn = repo._get_conn()
    insight_repo.apply_insight_schema(conn)
    return repo, conn


_N = [0]


def _contact(conn, name="Иван", user_id="me"):
    _N[0] += 1
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (user_id, f"+7900000{_N[0]:04d}", name),
    )
    return cur.lastrowid


def _call(conn, cid, dt, user_id="me"):
    _N[0] += 1
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
        "source_filename, source_md5, status) VALUES (?,?, 'IN', ?, ?, ?, 'done')",
        (user_id, cid, dt, f"f{_N[0]}.mp3", f"md5{_N[0]}"),
    )
    return cur.lastrowid


def _say(conn, call_id, speaker, text):
    conn.execute(
        "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) "
        "VALUES (?, 0, 1000, ?, ?)", (call_id, text, speaker),
    )


def _row(conn, cid):
    cur = conn.execute(
        "SELECT age_low, age_high, age_point, birth_year_low, birth_year_high, "
        "birth_year_point, confidence, method, evidence, prompt_version, "
        "llm_prompt_hash, llm_result, user_id, computed_at "
        "FROM contact_age_estimates WHERE contact_id = ?", (cid,))
    r = cur.fetchone()
    if r is None:
        return None
    return dict(zip([d[0] for d in cur.description], tuple(r)))


# ── Ф0: прямые маркеры → оценка ─────────────────────────────────────────────

def test_direct_marker_to_estimate(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2021-03-15T10:00:00")
    _say(conn, call, "OTHER", "да мне 45 лет, какие танцы")
    stats = run_age_estimate(conn, "me", reference_now=2026)
    row = _row(conn, cid)
    assert stats["estimated"] == 1
    assert row["method"] == "marker"
    assert (row["birth_year_low"], row["birth_year_high"]) == (1975, 1976)
    assert (row["age_low"], row["age_high"]) == (50, 51)   # к 2026 году
    assert 49 <= row["age_point"] <= 51
    assert row["confidence"] >= 85
    ev = json.loads(row["evidence"])
    assert any("45" in e["quote"] for e in ev)
    repo.close()


def test_owner_and_unknown_lines_ignored(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2021-03-15T10:00:00")
    _say(conn, call, "OWNER", "мне 50 лет")      # владелец о СЕБЕ — не контакт
    _say(conn, call, "UNKNOWN", "мне 60 лет")    # сломанная диаризация — не верим
    stats = run_age_estimate(conn, "me", reference_now=2026)
    assert stats["estimated"] == 0
    assert _row(conn, cid) is None
    repo.close()


def test_idempotent_upsert_single_row(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2021-03-15T10:00:00")
    _say(conn, call, "OTHER", "мне 45 лет")
    run_age_estimate(conn, "me", reference_now=2026)
    run_age_estimate(conn, "me", reference_now=2026)
    n = conn.execute(
        "SELECT COUNT(*) FROM contact_age_estimates WHERE contact_id = ?", (cid,)
    ).fetchone()[0]
    assert n == 1
    repo.close()


def test_agreement_bonus_capped(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    c1 = _call(conn, cid, "2024-02-01T10:00:00")
    c2 = _call(conn, cid, "2024-03-01T10:00:00")
    _say(conn, c1, "OTHER", "мне 62 года, между прочим")
    _say(conn, c2, "OTHER", "я ведь на пенсии уже")
    run_age_estimate(conn, "me", reference_now=2026)
    row = _row(conn, cid)
    # согласие независимых сигналов → conf = 90+10, интервал — узкий прямой
    assert row["confidence"] == 95  # cap
    assert (row["birth_year_low"], row["birth_year_high"]) == (1961, 1962)
    assert row["method"] == "marker"
    repo.close()


def test_no_signals_no_row(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2024-02-01T10:00:00")
    _say(conn, call, "OTHER", "привет, как дела, созвонимся завтра")
    stats = run_age_estimate(conn, "me", reference_now=2026)
    assert stats["estimated"] == 0
    assert _row(conn, cid) is None
    repo.close()


def test_user_isolation(tmp_path):
    repo, conn = _db(tmp_path)
    repo.add_user(
        user_id="other", display_name="O", telegram_chat_id="1",
        incoming_dir="/tmp/in2", sync_dir="/tmp/sync2", ref_audio="/tmp/r2.wav",
    )
    cid_o = _contact(conn, user_id="other")
    call = _call(conn, cid_o, "2021-03-15T10:00:00", user_id="other")
    _say(conn, call, "OTHER", "мне 45 лет")
    stats = run_age_estimate(conn, "me", reference_now=2026)
    assert stats["contacts"] == 0 and stats["estimated"] == 0
    assert _row(conn, cid_o) is None
    repo.close()


# ── Ф1: реляционные якоря в агрегате ────────────────────────────────────────

def test_relation_anchor_family(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn, name="Мама")
    call = _call(conn, cid, "2024-02-01T10:00:00")
    _say(conn, call, "OWNER", "привет, мам, как ты себя чувствуешь")
    run_age_estimate(conn, "me", reference_now=2026, owner_birth_year=1980)
    row = _row(conn, cid)
    assert row["method"] == "relation"
    assert (row["birth_year_low"], row["birth_year_high"]) == (1945, 1960)
    assert (row["age_low"], row["age_high"]) == (66, 81)
    assert row["confidence"] == 70
    repo.close()


def test_anchor_off_without_owner_year(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2024-02-01T10:00:00")
    _say(conn, call, "OWNER", "привет, мам")
    stats = run_age_estimate(conn, "me", reference_now=2026, owner_birth_year=0)
    assert stats["estimated"] == 0
    assert _row(conn, cid) is None
    repo.close()


def test_conflict_direct_beats_anchor(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2024-02-01T10:00:00")
    _say(conn, call, "OTHER", "мне 30 лет вообще-то")        # birth 1993-1994
    _say(conn, call, "OWNER", "ладно, мам, не сердись")      # якорь 1945-1960
    run_age_estimate(conn, "me", reference_now=2026, owner_birth_year=1980)
    row = _row(conn, cid)
    # прямой побеждает, conf падает до min+10 (план)
    assert (row["birth_year_low"], row["birth_year_high"]) == (1993, 1994)
    assert row["confidence"] == 80  # min(90, 70) + 10
    assert row["method"] == "combined"
    repo.close()


# ── Динамика: stale_only — инкрементальный пересчёт ─────────────────────────

def test_stale_only_skips_fresh_then_updates_on_new_call(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2021-03-15T10:00:00")
    _say(conn, call, "OTHER", "мне 45 лет")
    run_age_estimate(conn, "me", reference_now=2026)

    stats = run_age_estimate(conn, "me", reference_now=2026, stale_only=True)
    assert stats["skipped_fresh"] == 1 and stats["contacts"] == 0

    # новый звонок (дата в будущем относительно computed_at) → пересчёт
    c2 = _call(conn, cid, "2030-01-01T00:00:00")
    _say(conn, c2, "OTHER", "я 1976 года рождения, между прочим")
    stats = run_age_estimate(conn, "me", reference_now=2026, stale_only=True)
    assert stats["estimated"] == 1
    row = _row(conn, cid)
    # birth_year (92) + direct_age (90) согласны → интервал сузился, conf cap
    assert (row["birth_year_low"], row["birth_year_high"]) == (1976, 1976)
    assert row["confidence"] == 95
    repo.close()
