# -*- coding: utf-8 -*-
"""
Real-time event bus for dashboard updates.

Uses asyncio queues to broadcast events from pipeline to dashboard SSE clients.
No Redis, no external dependencies - pure Python in-memory event bus.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)

# Global event queue for SSE clients
_event_queues: list[asyncio.Queue] = []
_lock = asyncio.Lock()


@dataclass
class DashboardEvent:
    """Event sent to dashboard clients."""
    event_type: str  # call_created, transcription_complete, analysis_complete, entity_updated
    timestamp: str
    data: dict[str, Any]


async def subscribe() -> asyncio.Queue:
    """Subscribe to event stream. Returns queue that receives events."""
    async with _lock:
        queue = asyncio.Queue(maxsize=100)
        _event_queues.append(queue)
        log.info("New SSE client subscribed. Total clients: %d", len(_event_queues))
        return queue


async def unsubscribe(queue: asyncio.Queue):
    """Unsubscribe from event stream."""
    async with _lock:
        if queue in _event_queues:
            _event_queues.remove(queue)
            log.info("SSE client unsubscribed. Total clients: %d", len(_event_queues))


def emit_event_sync(event_type: str, data: dict[str, Any]):
    """
    Emit event from synchronous code (enricher, orchestrator).

    Creates event loop if needed and schedules broadcast.
    Safe to call from any thread.
    """
    event = DashboardEvent(
        event_type=event_type,
        timestamp=datetime.now().isoformat(),
        data=data,
    )

    try:
        # Try to get running loop
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop running - create new one and run broadcast
        asyncio.run(_broadcast(event))
        return

    # Schedule broadcast in existing loop
    asyncio.create_task(_broadcast(event))


async def _broadcast(event: DashboardEvent):
    """Broadcast event to all subscribed clients."""
    async with _lock:
        if not _event_queues:
            return  # No clients connected

        dead_queues = []
        for queue in _event_queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("Client queue full, dropping event")
                dead_queues.append(queue)
            except Exception as e:
                log.error("Failed to send event to client: %s", e)
                dead_queues.append(queue)

        # Remove dead queues
        for queue in dead_queues:
            _event_queues.remove(queue)

        if dead_queues:
            log.info("Removed %d dead clients. Active: %d", len(dead_queues), len(_event_queues))


def get_client_count() -> int:
    """Get number of connected SSE clients."""
    return len(_event_queues)
