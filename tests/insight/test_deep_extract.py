# -*- coding: utf-8 -*-
"""test_deep_extract.py — M8: map-reduce deep-extract по длинным звонкам (LLM mock)."""
from __future__ import annotations

import json
from unittest import mock

from callprofiler.analyze.llm_client import LLMResult
from callprofiler.db.repository import Repository
from callprofiler.deliver.digest import build_digest
from callprofiler.insight.deep_extract import (
    PROMPT_VERSION_DEEP,
    chunk_text,
    recent_deep_lines,
    run_deep_extract,
)
from callprofiler.insight.repository import apply_insight_schema


def _repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def _user(repo: Repository, user_id: str = "me") -> None:
    repo.add_user(
        user_id=user_id, display_name="T", telegram_chat_id="1",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )


def _contact(conn, user_id="me", name="Иван") -> int:
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (user_id, "+79001112233", name),
    )
    return cur.lastrowid


def _call(conn, user_id, contact_id, *, duration=900, status="done",
          call_type=None, dt="2026-07-01T10:00:00") -> int:
    seq = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]  # уникальность md5/filename
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, source_filename, "
        "source_md5, status, duration_sec, call_type) VALUES (?,?,?,?,?,?,?,?,?)",
        (user_id, contact_id, "IN", dt, f"f{contact_id}-{dt}-{seq}.mp3",
         f"md5-{contact_id}-{dt}-{seq}", status, duration, call_type),
    )
    return cur.lastrowid


def _transcript(conn, call_id, segments) -> None:
    for i, (speaker, text) in enumerate(segments):
        conn.execute(
            "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) VALUES (?,?,?,?,?)",
            (call_id, i * 1000, i * 1000 + 900, text, speaker),
        )


def _analysis(conn, call_id, priority) -> None:
    conn.execute("INSERT INTO analyses(call_id, priority) VALUES (?,?)", (call_id, priority))


def _llm_response(items: list[dict]) -> LLMResult:
    return LLMResult(text=json.dumps({"items": items}, ensure_ascii=False), finish_reason="stop")


# ── chunk_text (чистая функция) ──────────────────────────────────────────

def test_chunk_text_short_returns_single_chunk():
    assert chunk_text("hello world", size=9000, overlap=800) == ["hello world"]


def test_chunk_text_does_not_split_words():
    words = [f"слово{i:04d}" for i in range(600)]
    text = " ".join(words)
    chunks = chunk_text(text, size=300, overlap=50)
    assert len(chunks) > 1
    valid = set(words)
    for c in chunks:
        for tok in c.split():
            assert tok in valid  # ни один чанк не режет слово пополам


def test_chunk_text_overlap_visible():
    words = [f"w{i:04d}" for i in range(400)]
    text = " ".join(words)
    chunks = chunk_text(text, size=300, overlap=60)
    assert len(chunks) > 1
    assert set(chunks[0].split()) & set(chunks[1].split())  # общие слова в перекрытии


def test_chunk_text_step_guard_terminates():
    text = "a" * 500  # без пробелов вовсе — крайний случай для word-boundary логики
    chunks = chunk_text(text, size=50, overlap=1000)  # overlap > size -> step=max(1,...)
    assert len(chunks) > 1
    assert "".join(chunks[:1])[0] == "a"


# ── Гейты на item (через run_deep_extract, мок LLM) ─────────────────────

def test_run_deep_extract_saves_valid_item_and_marks_scanned():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    call_id = _call(conn, "me", cid)
    _transcript(conn, call_id, [("OTHER", "я перезвоню завтра насчёт сметы")])
    conn.commit()

    resp = _llm_response([{"type": "promise", "who": "OTHER", "what": "перезвонить",
                            "quote": "перезвоню завтра", "deadline": "завтра"}])
    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.return_value = resp
        stats = run_deep_extract(conn, "me", llm_url="http://fake")

    assert stats["calls_scanned"] == 1
    assert stats["items_saved"] == 1
    assert stats["items_dropped"] == 0
    row = conn.execute("SELECT type, who, what, quote, deadline_raw FROM deep_facts WHERE user_id='me'").fetchone()
    assert row["type"] == "promise" and row["who"] == "OTHER"
    assert row["what"] == "перезвонить"
    assert row["deadline_raw"] == "завтра"
    scanned = conn.execute(
        "SELECT 1 FROM deep_scans WHERE user_id='me' AND call_id=? AND prompt_version=?",
        (call_id, PROMPT_VERSION_DEEP),
    ).fetchone()
    assert scanned is not None
    # LLMClient walked через M3-кэш (cache_conn=conn) — не свой параллельный кэш
    assert MC.call_args.kwargs["cache_conn"] is conn
    assert MC.call_args.kwargs["prompt_version"] == PROMPT_VERSION_DEEP


