# -*- coding: utf-8 -*-
"""Тесты для deliver/card_generator.py — генерация caller cards."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tempfile
from pathlib import Path

from callprofiler.db.repository import Repository
from callprofiler.deliver.card_generator import CardGenerator, MAX_CARD_LENGTH
from callprofiler.models import Analysis


def _make_repo():
    """Создать in-memory Repository с инициализированной схемой."""
    repo = Repository(":memory:")
    repo.init_db()
    return repo


def _add_user(repo, user_id="serhio", sync_dir="/tmp/sync"):
    """Добавить тестового пользователя."""
    repo.add_user(
        user_id=user_id,
        display_name="Сергей",
        telegram_chat_id="12345",
        incoming_dir="/tmp/incoming",
        sync_dir=sync_dir,
        ref_audio="/tmp/ref.wav",
    )


def _add_contact_with_call_and_analysis(repo, user_id="serhio",
                                         phone="+79161234567",
                                         display_name="Иванов"):
    """Добавить контакт, звонок и анализ."""
    contact_id = repo.get_or_create_contact(user_id, phone, display_name)
    call_id = repo.create_call(
        user_id=user_id,
        contact_id=contact_id,
        direction="IN",
        call_datetime="2026-03-28 14:30:00",
        source_filename="test.mp3",
        source_md5="abc123",
        audio_path="/tmp/test.mp3",
    )
    analysis = Analysis(
        priority=75,
        risk_score=30,
        summary="Обсуждение поставки товара. Иванов подтвердил сроки.",
        action_items=["Отправить счёт", "Проверить наличие"],
        promises=[{"who": "OTHER", "what": "Оплатить до пятницы", "due": "2026-04-04"}],
        flags={"urgent": False, "follow_up_needed": True, "conflict_detected": False},
        key_topics=["поставка", "оплата"],
        raw_response="{}",
        model="qwen2.5:14b",
        prompt_version="v001",
    )
    repo.save_analysis(call_id, analysis)
    repo.save_promises(user_id, contact_id, call_id, analysis.promises)
    return contact_id, call_id


def test_generate_card_basic():
    """Карточка содержит имя, статистику, саммари, обещания."""
    repo = _make_repo()
    _add_user(repo)
    contact_id, _ = _add_contact_with_call_and_analysis(repo)

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "Иванов" in card
    assert "Звонков: 1" in card
    assert "Risk: 30" in card
    assert "поставки товара" in card
    assert "Обещания:" in card
    assert "OTHER: Оплатить до пятницы" in card
    assert "Actions:" in card
    assert "Отправить счёт" in card


def test_generate_card_no_analysis():
    """Карточка без анализа показывает 'Нет данных'."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = repo.get_or_create_contact("serhio", "+79161234567", "Иванов")
    repo.create_call(
        user_id="serhio",
        contact_id=contact_id,
        direction="OUT",
        call_datetime="2026-03-28",
        source_filename="test.mp3",
        source_md5="def456",
        audio_path="/tmp/test.mp3",
    )

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "Иванов" in card
    assert "Нет анализа" in card
    assert "Нет данных об анализе" in card


def test_generate_card_no_promises():
    """Карточка без обещаний показывает 'нет'."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = repo.get_or_create_contact("serhio", "+79161234567", "Иванов")
    call_id = repo.create_call(
        user_id="serhio",
        contact_id=contact_id,
        direction="IN",
        call_datetime="2026-03-28",
        source_filename="test.mp3",
        source_md5="ghi789",
        audio_path="/tmp/test.mp3",
    )
    analysis = Analysis(
        priority=20,
        risk_score=10,
        summary="Короткий звонок.",
        action_items=[],
        promises=[],
        flags={},
        key_topics=[],
        raw_response="{}",
        model="qwen2.5:14b",
        prompt_version="v001",
    )
    repo.save_analysis(call_id, analysis)

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "Обещания: нет" in card
    assert "Actions: нет" in card


def test_generate_card_unknown_contact():
    """Несуществующий контакт → пустая строка."""
    repo = _make_repo()
    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", 9999)

    assert card == ""


def test_generate_card_max_length():
    """Карточка не превышает 500 символов."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = repo.get_or_create_contact("serhio", "+79161234567", "Иванов")
    call_id = repo.create_call(
        user_id="serhio",
        contact_id=contact_id,
        direction="IN",
        call_datetime="2026-03-28",
        source_filename="test.mp3",
        source_md5="jkl012",
        audio_path="/tmp/test.mp3",
    )
    # Длинный саммари + длинные action items → обрезка
    analysis = Analysis(
        priority=90,
        risk_score=80,
        summary="А" * 300,
        action_items=["Б" * 100, "В" * 100, "Г" * 100],
        promises=[],
        flags={},
        key_topics=[],
        raw_response="{}",
        model="qwen2.5:14b",
        prompt_version="v001",
    )
    repo.save_analysis(call_id, analysis)

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert len(card) <= MAX_CARD_LENGTH
    assert card.endswith("...")


