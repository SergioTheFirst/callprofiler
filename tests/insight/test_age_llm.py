# -*- coding: utf-8 -*-
"""test_age_llm.py — Ф2 плана возраста: LLM-пасс (mock llama-server).

Подстройка под локальный Qwen3.5 (llama-server, OpenAI-формат): <think>-блоки
и markdown-fences срезаются парсером; verbatim-гейт против галлюцинаций;
memoization по sha1(prompt+версия) — повторные прогоны не платят токенами;
det-пересчёт (autofit) переиспользует оплаченный LLM-результат.
"""
import json
from unittest import mock

from callprofiler.db.repository import Repository
from callprofiler.insight import repository as insight_repo
from callprofiler.insight.age_estimate import PROMPT_VERSION_AGE, run_age_estimate


def _db(tmp_path, name="agellm.db"):
    repo = Repository(str(tmp_path / name))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav",
    )
    conn = repo._get_conn()
    insight_repo.apply_insight_schema(conn)
    return repo, conn


_N = [0]


def _contact(conn):
    _N[0] += 1
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) "
        "VALUES ('me', ?, 'Иван')", (f"+7911000{_N[0]:04d}",))
    return cur.lastrowid


def _call(conn, cid, dt):
    _N[0] += 1
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
        "source_filename, source_md5, status) VALUES ('me', ?, 'IN', ?, ?, ?, 'done')",
        (cid, dt, f"g{_N[0]}.mp3", f"md5g{_N[0]}"),
    )
    return cur.lastrowid


def _say(conn, call_id, speaker, text):
    conn.execute(
        "INSERT INTO transcripts(call_id, start_ms, end_ms, text, speaker) "
        "VALUES (?, 0, 1000, ?, ?)", (call_id, text, speaker),
    )


def _row(conn, cid):
    cur = conn.execute(
        "SELECT age_low, age_high, age_point, birth_year_low, birth_year_high, "
        "birth_year_point, confidence, method, evidence, prompt_version, "
        "llm_prompt_hash, llm_result FROM contact_age_estimates "
        "WHERE contact_id = ?", (cid,))
    r = cur.fetchone()
    return dict(zip([d[0] for d in cur.description], tuple(r))) if r else None


def _resp(content):
    m = mock.Mock()
    m.raise_for_status = mock.Mock()
    m.json.return_value = {"choices": [{"message": {"content": content}}]}
    return m


def _llm_json(**over):
    d = {"age_low": 40, "age_high": 55, "age_point": 48, "confidence": 35,
         "evidence": [{"quote": "дискотека была отличная", "signal": "лексика"}],
         "reasoning": "сленг поколения"}
    d.update(over)
    return json.dumps(d, ensure_ascii=False)


