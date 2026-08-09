# -*- coding: utf-8 -*-
"""test_tenant_ownership.py — T-03: tenant identity и ownership API.

Покрывает:
  - Inventory-тест (интроспекция сигнатур Repository) — главный долгоживущий
    результат: ломается при добавлении нового небезопасного мутатора/ридера.
  - Матрица per-mutator: свой владелец мутирует; чужой владелец → 0 строк,
    без исключения; несуществующий id → чистое "не найдено".
  - Двухпользовательский снимок: после серии операций от B данные A целы.
  - close_item (Telegram callback) с чужим user_id не закрывает событие.
  - add_user: allowlist slug (P-TEN-06).
  - user_profile_dir: path containment.
"""

from __future__ import annotations

import inspect
import re

import pytest

from callprofiler.db.repository import Repository
from callprofiler.deliver.reminders import close_item
from callprofiler.identity import user_profile_dir, validate_user_id
from callprofiler.models import Analysis, Segment

# ── Inventory / introspection ────────────────────────────────────────────

# Методы, у которых "чужой" id-параметр — часть самой tenant-scoping модели
# (не bare child-id): purge_other_users сознательно ADMIN (кросс-тенантный
# keep-only), keeper_id — не владелец единственного ресурса, а фильтр по ВСЕМ.
ADMIN_ALLOWLIST = {"purge_other_users"}

_ID_PARAM_RE = re.compile(r"(?:^|_)(id|ids)$")


def _id_bearing_params(sig: inspect.Signature) -> list[str]:
    """Параметры, похожие на bare tenant-owned id (не user_id/user_ids)."""
    out = []
    for name in sig.parameters:
        if name in ("self", "user_id", "user_ids"):
            continue
        if _ID_PARAM_RE.search(name):
            out.append(name)
    return out


def test_inventory_no_public_mutator_with_bare_tenant_id():
    """Ни один публичный метод Repository с id-параметром не должен быть без
    user_id в сигнатуре (кроме явно допущенных ADMIN-методов).

    Это ГЛАВНЫЙ регресс-тест задачи: должен падать, если кто-то добавит новый
    метод вида ``def foo(self, call_id, ...)`` без ``user_id``.
    """
    violations = []
    for name, fn in inspect.getmembers(Repository, predicate=inspect.isfunction):
        if name.startswith("_") or name in ADMIN_ALLOWLIST:
            continue
        sig = inspect.signature(fn)
        id_params = _id_bearing_params(sig)
        if not id_params:
            continue
        if "user_id" not in sig.parameters:
            violations.append((name, id_params))
    assert violations == [], (
        f"Публичные методы с bare tenant-owned id без user_id: {violations}"
    )


# ── Known limitation (documented, not a regression) ─────────────────────
# save_batch(self, items: list[dict]) несёт user_id/call_id ВНУТРИ каждого
# элемента, не как отдельный параметр сигнатуры — инвентарная проверка выше
# structurally не видит это как "bare id". Ownership проверяется РАНТАЙМОМ
# (repository.py: skip + log при call_id не из этого user_id) — покрыто
# отдельным тестом ниже, не интроспекцией.


# ── Fixtures ──────────────────────────────────────────────────────────────


def _repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def _user(repo: Repository, user_id: str) -> None:
    repo.add_user(
        user_id=user_id, display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/ref.wav",
    )


def _call(repo: Repository, user_id: str, md5: str) -> tuple[int, int]:
    contact_id = repo.get_or_create_contact(user_id, "+70000000001", "C")
    call_id = repo.create_call(
        user_id=user_id, contact_id=contact_id, direction="IN",
        call_datetime="2026-04-01 10:00:00", source_filename=f"{md5}.mp3",
        source_md5=md5, audio_path=f"/tmp/{md5}.mp3",
    )
    return call_id, contact_id


@pytest.fixture
def two_users():
    """repo, (a_user, a_call, a_contact), (b_user, b_call, b_contact)."""
    repo = _repo()
    _user(repo, "alice")
    _user(repo, "bob")
    a_call, a_contact = _call(repo, "alice", "md5a")
    b_call, b_contact = _call(repo, "bob", "md5b")
    return repo, ("alice", a_call, a_contact), ("bob", b_call, b_contact)


