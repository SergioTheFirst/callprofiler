# -*- coding: utf-8 -*-
"""test_doctor.py — M1: преполётная проверка окружения/схемы (ozalup2.md §3.1).

Всё офлайн: subprocess/requests мокаются, реальная сеть/ffmpeg не вызываются.
"""
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from callprofiler.doctor import Check, format_report, run_checks


def _schema_conn(tmp_path) -> sqlite3.Connection:
    schema_path = Path(__file__).parent.parent / "src" / "callprofiler" / "db" / "schema.sql"
    db = tmp_path / "cp.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO users (user_id, display_name, incoming_dir, sync_dir, ref_audio) "
        f"VALUES ('me', 'Me', '{tmp_path}', '{tmp_path}', '{tmp_path / 'ref.wav'}')"
    )
    conn.commit()
    return conn


def _fake_config(tmp_path, asr_backend="whisper"):
    return SimpleNamespace(
        data_dir=str(tmp_path),
        models=SimpleNamespace(
            asr_backend=asr_backend,
            gigaam_model_dir="",
            llm_url="http://127.0.0.1:8080/v1/chat/completions",
        ),
    )


@pytest.fixture(autouse=True)
def _mock_subprocess_ffmpeg():
    """Реальный ffmpeg/ffprobe не звать — по умолчанию считать их найденными."""
    with mock.patch("callprofiler.doctor.subprocess.run") as m:
        m.return_value = SimpleNamespace(returncode=0)
        yield m


def test_db_schema_full_schema_ok(tmp_path):
    conn = _schema_conn(tmp_path)
    checks = run_checks(_fake_config(tmp_path), conn=conn)
    schema_check = next(c for c in checks if c.name == "db-schema")
    assert schema_check.status == "OK", schema_check.detail


def test_db_schema_missing_column_fails(tmp_path):
    db = tmp_path / "broken.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    # calls БЕЗ error_message — остальные required-таблицы не создаём вовсе
    conn.execute("CREATE TABLE calls (call_id INTEGER PRIMARY KEY, user_id TEXT, "
                 "status TEXT, pipeline_stage INTEGER, audio_path TEXT, "
                 "contact_id INTEGER, call_datetime TEXT)")
    conn.commit()
    checks = run_checks(_fake_config(tmp_path), conn=conn)
    schema_check = next(c for c in checks if c.name == "db-schema")
    assert schema_check.status == "FAIL"
    assert "calls.error_message" in schema_check.detail


def test_env_hf_unexpanded_var_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "${HF_TOKEN}")
    checks = run_checks(_fake_config(tmp_path), conn=None)
    hf_check = next(c for c in checks if c.name == "env-hf")
    assert hf_check.status == "FAIL"


def test_env_hf_empty_warns(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    checks = run_checks(_fake_config(tmp_path), conn=None)
    hf_check = next(c for c in checks if c.name == "env-hf")
    assert hf_check.status == "WARN"


def test_llm_connection_error_warns_not_fails(tmp_path):
    import requests
    with mock.patch("requests.get", side_effect=requests.exceptions.ConnectionError("refused")):
        checks = run_checks(_fake_config(tmp_path), conn=None)
    llm_check = next(c for c in checks if c.name == "llm")
    assert llm_check.status == "WARN"  # никогда FAIL — GPU sequential, сервер может спать


def test_llm_ok_when_health_200(tmp_path):
    with mock.patch("requests.get") as mget:
        mget.return_value = SimpleNamespace(status_code=200)
        checks = run_checks(_fake_config(tmp_path), conn=None)
    llm_check = next(c for c in checks if c.name == "llm")
    assert llm_check.status == "OK"


def test_paths_missing_data_dir_fails():
    cfg = SimpleNamespace(data_dir="C:\\this\\does\\not\\exist\\anywhere",
                           models=SimpleNamespace(asr_backend="whisper", gigaam_model_dir="",
                                                   llm_url=""))
    with mock.patch("requests.get", side_effect=Exception("no network")):
        checks = run_checks(cfg, conn=None)
    paths_check = next(c for c in checks if c.name == "paths")
    assert paths_check.status == "FAIL"


def test_models_gigaam_missing_dir_fails(tmp_path):
    cfg = _fake_config(tmp_path, asr_backend="gigaam")
    with mock.patch("requests.get", side_effect=Exception("no network")):
        checks = run_checks(cfg, conn=None)
    models_check = next(c for c in checks if c.name == "models")
    assert models_check.status == "FAIL"


def test_models_ref_audio_missing_warns(tmp_path):
    conn = _schema_conn(tmp_path)
    # ref_audio указан но файла нет на диске
    with mock.patch("requests.get", side_effect=Exception("no network")):
        checks = run_checks(_fake_config(tmp_path), conn=conn)
    models_check = next(c for c in checks if c.name == "models")
    assert models_check.status == "WARN"
    assert "ref_audio" in models_check.detail


def test_no_db_conn_skips_db_checks(tmp_path):
    with mock.patch("requests.get", side_effect=Exception("no network")):
        checks = run_checks(_fake_config(tmp_path), conn=None)
    assert next(c for c in checks if c.name == "db-schema").status == "SKIP"
    assert next(c for c in checks if c.name == "db-wal").status == "SKIP"


def test_check_never_raises_even_on_bad_config():
    """Полностью пустой/сломанный config -> все чеки завершаются Check, не исключением."""
    cfg = SimpleNamespace()  # ни data_dir, ни models
    checks = run_checks(cfg, conn=None)
    assert all(isinstance(c, Check) for c in checks)
    assert any(c.status == "FAIL" for c in checks)


def test_format_report_one_line_per_check():
    checks = [Check("a", "OK", "все хорошо"), Check("b", "FAIL", "сломано")]
    report = format_report(checks)
    lines = report.splitlines()
    assert len(lines) == 2
    assert "a" in lines[0] and "OK" in lines[0]
    assert "b" in lines[1] and "FAIL" in lines[1]


def test_exit_code_logic_fail_present_vs_absent():
    """Контракт cmd_doctor: FAIL в списке -> 1, иначе -> 0 (см. cli/commands/doctor.py)."""
    checks_fail = [Check("a", "OK", ""), Check("b", "FAIL", "")]
    checks_ok = [Check("a", "OK", ""), Check("b", "WARN", "")]
    assert (1 if any(c.status == "FAIL" for c in checks_fail) else 0) == 1
    assert (1 if any(c.status == "FAIL" for c in checks_ok) else 0) == 0


def test_cmd_doctor_returns_1_on_fail(tmp_path):
    from callprofiler.cli.commands import doctor as doctor_cli

    with mock.patch("callprofiler.config.load_config", return_value=_fake_config(tmp_path)):
        with mock.patch.object(
            doctor_cli, "run_checks",
            return_value=[Check("a", "OK", ""), Check("b", "FAIL", "broken")],
        ):
            args = SimpleNamespace(config="configs/base.yaml", verbose=False, user_id=None)
            code = doctor_cli.cmd_doctor(args)
    assert code == 1


def test_cmd_doctor_returns_0_when_clean(tmp_path):
    from callprofiler.cli.commands import doctor as doctor_cli

    with mock.patch("callprofiler.config.load_config", return_value=_fake_config(tmp_path)):
        with mock.patch.object(
            doctor_cli, "run_checks",
            return_value=[Check("a", "OK", ""), Check("b", "WARN", "meh")],
        ):
            args = SimpleNamespace(config="configs/base.yaml", verbose=False, user_id=None)
            code = doctor_cli.cmd_doctor(args)
    assert code == 0
