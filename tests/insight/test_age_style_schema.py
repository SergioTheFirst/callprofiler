# -*- coding: utf-8 -*-
"""test_age_style_schema.py — Ф1 плана age.md: contact_age_style схема + synth ground-truth."""
from callprofiler.db.repository import Repository
from callprofiler.insight import repository as insight_repo
from callprofiler.insight.synth.corpus import SyntheticCorpus


def _db(tmp_path, name="age_style.db"):
    repo = Repository(str(tmp_path / name))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )
    conn = repo._get_conn()
    insight_repo.apply_insight_schema(conn)
    return repo, conn


def test_schema_idempotent(tmp_path):
    repo, conn = _db(tmp_path)
    insight_repo.apply_insight_schema(conn)  # повторный вызов не должен упасть
    insight_repo.apply_insight_schema(conn)
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact_age_style'"
    ).fetchone()
    assert row is not None
    repo.close()


def test_save_load_roundtrip(tmp_path):
    repo, conn = _db(tmp_path)
    cur = conn.execute(
        "INSERT INTO contacts(user_id, display_name) VALUES (?, ?)", ("me", "Иван"))
    cid = cur.lastrowid

    insight_repo.save_contact_age_style(
        conn, "me", contact_id=cid, group_code="G4",
        group_dist={"G1": 0.0, "G2": 0.02, "G3": 0.1, "G4": 0.5, "G5": 0.3, "G6": 0.08},
        birth_low=1978, birth_high=1988, birth_point=1983,
        confidence=55, confidence_level=3, n_conversations=12, total_tokens=900,
        top=[["Т1 карьера", 0.31], ["Ч6", 0.18]], warnings=[],
        table_version="age-style-v1+age-rules-v1",
    )
    rows = insight_repo.load_contact_age_style(conn, "me", contact_id=cid)
    assert len(rows) == 1
    row = rows[0]
    assert row["group_code"] == "G4"
    assert row["birth_year_point"] == 1983
    assert row["confidence"] == 55
    assert row["n_conversations"] == 12

    # user-guard: чужой user_id не перезаписывает существующую строку (UPSERT no-op)
    repo.add_user(
        user_id="other", display_name="O", telegram_chat_id="0",
        incoming_dir="/tmp/in2", sync_dir="/tmp/sync2", ref_audio="/tmp/r2.wav",
    )
    insight_repo.save_contact_age_style(
        conn, "other", contact_id=cid, group_code="G1",
        group_dist={"G1": 1.0}, birth_low=2015, birth_high=2020, birth_point=2018,
        confidence=90, confidence_level=5, n_conversations=1, total_tokens=10,
        top=[], warnings=[], table_version="age-style-v1+age-rules-v1",
    )
    row_after = insight_repo.load_contact_age_style(conn, "me", contact_id=cid)[0]
    assert row_after["group_code"] == "G4"  # не перезаписано чужим user_id
    assert insight_repo.load_contact_age_style(conn, "other", contact_id=cid) == []
    repo.close()


def test_synth_age_corpus_builds():
    corpus = SyntheticCorpus(seed=0)
    truth = {0: 1980, 1: 1955, 2: 2005}
    conn = corpus.build(n_per=5, age_ground_truth=truth)
    assert len(corpus.age_ground_truth) == 3
    for cid, birth_year in corpus.age_ground_truth.items():
        assert birth_year in truth.values()
        calls = conn.execute(
            "SELECT call_id, call_datetime FROM calls WHERE contact_id = ?", (cid,)
        ).fetchall()
        assert len(calls) == 5
        for call_id, dt in calls:
            assert dt
            other = conn.execute(
                "SELECT text FROM transcripts WHERE call_id = ? AND speaker = 'OTHER'",
                (call_id,),
            ).fetchall()
            assert len(other) == 1
            assert len(other[0][0].split()) >= 30
    conn.close()
