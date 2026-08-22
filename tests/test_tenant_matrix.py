# -*- coding: utf-8 -*-
"""T-24: матрица изоляции арендаторов — каждый user-scoped read Repository не видит чужие строки.

Добавляя новый read-метод с user_id, добавьте строку в MATRIX: тест — исполняемый гейт P-TEN.
"""
from __future__ import annotations

import pytest

from callprofiler.models import Segment

from test_repository import add_call, add_user, repo  # noqa: F401 — фикстура repo (tests/ в sys.path, importmode=prepend)

A, B = "tenant_a", "tenant_b"


def _seed(repo, uid: str, md5: str) -> tuple[int, int]:
    add_user(repo, uid)
    call_id, _ = add_call(repo, uid, md5=md5)
    conn = repo._get_conn()
    contact_id = 100 if uid == A else 200
    conn.execute("INSERT INTO contacts(contact_id, user_id, phone_e164, display_name) VALUES (?,?,?,?)",
                 (contact_id, uid, f"+7{contact_id}", uid))
    conn.execute("UPDATE calls SET contact_id=? WHERE call_id=?", (contact_id, call_id))
    conn.commit()
    repo.save_transcripts(uid, call_id, [Segment(start_ms=0, end_ms=900, text=f"обещаю {uid}", speaker="OTHER")])
    repo.save_promises(uid, contact_id, call_id, [{"who": "OTHER", "what": f"what {uid}", "due": None}])
    repo.save_events(uid, call_id, [{"event_type": "promise", "who": "OTHER", "payload": f"ev {uid}", "contact_id": contact_id}])
    repo.update_call_status(uid, call_id, "error", "boom", backoff_base_sec=0)
    return call_id, contact_id


def _ids(rows) -> set:
    out = set()
    for r in rows:
        for k in ("call_id", "contact_id", "user_id"):
            if isinstance(r, dict) and r.get(k) is not None:
                out.add((k, r[k]))
    return out


# (имя метода, builder аргументов для ЧУЖОГО вызова: (user_id=B, ids of A)) → ожидание: пусто/None
MATRIX = [
    ("get_call", lambda ca, cb, ka, kb: (B, ca)),
    ("get_transcript", lambda ca, cb, ka, kb: (B, ca)),
    ("get_analysis", lambda ca, cb, ka, kb: (B, ca)),
    ("get_contact", lambda ca, cb, ka, kb: (B, ka)),
    ("get_contact_for_user", lambda ca, cb, ka, kb: (B, ka)),
    ("get_calls_for_contact", lambda ca, cb, ka, kb: (B, ka)),
    ("get_contact_promises", lambda ca, cb, ka, kb: (B, ka)),
    ("get_contact_summary", lambda ca, cb, ka, kb: (B, ka)),
    ("get_call_count_for_contact", lambda ca, cb, ka, kb: (B, ka)),
]


@pytest.mark.parametrize("method,args", MATRIX, ids=[m for m, _ in MATRIX])
def test_foreign_ids_invisible(repo, method, args):
    ca, ka = _seed(repo, A, "md5a")
    cb, kb = _seed(repo, B, "md5b")
    res = getattr(repo, method)(*args(ca, cb, ka, kb))
    assert res in (None, [], 0, {}), f"{method}: чужие данные видны: {res!r}"


@pytest.mark.parametrize("method", ["get_open_promises", "get_calls_for_user", "get_stalled_calls",
                                    "get_pending_calls", "get_all_contacts_for_user"])
def test_list_methods_only_own_rows(repo, method):
    ca, ka = _seed(repo, A, "md5a")
    cb, kb = _seed(repo, B, "md5b")
    rows = getattr(repo, method)(B)
    assert rows is not None
    assert ("user_id", A) not in _ids(rows) and ("call_id", ca) not in _ids(rows) and ("contact_id", ka) not in _ids(rows)


def test_get_error_calls_scoped(repo):
    ca, _ = _seed(repo, A, "md5a")
    cb, _ = _seed(repo, B, "md5b")
    assert {r["call_id"] for r in repo.get_error_calls(3, user_id=B)} == {cb}