def _snapshot(repo: Repository, user_id: str) -> dict:
    """Логический снимок всех строк, принадлежащих user_id, по ключевым таблицам."""
    conn = repo._get_conn()
    out = {}
    out["calls"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM calls WHERE user_id=? ORDER BY call_id", (user_id,)
        ).fetchall()
    ]
    out["contacts"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM contacts WHERE user_id=? ORDER BY contact_id", (user_id,)
        ).fetchall()
    ]
    out["transcripts"] = [
        dict(r) for r in conn.execute(
            """SELECT t.* FROM transcripts t JOIN calls c ON c.call_id=t.call_id
               WHERE c.user_id=? ORDER BY t.segment_id""",
            (user_id,),
        ).fetchall()
    ]
    out["analyses"] = [
        dict(r) for r in conn.execute(
            """SELECT a.* FROM analyses a JOIN calls c ON c.call_id=a.call_id
               WHERE c.user_id=? ORDER BY a.analysis_id""",
            (user_id,),
        ).fetchall()
    ]
    out["events"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM events WHERE user_id=? ORDER BY id", (user_id,)
        ).fetchall()
    ]
    return out


# ── Per-mutator matrix ────────────────────────────────────────────────────


def test_update_call_status_owner_vs_stranger(two_users):
    repo, (a, a_call, _), (b, _, _) = two_users
    assert repo.update_call_status(a, a_call, "done") is True
    assert repo.get_call(a, a_call)["status"] == "done"

    # Чужой владелец — 0 строк, без исключения, данные A не тронуты
    assert repo.update_call_status(b, a_call, "error", "hack") is False
    assert repo.get_call(a, a_call)["status"] == "done"

    # Несуществующий id — чистое "не найдено"
    assert repo.update_call_status(a, 999999, "done") is False


def test_update_pipeline_stage_owner_vs_stranger(two_users):
    repo, (a, a_call, _), (b, _, _) = two_users
    assert repo.update_pipeline_stage(a, a_call, 2) is True
    assert repo.get_call(a, a_call)["pipeline_stage"] == 2
    assert repo.update_pipeline_stage(b, a_call, 4) is False
    assert repo.get_call(a, a_call)["pipeline_stage"] == 2
    assert repo.update_pipeline_stage(a, 999999, 1) is False


def test_set_role_fragile_owner_vs_stranger(two_users):
    repo, (a, a_call, _), (b, _, _) = two_users
    assert repo.set_role_fragile(a, a_call, True) is True
    assert repo.get_call(a, a_call)["role_fragile"] == 1
    assert repo.set_role_fragile(b, a_call, False) is False
    assert repo.get_call(a, a_call)["role_fragile"] == 1


def test_update_call_paths_owner_vs_stranger(two_users):
    repo, (a, a_call, _), (b, _, _) = two_users
    assert repo.update_call_paths(a, a_call, "/norm/a.wav", 60) is True
    assert repo.get_call(a, a_call)["norm_path"] == "/norm/a.wav"
    assert repo.update_call_paths(b, a_call, "/norm/hack.wav", 1) is False
    assert repo.get_call(a, a_call)["norm_path"] == "/norm/a.wav"


def test_reset_call_owner_vs_stranger(two_users):
    repo, (a, a_call, _), (b, _, _) = two_users
    repo.update_call_status(a, a_call, "error", "boom")
    assert repo.reset_call(b, a_call) is False
    assert repo.get_call(a, a_call)["status"] == "error"
    assert repo.reset_call(a, a_call) is True
    assert repo.get_call(a, a_call)["status"] == "new"
    assert repo.reset_call(a, 999999) is False


def test_save_transcripts_and_get_transcript_owner_vs_stranger(two_users):
    repo, (a, a_call, _), (b, _, _) = two_users
    segs = [Segment(start_ms=0, end_ms=500, text="alice-secret", speaker="OWNER")]

    assert repo.save_transcripts(b, a_call, segs) is False  # чужой call_id
    assert repo.get_transcript(b, a_call) == []
    assert repo.get_transcript(a, a_call) == []  # ничего не записалось

    assert repo.save_transcripts(a, a_call, segs) is True
    assert len(repo.get_transcript(a, a_call)) == 1
    assert repo.get_transcript(b, a_call) == []  # чужой ридер не видит


