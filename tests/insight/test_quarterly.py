"""Tests for quarterly social-universe report over aggregates (D3)."""
from unittest.mock import MagicMock, patch

import pytest

from callprofiler.db.repository import Repository
from callprofiler.insight.quarterly import PROMPT_VERSION_QREPORT, build_report, gather_aggregates


def _db(tmp_path):
    repo = Repository(str(tmp_path / "quarterly.db"))
    repo.init_db()
    repo.add_user(user_id="me", display_name="T", telegram_chat_id="0",
                  incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/r.wav")
    return repo, repo._get_conn()


def _contact(conn, name, user_id="me"):
    cur = conn.execute(
        "INSERT INTO contacts(user_id, phone_e164, display_name) VALUES (?,?,?)",
        (user_id, f"+7900{ord(name[-1])}", name),
    )
    return cur.lastrowid


def _call(conn, contact_id, call_datetime, user_id="me"):
    cur = conn.execute(
        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
        "source_filename, source_md5, status, duration_sec) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, contact_id, "IN", call_datetime, f"f{contact_id}-{call_datetime}.mp3",
         f"md5{contact_id}-{call_datetime}", "done", 60),
    )
    return cur.lastrowid


def _fake_llm_response(text):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"content": text}}]}
    return resp


def test_gather_aggregates_risers_fallers_correct_sign(tmp_path):
    repo, conn = _db(tmp_path)
    a = _contact(conn, "Alpha")
    b = _contact(conn, "Bravo")
    _call(conn, a, "2026-02-10T10:00:00")
    for i in range(5):
        _call(conn, a, f"2026-05-{10 + i:02d}T10:00:00")
    for i in range(5):
        _call(conn, b, f"2026-02-{10 + i:02d}T10:00:00")
    _call(conn, b, "2026-05-10T10:00:00")
    conn.commit()

    agg = gather_aggregates(conn, "me", "2026-Q2")
    by_cid = {d["contact_id"]: d for d in agg["risers_fallers"]}
    assert by_cid[a]["direction"] == "riser"
    assert by_cid[a]["delta"] == 4
    assert by_cid[b]["direction"] == "faller"
    assert by_cid[b]["delta"] == -4
    repo.close()


def test_gather_aggregates_no_data_still_returns_shape(tmp_path):
    repo, conn = _db(tmp_path)
    agg = gather_aggregates(conn, "me", "2026-Q2")
    reader_keys = {"period", "risers_fallers", "risk_shifts", "new_people", "unresolved", "dormant"}
    assert reader_keys.issubset(agg.keys())
    assert agg["risers_fallers"] == []
    repo.close()


def test_build_report_mock_llm_saves_db_and_file(tmp_path):
    repo, conn = _db(tmp_path)
    a = _contact(conn, "Alpha")
    _call(conn, a, "2026-05-10T10:00:00")
    conn.commit()
    reports_dir = tmp_path / "reports"

    with patch("callprofiler.insight.quarterly.requests.post",
               return_value=_fake_llm_response("# Отчёт\n\nВесенний квартал.")) as mock_post:
        result = build_report(conn, "me", "2026-Q2", reports_dir=reports_dir)

    assert mock_post.call_count == 1
    assert result["cached"] is False
    assert "Весенний квартал" in result["body_md"]

    row = conn.execute(
        "SELECT body_md FROM insight_reports WHERE user_id='me' AND period='2026-Q2' "
        "AND prompt_version=?", (PROMPT_VERSION_QREPORT,),
    ).fetchone()
    assert row is not None and "Весенний квартал" in row["body_md"]

    out_file = reports_dir / "me-2026-Q2.md"
    assert out_file.exists()
    assert "Весенний квартал" in out_file.read_text(encoding="utf-8")
    repo.close()


def test_second_call_without_force_skips_http(tmp_path):
    repo, conn = _db(tmp_path)
    a = _contact(conn, "Alpha")
    _call(conn, a, "2026-05-10T10:00:00")
    conn.commit()
    reports_dir = tmp_path / "reports"

    with patch("callprofiler.insight.quarterly.requests.post",
               return_value=_fake_llm_response("текст")) as mock_post:
        build_report(conn, "me", "2026-Q2", reports_dir=reports_dir)
        assert mock_post.call_count == 1

        result2 = build_report(conn, "me", "2026-Q2", reports_dir=reports_dir)
        assert mock_post.call_count == 1  # не вырос — HTTP не звался
        assert result2["cached"] is True
    repo.close()


def test_force_bypasses_cache_and_calls_http_again(tmp_path):
    repo, conn = _db(tmp_path)
    a = _contact(conn, "Alpha")
    _call(conn, a, "2026-05-10T10:00:00")
    conn.commit()
    reports_dir = tmp_path / "reports"

    with patch("callprofiler.insight.quarterly.requests.post",
               return_value=_fake_llm_response("текст")) as mock_post:
        build_report(conn, "me", "2026-Q2", reports_dir=reports_dir)
        build_report(conn, "me", "2026-Q2", reports_dir=reports_dir, force=True)
        assert mock_post.call_count == 2
    repo.close()


def test_llm_down_raises_runtime_error(tmp_path):
    repo, conn = _db(tmp_path)
    a = _contact(conn, "Alpha")
    _call(conn, a, "2026-05-10T10:00:00")
    conn.commit()

    with patch("callprofiler.insight.quarterly.requests.post",
               side_effect=ConnectionError("no server")):
        with pytest.raises(RuntimeError):
            build_report(conn, "me", "2026-Q2", reports_dir=tmp_path / "reports")
    repo.close()
