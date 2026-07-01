# -*- coding: utf-8 -*-
"""test_age_style_estimate.py — Ф4 плана age.md: год рождения + доверие + оркестратор (офлайн)."""
from datetime import datetime

import numpy as np

from callprofiler.db.repository import Repository
from callprofiler.insight import repository as insight_repo
from callprofiler.insight.age_style.estimate_style import run_style_estimate
from callprofiler.insight.archetypes import adjusted_rand_index
from callprofiler.insight.synth.age_profiles import AGE_TEMPLATES, group_for_age
from callprofiler.insight.synth.corpus import SyntheticCorpus

_N = [0]


def _db(tmp_path, name="age_style_estimate.db"):
    repo = Repository(str(tmp_path / name))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                 incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    conn = repo._get_conn()
    insight_repo.apply_insight_schema(conn)
    return repo, conn


def _contact(conn, name="X", user_id="me"):
    _N[0] += 1
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (user_id, f"+7900{_N[0]:07d}", name))
    return cur.lastrowid


def _add_calls(conn, cid, group, n_calls, year=2026, user_id="me", seed=0, n_words=60):
    """n_calls звонков в году `year` с речью по шаблону group, спикер OTHER."""
    rng = np.random.default_rng(seed)
    tmpl = AGE_TEMPLATES[group]
    for i in range(n_calls):
        _N[0] += 1
        month = 1 + (i % 12)
        cur = conn.execute(
            "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
            "source_filename, source_md5, status) VALUES (?,?, 'IN', ?, ?, ?, 'done')",
            (user_id, cid, f"{year}-{month:02d}-01T10:00:00", f"f{_N[0]}.mp3", f"md5{_N[0]}"))
        call_id = cur.lastrowid
        text = tmpl.sample_other_text(rng, n_words=n_words)
        conn.execute(
            "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) "
            "VALUES (?, 0, 5000, ?, 'OTHER')", (call_id, text))


def _seed_population(conn, year=2026, user_id="me"):
    """Фоновая популяция для z-нормировки (без неё std=0 -> вырожденный z)."""
    for group in ("G1", "G2", "G3", "G5", "G6"):
        cid = _contact(conn, f"bg_{group}", user_id)
        _add_calls(conn, cid, group, 10, year=year, user_id=user_id, seed=abs(hash(group)) % 1000)


def test_confidence_grows_with_conversations(tmp_path):
    repo, conn = _db(tmp_path)
    _seed_population(conn)
    c_few = _contact(conn, "Few")
    c_many = _contact(conn, "Many")
    _add_calls(conn, c_few, "G4", 3, seed=42)
    _add_calls(conn, c_many, "G4", 40, seed=42)

    run_style_estimate(conn, "me")

    row_few = insight_repo.load_contact_age_style(conn, "me", contact_id=c_few)[0]
    row_many = insight_repo.load_contact_age_style(conn, "me", contact_id=c_many)[0]

    assert row_many["confidence"] > row_few["confidence"]
    width_few = row_few["birth_year_high"] - row_few["birth_year_low"]
    width_many = row_many["birth_year_high"] - row_many["birth_year_low"]
    assert width_many < width_few
    repo.close()


def test_birth_year_from_reference(tmp_path):
    # Один и тот же стиль/даты звонков -> ОДИН год рождения независимо от
    # reference_now (якорь — год звонков контакта, не время запуска пересчёта).
    results = {}
    for ref_now in (2021, 2026):
        repo, conn = _db(tmp_path, name=f"age_ref_{ref_now}.db")
        _seed_population(conn, year=2018)
        cid = _contact(conn, "G4contact")
        _add_calls(conn, cid, "G4", 20, year=2018, seed=7)
        run_style_estimate(conn, "me", reference_now=ref_now)
        results[ref_now] = insight_repo.load_contact_age_style(conn, "me", contact_id=cid)[0]
        repo.close()

    assert results[2021]["birth_year_point"] == results[2026]["birth_year_point"]
    assert results[2021]["group_code"] == results[2026]["group_code"]


def test_low_data_level1_no_point(tmp_path):
    repo, conn = _db(tmp_path)
    _seed_population(conn)
    cid = _contact(conn, "OneCall")
    _add_calls(conn, cid, "G4", 1, n_words=20)

    run_style_estimate(conn, "me")

    row = insight_repo.load_contact_age_style(conn, "me", contact_id=cid)[0]
    assert row["confidence_level"] == 1
    assert row["birth_year_point"] is None
    assert "мало данных" in (row["warnings_json"] or "")
    repo.close()


def test_idempotent(tmp_path):
    repo, conn = _db(tmp_path)
    _seed_population(conn)
    cid = _contact(conn, "Idem")
    _add_calls(conn, cid, "G6", 15, seed=3)

    run_style_estimate(conn, "me")
    row1 = insight_repo.load_contact_age_style(conn, "me", contact_id=cid)[0]
    run_style_estimate(conn, "me")
    row2 = insight_repo.load_contact_age_style(conn, "me", contact_id=cid)[0]

    for key in ("group_code", "birth_year_low", "birth_year_high", "birth_year_point",
                "confidence", "confidence_level", "n_conversations", "total_tokens"):
        assert row1[key] == row2[key], key
    repo.close()


def test_recovery_groups(tmp_path):
    corpus = SyntheticCorpus(seed=1)
    ref_year = 2026
    truth_by = {}
    idx = 0
    for by in (2003, 2004, 2005, 2002, 2001, 2006):  # -> G2 к 2026
        truth_by[idx] = by
        idx += 1
    for by in (1985, 1986, 1984, 1983, 1987, 1988):  # -> G4
        truth_by[idx] = by
        idx += 1
    for by in (1955, 1950, 1945, 1958, 1952, 1948):  # -> G6
        truth_by[idx] = by
        idx += 1

    conn = corpus.build(n_per=15, templates=(), age_ground_truth=truth_by,
                       end_date=datetime(2026, 6, 1))
    stats = run_style_estimate(conn, "me", reference_now=ref_year)
    assert stats["estimated"] == len(truth_by)

    rows = {r["contact_id"]: r for r in insight_repo.load_contact_age_style(conn, "me")}
    true_groups = {cid: group_for_age(ref_year - by)
                   for cid, by in corpus.age_ground_truth.items()}
    common = sorted(true_groups)
    pred = [rows[cid]["group_code"] for cid in common]
    true = [true_groups[cid] for cid in common]
    ari = adjusted_rand_index(pred, true)
    assert ari >= 0.6, f"ARI={ari}, pred={pred}, true={true}"
    conn.close()


def test_user_isolation(tmp_path):
    repo, conn = _db(tmp_path)
    repo.add_user(user_id="other", display_name="O", telegram_chat_id="0",
                 incoming_dir="/tmp/in2", sync_dir="/tmp/sync2", ref_audio="/tmp/r2.wav")
    _seed_population(conn, user_id="me")
    _seed_population(conn, user_id="other")
    cid_me = _contact(conn, "MineG4", user_id="me")
    _add_calls(conn, cid_me, "G4", 15, user_id="me", seed=5)
    cid_other = _contact(conn, "OtherG6", user_id="other")
    _add_calls(conn, cid_other, "G6", 15, user_id="other", seed=6)

    stats_me = run_style_estimate(conn, "me")
    assert insight_repo.load_contact_age_style(conn, "other") == []
    assert stats_me["estimated"] > 0

    stats_other = run_style_estimate(conn, "other")
    assert stats_other["estimated"] > 0
    rows_me = insight_repo.load_contact_age_style(conn, "me")
    assert all(r["contact_id"] != cid_other for r in rows_me)
    repo.close()
