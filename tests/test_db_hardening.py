import pytest
from callprofiler.db.repository import Repository


# --- local helpers (self-contained, do not import from sibling test modules) ---
def _add_user(
    repo: Repository,
    user_id: str,
    display_name: str = "Test User",
    phone_e164: str = "+79161234567",
    telegram_chat_id: str = None,
) -> None:
    repo.add_user(
        user_id=user_id,
        display_name=display_name,
        telegram_chat_id=telegram_chat_id,
        incoming_dir="C:\\calls",
        sync_dir="C:\\sync",
        ref_audio="C:\\ref.wav",
    )


def _add_call(
    repo: Repository,
    user_id: str,
    md5: str,
    contact_id: int | None = None,
    filename: str = "test.mp3",
    call_datetime=None,
    audio_path: str = "audio.wav",
) -> None:
    repo.create_call(
        user_id=user_id,
        contact_id=contact_id,
        source_md5=md5,
        direction="IN",
        source_filename=filename,
        call_datetime=call_datetime,
        audio_path=audio_path,
    )


@pytest.fixture
def repo() -> Repository:
    r = Repository(":memory:")
    r.init_db()
    return r


def test_contact_name_overwrite_and_confirmation(repo: Repository) -> None:
    """get_or_create_contact must overwrite display_name and set name_confirmed=1
    when a display_name is supplied, protecting it from guessed-name overwrites."""
    _add_user(repo, user_id="user1")
    phone = "+79990001122"

    # Step 1: create contact without display_name -> unconfirmed, NULL display_name
    cid = repo.get_or_create_contact(
        user_id="user1", phone_e164=phone, display_name=None
    )
    assert isinstance(cid, int)

    row = (
        repo._get_conn()
        .execute(
            "SELECT display_name, name_confirmed, guessed_name FROM contacts WHERE contact_id = ?",
            (cid,),
        )
        .fetchone()
    )
    assert row["display_name"] is None
    assert row["name_confirmed"] == 0
    assert row["guessed_name"] is None

    # Step 2: supply display_name -> overwrite + confirm
    cid2 = repo.get_or_create_contact(
        user_id="user1", phone_e164=phone, display_name="Alice"
    )
    assert cid2 == cid

    row = (
        repo._get_conn()
        .execute(
            "SELECT display_name, name_confirmed, guessed_name FROM contacts WHERE contact_id = ?",
            (cid,),
        )
        .fetchone()
    )
    assert row["display_name"] == "Alice"
    assert row["name_confirmed"] == 1


def test_guessed_name_guard(repo: Repository) -> None:
    """update_contact_guessed_name must only update contacts where
    name_confirmed = 0 (or NULL). Confirmed names are protected."""
    _add_user(repo, user_id="user1")
    phone = "+79990003344"

    # Unconfirmed contact -> guessed name accepted
    cid = repo.get_or_create_contact(
        user_id="user1", phone_e164=phone, display_name=None
    )
    call_id = repo.create_call(
        user_id="user1",
        contact_id=cid,
        direction="IN",
        call_datetime="2024-01-01 12:00:00",
        source_filename="test.wav",
        source_md5=phone,
        audio_path="/tmp/test.wav",
    )
    assert repo.update_contact_guessed_name(cid, "Guessed-A", "test", call_id, "high") is True

    row = (
        repo._get_conn()
        .execute(
            "SELECT guessed_name, name_confirmed FROM contacts WHERE contact_id = ?",
            (cid,),
        )
        .fetchone()
    )
    assert row["guessed_name"] == "Guessed-A"
    assert row["name_confirmed"] == 0

    # Confirm the contact name via get_or_create_contact with display_name
    repo.get_or_create_contact(
        user_id="user1", phone_e164=phone, display_name="RealName"
    )

    # Now update_contact_guessed_name must return False and leave name unchanged
    assert repo.update_contact_guessed_name(cid, "Guessed-B", "test", 1, "high") is False

    row = (
        repo._get_conn()
        .execute(
            "SELECT guessed_name, name_confirmed FROM contacts WHERE contact_id = ?",
            (cid,),
        )
        .fetchone()
    )
    assert row["guessed_name"] == "Guessed-A"
    assert row["name_confirmed"] == 1


def test_call_idempotency_via_call_exists(repo: Repository) -> None:
    """create_call performs a blind INSERT; callers must use call_exists
    to avoid duplicates. This test documents the required guard pattern."""
    _add_user(repo, user_id="user1")
    md5 = "deadbeef000000000000000000000000"

    # Should not exist yet
    assert repo.call_exists(user_id="user1", source_md5=md5) is False

    # Idempotent insertion pattern
    if not repo.call_exists(user_id="user1", source_md5=md5):
        _add_call(repo, user_id="user1", md5=md5)

    assert repo.call_exists(user_id="user1", source_md5=md5) is True

    # Second pass through the same guard must NOT insert a duplicate
    if not repo.call_exists(user_id="user1", source_md5=md5):
        _add_call(repo, user_id="user1", md5=md5)

    row = (
        repo._get_conn()
        .execute(
            "SELECT COUNT(*) AS cnt FROM calls WHERE user_id = ? AND source_md5 = ?",
            ("user1", md5),
        )
        .fetchone()
    )
    assert row["cnt"] == 1


def test_migration_safety_init_db_and_columns(repo: Repository) -> None:
    """init_db() internally runs _migrate() which ALTER TABLE-adds post-release
    columns (e.g. guessed_name). After init_db, those columns must be present
    and writable without error."""
    _add_user(repo, user_id="user1")
    repo.get_or_create_contact(user_id="user1", phone_e164="+111", display_name=None)

    # Prove that migrated columns exist and accept data
    repo._get_conn().execute(
        "UPDATE contacts SET guessed_name = ?, name_confirmed = ? WHERE user_id = ?",
        ("MigratedOK", 0, "user1"),
    )

    row = (
        repo._get_conn()
        .execute(
            "SELECT guessed_name, name_confirmed FROM contacts WHERE user_id = ?",
            ("user1",),
        )
        .fetchone()
    )
    assert row["guessed_name"] == "MigratedOK"
    assert row["name_confirmed"] == 0
