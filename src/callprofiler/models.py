# -*- coding: utf-8 -*-
"""
models.py — dataclasses для всех доменных объектов.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CallMetadata:
    phone: str | None           # E.164, например +79161234567
    call_datetime: datetime | None
    direction: str              # IN / OUT / UNKNOWN
    contact_name: str | None
    raw_filename: str


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    text: str
    speaker: str = "UNKNOWN"    # OWNER / OTHER / UNKNOWN


@dataclass
class Analysis:
    priority: int               # 0-100
    risk_score: int             # 0-100
    summary: str
    action_items: list[str] = field(default_factory=list)
    promises: list[dict] = field(default_factory=list)
    flags: dict = field(default_factory=dict)
    key_topics: list[str] = field(default_factory=list)
    raw_response: str = ""
    model: str = ""
    prompt_version: str = ""
    call_type: str = "unknown"  # business/smalltalk/short/spam/personal/unknown
    hook: str | None = None     # одна фраза-напоминание для следующего звонка
    parse_status: str = "unknown"  # parsed_ok/parsed_partial/parse_failed/output_truncated
