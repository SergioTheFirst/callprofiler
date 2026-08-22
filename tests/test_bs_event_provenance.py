# -*- coding: utf-8 -*-
"""
test_bs_event_provenance.py — R-05/R-06: один role-tagged транскрипт на всех
путях билдера и полная provenance-строка факта (fact_type/who/quote_match).
"""

from __future__ import annotations

import hashlib

from callprofiler.analyze.transcript_format import format_role_tagged, load_role_tagged
from callprofiler.db.repository import Repository


def _sha(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _seed(tmp_path):
    repo = Repository(str(tmp_path / "prov.db"))
    repo.init_db()
    repo.add_user("me", "Me", None, "/in", "/sync", "/ref.wav")
    conn = repo._get_conn()
    contact_id = repo.get_or_create_contact("me", "+79990000123", "Пётр")
    call_id = repo.create_call(
        user_id="me",
        contact_id=contact_id,
        direction="IN",
        call_datetime="2026-02-01 10:00:00",
        source_filename="a.mp3",
        source_md5="md5a",
        audio_path=None,
    )
    conn.executemany(
        "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) VALUES (?,?,?,?,?)",
        [
            (call_id, 0, 1000, "Когда пришлёшь документы?", "OWNER"),
            (call_id, 1000, 2000, "Привезу документы в пятницу", "OTHER"),
            (call_id, 2000, 3000, "неразборчиво", "UNKNOWN"),
        ],
    )
    conn.commit()
    return repo, conn, contact_id, call_id


def test_all_builder_paths_use_same_role_tagged_transcript(tmp_path):
    """Live (_format_transcript), bulk (_format_transcript) и builder-load дают
    БАЙТОВО один текст с маркерами [me]/[s2]/[?].

    Раньше форматов было три (``[MM:SS] SPEAKER:``, ``[Я]/[Собеседник]``,
    голая склейка) — ``FactValidator._detect_speaker_context`` ищет ``[me]``/
    ``[s2]``, поэтому в боевом пути speaker у каждого факта был ``unknown``.
    """
    from callprofiler.bulk.enricher import _format_transcript as bulk_fmt
    from callprofiler.models import Segment
    from callprofiler.pipeline.orchestrator import _format_transcript as live_fmt

    repo, conn, _contact_id, call_id = _seed(tmp_path)
    rows = [dict(r) for r in conn.execute(
        "SELECT text, speaker, start_ms FROM transcripts WHERE call_id=? ORDER BY start_ms",
        (call_id,),
    )]
    segments = [
        Segment(start_ms=r["start_ms"], end_ms=r["start_ms"] + 1000, text=r["text"],
                speaker=r["speaker"])
        for r in rows
    ]

    live = live_fmt(segments)
    bulk = bulk_fmt(rows)
    builder = load_role_tagged(conn, call_id)

    assert _sha(live) == _sha(bulk) == _sha(builder)
    assert builder is not None
    assert builder.splitlines() == [
        "[me] Когда пришлёшь документы?",
        "[s2] Привезу документы в пятницу",
        "[?] неразборчиво",
    ]
    repo.close()


def test_role_tagged_formatter_is_order_and_shape_stable():
    """Сегменты приходят как dict, sqlite3.Row и dataclass — формат один;
    порядок — по start_ms, пустые сегменты выброшены."""
    from callprofiler.models import Segment

    dicts = [
        {"text": "второй", "speaker": "OTHER", "start_ms": 500},
        {"text": "", "speaker": "OWNER", "start_ms": 100},
        {"text": "первый", "speaker": "OWNER", "start_ms": 0},
    ]
    segs = [
        Segment(start_ms=500, end_ms=600, text="второй", speaker="OTHER"),
        Segment(start_ms=100, end_ms=200, text="", speaker="OWNER"),
        Segment(start_ms=0, end_ms=100, text="первый", speaker="OWNER"),
    ]
    expected = "[me] первый\n[s2] второй"
    assert format_role_tagged(dicts) == expected
    assert format_role_tagged(segs) == expected
    assert format_role_tagged([]) == ""


def test_builder_prefers_canonical_json_and_falls_back_raw(tmp_path):
    """R-04: канон → raw → invalid; невалидный payload не даёт фактов."""
    from callprofiler.analyze.payload_reader import (
        load_analysis_payload,
        parse_analysis_payload,
    )

    repo, conn, _contact_id, call_id = _seed(tmp_path)

    payload, reason = parse_analysis_payload('{"a": 1}', '{"b": 2}')
    assert (payload, reason) == ({"a": 1}, "canonical")
    payload, reason = parse_analysis_payload("", '{"b": 2}')
    assert (payload, reason) == ({"b": 2}, "raw")
    payload, reason = parse_analysis_payload("не json", "тоже не json")
    assert (payload, reason) == (None, "invalid")

    conn.execute(
        "INSERT INTO analyses (call_id, raw_response, canonical_json, schema_version) "
        "VALUES (?,?,?,'v2')",
        (call_id, '{"entities": []}', '{"entities": [{"normalized_key": "x"}]}'),
    )
    conn.commit()
    payload, reason = load_analysis_payload(conn, call_id)
    assert reason == "canonical"
    assert payload["entities"][0]["normalized_key"] == "x"
    repo.close()
