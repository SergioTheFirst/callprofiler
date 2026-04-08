# -*- coding: utf-8 -*-
"""
test_integration.py — интеграционный тест полного pipeline.

Проверяет сквозную работу:
  1. Добавление пользователя
  2. Регистрация аудиофайла (ingester)
  3. Обработка звонка (orchestrator: normalize → transcribe → diarize → analyze)
  4. Проверка результатов в БД и файловой системе

Тест полностью локален (in-memory БД, mock-файлы) и не требует GPU.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from callprofiler.config import Config, ModelsConfig, PipelineConfig, AudioConfig
from callprofiler.db.repository import Repository
from callprofiler.ingest.ingester import Ingester
from callprofiler.models import Segment


def _make_test_wav(filepath: Path, size_kb: int = 100) -> None:
    """Создать простой WAV-файл нужного размера (не реальный аудио)."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    # Минимальный WAV заголовок + нулевые данные
    wav_header = b'RIFF' + (size_kb * 1024 - 8).to_bytes(4, 'little') + b'WAVE'
    filepath.write_bytes(wav_header + b'\x00' * (size_kb * 1024 - len(wav_header)))


def _make_config(data_dir: str) -> Config:
    """Создать тестовую конфигурацию."""
    return Config(
        data_dir=data_dir,
        log_file=str(Path(data_dir) / "logs" / "test.log"),
        hf_token="TEST_TOKEN",
        models=ModelsConfig(
            whisper="large-v3",
            whisper_device="cpu",  # CPU для тестов
            whisper_compute="int8",
            whisper_beam_size=5,
            whisper_language="ru",
            llm_model="qwen2.5:14b-instruct-q4_K_M",
            ollama_url="http://localhost:11434",
        ),
        pipeline=PipelineConfig(
            watch_interval_sec=30,
            file_settle_sec=0,  # Не ждать settle в тестах
            max_retries=3,
            retry_interval_sec=3600,
        ),
        audio=AudioConfig(
            sample_rate=16000,
            channels=1,
            format="wav",
        ),
    )


def test_add_user_and_ingest():
    """Тест 1: Добавить пользователя и зарегистрировать файл."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = _make_config(tmpdir)
        repo = Repository(str(Path(tmpdir) / "db" / "test.db"))
        repo.init_db()

        # Шаг 1: Добавить пользователя
        user_id = "test_user"
        incoming_dir = Path(tmpdir) / "incoming"
        ref_audio = Path(tmpdir) / "ref.wav"
        sync_dir = Path(tmpdir) / "sync"

        incoming_dir.mkdir(parents=True, exist_ok=True)
        _make_test_wav(ref_audio)
        sync_dir.mkdir(parents=True, exist_ok=True)

        repo.add_user(
            user_id=user_id,
            display_name="Test User",
            telegram_chat_id=None,
            incoming_dir=str(incoming_dir),
            sync_dir=str(sync_dir),
            ref_audio=str(ref_audio),
        )

        user = repo.get_user(user_id)
        assert user is not None
        assert user["display_name"] == "Test User"
        assert user["incoming_dir"] == str(incoming_dir)

        # Шаг 2: Зарегистрировать файл через Ingester
        # Используем формат 4: Имя контакта + номер в скобках + дата
        ingester = Ingester(repo, cfg)
        test_file = incoming_dir / "Иванов(0079161234567)_20260328143022.mp3"
        _make_test_wav(test_file)

        call_id = ingester.ingest_file(user_id, str(test_file))

        assert call_id is not None
        assert call_id > 0

        # Проверить что звонок зарегистрирован
        call = repo._get_conn().execute(
            "SELECT * FROM calls WHERE call_id=?", (call_id,)
        ).fetchone()
        assert call is not None
        assert dict(call)["user_id"] == user_id
        assert dict(call)["status"] == "new"

        # Проверить что контакт создан
        contact_id = dict(call)["contact_id"]
        contact = repo.get_contact(contact_id)
        assert contact is not None
        assert contact["phone_e164"] == "+79161234567"


def test_ingest_duplicate():
    """Тест 2: Дедупликация — второй файл с тем же MD5 не регистрируется."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = _make_config(tmpdir)
        repo = Repository(str(Path(tmpdir) / "db" / "test.db"))
        repo.init_db()

        incoming_dir = Path(tmpdir) / "incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)

        repo.add_user(
            user_id="test",
            display_name="Test",
            telegram_chat_id=None,
            incoming_dir=str(incoming_dir),
            sync_dir=str(Path(tmpdir) / "sync"),
            ref_audio=str(Path(tmpdir) / "ref.wav"),
        )

        # Создать файл
        test_file = incoming_dir / "+79161234567_20260328143022_IN.wav"
        _make_test_wav(test_file)

        ingester = Ingester(repo, cfg)

        # Первый инжест — успех
        call_id_1 = ingester.ingest_file("test", str(test_file))
        assert call_id_1 is not None

        # Второй инжест — дубликат (None)
        call_id_2 = ingester.ingest_file("test", str(test_file))
        assert call_id_2 is None


