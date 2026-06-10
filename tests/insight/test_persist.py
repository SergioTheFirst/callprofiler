import sqlite3

from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight import repository as repo
from callprofiler.insight import cli_ops


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


def test_contact_archetype_upsert_is_user_scoped():
    """Defense-in-depth: чужой user_id с тем же contact_id НЕ перезаписывает строку."""
    conn = SyntheticCorpus(seed=0).build(n_per=5)
    repo.save_contact_archetype(conn, "me", contact_id=1, model_id=None, cluster_idx=0,
                                label="A", membership=1.0, distinctive_dims=[],
                                confidence="high", evidence=[])
    repo.save_contact_archetype(conn, "intruder", contact_id=1, model_id=None, cluster_idx=9,
                                label="B", membership=0.1, distinctive_dims=[],
                                confidence="low", evidence=[])
    row = conn.execute(
        "SELECT user_id, cluster_idx, archetype_label FROM contact_archetypes WHERE contact_id=1"
    ).fetchone()
    assert row[0] == "me" and row[1] == 0 and row[2] == "A"


# ── Phase 7: PCA-2D coordinate persistence ──────────────────────────────────

def test_save_contact_archetype_persists_pca_coords():
    conn = SyntheticCorpus(seed=0).build(n_per=5)
    repo.save_contact_archetype(conn, "me", contact_id=1, model_id=None, cluster_idx=0,
                                label="A", membership=0.9, distinctive_dims=[],
                                confidence="high", evidence=[], pca_x=1.5, pca_y=-2.25)
    row = conn.execute(
        "SELECT pca_x, pca_y FROM contact_archetypes WHERE contact_id=1 AND user_id='me'"
    ).fetchone()
    assert row[0] == 1.5 and row[1] == -2.25


def test_fit_persists_pca_coordinates():
    """archetypes-fit must store the 2D projection for every assigned contact."""
    conn = SyntheticCorpus(seed=0).build(n_per=12)
    res = cli_ops.run_archetypes_fit(conn, "me")
    assert res["n_assigned"] > 0
    rows = conn.execute(
        "SELECT pca_x, pca_y FROM contact_archetypes WHERE user_id='me'"
    ).fetchall()
    assert len(rows) == res["n_assigned"]
    assert all(r[0] is not None and r[1] is not None for r in rows)  # coords populated
    # not degenerate — the map must actually spread points, not collapse to a dot
    assert len({(round(r[0], 3), round(r[1], 3)) for r in rows}) >= 2


def test_apply_schema_adds_pca_columns_to_legacy_table():
    """Idempotent ALTER: a pre-Phase-7 contact_archetypes gains pca_x/pca_y."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE contact_archetypes ("
        "contact_id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, model_id INTEGER,"
        "cluster_idx INTEGER NOT NULL, archetype_label TEXT, membership REAL,"
        "distinctive_dims TEXT, confidence TEXT, evidence TEXT, computed_at TEXT);"
    )
    repo.apply_insight_schema(conn)  # migrates: ADD COLUMN pca_x/pca_y
    cols = {r[1] for r in conn.execute("PRAGMA table_info(contact_archetypes)").fetchall()}
    assert "pca_x" in cols and "pca_y" in cols
    repo.apply_insight_schema(conn)  # second run is a no-op (must not raise)
