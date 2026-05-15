# -*- coding: utf-8 -*-
"""test_graph_builder.py — additional tests for GraphBuilder not in test_graph.py."""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from callprofiler.db.repository import Repository
from callprofiler.graph.builder import GraphBuilder, _hash
from callprofiler.graph.repository import GraphRepository, apply_graph_schema


def _make_repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def _add_user(repo: Repository, user_id: str = "u1") -> None:
    repo.add_user(
        user_id=user_id, display_name="Test", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/ref.wav",
    )


def _add_call(repo: Repository, user_id: str = "u1", md5: str = "abc") -> int:
    contact_id = repo.get_or_create_contact(user_id, "+70000000001", "Test")
    return repo.create_call(
        user_id=user_id, contact_id=contact_id, direction="IN",
        call_datetime="2026-04-01 10:00:00", source_filename="t.mp3",
        source_md5=md5, audio_path="/tmp/t.mp3",
    )


def _save_v2(repo: Repository, call_id: int, raw: dict) -> None:
    from callprofiler.models import Analysis
    a = Analysis(
        priority=50, risk_score=30, summary="test",
        action_items=[], promises=[], flags={}, key_topics=[],
        raw_response=json.dumps(raw, ensure_ascii=False),
        model="test", prompt_version="v2", call_type="business", hook=None,
    )
    repo.save_analysis(call_id, a)
    conn = repo._get_conn()
    conn.execute("UPDATE analyses SET schema_version='v2' WHERE call_id=?", (call_id,))
    conn.commit()


def _payload(**kw) -> dict:
    return {
        "entities": kw.get("entities", []),
        "relations": kw.get("relations", []),
        "structured_facts": kw.get("facts", []),
    }


def test_builder_empty_update_returns_false():
    repo = _make_repo()
    apply_graph_schema(repo._get_conn())
    _add_user(repo)
    call_id = _add_call(repo)
    _save_v2(repo, call_id, _payload())

    builder = GraphBuilder(repo._get_conn())
    result = builder.update_from_call(call_id)
    assert result is False


def test_builder_stats_tracking():
    repo = _make_repo()
    apply_graph_schema(repo._get_conn())
    _add_user(repo)
    call_id = _add_call(repo)
    _save_v2(repo, call_id, _payload(
        entities=[{"type": "person", "canonical_name": "Сергей", "normalized_key": "sergey",
                    "aliases": ["Серёжа"], "attributes": {}}],
        facts=[{"fact_type": "promise", "entity_key": "sergey",
                 "quote": "перезвоню завтра утром точно", "confidence": 0.85}],
    ))

    builder = GraphBuilder(repo._get_conn())
    builder.update_from_call(call_id)
    stats = builder.get_stats()
    assert stats["facts_total"] == 1
    assert "facts_inserted" in stats
    assert "facts_rejected" in stats


def test_builder_entity_attributes_persisted():
    repo = _make_repo()
    apply_graph_schema(repo._get_conn())
    _add_user(repo)
    call_id = _add_call(repo)
    _save_v2(repo, call_id, _payload(
        entities=[{"type": "person", "canonical_name": "Пётр", "normalized_key": "petr",
                    "aliases": [], "attributes": {"role": "менеджер"}}],
    ))

    GraphBuilder(repo._get_conn()).update_from_call(call_id)
    grepo = GraphRepository(repo._get_conn())
    entities = grepo.get_entities("u1", "person")
    assert any(e["normalized_key"] == "petr" for e in entities)


def test_builder_relation_passed_to_repo():
    repo = _make_repo()
    apply_graph_schema(repo._get_conn())
    _add_user(repo)
    call_id = _add_call(repo)
    _save_v2(repo, call_id, _payload(
        entities=[
            {"type": "person", "canonical_name": "Иван", "normalized_key": "ivan",
             "aliases": [], "attributes": {}},
            {"type": "org", "canonical_name": "Фирма", "normalized_key": "firma",
             "aliases": [], "attributes": {}},
        ],
        relations=[{"src_key": "ivan", "dst_key": "firma", "relation_type": "works_for", "confidence": 0.9}],
    ))

    GraphBuilder(repo._get_conn()).update_from_call(call_id)
    grepo = GraphRepository(repo._get_conn())
    entities = {e["normalized_key"]: e["id"] for e in grepo.get_entities("u1")}
    rel = grepo.get_relation("u1", entities["ivan"], entities["firma"], "works_for")
    assert rel is not None


def test_builder_fact_hash_reproducible():
    assert _hash("promise|1|some text") == _hash("promise|1|some text")
    assert len(_hash("test")) == 16


def test_builder_skips_empty_entities_list():
    repo = _make_repo()
    apply_graph_schema(repo._get_conn())
    _add_user(repo)
    call_id = _add_call(repo)
    _save_v2(repo, call_id, _payload(
        entities=[
            {"type": "person", "canonical_name": "Valid", "normalized_key": "valid",
             "aliases": [], "attributes": {}},
            {},
        ],
    ))

    builder = GraphBuilder(repo._get_conn())
    result = builder.update_from_call(call_id)
    assert result is True
