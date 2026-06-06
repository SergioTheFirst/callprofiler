from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight.cli_ops import run_features_build, run_archetypes_fit


def test_end_to_end_on_synth():
    conn = SyntheticCorpus(seed=0).build(n_per=15)
    n_feat = run_features_build(conn, "me")
    assert n_feat > 0
    res = run_archetypes_fit(conn, "me", version="arch-v1")
    assert res["k"] >= 2
    assert res["n_assigned"] == conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE user_id='me'").fetchone()[0]


def test_features_build_idempotent():
    conn = SyntheticCorpus(seed=1).build(n_per=10)
    n1 = run_features_build(conn, "me")
    n2 = run_features_build(conn, "me")
    assert n1 == n2  # UPSERT, не растёт
    rows = conn.execute("SELECT COUNT(*) FROM contact_features WHERE user_id='me'").fetchone()[0]
    assert rows == n1


def test_fit_skips_when_too_few_contacts():
    conn = SyntheticCorpus(seed=2).build(n_per=15)
    res = run_archetypes_fit(conn, "ghost")  # нет такого user → 0 контактов
    assert res["n_assigned"] == 0 and res["k"] == 0
