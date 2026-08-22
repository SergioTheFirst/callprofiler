# -*- coding: utf-8 -*-
"""test_doctor.py — M1: преполётная проверка окружения/схемы (ozalup2.md §3.1).

Всё офлайн: subprocess/requests мокаются, реальная сеть/ffmpeg не вызываются.
"""
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from callprofiler.doctor import Check, build_doctor_message, format_report, run_checks


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


# ── F6: heartbeat + плановые чеки живучести ────────────────────────────

def _cfg_with_pipeline(tmp_path, interval=30):
    return SimpleNamespace(
        data_dir=str(tmp_path),
        pipeline=SimpleNamespace(watch_interval_sec=interval),
        models=SimpleNamespace(asr_backend="whisper", gigaam_model_dir="", llm_url=""),
    )


def test_heartbeat_missing_file_warns(tmp_path):
    checks = run_checks(_cfg_with_pipeline(tmp_path), conn=None)
    hb = next(c for c in checks if c.name == "heartbeat")
    assert hb.status == "WARN"


def test_heartbeat_fresh_ok(tmp_path):
    (tmp_path / "watcher.heartbeat").write_text("now", encoding="utf-8")
    checks = run_checks(_cfg_with_pipeline(tmp_path), conn=None)
    hb = next(c for c in checks if c.name == "heartbeat")
    assert hb.status == "OK"


def test_heartbeat_stale_fails(tmp_path):
    import os
    import time as time_mod

    hb_path = tmp_path / "watcher.heartbeat"
    hb_path.write_text("old", encoding="utf-8")
    old_ts = time_mod.time() - 1000  # >> 3*30s
    os.utime(hb_path, (old_ts, old_ts))
    checks = run_checks(_cfg_with_pipeline(tmp_path, interval=30), conn=None)
    hb = next(c for c in checks if c.name == "heartbeat")
    assert hb.status == "FAIL"


def _insert_call(conn, status="new", hours_ago=0, source_filename="a.mp3"):
    conn.execute(
        "INSERT INTO calls (user_id, contact_id, direction, source_filename, source_md5, "
        "audio_path, status, created_at) VALUES ('me', NULL, 'incoming', ?, ?, ?, ?, "
        "datetime('now', ?))",
        (source_filename, f"md5-{source_filename}-{hours_ago}", "/a.mp3", status,
         f"-{hours_ago} hours"),
    )
    conn.commit()


def test_queue_stuck_detects_old_non_terminal(tmp_path):
    conn = _schema_conn(tmp_path)
    _insert_call(conn, status="normalizing", hours_ago=8)
    checks = run_checks(_fake_config(tmp_path), conn=conn)
    c = next(x for x in checks if x.name == "queue-stuck")
    assert c.status == "FAIL"
    assert "call_id=" in c.detail


def test_queue_stuck_ignores_terminal_and_recent(tmp_path):
    conn = _schema_conn(tmp_path)
    _insert_call(conn, status="done", hours_ago=8)
    _insert_call(conn, status="normalizing", hours_ago=1)
    checks = run_checks(_fake_config(tmp_path), conn=conn)
    c = next(x for x in checks if x.name == "queue-stuck")
    assert c.status == "OK"


def test_error_burst_warns_over_threshold(tmp_path):
    conn = _schema_conn(tmp_path)
    for i in range(3):
        _insert_call(conn, status="error", hours_ago=1, source_filename=f"e{i}.mp3")
    _insert_call(conn, status="done", hours_ago=1, source_filename="ok.mp3")
    checks = run_checks(_fake_config(tmp_path), conn=conn)
    c = next(x for x in checks if x.name == "error-burst")
    assert c.status == "WARN"


def test_error_burst_ok_under_threshold(tmp_path):
    conn = _schema_conn(tmp_path)
    _insert_call(conn, status="error", hours_ago=1, source_filename="e.mp3")
    for i in range(10):
        _insert_call(conn, status="done", hours_ago=1, source_filename=f"ok{i}.mp3")
    checks = run_checks(_fake_config(tmp_path), conn=conn)
    c = next(x for x in checks if x.name == "error-burst")
    assert c.status == "OK"


