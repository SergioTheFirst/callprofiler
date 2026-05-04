# -*- coding: utf-8 -*-
"""Real-time event system for dashboard updates."""

from callprofiler.events.event_bus import (
    DashboardEvent,
    emit_event_sync,
    get_client_count,
    subscribe,
    unsubscribe,
)

__all__ = [
    "DashboardEvent",
    "emit_event_sync",
    "subscribe",
    "unsubscribe",
    "get_client_count",
]