def test_quote_not_in_chunk_dropped_entirely():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    call_id = _call(conn, "me", cid)
    _transcript(conn, call_id, [("OTHER", "короткая реплика без обещаний")])
    conn.commit()

    resp = _llm_response([{"type": "promise", "who": "OTHER", "what": "выдумано",
                            "quote": "этого текста не было в разговоре", "deadline": None}])
    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.return_value = resp
        stats = run_deep_extract(conn, "me", llm_url="http://fake")

    assert stats["items_saved"] == 0
    assert stats["items_dropped"] == 1
    n = conn.execute("SELECT COUNT(*) FROM deep_facts").fetchone()[0]
    assert n == 0


def test_who_not_owner_or_other_dropped():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    call_id = _call(conn, "me", cid)
    _transcript(conn, call_id, [("UNKNOWN", "фраза без атрибуции говорящего")])
    conn.commit()

    resp = _llm_response([{"type": "fact", "who": "UNKNOWN", "what": "что-то",
                            "quote": "фраза без атрибуции", "deadline": None}])
    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.return_value = resp
        stats = run_deep_extract(conn, "me", llm_url="http://fake")

    assert stats["items_saved"] == 0
    assert stats["items_dropped"] == 1


def test_empty_what_dropped():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    call_id = _call(conn, "me", cid)
    _transcript(conn, call_id, [("OWNER", "я обязательно это сделаю")])
    conn.commit()

    resp = _llm_response([{"type": "promise", "who": "OWNER", "what": "  ",
                            "quote": "обязательно это сделаю", "deadline": None}])
    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.return_value = resp
        stats = run_deep_extract(conn, "me", llm_url="http://fake")

    assert stats["items_saved"] == 0
    assert stats["items_dropped"] == 1


def test_invalid_type_dropped():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    call_id = _call(conn, "me", cid)
    _transcript(conn, call_id, [("OWNER", "я обязательно это сделаю")])
    conn.commit()

    resp = _llm_response([{"type": "opinion", "who": "OWNER", "what": "сделать",
                            "quote": "обязательно это сделаю", "deadline": None}])
    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.return_value = resp
        stats = run_deep_extract(conn, "me", llm_url="http://fake")

    assert stats["items_saved"] == 0
    assert stats["items_dropped"] == 1


def test_dedup_across_overlapping_chunks():
    """Один и тот же факт, извлечённый из нескольких чанков одного звонка -> 1 строка."""
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    call_id = _call(conn, "me", cid)
    long_text = ("маркерслово " * 2000).strip()  # >9000 симв -> гарантированно >1 чанка
    _transcript(conn, call_id, [("OTHER", long_text)])
    conn.commit()

    calls_made = []

    def fake_complete(messages, **kw):
        calls_made.append(messages)
        return _llm_response([{"type": "promise", "who": "OTHER", "what": "перезвонить",
                                "quote": "маркерслово", "deadline": None}])

    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.side_effect = fake_complete
        stats = run_deep_extract(conn, "me", llm_url="http://fake")

    assert len(calls_made) > 1  # реально прошло несколько чанков
    assert stats["items_saved"] == 1
    assert stats["items_dropped"] == len(calls_made) - 1
    n = conn.execute("SELECT COUNT(*) FROM deep_facts WHERE user_id='me'").fetchone()[0]
    assert n == 1


# ── Повторный прогон / force / фильтры отбора ────────────────────────────

