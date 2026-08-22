# -*- coding: utf-8 -*-
"""
analyze/roles.py — одна каноническая нормализация роли говорящего (R-08).

Промпт (`analyze_v002.txt`) отдаёт `promises[].who` как ``Me``/``S2``, БД и
графовый слой хранят ``OWNER``/``OTHER``/``UNKNOWN``, а потребители
(``insight/promise_outcomes.py::_side``, ``deliver/digest.py::_side``)
понимали только вторую форму — из-за чего live-обещания никогда не попадали
в outcomes. Нормализация теперь одна на все пути.
"""

from __future__ import annotations

OWNER = "OWNER"
OTHER = "OTHER"
UNKNOWN = "UNKNOWN"

_OWNER_FORMS = {"me", "owner", "[me]", "я"}
_OTHER_FORMS = {"s2", "other", "[s2]", "contact"}


def canonical_who(raw: object) -> str:
    """``Me|me|OWNER`` → ``OWNER``; ``S2|s2|OTHER`` → ``OTHER``; всё прочее → ``UNKNOWN``.

    Роль наугад не приписываем (шум-доктрина): пустое/незнакомое = UNKNOWN.
    """
    value = str(raw or "").strip().lower()
    if value in _OWNER_FORMS:
        return OWNER
    if value in _OTHER_FORMS:
        return OTHER
    return UNKNOWN


def side_of(raw: object) -> str | None:
    """Сторона обязательства: ``owner``/``contact``; UNKNOWN → ``None`` (исключаем)."""
    who = canonical_who(raw)
    if who == OWNER:
        return "owner"
    if who == OTHER:
        return "contact"
    return None
