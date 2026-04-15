# -*- coding: utf-8 -*-
"""Тесты для deliver/card_generator.py — генерация caller cards (structured format)."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
import tempfile
from pathlib import Path

from callprofiler.db.repository import Repository
from callprofiler.deliver.card_generator import CardGenerator, MAX_CARD_BYTES
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


def _add_contact(repo, user_id="serhio", phone="+79161234567", display_name="Иванов"):
    """Добавить контакт."""
    return repo.get_or_create_contact(user_id, phone, display_name)


def _add_contact_with_summary(repo, user_id="serhio", phone="+79161234567",
                               display_name="Иванов", risk=30,
                               top_hook="Спроси про сына",
                               advice="Говорит конкретно"):
    """Добавить контакт с contact_summary."""
    contact_id = repo.get_or_create_contact(user_id, phone, display_name)
    repo.save_contact_summary(
        contact_id=contact_id,
        user_id=user_id,
        global_risk=risk,
        contact_role="Поставщик",
        top_hook=top_hook,
        open_promises=json.dumps([]),
        open_debts=json.dumps([]),
        personal_facts=json.dumps([]),
        advice=advice,
    )
    return contact_id


def test_generate_card_basic():
    """Карточка содержит имя в header и risk."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = _add_contact_with_summary(repo, risk=30, top_hook="Напомни про оплату")

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "header:" in card
    assert "Иванов" in card
    assert "risk:" in card
    assert "30" in card
    assert "hook:" in card
    assert "Напомни про оплату" in card


def test_generate_card_no_summary():
    """Карточка без summary показывает 'Нет истории'."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = _add_contact(repo)

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "Иванов" in card
    assert "Нет истории" in card


def test_generate_card_risk_emoji_red():
    """risk >= 70 → красный эмодзи."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = _add_contact_with_summary(repo, risk=80)

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "🔴" in card


def test_generate_card_risk_emoji_yellow():
    """30 <= risk < 70 → жёлтый эмодзи."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = _add_contact_with_summary(repo, risk=50)

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "🟡" in card


def test_generate_card_risk_emoji_green():
    """risk < 30 → зелёный эмодзи."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = _add_contact_with_summary(repo, risk=10)

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "🟢" in card


def test_generate_card_with_bullets():
    """Карточка с promises и debts показывает bullet-строки."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = repo.get_or_create_contact("serhio", "+79161234567", "Иванов")
    repo.save_contact_summary(
        contact_id=contact_id,
        user_id="serhio",
        global_risk=40,
        contact_role="Клиент",
        top_hook="Спроси про сделку",
        open_promises=json.dumps([{"payload": "Оплатить до пятницы"}]),
        open_debts=json.dumps([{"payload": "Должен 50000 руб."}]),
        personal_facts=json.dumps([]),
        advice="Держи дистанцию",
    )

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "bullet1:" in card
    assert "Должен 50000 руб." in card


def test_generate_card_unknown_contact():
    """Несуществующий контакт → пустая строка."""
    repo = _make_repo()
    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", 9999)

    assert card == ""


def test_generate_card_max_bytes():
    """Карточка не превышает MAX_CARD_BYTES байт."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = repo.get_or_create_contact("serhio", "+79161234567", "Иванов")
    repo.save_contact_summary(
        contact_id=contact_id,
        user_id="serhio",
        global_risk=90,
        contact_role="А" * 100,
        top_hook="Б" * 100,
        open_promises=json.dumps([{"payload": "В" * 100}]),
        open_debts=json.dumps([{"payload": "Г" * 100}]),
        personal_facts=json.dumps([{"payload": "Д" * 100}]),
        advice="Е" * 100,
    )

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert len(card.encode("utf-8")) <= MAX_CARD_BYTES
    assert card.endswith("...")


def test_write_card_creates_file():
    """write_card создаёт файл {phone}.txt в sync_dir."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = _add_contact_with_summary(repo)

    gen = CardGenerator(repo)
    with tempfile.TemporaryDirectory() as tmpdir:
        gen.write_card("serhio", contact_id, tmpdir)

        card_file = Path(tmpdir) / "+79161234567.txt"
        assert card_file.exists()
        content = card_file.read_text(encoding="utf-8")
        assert "Иванов" in content
        assert len(content.encode("utf-8")) <= MAX_CARD_BYTES


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
    contact_id = _add_contact_with_summary(repo)

    gen = CardGenerator(repo)
    with tempfile.TemporaryDirectory() as tmpdir:
        nested = str(Path(tmpdir) / "sub" / "cards")
        gen.write_card("serhio", contact_id, nested)

        card_file = Path(nested) / "+79161234567.txt"
        assert card_file.exists()


def test_update_all_cards():
    """update_all_cards создаёт карточки для всех контактов с phone_e164."""
    repo = _make_repo()
    with tempfile.TemporaryDirectory() as tmpdir:
        _add_user(repo, sync_dir=tmpdir)
        _add_contact_with_summary(repo, phone="+79161111111", display_name="Первый")
        _add_contact_with_summary(repo, phone="+79162222222", display_name="Второй")

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


def test_no_hook_line_when_empty():
    """Если top_hook пустой, строка hook: не добавляется."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = repo.get_or_create_contact("serhio", "+79161234567", "Иванов")
    repo.save_contact_summary(
        contact_id=contact_id,
        user_id="serhio",
        global_risk=20,
        contact_role="",
        top_hook="",
        open_promises=json.dumps([]),
        open_debts=json.dumps([]),
        personal_facts=json.dumps([]),
        advice="",
    )

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "hook:" not in card
    assert "advice:" not in card


def test_user_isolation():
    """Карточки изолированы по user_id."""
    repo = _make_repo()
    _add_user(repo, user_id="user_a")
    _add_user(repo, user_id="user_b")

    cid_a = _add_contact(repo, user_id="user_a", phone="+79161234567", display_name="Контакт A")
    cid_b = _add_contact(repo, user_id="user_b", phone="+79161234567", display_name="Контакт B")

    gen = CardGenerator(repo)
    card_a = gen.generate_card("user_a", cid_a)
    card_b = gen.generate_card("user_b", cid_b)

    assert "Контакт A" in card_a
    assert "Контакт B" not in card_a
    assert "Контакт B" in card_b
    assert "Контакт A" not in card_b
