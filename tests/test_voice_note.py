# -*- coding: utf-8 -*-
"""test_voice_note.py — F4: голосовая заметка владельца → конвейер.

Покрывает: filename_parser (voicenote_* формат), ingester (call_type='note',
спец-контакт self:notes), repository (find_contact_by_name), orchestrator
(диаризация/анализ пропускаются, speaker=OWNER, caption-привязка), bot
(приём voice/audio, cap 50MB, allowlist).
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from callprofiler.config import Config
from callprofiler.db.repository import Repository
from callprofiler.ingest.filename_parser import parse_filename
from callprofiler.ingest.ingester import Ingester
from callprofiler.models import Segment
from callprofiler.pipeline.orchestrator import Orchestrator


# ── filename_parser ──────────────────────────────────────────────────────

def test_parse_voicenote_no_target():
    meta = parse_filename("voicenote_20260717-153000.ogg")
    assert meta.phone == "self:notes"
    assert meta.contact_name == "Мои заметки"
    assert meta.note_target_name is None
    assert meta.call_datetime == datetime(2026, 7, 17, 15, 30, 0)


def test_parse_voicenote_with_target():
    meta = parse_filename("voicenote_20260717-153000__Вася.ogg")
    assert meta.phone == "self:notes"
    assert meta.note_target_name == "Вася"


def test_parse_voicenote_does_not_misfire_on_regular_formats():
    # Формат 5 (имя + дата) не должен спутаться с voicenote_*
    meta = parse_filename("Вив 2009_08_17 12_15_49.mp3")
    assert meta.phone is None
    assert meta.contact_name == "Вив"


# ── ingester ──────────────────────────────────────────────────────────────

def _make_repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def _add_user(repo: Repository, user_id: str = "me") -> None:
    repo.add_user(
        user_id=user_id, display_name="Test", telegram_chat_id="555",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/ref.wav",
    )


def test_ingest_voicenote_sets_call_type_note_and_self_notes_contact(tmp_path):
    repo = _make_repo()
    _add_user(repo)
    cfg = Config(data_dir=str(tmp_path))
    ing = Ingester(repo, cfg)

    src = tmp_path / "voicenote_20260717-153000.ogg"
    src.write_bytes(b"fake-ogg-audio")

    call_id = ing.ingest_file("me", str(src))
    assert call_id is not None

    call = repo.get_call("me", call_id)
    assert call["call_type"] == "note"

    contact = repo.get_contact("me", call["contact_id"])
    assert contact["phone_e164"] == "self:notes"
    assert contact["display_name"] == "Мои заметки"


def test_ingest_voicenote_reuses_same_notes_contact_across_calls(tmp_path):
    repo = _make_repo()
    _add_user(repo)
    cfg = Config(data_dir=str(tmp_path))
    ing = Ingester(repo, cfg)

    src1 = tmp_path / "voicenote_20260717-153000.ogg"
    src1.write_bytes(b"a")
    src2 = tmp_path / "voicenote_20260717-160000.ogg"
    src2.write_bytes(b"b")

    call_id1 = ing.ingest_file("me", str(src1))
    call_id2 = ing.ingest_file("me", str(src2))

    c1 = repo.get_call("me", call_id1)
    c2 = repo.get_call("me", call_id2)
    assert c1["contact_id"] == c2["contact_id"]


def test_ingest_regular_call_has_no_call_type(tmp_path):
    repo = _make_repo()
    _add_user(repo)
    cfg = Config(data_dir=str(tmp_path))
    ing = Ingester(repo, cfg)

    src = tmp_path / "8(495)197-87-11(84951978711)_20240502164535.mp3"
    src.write_bytes(b"x")
    call_id = ing.ingest_file("me", str(src))

    call = repo.get_call("me", call_id)
    assert call["call_type"] is None


# ── repository.find_contact_by_name ─────────────────────────────────────

def test_find_contact_by_name_exact_match():
    repo = _make_repo()
    _add_user(repo)
    repo.get_or_create_contact("me", "+70000000001", "Вася")

    contact, ambiguous = repo.find_contact_by_name("me", "Вася")
    assert ambiguous is False
    assert contact["display_name"] == "Вася"


def test_find_contact_by_name_prefix_case_insensitive():
    repo = _make_repo()
    _add_user(repo)
    repo.get_or_create_contact("me", "+70000000001", "Василий Петров")

    contact, ambiguous = repo.find_contact_by_name("me", "василий")
    assert ambiguous is False
    assert contact["display_name"] == "Василий Петров"


def test_find_contact_by_name_ambiguous():
    repo = _make_repo()
    _add_user(repo)
    repo.get_or_create_contact("me", "+70000000001", "Вася Иванов")
    repo.get_or_create_contact("me", "+70000000002", "Вася Петров")

    contact, ambiguous = repo.find_contact_by_name("me", "Вася")
    assert ambiguous is True
    assert contact is None


def test_find_contact_by_name_not_found():
    repo = _make_repo()
    _add_user(repo)
    contact, ambiguous = repo.find_contact_by_name("me", "Никто")
    assert contact is None
    assert ambiguous is False


# ── orchestrator: process_call note branch ──────────────────────────────

class _FakeASRFlat:
    """Возвращает сегменты со speaker=UNKNOWN — orchestrator должен принудить OWNER."""

    def load(self):
        pass

    def unload(self):
        pass

    def transcribe(self, norm_path):
        return [Segment(0, 1000, "нужно позвонить Пете завтра", "UNKNOWN")]


def _make_note_call(repo: Repository, tmp_path, user_id="me", target=None) -> int:
    cfg = Config(data_dir=str(tmp_path))
    ing = Ingester(repo, cfg)
    name = f"voicenote_20260717-153000{'__' + target if target else ''}.ogg"
    src = tmp_path / name
    src.write_bytes(b"fake")
    return ing.ingest_file(user_id, str(src))


def _patch_normalize(monkeypatch):
    import callprofiler.pipeline.orchestrator as orch_mod

    def _fake_normalize(src, dst):
        from pathlib import Path
        Path(dst).write_bytes(b"RIFF....WAVEfmt ")

    monkeypatch.setattr(orch_mod, "normalize", _fake_normalize)
    monkeypatch.setattr(orch_mod, "get_duration_sec", lambda p: 5)


def test_process_call_note_skips_diarize_forces_owner_done(tmp_path, monkeypatch):
    repo = _make_repo()
    _add_user(repo)
    call_id = _make_note_call(repo, tmp_path)

    cfg = Config(data_dir=str(tmp_path))
    cfg.features.enable_diarization = True   # включена, но заметка обязана её пропустить
    cfg.features.enable_llm_analysis = True  # включён, но заметка обязана его пропустить
    _patch_normalize(monkeypatch)
    orch = Orchestrator(cfg, repo)
    orch.asr_runner = _FakeASRFlat()
    orch._analyze_call = MagicMock(side_effect=AssertionError("analyze не должен вызываться для заметки"))

    ok = orch.process_call(call_id)

    assert ok is True
    call = repo.get_call("me", call_id)
    assert call["status"] == "done"
    assert call["pipeline_stage"] == 4
    assert orch.pyannote_runner is None  # диаризация не тронута

    rows = repo.get_transcript(call_id)
    assert len(rows) == 1
    assert rows[0]["speaker"] == "OWNER"


def test_process_call_regular_still_diarizes(tmp_path, monkeypatch):
    """Контроль: обычный звонок НЕ должен получить новое поведение заметок."""
    repo = _make_repo()
    _add_user(repo)
    cfg = Config(data_dir=str(tmp_path))
    ing = Ingester(repo, cfg)
    src = tmp_path / "8(495)197-87-11(84951978711)_20240502164535.mp3"
    src.write_bytes(b"x")
    call_id = ing.ingest_file("me", str(src))

    cfg2 = Config(data_dir=str(tmp_path))
    cfg2.features.enable_diarization = False  # избегаем реального pyannote в тесте
    cfg2.features.enable_llm_analysis = False
    _patch_normalize(monkeypatch)
    orch = Orchestrator(cfg2, repo)
    orch.asr_runner = _FakeASRFlat()

    ok = orch.process_call(call_id)
    assert ok is True
    call = repo.get_call("me", call_id)
    assert call["status"] == "transcribed"  # обычный Stage-1 путь, не 'done'
    rows = repo.get_transcript(call_id)
    assert rows[0]["speaker"] == "UNKNOWN"  # НЕ форсится в OWNER для обычных звонков


# ── orchestrator: process_batch note branch ─────────────────────────────

def test_process_batch_note_and_regular_mixed(tmp_path, monkeypatch):
    repo = _make_repo()
    _add_user(repo)

    note_call_id = _make_note_call(repo, tmp_path)

    cfg = Config(data_dir=str(tmp_path))
    ing = Ingester(repo, cfg)
    src = tmp_path / "8(495)197-87-11(84951978711)_20240502164535.mp3"
    src.write_bytes(b"x")
    regular_call_id = ing.ingest_file("me", str(src))

    cfg2 = Config(data_dir=str(tmp_path))
    cfg2.features.enable_diarization = True
    cfg2.features.enable_llm_analysis = False  # обычный звонок пойдёт в 'transcribed'
    _patch_normalize(monkeypatch)
    orch = Orchestrator(cfg2, repo)
    orch.asr_runner = _FakeASRFlat()

    diarize_calls_seen = {}
    orig_diarize_batch = orch._diarize_batch

    def _spy_diarize_batch(calls, users_cache):
        diarize_calls_seen["ids"] = [c["call_id"] for c in calls]
        return orig_diarize_batch(calls, users_cache)

    orch._diarize_batch = _spy_diarize_batch

    orch.process_batch([note_call_id, regular_call_id])

    # Заметка исключена из диаризации, обычный звонок — нет
    assert note_call_id not in diarize_calls_seen["ids"]
    assert regular_call_id in diarize_calls_seen["ids"]

    note_call = repo.get_call("me", note_call_id)
    assert note_call["status"] == "done"
    assert note_call["pipeline_stage"] == 4
    note_rows = repo.get_transcript(note_call_id)
    assert note_rows[0]["speaker"] == "OWNER"

    regular_call = repo.get_call("me", regular_call_id)
    assert regular_call["status"] == "transcribed"


# ── orchestrator: caption binding ───────────────────────────────────────

def test_finalize_note_binds_to_contact_when_target_found(tmp_path):
    repo = _make_repo()
    _add_user(repo)
    repo.get_or_create_contact("me", "+70000000001", "Вася")
    call_id = _make_note_call(repo, tmp_path, target="Вася")

    cfg = Config(data_dir=str(tmp_path))
    orch = Orchestrator(cfg, repo)
    call = repo.get_call("me", call_id)
    segments = [Segment(0, 1000, "надо купить кабель", "OWNER")]

    bind_status = orch._maybe_bind_note_to_contact("me", call, "надо купить кабель")

    assert bind_status is not None
    assert "Привязано" in bind_status
    conn = repo._get_conn()
    row = conn.execute(
        "SELECT note FROM contact_notes WHERE user_id='me'"
    ).fetchone()
    assert row is not None
    assert "надо купить кабель" in row["note"]


def test_finalize_note_ambiguous_target_not_bound(tmp_path):
    repo = _make_repo()
    _add_user(repo)
    repo.get_or_create_contact("me", "+70000000001", "Вася Иванов")
    repo.get_or_create_contact("me", "+70000000002", "Вася Петров")
    call_id = _make_note_call(repo, tmp_path, target="Вася")

    cfg = Config(data_dir=str(tmp_path))
    orch = Orchestrator(cfg, repo)
    call = repo.get_call("me", call_id)

    bind_status = orch._maybe_bind_note_to_contact("me", call, "текст заметки")

    assert bind_status is not None
    assert bind_status.startswith("⚠")
    # Ambiguous -> append_contact_note никогда не звался -> таблица могла не создаться.
    conn = repo._get_conn()
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact_notes'"
    ).fetchone()
    if has_table:
        row = conn.execute("SELECT note FROM contact_notes WHERE user_id='me'").fetchone()
        assert row is None


def test_finalize_note_no_caption_returns_none(tmp_path):
    repo = _make_repo()
    _add_user(repo)
    call_id = _make_note_call(repo, tmp_path)  # без target

    cfg = Config(data_dir=str(tmp_path))
    orch = Orchestrator(cfg, repo)
    call = repo.get_call("me", call_id)

    bind_status = orch._maybe_bind_note_to_contact("me", call, "просто заметка")
    assert bind_status is None


def test_finalize_note_sends_telegram_notification(tmp_path):
    repo = _make_repo()
    _add_user(repo)
    call_id = _make_note_call(repo, tmp_path)
    call = repo.get_call("me", call_id)

    cfg = Config(data_dir=str(tmp_path))
    fake_telegram = MagicMock()
    fake_telegram.send_note_ready = AsyncMock()
    orch = Orchestrator(cfg, repo, telegram=fake_telegram)

    segments = [Segment(0, 1000, "напоминание себе", "OWNER")]
    # orchestrator использует asyncio.get_event_loop().run_until_complete() (тот же
    # паттерн, что send_summary) — в full-suite прогоне другой тест может было
    # обнулить event loop потока через asyncio.run(). Гарантируем валидный loop
    # для этого конкретного вызова, не трогая сам orchestrator-код.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        orch._finalize_note(call, segments)
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    fake_telegram.send_note_ready.assert_awaited_once()
    args = fake_telegram.send_note_ready.await_args.args
    assert args[0] == "me"
    assert "напоминание себе" in args[1]


# ── bot: handle_voice_note ──────────────────────────────────────────────

class FakeVoice:
    def __init__(self, file_size=1000):
        self.file_size = file_size

        async def _fake_download(custom_path=None, **kwargs):
            from pathlib import Path
            Path(custom_path).write_bytes(b"fake-ogg-bytes")

        fake_tg_file = SimpleNamespace(download_to_drive=AsyncMock(side_effect=_fake_download))
        self.get_file = AsyncMock(return_value=fake_tg_file)


class FakeMessage:
    def __init__(self, voice=None, audio=None, caption=None):
        self.voice = voice
        self.audio = audio
        self.caption = caption
        self.reply_text = AsyncMock()


class FakeUpdate:
    def __init__(self, voice=None, audio=None, caption=None, chat_id=555):
        self.message = FakeMessage(voice=voice, audio=audio, caption=caption)
        self.effective_user = SimpleNamespace(id=chat_id)


def _bot_repo(tmp_path):
    repo = Repository(str(tmp_path / "bot.db"))
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="Me", telegram_chat_id="555",
        incoming_dir=str(tmp_path / "in"), sync_dir=str(tmp_path / "sync"),
        ref_audio=str(tmp_path / "ref.wav"),
    )
    return repo


def test_handle_voice_note_downloads_and_replies(tmp_path):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    repo = _bot_repo(tmp_path)
    notifier = TelegramNotifier(repo, token=None)
    voice = FakeVoice()
    update = FakeUpdate(voice=voice)

    asyncio.run(notifier.handle_voice_note(update, context=None))

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args.args[0]
    assert "Принял" in text
    voice.get_file.assert_awaited_once()

    files = list((tmp_path / "in").glob("voicenote_*.ogg"))
    assert len(files) == 1
    assert not files[0].name.endswith(".part")


def test_handle_voice_note_caption_target_sanitized_into_filename(tmp_path):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    repo = _bot_repo(tmp_path)
    notifier = TelegramNotifier(repo, token=None)
    voice = FakeVoice()
    update = FakeUpdate(voice=voice, caption="@Вася Петров!")

    asyncio.run(notifier.handle_voice_note(update, context=None))

    files = list((tmp_path / "in").glob("voicenote_*__*.ogg"))
    assert len(files) == 1
    assert "Вася" in files[0].name


def test_handle_voice_note_rejects_oversized_file(tmp_path):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    repo = _bot_repo(tmp_path)
    notifier = TelegramNotifier(repo, token=None)
    voice = FakeVoice(file_size=60 * 1024 * 1024)
    update = FakeUpdate(voice=voice)

    asyncio.run(notifier.handle_voice_note(update, context=None))

    voice.get_file.assert_not_called()
    text = update.message.reply_text.await_args.args[0]
    assert "большой" in text
    assert list((tmp_path / "in").glob("voicenote_*")) == []


def test_handle_voice_note_non_allowlisted_ignored(tmp_path):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    repo = _bot_repo(tmp_path)
    notifier = TelegramNotifier(repo, token=None)
    voice = FakeVoice()
    update = FakeUpdate(voice=voice, chat_id=99999)

    asyncio.run(notifier.handle_voice_note(update, context=None))

    voice.get_file.assert_not_called()
    update.message.reply_text.assert_not_awaited()


def test_handle_voice_note_no_media_is_noop(tmp_path):
    from callprofiler.deliver.telegram_bot import TelegramNotifier

    repo = _bot_repo(tmp_path)
    notifier = TelegramNotifier(repo, token=None)
    update = FakeUpdate()  # voice=None, audio=None

    asyncio.run(notifier.handle_voice_note(update, context=None))
    update.message.reply_text.assert_not_awaited()