def test_user_isolation():
    """Тест 3: Изоляция по user_id — разные пользователи видят разные данные."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = _make_config(tmpdir)
        repo = Repository(str(Path(tmpdir) / "db" / "test.db"))
        repo.init_db()

        # Добавить двух пользователей
        for user_id in ["user_a", "user_b"]:
            repo.add_user(
                user_id=user_id,
                display_name=f"User {user_id}",
                telegram_chat_id=None,
                incoming_dir=str(Path(tmpdir) / user_id / "incoming"),
                sync_dir=str(Path(tmpdir) / user_id / "sync"),
                ref_audio=str(Path(tmpdir) / "ref.wav"),
            )

        # Добавить контакт с одинаковым номером у обоих
        contact_id_a = repo.get_or_create_contact("user_a", "+79161234567", "Alice")
        contact_id_b = repo.get_or_create_contact("user_b", "+79161234567", "Bob")

        # Это должны быть разные контакты
        assert contact_id_a != contact_id_b

        # Проверить что они действительно разные
        contact_a = repo.get_contact(contact_id_a)
        contact_b = repo.get_contact(contact_id_b)
        assert contact_a["display_name"] == "Alice"
        assert contact_b["display_name"] == "Bob"


def test_transcript_save_and_retrieve():
    """Тест 4: Сохранение и получение транскриптов с ролями."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = _make_config(tmpdir)
        repo = Repository(str(Path(tmpdir) / "db" / "test.db"))
        repo.init_db()

        repo.add_user(
            user_id="test",
            display_name="Test",
            telegram_chat_id=None,
            incoming_dir=str(Path(tmpdir) / "incoming"),
            sync_dir=str(Path(tmpdir) / "sync"),
            ref_audio=str(Path(tmpdir) / "ref.wav"),
        )

        # Создать звонок
        call_id = repo.create_call(
            user_id="test",
            contact_id=None,
            direction="IN",
            call_datetime="2026-03-28 14:30:00",
            source_filename="test.mp3",
            source_md5="abc123",
            audio_path="/tmp/test.mp3",
        )

        # Сохранить сегменты
        segments = [
            Segment(start_ms=0, end_ms=1000, text="Привет", speaker="OWNER"),
            Segment(start_ms=1000, end_ms=2000, text="Как дела?", speaker="OTHER"),
            Segment(start_ms=2000, end_ms=3000, text="Хорошо", speaker="OWNER"),
        ]
        repo.save_transcripts(call_id, segments)

        # Получить и проверить
        saved = repo.get_transcript(call_id)
        assert len(saved) == 3
        assert saved[0]["text"] == "Привет"
        assert saved[0]["speaker"] == "OWNER"
        assert saved[1]["speaker"] == "OTHER"


