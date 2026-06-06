from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight import repository as repo


def test_save_model_and_assignments_idempotent():
    conn = SyntheticCorpus(seed=0).build(n_per=10)
    mid1 = repo.save_archetype_model(conn, "me", version="arch-v1", k=4,
                                     silhouette=0.5, n_contacts=40,
                                     feature_list=["a"], centroids=[[0.0]],
                                     labels={"0": "x"})
    repo.save_contact_archetype(conn, "me", contact_id=1, model_id=mid1,
                                cluster_idx=0, label="x", membership=0.9,
                                distinctive_dims=[], confidence="high", evidence=[])
    # повтор по тому же contact_id — UPSERT, не дубль
    repo.save_contact_archetype(conn, "me", contact_id=1, model_id=mid1,
                                cluster_idx=1, label="y", membership=0.8,
                                distinctive_dims=[], confidence="high", evidence=[])
    rows = conn.execute("SELECT cluster_idx FROM contact_archetypes WHERE contact_id=1").fetchall()
    assert len(rows) == 1 and rows[0][0] == 1  # перезаписан


def test_user_isolation_on_load():
    conn = SyntheticCorpus(seed=0).build(n_per=5, user_id="me")
    assert repo.load_contact_archetypes(conn, "other") == []
