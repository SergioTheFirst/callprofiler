from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight.synth.archetypes import DEFAULT_TEMPLATES


def test_corpus_builds_faithful_db():
    corpus = SyntheticCorpus(seed=0)
    conn = corpus.build(n_per=8)
    n_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    n_contacts = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    n_calls = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    assert n_users == 1
    assert n_contacts == len(DEFAULT_TEMPLATES) * 8
    assert n_calls > 0


def test_corpus_exposes_ground_truth():
    corpus = SyntheticCorpus(seed=0)
    corpus.build(n_per=8)
    gt = corpus.ground_truth  # dict contact_id -> archetype name
    assert len(gt) == len(DEFAULT_TEMPLATES) * 8
    assert set(gt.values()) == {t.name for t in DEFAULT_TEMPLATES}


def test_corpus_user_isolation():
    corpus = SyntheticCorpus(seed=0)
    conn = corpus.build(n_per=5, user_id="me")
    bad = conn.execute("SELECT COUNT(*) FROM calls WHERE user_id != 'me'").fetchone()[0]
    assert bad == 0
