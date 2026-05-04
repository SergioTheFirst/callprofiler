# -*- coding: utf-8 -*-
"""
FastAPI server for dashboard with SSE event stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from callprofiler.dashboard.config import SSE_KEEPALIVE_SEC
from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.dashboard.models import (
    CallHistoryItem,
    DashboardStats,
    EntityProfile,
)

log = logging.getLogger(__name__)

app = FastAPI(title="CallProfiler Dashboard", version="1.0.0")

# Global state
_USER_ID: str | None = None
_DB_READER: DashboardDBReader | None = None

# Templates and static files
DASHBOARD_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR / "static")), name="static")


def set_user_id(user_id: str):
    """Set global user_id and initialize DB reader."""
    global _USER_ID, _DB_READER
    _USER_ID = user_id
    db_path = Path("D:/calls/data/db/callprofiler.db")
    if not db_path.exists():
        db_path = Path("C:/calls/data/db/callprofiler.db")
    _DB_READER = DashboardDBReader(db_path)
    log.info("Dashboard initialized for user_id=%s, db_path=%s", user_id, db_path)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve main dashboard page."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@app.get("/events/stream")
async def event_stream(request: Request):
    """SSE endpoint for real-time events."""
    from callprofiler.events import subscribe, unsubscribe

    async def generate():
        queue = await subscribe()
        last_keepalive = datetime.now()

        try:
            while True:
                if await request.is_disconnected():
                    log.info("Client disconnected from SSE stream")
                    break

                try:
                    # Wait for event with timeout for keepalive
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_SEC)
                    yield f"data: {json.dumps({'event_type': event.event_type, 'timestamp': event.timestamp, 'data': event.data})}\n\n"
                    last_keepalive = datetime.now()

                except asyncio.TimeoutError:
                    # Send keepalive comment
                    now = datetime.now()
                    yield f": keepalive {now.isoformat()}\n\n"
                    last_keepalive = now

                except Exception as e:
                    log.error("Error in SSE stream: %s", e, exc_info=True)
                    yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        finally:
            await unsubscribe(queue)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/history")
async def get_history(limit: int = 50) -> list[CallHistoryItem]:
    """Get call history."""
    calls = _DB_READER.get_recent_calls(_USER_ID, limit=limit)
    return [CallHistoryItem(**call) for call in calls]


@app.get("/api/entity/{entity_id}")
async def get_entity(entity_id: int) -> EntityProfile:
    """Get full entity profile."""
    profile = _DB_READER.get_entity_profile(entity_id, _USER_ID)
    if not profile:
        return {"error": "Entity not found"}
    return EntityProfile(**profile)


@app.get("/api/stats")
async def get_stats() -> DashboardStats:
    """Get system statistics."""
    stats = _DB_READER.get_stats(_USER_ID)
    return DashboardStats(**stats)