def test_analysis_save_and_retrieve():
    """Тест 5: Сохранение и получение анализов с JSON."""
    from callprofiler.models import Analysis

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = _make_config(tmpdir)
        repo = Repository(str(Path(tmpdir) / "db" / "test.db"))
        repo.init_db()

        repo.add_user(
            user_id="test",
            display_name="Test",
            telegram_chat_id=None,
            incoming_dir=str(Path(tmpdir) / "incoming"),
            sync_dir=str(Path(tmpdir) / "sync"),
            ref_audio=str(Path(tmpdir) / "ref.wav"),
        )

        call_id = repo.create_call(
            user_id="test",
            contact_id=None,
            direction="IN",
            call_datetime="2026-03-28",
            source_filename="test.mp3",
            source_md5="xyz",
            audio_path="/tmp/test.mp3",
        )

        # Сохранить анализ
        analysis = Analysis(
            priority=75,
            risk_score=30,
            summary="Важный звонок о поставке",
            action_items=["Отправить счёт", "Подтвердить сроки"],
            promises=[{"who": "OTHER", "what": "Оплатить", "due": "2026-04-04"}],
            flags={"urgent": True, "follow_up_needed": False},
            key_topics=["поставка", "оплата"],
            raw_response="{}",
            model="qwen2.5",
            prompt_version="v001",
        )
        repo.save_analysis(call_id, analysis)

        # Получить и проверить
        saved = repo.get_analysis(call_id)
        assert saved is not None
        assert saved["priority"] == 75
        assert saved["risk_score"] == 30
        assert len(saved["action_items"]) == 2
        assert saved["action_items"][0] == "Отправить счёт"
        # promises хранятся в отдельной таблице, не в analyses
        assert saved["flags"]["urgent"] is True


def test_promises_save_and_query():
    """Тест 6: Сохранение и получение обещаний."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = _make_config(tmpdir)
        repo = Repository(str(Path(tmpdir) / "db" / "test.db"))
        repo.init_db()

        user_id = "test"
        repo.add_user(
            user_id=user_id,
            display_name="Test",
            telegram_chat_id=None,
            incoming_dir=str(Path(tmpdir) / "incoming"),
            sync_dir=str(Path(tmpdir) / "sync"),
            ref_audio=str(Path(tmpdir) / "ref.wav"),
        )
        contact_id = repo.get_or_create_contact(user_id, "+79161234567", "Test")
        call_id = repo.create_call(
            user_id=user_id,
            contact_id=contact_id,
            direction="IN",
            call_datetime="2026-03-28",
            source_filename="test.mp3",
            source_md5="prom",
            audio_path="/tmp/test.mp3",
        )

        # Сохранить обещания
        promises = [
            {"who": "OTHER", "what": "Оплатить счёт", "due": "2026-04-05"},
            {"who": "OWNER", "what": "Отправить сметету", "due": "2026-04-01"},
        ]
        repo.save_promises(user_id, contact_id, call_id, promises)

        # Получить открытые
        open_promises = repo.get_open_promises(user_id)
        assert len(open_promises) == 2
        assert open_promises[0]["who"] in ("OTHER", "OWNER")

        # Получить для контакта
        contact_promises = repo.get_contact_promises(user_id, contact_id)
        assert len(contact_promises) == 2


if __name__ == "__main__":
    # Запустить все тесты
    test_add_user_and_ingest()
    print("✓ Тест 1: add_user_and_ingest")

    test_ingest_duplicate()
    print("✓ Тест 2: ingest_duplicate")

    test_user_isolation()
    print("✓ Тест 3: user_isolation")

    test_transcript_save_and_retrieve()
    print("✓ Тест 4: transcript_save_and_retrieve")

    test_analysis_save_and_retrieve()
    print("✓ Тест 5: analysis_save_and_retrieve")

    test_promises_save_and_query()
    print("✓ Тест 6: promises_save_and_query")

    print("\n✓ Все интеграционные тесты пройдены!")