def test_write_card_creates_file():
    """write_card создаёт файл {phone}.txt в sync_dir."""
    repo = _make_repo()
    _add_user(repo)
    contact_id, _ = _add_contact_with_call_and_analysis(repo)

    gen = CardGenerator(repo)
    with tempfile.TemporaryDirectory() as tmpdir:
        gen.write_card("serhio", contact_id, tmpdir)

        card_file = Path(tmpdir) / "+79161234567.txt"
        assert card_file.exists()
        content = card_file.read_text(encoding="utf-8")
        assert "Иванов" in content
        assert len(content) <= MAX_CARD_LENGTH


def test_write_card_no_phone():
    """Контакт без phone_e164 → карточка не записывается."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = repo.get_or_create_contact("serhio", None, "Без номера")

    gen = CardGenerator(repo)
    with tempfile.TemporaryDirectory() as tmpdir:
        gen.write_card("serhio", contact_id, tmpdir)

        files = list(Path(tmpdir).iterdir())
        assert len(files) == 0


def test_write_card_creates_sync_dir():
    """write_card создаёт sync_dir если не существует."""
    repo = _make_repo()
    _add_user(repo)
    contact_id, _ = _add_contact_with_call_and_analysis(repo)

    gen = CardGenerator(repo)
    with tempfile.TemporaryDirectory() as tmpdir:
        nested = str(Path(tmpdir) / "sub" / "cards")
        gen.write_card("serhio", contact_id, nested)

        card_file = Path(nested) / "+79161234567.txt"
        assert card_file.exists()


def test_update_all_cards():
    """update_all_cards создаёт карточки для всех контактов."""
    repo = _make_repo()
    with tempfile.TemporaryDirectory() as tmpdir:
        _add_user(repo, sync_dir=tmpdir)
        _add_contact_with_call_and_analysis(
            repo, phone="+79161111111", display_name="Первый"
        )
        _add_contact_with_call_and_analysis(
            repo, phone="+79162222222", display_name="Второй"
        )

        # Нужно обойти дубликат md5 — второй контакт
        # (уже создан выше через helper, md5 совпадает — нужен другой)
        # На самом деле helper использует один и тот же md5 "abc123",
        # но call_exists проверяет по user_id + md5, и для одного user
        # второй вызов с тем же md5 не создаст call.
        # Пересоздадим второй контакт вручную:
        contact2 = repo.get_contact_by_phone("serhio", "+79162222222")
        if contact2:
            call_id2 = repo.create_call(
                user_id="serhio",
                contact_id=contact2["contact_id"],
                direction="OUT",
                call_datetime="2026-03-29",
                source_filename="test2.mp3",
                source_md5="xyz999",
                audio_path="/tmp/test2.mp3",
            )
            analysis2 = Analysis(
                priority=50, risk_score=20,
                summary="Второй звонок.",
                raw_response="{}",
                model="test", prompt_version="v001",
            )
            repo.save_analysis(call_id2, analysis2)

        gen = CardGenerator(repo)
        gen.update_all_cards("serhio")

        files = sorted(Path(tmpdir).glob("*.txt"))
        assert len(files) == 2
        names = [f.stem for f in files]
        assert "+79161111111" in names
        assert "+79162222222" in names


def test_update_all_cards_unknown_user():
    """update_all_cards для несуществующего пользователя → ничего."""
    repo = _make_repo()
    gen = CardGenerator(repo)
    # Не должен падать
    gen.update_all_cards("nonexistent")


def test_multiple_calls_count():
    """Карточка показывает правильное количество звонков."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = repo.get_or_create_contact("serhio", "+79161234567", "Иванов")

    for i in range(5):
        repo.create_call(
            user_id="serhio",
            contact_id=contact_id,
            direction="IN",
            call_datetime=f"2026-03-2{i} 10:00:00",
            source_filename=f"test_{i}.mp3",
            source_md5=f"md5_{i}",
            audio_path=f"/tmp/test_{i}.mp3",
        )

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)
    assert "Звонков: 5" in card


def test_user_isolation():
    """Карточки изолированы по user_id."""
    repo = _make_repo()
    _add_user(repo, user_id="user_a")
    _add_user(repo, user_id="user_b")

    cid_a = repo.get_or_create_contact("user_a", "+79161234567", "Контакт A")
    repo.create_call(
        user_id="user_a", contact_id=cid_a, direction="IN",
        call_datetime="2026-03-28", source_filename="a.mp3",
        source_md5="aaa", audio_path="/tmp/a.mp3",
    )

    cid_b = repo.get_or_create_contact("user_b", "+79161234567", "Контакт B")
    repo.create_call(
        user_id="user_b", contact_id=cid_b, direction="OUT",
        call_datetime="2026-03-28", source_filename="b.mp3",
        source_md5="bbb", audio_path="/tmp/b.mp3",
    )

    gen = CardGenerator(repo)
    card_a = gen.generate_card("user_a", cid_a)
    card_b = gen.generate_card("user_b", cid_b)

    assert "Контакт A" in card_a
    assert "Контакт B" not in card_a
    assert "Контакт B" in card_b
    assert "Контакт A" not in card_b