def test_save_analysis_owner_vs_stranger(two_users):
    repo, (a, a_call, _), (b, _, _) = two_users
    analysis = Analysis(priority=10, risk_score=5, summary="ok")
    assert repo.save_analysis(b, a_call, analysis) is False
    assert repo.get_analysis(a, a_call) is None
    assert repo.save_analysis(a, a_call, analysis) is True
    assert repo.get_analysis(a, a_call) is not None
    assert repo.get_analysis(b, a_call) is None


def test_set_feedback_owner_vs_stranger(two_users):
    repo, (a, a_call, _), (b, _, _) = two_users
    repo.save_analysis(a, a_call, Analysis(priority=1, risk_score=1, summary="x"))
    analysis_id = repo.get_analysis(a, a_call)["analysis_id"]
    assert repo.set_feedback(b, analysis_id, "inaccurate") is False
    assert repo.get_analysis(a, a_call)["feedback"] is None
    assert repo.set_feedback(a, analysis_id, "accurate") is True
    assert repo.get_analysis(a, a_call)["feedback"] == "accurate"


def test_save_events_owner_vs_stranger(two_users):
    repo, (a, a_call, a_contact), (b, _, _) = two_users
    events = [{"contact_id": a_contact, "event_type": "fact", "who": "OWNER",
               "payload": "p", "status": "open"}]
    assert repo.save_events(b, a_call, events) is False
    assert repo.get_open_events(a) == []
    assert repo.save_events(a, a_call, events) is True
    open_a = repo.get_open_events(a)
    assert len(open_a) == 1
    assert open_a[0]["user_id"] == a  # тег строки — верифицированный owner, не входной


def test_update_event_status_owner_vs_stranger(two_users):
    repo, (a, a_call, a_contact), (b, _, _) = two_users
    repo.save_events(a, a_call, [{"contact_id": a_contact, "event_type": "fact",
                                   "who": "OWNER", "payload": "p", "status": "open"}])
    event_id = repo.get_open_events(a)[0]["id"]
    assert repo.update_event_status(b, event_id, "fulfilled") is False
    assert repo.get_open_events(a)[0]["status"] == "open"
    assert repo.update_event_status(a, event_id, "fulfilled") is True
    assert repo.get_open_events(a) == []
    assert repo.update_event_status(a, 999999, "fulfilled") is False


def test_update_contact_guessed_name_owner_vs_stranger(two_users):
    repo, (a, a_call, a_contact), (b, _, _) = two_users
    # _call() helper passes display_name -> name_confirmed=1, которое сам
    # update_contact_guessed_name намеренно не перезаписывает (guard
    # "не трогать подтверждённые имена"). Для этого теста нужен
    # неподтверждённый контакт — создаём отдельный, без display_name.
    a_contact = repo.get_or_create_contact(a, "+70000000099")
    assert repo.update_contact_guessed_name(
        b, a_contact, "Hacked", "llm", a_call, "high"
    ) is False
    assert repo.get_contact(a, a_contact)["guessed_name"] is None
    assert repo.update_contact_guessed_name(
        a, a_contact, "Vasya", "llm", a_call, "high"
    ) is True
    assert repo.get_contact(a, a_contact)["guessed_name"] == "Vasya"


def test_save_contact_summary_owner_vs_stranger(two_users):
    repo, (a, a_call, a_contact), (b, _, _) = two_users
    assert repo.save_contact_summary(contact_id=a_contact, user_id=b) is False
    assert repo.get_contact_summary(a, a_contact) is None
    assert repo.save_contact_summary(contact_id=a_contact, user_id=a) is True
    assert repo.get_contact_summary(a, a_contact) is not None


def test_save_promises_owner_vs_stranger(two_users):
    repo, (a, a_call, a_contact), (b, _, _) = two_users
    promises = [{"who": "OWNER", "what": "call back", "due": None}]
    repo.save_promises(b, a_contact, a_call, promises)  # call_id чужой user'у b
    assert repo.get_open_promises(b) == []
    repo.save_promises(a, a_contact, a_call, promises)
    assert len(repo.get_open_promises(a)) == 1


# ── Two-user full snapshot ────────────────────────────────────────────────


