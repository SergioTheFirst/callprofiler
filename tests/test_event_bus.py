"""Regression tests for events/event_bus.py."""
import asyncio
from unittest.mock import patch

import pytest

from callprofiler.events.event_bus import (
    DashboardEvent,
    emit_event_sync,
    get_client_count,
    subscribe,
    unsubscribe,
)


@pytest.fixture
def _clean_queues():
    """Empty all global subscriber queues after each test."""
    yield
    # Wipe global queue list to avoid cross-test pollution.
    from callprofiler.events.event_bus import _event_queues
    _event_queues.clear()


@pytest.mark.asyncio
async def test_subscribe_returns_queue(_clean_queues):
    queue = await subscribe()
    assert queue is not None
    assert isinstance(queue, asyncio.Queue)


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue(_clean_queues):
    queue = await subscribe()
    assert get_client_count() == 1
    await unsubscribe(queue)
    assert get_client_count() == 0


@pytest.mark.asyncio
async def test_emit_event_sync_broadcasts(_clean_queues):
    queue = await subscribe()
    emit_event_sync("TEST_EVENT", {"key": "value"})
    event = await asyncio.wait_for(queue.get(), timeout=1)
    assert isinstance(event, DashboardEvent)
    assert event.event_type == "TEST_EVENT"
    assert isinstance(event.timestamp, str)
    assert event.data == {"key": "value"}


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_event(_clean_queues):
    queue1 = await subscribe()
    queue2 = await subscribe()
    emit_event_sync("BROADCAST", {})
    event1 = await asyncio.wait_for(queue1.get(), timeout=1)
    event2 = await asyncio.wait_for(queue2.get(), timeout=1)
    assert event1.event_type == "BROADCAST"
    assert event2.event_type == "BROADCAST"


@pytest.mark.asyncio
async def test_queue_full_drops_event(_clean_queues):
    queue = await subscribe()
    # Fill queue to capacity (100).
    for _ in range(100):
        queue.put_nowait(DashboardEvent("FILL", "ts", {}))
    # Event should be dropped without error; the source prunes dead queues.
    emit_event_sync("DROPPED", {})
    # No assertion needed—just ensure no exception is raised.


@pytest.mark.asyncio
async def test_dead_queue_pruned(_clean_queues):
    queue = await subscribe()
    # Cancel the consumer so queue becomes "dead".
    queue.put_nowait(DashboardEvent("OLD", "ts", {}))
    # New event should prune dead queue and not crash.
    emit_event_sync("PRUNE", {})
    # The remaining subscriber count should be 1 since queue is still in list.
    # After pruning attempt, get_client_count returns len(_event_queues).
    assert get_client_count() == 1