def test_disk_fail_when_low(tmp_path):
    with mock.patch(
        "callprofiler.doctor.shutil.disk_usage",
        return_value=SimpleNamespace(total=0, used=0, free=1 * 1024 ** 3),
    ):
        checks = run_checks(_fake_config(tmp_path), conn=None)
    c = next(x for x in checks if x.name == "disk")
    assert c.status == "FAIL"


def test_disk_ok_when_plenty(tmp_path):
    with mock.patch(
        "callprofiler.doctor.shutil.disk_usage",
        return_value=SimpleNamespace(total=0, used=0, free=50 * 1024 ** 3),
    ):
        checks = run_checks(_fake_config(tmp_path), conn=None)
    c = next(x for x in checks if x.name == "disk")
    assert c.status == "OK"


def test_reminders_stale_skip_when_table_missing(tmp_path):
    conn = _schema_conn(tmp_path)  # no insight schema applied -> no reminders table
    checks = run_checks(_fake_config(tmp_path), conn=conn)
    c = next(x for x in checks if x.name == "reminders-stale")
    assert c.status == "SKIP"


def test_reminders_stale_warns_when_overdue(tmp_path):
    conn = _schema_conn(tmp_path)
    from callprofiler.insight.repository import apply_insight_schema

    apply_insight_schema(conn)
    conn.execute(
        "INSERT INTO reminders(user_id,item_kind,item_key,text,due_at,chat_id) "
        "VALUES ('me','promise','1','x', datetime('now','-48 hours'), 555)"
    )
    conn.commit()
    checks = run_checks(_fake_config(tmp_path), conn=conn)
    c = next(x for x in checks if x.name == "reminders-stale")
    assert c.status == "WARN"


def test_input_silence_warns_when_both_stale(tmp_path):
    conn = _schema_conn(tmp_path)
    # incoming_dir отдельно от tmp_path — иначе rglob() находит свежую cp.db
    empty_incoming = tmp_path / "in_empty"
    empty_incoming.mkdir()
    conn.execute("UPDATE users SET incoming_dir = ? WHERE user_id='me'", (str(empty_incoming),))
    conn.commit()
    _insert_call(conn, status="done", hours_ago=200)
    checks = run_checks(_fake_config(tmp_path), conn=conn)
    c = next(x for x in checks if x.name == "input-silence")
    assert c.status == "WARN"


def test_input_silence_ok_when_call_recent(tmp_path):
    conn = _schema_conn(tmp_path)
    _insert_call(conn, status="done", hours_ago=1)
    checks = run_checks(_fake_config(tmp_path), conn=conn)
    c = next(x for x in checks if x.name == "input-silence")
    assert c.status == "OK"


def test_build_doctor_message_header_ok_vs_fail():
    ok_msg = build_doctor_message([Check("a", "OK", ""), Check("b", "WARN", "meh")])
    assert ok_msg.startswith("🟢 Осмотр пройден")

    fail_msg = build_doctor_message([Check("a", "OK", ""), Check("b", "FAIL", "broken")])
    assert fail_msg.startswith("🔴 Есть проблемы (1 FAIL)")


def test_cmd_doctor_send_sends_to_users_with_chat_id(tmp_path):
    from callprofiler.cli.commands import doctor as doctor_cli
    from callprofiler.db.repository import Repository

    db_path = tmp_path / "db" / "callprofiler.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo = Repository(str(db_path))
    repo.init_db()
    repo.add_user(user_id="me", display_name="Me", telegram_chat_id="555",
                  incoming_dir=str(tmp_path), sync_dir=str(tmp_path),
                  ref_audio=str(tmp_path / "ref.wav"))
    repo.add_user(user_id="nochat", display_name="NoChat", telegram_chat_id=None,
                  incoming_dir=str(tmp_path), sync_dir=str(tmp_path),
                  ref_audio=str(tmp_path / "ref.wav"))

    cfg = SimpleNamespace(data_dir=str(tmp_path), models=SimpleNamespace(
        asr_backend="whisper", gigaam_model_dir="", llm_url=""))

    with mock.patch("callprofiler.config.load_config", return_value=cfg):
        with mock.patch.object(doctor_cli, "run_checks", return_value=[Check("a", "OK", "")]):
            with mock.patch(
                "callprofiler.deliver.telegram_sender.send_telegram_message", return_value=True
            ) as sender:
                args = SimpleNamespace(config="configs/base.yaml", verbose=False,
                                        user_id=None, send=True)
                doctor_cli.cmd_doctor(args)

    assert sender.call_count == 1
    assert sender.call_args.args[0] == "555"


