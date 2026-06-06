from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight.cli_ops import run_features_build, run_archetypes_fit
from callprofiler.insight.cards import build_card


def _fitted(seed=0, n_per=15):
    conn = SyntheticCorpus(seed=seed).build(n_per=n_per)
    run_features_build(conn, "me")
    run_archetypes_fit(conn, "me")
    return conn


def _first_contact(conn):
    return conn.execute(
        "SELECT contact_id FROM contacts WHERE user_id='me' ORDER BY contact_id LIMIT 1"
    ).fetchone()[0]


def test_card_has_archetype_traits_confidence():
    conn = _fitted()
    card = build_card(conn, "me", _first_contact(conn))
    assert card is not None
    assert card["archetype"]                       # непустое имя архетипа
    assert card["confidence"] in ("high", "medium", "low")
    assert isinstance(card["traits"], list)
    assert 0.0 <= (card["membership"] or 0) <= 1.0
    assert card["last_seen"]                        # есть дата последнего контакта


def test_card_traits_are_phrases_not_raw():
    conn = _fitted()
    card = build_card(conn, "me", _first_contact(conn))
    for t in card["traits"]:
        assert isinstance(t, str) and not t.isdigit()  # фразы, не сырые числа


def test_card_unknown_contact_is_none():
    conn = _fitted()
    assert build_card(conn, "me", 999999) is None


def test_card_user_isolation():
    conn = _fitted()
    cid = _first_contact(conn)
    assert build_card(conn, "other", cid) is None   # чужой user не видит