def test_llm_parsed_with_think_and_fences(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2024-03-15T10:00:00")
    _say(conn, call, "OTHER", "дискотека была отличная, как в молодости")
    content = "<think>хм, лексика 80-х</think>```json\n" + _llm_json() + "\n```"
    with mock.patch("requests.post", return_value=_resp(content)) as mp:
        stats = run_age_estimate(conn, "me", reference_now=2026, use_llm=True,
                                 llm_url="http://test/v1")
    assert mp.call_count == 1 and stats["llm_called"] == 1
    row = _row(conn, cid)
    assert row["method"] == "llm"
    assert row["prompt_version"] == PROMPT_VERSION_AGE
    # 40-55 лет на 2024 → год рождения 1969-1984 → возраст к 2026: 42-57
    assert (row["birth_year_low"], row["birth_year_high"]) == (1969, 1984)
    assert (row["age_low"], row["age_high"]) == (42, 57)
    assert row["confidence"] <= 50  # лексика — слабый сигнал
    repo.close()


def test_hallucinated_quote_dropped_and_penalized(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2024-03-15T10:00:00")
    _say(conn, call, "OTHER", "дискотека была отличная, как в молодости")
    content = _llm_json(evidence=[
        {"quote": "дискотека была отличная", "signal": "лексика"},
        {"quote": "я родился при Брежневе", "signal": "реалия"},  # выдумка
    ])
    with mock.patch("requests.post", return_value=_resp(content)):
        run_age_estimate(conn, "me", reference_now=2026, use_llm=True,
                         llm_url="http://test/v1")
    row = _row(conn, cid)
    assert row["confidence"] == 20  # 35 − 15 за галлюцинацию
    wrapped = json.loads(row["llm_result"])
    assert wrapped["dropped"] == 1 and len(wrapped["evidence"]) == 1
    repo.close()


def test_all_hallucinated_discards_llm_but_caches(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2024-03-15T10:00:00")
    _say(conn, call, "OTHER", "дискотека была отличная, как в молодости")
    content = _llm_json(evidence=[{"quote": "полная выдумка", "signal": "лексика"}])
    with mock.patch("requests.post", return_value=_resp(content)) as mp:
        run_age_estimate(conn, "me", reference_now=2026, use_llm=True,
                         llm_url="http://test/v1")
        # повторный run: hash совпал → сервер не дёргаем (даже за мусор не платим дважды)
        run_age_estimate(conn, "me", reference_now=2026, use_llm=True,
                         llm_url="http://test/v1")
    assert mp.call_count == 1
    row = _row(conn, cid)
    assert row["age_point"] is None and row["confidence"] == 1
    assert json.loads(row["llm_result"])["valid"] is False
    repo.close()


def test_llm_cache_hit_no_second_call(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2024-03-15T10:00:00")
    _say(conn, call, "OTHER", "дискотека была отличная, как в молодости")
    with mock.patch("requests.post", return_value=_resp(_llm_json())) as mp:
        run_age_estimate(conn, "me", reference_now=2026, use_llm=True,
                         llm_url="http://test/v1")
        stats = run_age_estimate(conn, "me", reference_now=2026, use_llm=True,
                                 llm_url="http://test/v1")
    assert mp.call_count == 1
    assert stats["llm_cached"] == 1 and stats["llm_called"] == 0
    repo.close()


def test_det_rerun_reuses_stored_llm_without_call(tmp_path):
    """Динамика: ночной det-пересчёт не теряет оплаченный LLM-сигнал."""
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2024-03-15T10:00:00")
    _say(conn, call, "OTHER", "дискотека была отличная, как в молодости")
    with mock.patch("requests.post", return_value=_resp(_llm_json())) as mp:
        run_age_estimate(conn, "me", reference_now=2026, use_llm=True,
                         llm_url="http://test/v1")
        run_age_estimate(conn, "me", reference_now=2026, use_llm=False)
    assert mp.call_count == 1
    row = _row(conn, cid)
    assert row["age_point"] is not None and row["method"] == "llm"
    repo.close()


def test_llm_conflict_det_priority(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2024-03-15T10:00:00")
    _say(conn, call, "OTHER", "мне 30 лет, и дискотека была отличная")
    content = _llm_json(age_low=50, age_high=60, evidence=[
        {"quote": "дискотека была отличная", "signal": "лексика"}])
    with mock.patch("requests.post", return_value=_resp(content)):
        run_age_estimate(conn, "me", reference_now=2026, use_llm=True,
                         llm_url="http://test/v1")
    row = _row(conn, cid)
    # детерминированный интервал не сдвинут, conf упал на 15
    assert (row["birth_year_low"], row["birth_year_high"]) == (1993, 1994)
    assert row["confidence"] == 75  # 90 − 15
    assert row["method"] == "combined"
    repo.close()


def test_llm_error_falls_back_to_det(tmp_path):
    repo, conn = _db(tmp_path)
    cid = _contact(conn)
    call = _call(conn, cid, "2021-03-15T10:00:00")
    _say(conn, call, "OTHER", "мне 45 лет, какие танцы")
    with mock.patch("requests.post", side_effect=ConnectionError("refused")):
        stats = run_age_estimate(conn, "me", reference_now=2026, use_llm=True,
                                 llm_url="http://test/v1")
    assert stats["llm_called"] == 0
    row = _row(conn, cid)
    assert row["method"] == "marker" and row["llm_result"] is None
    repo.close()