def test_repeat_run_without_force_makes_no_new_llm_calls():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    call_id = _call(conn, "me", cid)
    _transcript(conn, call_id, [("OTHER", "я перезвоню завтра")])
    conn.commit()

    resp = _llm_response([{"type": "promise", "who": "OTHER", "what": "перезвонить",
                            "quote": "перезвоню завтра", "deadline": "завтра"}])
    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.return_value = resp
        run_deep_extract(conn, "me", llm_url="http://fake")
        first_calls = MC.return_value.complete.call_count
        stats2 = run_deep_extract(conn, "me", llm_url="http://fake")  # без --force

    assert first_calls == 1
    assert MC.return_value.complete.call_count == first_calls  # 0 новых HTTP
    assert stats2["calls_seen"] == 0
    n = conn.execute("SELECT COUNT(*) FROM deep_facts").fetchone()[0]
    assert n == 1  # без новых строк


def test_force_rescans_already_scanned_call():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    call_id = _call(conn, "me", cid)
    _transcript(conn, call_id, [("OTHER", "я перезвоню завтра")])
    conn.commit()

    resp = _llm_response([{"type": "promise", "who": "OTHER", "what": "перезвонить",
                            "quote": "перезвоню завтра", "deadline": "завтра"}])
    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.return_value = resp
        run_deep_extract(conn, "me", llm_url="http://fake")
        stats2 = run_deep_extract(conn, "me", llm_url="http://fake", force=True)

    assert stats2["calls_seen"] == 1
    assert stats2["calls_scanned"] == 1
    assert MC.return_value.complete.call_count == 2  # пересчёт реально вызвал LLM повторно


def test_min_duration_filters_short_calls():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    short_id = _call(conn, "me", cid, duration=100)
    long_id = _call(conn, "me", cid, duration=900)
    _transcript(conn, short_id, [("OTHER", "коротко")])
    _transcript(conn, long_id, [("OTHER", "длинный разговор про обещания")])
    conn.commit()

    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.return_value = _llm_response([])
        stats = run_deep_extract(conn, "me", llm_url="http://fake", min_duration=600)

    assert stats["calls_seen"] == 1
    assert stats["calls_scanned"] == 1
    scanned = {r[0] for r in conn.execute("SELECT call_id FROM deep_scans").fetchall()}
    assert scanned == {long_id}


def test_min_priority_requires_analysis_row():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    high_id = _call(conn, "me", cid)
    no_analysis_id = _call(conn, "me", cid)
    _analysis(conn, high_id, priority=80)
    _transcript(conn, high_id, [("OTHER", "важный разговор")])
    _transcript(conn, no_analysis_id, [("OTHER", "звонок без анализа")])
    conn.commit()

    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.return_value = _llm_response([])
        stats = run_deep_extract(conn, "me", llm_url="http://fake", min_priority=50)

    assert stats["calls_seen"] == 1  # transcribed-без-анализа не проходит с min_priority
    scanned = {r[0] for r in conn.execute("SELECT call_id FROM deep_scans").fetchall()}
    assert scanned == {high_id}


def test_note_call_type_excluded():
    """F4 голосовые заметки (call_type='note') — не разговор с контактом, вне охвата M8."""
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    note_id = _call(conn, "me", cid, call_type="note")
    _transcript(conn, note_id, [("OWNER", "заметка самому себе про обещание")])
    conn.commit()

    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        stats = run_deep_extract(conn, "me", llm_url="http://fake")

    assert stats["calls_seen"] == 0
    MC.assert_not_called()


def test_user_isolation():
    repo = _repo()
    _user(repo, "me")
    _user(repo, "other")
    conn = repo._get_conn()
    cid_me = _contact(conn, "me")
    cid_other = _contact(conn, "other")
    call_me = _call(conn, "me", cid_me)
    call_other = _call(conn, "other", cid_other)
    _transcript(conn, call_me, [("OTHER", "я перезвоню завтра по делу me")])
    _transcript(conn, call_other, [("OTHER", "я перезвоню завтра по делу other")])
    conn.commit()

    resp_me = _llm_response([{"type": "promise", "who": "OTHER", "what": "перезвонить",
                               "quote": "перезвоню завтра по делу me", "deadline": None}])
    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        MC.return_value.complete.return_value = resp_me
        run_deep_extract(conn, "me", llm_url="http://fake")

    rows = conn.execute("SELECT user_id, call_id FROM deep_facts").fetchall()
    assert len(rows) == 1
    assert rows[0]["user_id"] == "me" and rows[0]["call_id"] == call_me
    scanned_other = conn.execute(
        "SELECT 1 FROM deep_scans WHERE user_id='other'"
    ).fetchone()
    assert scanned_other is None  # прогон был только для 'me'


