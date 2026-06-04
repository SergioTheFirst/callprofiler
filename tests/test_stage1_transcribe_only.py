# -*- coding: utf-8 -*-
"""Stage-1 transcribe-only: транскрибированный звонок терминализуется как
'transcribed' (LLM-анализ отложён на Stage-2), не залипает и не реклаймится.

Регрессия: при ``enable_llm_analysis=False`` ``process_batch`` не доводил звонок
до терминального статуса — Pass C ставит stage 2, но статус остаётся
'transcribing', Phase 4 deliver гейтит ``stage<3`` → звонок навсегда залипал и
``get_stalled_calls`` (status NOT IN new/done/error) реклаймил его каждый прогон
(бесконечный stall-loop, дашборд вечно «transcribing»). Фикс: терминальный
статус 'transcribed' + исключение из get_stalled_calls.
"""

from callprofiler.config import Config
from callprofiler.db.repository import Repository
from callprofiler.pipeline.orchestrator import Orchestrator


def _repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    r.add_user("me", "Me", None, "", "", "")
    return r


def test_transcribed_is_terminal_not_stalled():
    r = _repo()
    in_progress = r.create_call("me", None, "in", None, "a.mp3", "md5a", "a.mp3")
    r.update_call_status(in_progress, "transcribing")
    terminal = r.create_call("me", None, "in", None, "b.mp3", "md5b", "b.mp3")
    r.update_call_status(terminal, "transcribed")

    stalled = {c["call_id"] for c in r.get_stalled_calls("me")}
    assert in_progress in stalled       # промежуточный статус — реклаймится
    assert terminal not in stalled      # Stage-1 терминальный — НЕ реклаймится


def test_batch_transcribe_only_terminalizes_to_transcribed():
    r = _repo()
    cid = r.create_call("me", None, "in", None, "x.mp3", "md5x", "x.mp3")
    r.update_pipeline_stage(cid, 2)            # транскрипт уже в БД (stage 2)
    r.update_call_status(cid, "transcribing")  # как оставляет Pass B/C

    cfg = Config()
    cfg.features.enable_llm_analysis = False
    cfg.features.enable_diarization = False
    o = Orchestrator(cfg, r)

    o.process_batch([cid])

    row = r._get_conn().execute(
        "SELECT status FROM calls WHERE call_id=?", (cid,)
    ).fetchone()
    assert row["status"] == "transcribed"
    # и больше не считается зависшим → не будет переподхвачен resume
    assert cid not in {c["call_id"] for c in r.get_stalled_calls("me")}


def test_batch_keeps_done_calls_done_when_analysis_disabled():
    """Уже доведённый звонок (status='done') не трогается при отключённом анализе."""
    r = _repo()
    cid = r.create_call("me", None, "in", None, "d.mp3", "md5d", "d.mp3")
    r.update_pipeline_stage(cid, 4)
    r.update_call_status(cid, "done")

    cfg = Config()
    cfg.features.enable_llm_analysis = False
    cfg.features.enable_diarization = False
    Orchestrator(cfg, r).process_batch([cid])

    row = r._get_conn().execute(
        "SELECT status FROM calls WHERE call_id=?", (cid,)
    ).fetchone()
    assert row["status"] == "done"
