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


def test_generate_card_uses_calibrated_risk_thresholds(tmp_path):
    """A4: risk emoji читает risk_thresholds (НЕ BS-index).

    Файловый repo (не in-memory _make_repo) — calibrate_risk пишет через
    отдельный коннект к тому же файлу, CardGenerator._get_conn() должен его увидеть.
    """
    from callprofiler.insight.risk_calibration import calibrate_risk

    repo = Repository(str(tmp_path / "card.db"))
    repo.init_db()
    _add_user(repo)
    contact_id = _add_contact_with_summary(repo, risk=10)  # 🟢 под старым фиксированным 30/70

    conn = repo._get_conn()
    for i in range(60):
        cur = conn.execute(
            "INSERT INTO calls(user_id, direction, call_datetime, source_filename, "
            "source_md5, status, duration_sec) VALUES (?,?,?,?,?,?,?)",
            ("serhio", "IN", f"2026-01-{(i % 28) + 1:02d}T10:00:00", f"f{i}.mp3",
             f"md5{i}", "done", 60),
        )
        conn.execute(
            "INSERT INTO analyses(call_id, prompt_version, risk_score) VALUES (?,?,?)",
            (cur.lastrowid, "v001", 5),  # все звонки юзера риск=5 -> green_max=yellow_max=5.0
        )
    conn.commit()
    calibrate_risk(conn, "serhio")

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    # risk=10 > калиброванный green_max=5.0 -> уже НЕ 🟢 (был бы под старым фикс. 30/70)
    assert "🟢" not in card
    assert "🔴" in card


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
    """Карточка не превышает MAX_CARD_BYTES байт; штамп свежести — последняя строка."""
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
    assert "..." in card
    assert card.split("\n")[-1].startswith("обновлено ")


def test_generate_card_freshness_stamp_last_line():
    """A6/§4.3 п.1: последняя строка карточки — штамп свежести DD.MM HH:MM."""
    from datetime import datetime

    repo = _make_repo()
    _add_user(repo)
    contact_id = _add_contact_with_summary(repo)

    gen = CardGenerator(repo)
    fixed_now = datetime(2026, 7, 17, 14, 32)
    card = gen.generate_card("serhio", contact_id, now=fixed_now)

    assert card.split("\n")[-1] == "обновлено 17.07 14:32"


def test_generate_card_no_advice_line():
    """A6/§4.3 п.4: advice убран из карточки v2."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = _add_contact_with_summary(repo, advice="Держи дистанцию")

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "advice:" not in card
    assert "Держи дистанцию" not in card


def test_generate_card_grade_line_always_present():
    """A6 п.2: grade-строка рендерится всегда, даже без graph/entity-слоя (F6 худший случай)."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = _add_contact_with_summary(repo)

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert "grade: F6" in card


def test_generate_card_hook_after_bullets():
    """Fable §4.3 п.4: приоритет строк — обещания/долги выше hook."""
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
        open_debts=json.dumps([]),
        personal_facts=json.dumps([]),
        advice="",
    )

    gen = CardGenerator(repo)
    card = gen.generate_card("serhio", contact_id)

    assert card.index("bullet1:") < card.index("hook:")


def test_write_card_creates_file():
    """write_card создаёт файл {phone}.txt в sync_dir."""
    repo = _make_repo()
    _add_user(repo)
    contact_id = _add_contact_with_summary(repo)

    gen = CardGenerator(repo)
    with tempfile.TemporaryDirectory() as tmpdir:
        gen.write_card("serhio", contact_id, tmpdir)

        card_file = Path(tmpdir) / "79161234567.txt"
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

        card_file = Path(nested) / "79161234567.txt"
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
        assert "79161111111" in names
        assert "79162222222" in names


def test_update_all_cards_removes_legacy_plus_prefixed_files():
    """A6/§4.3 п.6: старые карточки с '+' в имени удаляются при rebuild-cards."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _make_repo()
        _add_user(repo, sync_dir=tmpdir)
        _add_contact_with_summary(repo, phone="+79161111111", display_name="Первый")

        stale = Path(tmpdir) / "+79169999999.txt"
        stale.write_text("header: Устаревший", encoding="utf-8")

        gen = CardGenerator(repo)
        gen.update_all_cards("serhio")

        assert not stale.exists()
        assert (Path(tmpdir) / "79161111111.txt").exists()


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


def test_card_write_is_atomic_old_card_survives_crash(tmp_path, monkeypatch):
    """T-08: сбой в момент публикации карточки не оставляет частичного файла, старая карточка цела."""
    import os
    from callprofiler import artifacts

    dest = tmp_path / "card.txt"
    artifacts.atomic_write_text(dest, "old")
    real_replace = os.replace

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(artifacts.os, "replace", boom)
    try:
        artifacts.atomic_write_text(dest, "new")
    except OSError:
        pass
    monkeypatch.setattr(artifacts.os, "replace", real_replace)
    assert dest.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["card.txt"]  # нет .tmp/.part сирот