# ── watcher: heartbeat write + плановый doctor-триггер ──────────────────

def _watcher_repo(tmp_path):
    from callprofiler.db.repository import Repository

    repo = Repository(":memory:")
    repo.init_db()
    repo.add_user(user_id="me", display_name="Me", telegram_chat_id="555",
                  incoming_dir=str(tmp_path), sync_dir=str(tmp_path),
                  ref_audio=str(tmp_path / "ref.wav"))
    return repo


def test_watcher_writes_heartbeat_file(tmp_path):
    from callprofiler.pipeline.watcher import FileWatcher

    cfg = SimpleNamespace(data_dir=str(tmp_path))
    watcher = FileWatcher(cfg, _watcher_repo(tmp_path), mock.MagicMock(), mock.MagicMock())
    watcher._write_heartbeat()
    assert (tmp_path / "watcher.heartbeat").exists()


def test_watcher_doctor_report_once_per_day(tmp_path):
    from datetime import datetime

    from callprofiler.insight.repository import get_doctor_state
    from callprofiler.pipeline.watcher import FileWatcher

    cfg = SimpleNamespace(data_dir=str(tmp_path))
    repo = _watcher_repo(tmp_path)
    watcher = FileWatcher(cfg, repo, mock.MagicMock(), mock.MagicMock())
    fake_now = datetime(2026, 7, 17, 9, 5).astimezone()

    with mock.patch("callprofiler.pipeline.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        with mock.patch("callprofiler.doctor.run_checks", return_value=[Check("a", "OK", "")]):
            with mock.patch(
                "callprofiler.deliver.telegram_sender.send_telegram_message", return_value=True
            ) as sender:
                watcher._maybe_send_doctor_report()
                watcher._maybe_send_doctor_report()

    sender.assert_called_once()
    assert get_doctor_state(repo._get_conn(), "me") == fake_now.date().isoformat()


def test_watcher_doctor_report_skips_before_9am(tmp_path):
    from datetime import datetime

    from callprofiler.pipeline.watcher import FileWatcher

    cfg = SimpleNamespace(data_dir=str(tmp_path))
    watcher = FileWatcher(cfg, _watcher_repo(tmp_path), mock.MagicMock(), mock.MagicMock())
    fake_now = datetime(2026, 7, 17, 8, 59).astimezone()

    with mock.patch("callprofiler.pipeline.watcher.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        with mock.patch(
            "callprofiler.deliver.telegram_sender.send_telegram_message"
        ) as sender:
            watcher._maybe_send_doctor_report()
    sender.assert_not_called()


def test_backup_and_dead_letters_checks(tmp_path):
    """T-21: нет бэкапа → WARN; error с исчерпанными повторами → WARN, иначе OK."""
    from callprofiler.doctor import run_checks
    conn = _schema_conn(tmp_path)
    cfg = _fake_config(tmp_path)
    by = {c.name: c for c in run_checks(cfg, conn=conn)}
    assert by["backup"].status == "WARN"
    assert by["dead-letters"].status == "OK"
    conn.execute("INSERT INTO users(user_id, display_name, incoming_dir, sync_dir, ref_audio) VALUES ('u1','U','C:/tmp/in','C:/tmp/sync','C:/tmp/ref.wav')")
    conn.execute("INSERT INTO calls(user_id, status, retry_count, source_filename, source_md5, audio_path) "
                 "VALUES ('u1','error', 99, 'a.mp3', 'm', 'p')")
    conn.commit()
    by = {c.name: c for c in run_checks(cfg, conn=conn)}
    assert by["dead-letters"].status == "WARN" and "1" in by["dead-letters"].detail
