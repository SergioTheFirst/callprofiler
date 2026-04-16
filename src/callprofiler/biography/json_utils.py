# -*- coding: utf-8 -*-
"""
json_utils.py — robust JSON extraction from LLM replies.

Local models often wrap JSON in markdown fences, add a prose prefix, or leave
trailing commas / unclosed braces. This utility tries hard to recover a dict
or list before giving up.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)


def extract_json(text: str | None) -> Any | None:
    """Return parsed JSON (dict/list) or None. Never raises."""
    if not text:
        return None

    stripped = text.strip()

    # 1) Strip markdown fences.
    stripped = _unfence(stripped)

    # 2) Direct parse attempt.
    parsed = _try_load(stripped)
    if parsed is not None:
        return parsed

    # 3) Substring between outermost {...} or [...].
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i = stripped.find(open_c)
        j = stripped.rfind(close_c)
        if 0 <= i < j:
            candidate = stripped[i : j + 1]
            parsed = _try_load(candidate)
            if parsed is not None:
                return parsed
            # Attempt lenient repair.
            repaired = _lenient_repair(candidate)
            parsed = _try_load(repaired)
            if parsed is not None:
                return parsed

    log.debug("extract_json failed; first 200 chars: %r", stripped[:200])
    return None


def _unfence(s: str) -> str:
    # ```json ... ```  or ``` ... ```
    m = re.search(r"```(?:json)?\s*(.*?)```", s, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return s


def _try_load(s: str) -> Any | None:
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


def _lenient_repair(s: str) -> str:
    # Remove trailing commas before } or ].
    s = re.sub(r",\s*([}\]])", r"\1", s)
    # Balance braces if the tail was cut off.
    open_braces = s.count("{") - s.count("}")
    open_brackets = s.count("[") - s.count("]")
    if open_brackets > 0:
        s += "]" * open_brackets
    if open_braces > 0:
        s += "}" * open_braces
    return s
