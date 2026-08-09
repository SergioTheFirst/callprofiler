# -*- coding: utf-8 -*-
"""Tenant identity helpers (T-03).

Two responsibilities:
  1. ``validate_user_id`` — allowlist slug check for ``user_id`` before it is
     ever persisted (``Repository.add_user``) or used to build a filesystem path.
  2. ``user_profile_dir`` — resolve a path under ``data_dir/users/{user_id}/...``
     and assert (via realpath containment) that it did not escape the users
     root. Callers that build such paths should go through this helper
     instead of raw ``Path(data_dir) / "users" / user_id / ...``.
"""

from __future__ import annotations

import re
from pathlib import Path

_USER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def validate_user_id(user_id: str) -> str:
    """Return ``user_id`` if it matches the allowlist slug, else raise ValueError.

    Allowlist: ``[A-Za-z0-9][A-Za-z0-9_-]{0,63}`` — no ``..``, ``/``, ``\\``,
    no leading dash/underscore, no unicode, max 64 chars. Rejects empty string.
    """
    if not isinstance(user_id, str) or not _USER_ID_RE.match(user_id):
        raise ValueError(
            f"Недопустимый user_id: {user_id!r} — разрешено "
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
        )
    return user_id


def user_profile_dir(data_dir: str | Path, user_id: str, *parts: str) -> Path:
    """Resolve ``data_dir/users/{user_id}/*parts`` with containment check.

    Raises ValueError if ``user_id`` is invalid or if the resolved path
    escapes ``data_dir/users`` (defense-in-depth — validate_user_id already
    blocks ``..``/``/`` characters, this catches symlink/edge cases too).
    """
    validate_user_id(user_id)
    users_root = (Path(data_dir) / "users").resolve()
    target = (users_root / user_id).joinpath(*parts).resolve()
    if users_root != target and users_root not in target.parents:
        raise ValueError(f"Путь профиля вне data_dir/users: {target}")
    return target