def test_empty_selection_never_touches_llm_client():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    # ни одного подходящего звонка вообще
    with mock.patch("callprofiler.insight.deep_extract.LLMClient") as MC:
        stats = run_deep_extract(conn, "me", llm_url="http://fake")
    assert stats["calls_seen"] == 0
    MC.assert_not_called()  # пустая выборка не должна бить в сеть health-check'ом


# ── recent_deep_lines (digest-потребитель) ───────────────────────────────

def test_recent_deep_lines_guarded_without_table():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    assert recent_deep_lines(conn, "me") == []  # deep_facts ещё не создана — не 500


def test_recent_deep_lines_only_promise_debt_within_window_truncated():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    call_id = _call(conn, "me", cid, dt="2026-07-15T10:00:00")
    apply_insight_schema(conn)
    long_what = "обещание " * 60  # > 300 симв после сборки строки
    conn.execute(
        "INSERT INTO deep_facts(user_id,item_key,call_id,contact_id,type,who,what,quote,"
        "prompt_version) VALUES (?,?,?,?,?,?,?,?,?)",
        ("me", "k1", call_id, cid, "promise", "OTHER", long_what, "цитата", PROMPT_VERSION_DEEP),
    )
    conn.execute(
        "INSERT INTO deep_facts(user_id,item_key,call_id,contact_id,type,who,what,quote,"
        "prompt_version) VALUES (?,?,?,?,?,?,?,?,?)",
        ("me", "k2", call_id, cid, "fact", "OTHER", "просто факт, не обещание",
         "цитата2", PROMPT_VERSION_DEEP),
    )
    conn.commit()

    lines = recent_deep_lines(conn, "me", days=30, top=5)
    assert len(lines) == 1  # только promise/debt
    assert all(len(l) <= 300 for l in lines)


# ── digest extra_sections (A1 интеграция) ────────────────────────────────

def test_build_digest_extra_sections_rendered_and_skipped_when_empty():
    repo = _repo()
    _user(repo)
    conn = repo._get_conn()

    with_section = build_digest(conn, "me", extra_sections=[("🔎 Секция", ["- строка"])])
    assert "🔎 Секция" in with_section
    assert "- строка" in with_section

    without_section = build_digest(conn, "me", extra_sections=[("🔎 Пусто", [])])
    assert "🔎 Пусто" not in without_section


# ── дашборд-досье: guarded без таблицы, наполнено с таблицей ─────────────

def test_dossier_deep_facts_guarded_without_table(tmp_path):
    from callprofiler.dashboard.db_reader import DashboardDBReader

    db = tmp_path / "cp.db"
    repo = Repository(str(db))
    repo.init_db()
    _user(repo)
    cid = _contact(repo._get_conn())
    repo._get_conn().commit()
    repo.close()

    reader = DashboardDBReader(str(db))
    reader.connect()
    dossier = reader.get_person_dossier(cid, "me")
    reader.close()

    assert dossier["deep_facts"] == []  # deep_facts не создана — не 500


def test_dossier_deep_facts_populated_top5_by_created_at(tmp_path):
    from callprofiler.dashboard.db_reader import DashboardDBReader

    db = tmp_path / "cp2.db"
    repo = Repository(str(db))
    repo.init_db()
    _user(repo)
    conn = repo._get_conn()
    cid = _contact(conn)
    call_id = _call(conn, "me", cid)
    apply_insight_schema(conn)
    for i in range(3):
        conn.execute(
            "INSERT INTO deep_facts(user_id,item_key,call_id,contact_id,type,who,what,quote,"
            "prompt_version) VALUES (?,?,?,?,?,?,?,?,?)",
            ("me", f"k{i}", call_id, cid, "fact", "OTHER", f"факт {i}", f"цитата {i}",
             PROMPT_VERSION_DEEP),
        )
    conn.commit()
    repo.close()

    reader = DashboardDBReader(str(db))
    reader.connect()
    dossier = reader.get_person_dossier(cid, "me")
    reader.close()

    assert len(dossier["deep_facts"]) == 3
    assert {f["what"] for f in dossier["deep_facts"]} == {"факт 0", "факт 1", "факт 2"}