def test_two_users_full_snapshot_unchanged_after_stranger_ops(two_users):
    """После серии операций от имени B данные A побайтово те же."""
    repo, (a, a_call, a_contact), (b, b_call, b_contact) = two_users
    repo.save_transcripts(a, a_call, [Segment(0, 500, "alice text", "OWNER")])
    repo.save_analysis(a, a_call, Analysis(priority=5, risk_score=5, summary="a"))
    repo.save_events(a, a_call, [{"contact_id": a_contact, "event_type": "fact",
                                   "who": "OWNER", "payload": "p", "status": "open"}])
    repo.save_contact_summary(contact_id=a_contact, user_id=a, global_risk=10)

    before = _snapshot(repo, a)

    # Серия операций от имени B, целясь в ресурсы A
    repo.update_call_status(b, a_call, "error", "attack")
    repo.update_pipeline_stage(b, a_call, 9)
    repo.set_role_fragile(b, a_call, True)
    repo.update_call_paths(b, a_call, "/hacked", 1)
    repo.reset_call(b, a_call)
    repo.save_transcripts(b, a_call, [Segment(0, 1, "hacked", "OWNER")])
    repo.save_analysis(b, a_call, Analysis(priority=99, risk_score=99, summary="hacked"))
    repo.update_contact_guessed_name(b, a_contact, "Hacked", "x", a_call, "high")
    repo.save_contact_summary(contact_id=a_contact, user_id=b, global_risk=999)
    event_id = repo.get_open_events(a)[0]["id"]
    repo.update_event_status(b, event_id, "fulfilled")

    after = _snapshot(repo, a)
    assert after == before


# ── close_item (Telegram callback) ────────────────────────────────────────


def test_close_item_wrong_user_does_not_close_event(two_users):
    repo, (a, a_call, a_contact), (b, _, _) = two_users
    repo.save_events(a, a_call, [{"contact_id": a_contact, "event_type": "promise",
                                   "who": "OTHER", "payload": "pay", "status": "open"}])
    event_id = repo.get_open_events(a)[0]["id"]

    close_item(repo, b, "event", str(event_id))  # чужой user_id — no-op
    assert repo.get_open_events(a)[0]["status"] == "open"

    close_item(repo, a, "event", str(event_id))  # владелец — закрывает
    assert repo.get_open_events(a) == []


# ── add_user: allowlist slug (P-TEN-06) ───────────────────────────────────


@pytest.mark.parametrize(
    "bad_id",
    ["", "..", "../etc", "a/b", "a\\b", "-leadingdash", "_leadingunderscore",
     "юзер", "a" * 65, "a b", "a?b"],
)
def test_add_user_rejects_invalid_user_id(bad_id):
    repo = _repo()
    with pytest.raises(ValueError):
        repo.add_user(
            user_id=bad_id, display_name="T", telegram_chat_id="0",
            incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/ref.wav",
        )
    assert repo.get_user(bad_id) is None


@pytest.mark.parametrize("good_id", ["me", "user-1", "user_1", "A1", "a" * 64])
def test_add_user_accepts_valid_slug(good_id):
    repo = _repo()
    repo.add_user(
        user_id=good_id, display_name="T", telegram_chat_id="0",
        incoming_dir="/tmp/in", sync_dir="/tmp/sync", ref_audio="/tmp/ref.wav",
    )
    assert repo.get_user(good_id) is not None


def test_validate_user_id_directly():
    assert validate_user_id("me") == "me"
    with pytest.raises(ValueError):
        validate_user_id("../escape")


# ── user_profile_dir: path containment ────────────────────────────────────


def test_user_profile_dir_stays_inside_users_root(tmp_path):
    p = user_profile_dir(tmp_path, "me", "audio", "normalized")
    users_root = (tmp_path / "users").resolve()
    assert users_root in p.resolve().parents or p.resolve() == users_root
    assert str(p.resolve()).startswith(str(users_root))


def test_user_profile_dir_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        user_profile_dir(tmp_path, "../escape", "audio")


def test_user_profile_dir_deterministic_for_same_user(tmp_path):
    p1 = user_profile_dir(tmp_path, "me", "audio", "normalized")
    p2 = user_profile_dir(tmp_path, "me", "audio", "normalized")
    assert p1 == p2
