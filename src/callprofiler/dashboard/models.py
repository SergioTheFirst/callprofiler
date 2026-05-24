# -*- coding: utf-8 -*-
"""
Pydantic models for dashboard API responses.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class DashboardEvent(BaseModel):
    """Real-time event pushed via SSE."""

    event_type: Literal["call_created", "transcription_complete", "analysis_complete", "entity_updated"]
    timestamp: str  # ISO 8601
    data: dict[str, Any]


class CallHistoryItem(BaseModel):
    """Single call in history list."""

    call_id: int
    call_datetime: str | None
    contact_label: str
    direction: str
    duration_sec: int | None
    status: str
    call_type: str | None = None
    risk_score: int | None = None
    summary: str | None = None


class EntityProfile(BaseModel):
    """Full entity profile with psychology + biography."""

    entity_id: int
    canonical_name: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)

    # Entity metrics
    bs_index: float | None = None
    avg_risk: float | None = None
    total_calls: int | None = None
    trust_score: float | None = None
    volatility: float | None = None
    conflict_count: int | None = None

    # Psychology profile
    temperament: dict[str, Any] | None = None
    big_five: dict[str, float] | None = None
    motivation: dict[str, Any] | None = None

    # Biography portrait
    prose: str | None = None
    traits: list[str] = Field(default_factory=list)
    relationship: str | None = None


class ContactProfile(BaseModel):
    """Contact profile with summary, promises, and recent calls."""

    contact_id: int
    phone_e164: str | None = None
    display_name: str | None = None
    guessed_name: str | None = None
    name_confirmed: bool = False
    total_calls: int = 0
    last_call_date: str | None = None
    global_risk: float | None = None
    avg_bs_score: float | None = None
    top_hook: str | None = None
    contact_role: str | None = None
    advice: str | None = None
    open_promises: list[dict[str, Any]] = Field(default_factory=list)
    open_debts: list[dict[str, Any]] = Field(default_factory=list)
    personal_facts: list[dict[str, Any]] = Field(default_factory=list)
    recent_calls: list[CallHistoryItem] = Field(default_factory=list)


class CharacterSummary(BaseModel):
    """Brief character info for the list view."""

    entity_id: int
    canonical_name: str
    entity_type: str
    total_calls: int = 0
    avg_risk: float | None = None
    bs_index: float | None = None
    temperament_type: str | None = None
    motivation_primary: str | None = None
    character_label: str = ""
    has_portrait: bool = False
    has_psychology: bool = False


class CharacterProfile(EntityProfile):
    """Full character profile extending entity data with contact, calls, patterns."""

    character_summary: str = ""
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    contact: dict[str, Any] | None = None
    open_promises: list[dict[str, Any]] = Field(default_factory=list)
    recent_calls: list[CallHistoryItem] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    temporal: dict[str, Any] | None = None
    network: dict[str, Any] | None = None


class DashboardStats(BaseModel):
    """Overall system statistics."""

    total_calls: int
    total_entities: int
    total_portraits: int
    avg_risk: float | None = None
    last_call_datetime: str | None = None
