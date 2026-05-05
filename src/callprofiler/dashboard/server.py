# -*- coding: utf-8 -*-
"""
FastAPI server for CallProfiler dashboard — real-time pipeline monitoring.
Read-only, zero-impact on workflow. Polls SQLite every 2s for new data.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from callprofiler.dashboard.config import POLL_INTERVAL_SEC, SSE_KEEPALIVE_SEC
from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.dashboard.models import CallHistoryItem, DashboardStats, EntityProfile

log = logging.getLogger(__name__)

app = FastAPI(title="CallProfiler Dashboard", version="2.0.0")

_USER_ID: str | None = None
_DB_READER: DashboardDBReader | None = None
_sse_queue: asyncio.Queue = asyncio.Queue()
_poller_running = False

DASHBOARD_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR / "static")), name="static")


def set_user_id(user_id: str):
    global _USER_ID, _DB_READER
    _USER_ID = user_id
    db_path = Path("C:/calls/data/db/callprofiler.db")
    _DB_READER = DashboardDBReader(str(db_path))
    log.info("Dashboard initialized: user_id=%s, db=%s", user_id, db_path)


@app.on_event("startup")
async def start_poller():
    global _poller_running
    if not _poller_running:
        _poller_running = True
        asyncio.create_task(_event_poller())
        log.info("Event poller started")


async def _event_poller():
    """Background task: poll DB for new analyses and push to SSE queue."""
    last_analysis_id = 0
    global_stats_sent_at = 0.0

    while True:
        await asyncio.sleep(POLL_INTERVAL_SEC)
        if not _DB_READER or not _USER_ID:
            continue

        try:
            rows = _DB_READER.get_new_analyses(_USER_ID, since_id=last_analysis_id, limit=20)
            for row in rows:
                aid = row.get("analysis_id", 0)
                if aid > last_analysis_id:
                    last_analysis_id = aid
                await _sse_queue.put({
                    "type": "analysis",
                    "ts": datetime.now().isoformat(),
                    "call_id": row.get("call_id"),
                    "contact": row.get("contact_name") or "?",
                    "phone": row.get("phone_e164") or "",
                    "parse_status": row.get("parse_status"),
                    "summary": (row.get("summary") or "")[:200],
                    "risk_score": row.get("risk_score"),
                    "call_type": row.get("call_type"),
                    "schema_version": row.get("schema_version"),
                    "created_at": row.get("created_at"),
                    "call_datetime": row.get("call_datetime"),
                    "direction": row.get("direction"),
                    "duration_sec": row.get("duration_sec"),
                    "model": row.get("model"),
                    "source_filename": row.get("source_filename"),
                })

            now = time.monotonic()
            if now - global_stats_sent_at > 30:
                global_stats_sent_at = now
                stats = _DB_READER.get_stats(_USER_ID)
                await _sse_queue.put({"type": "stats", "ts": datetime.now().isoformat(), "data": stats})

        except Exception as exc:
            log.error("[poller] error: %s", exc)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/events/stream")
async def event_stream(request: Request):
    """SSE endpoint — pushes poller events to browser in real-time."""

    async def generate():
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(_sse_queue.get(), timeout=SSE_KEEPALIVE_SEC)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield f": keepalive {datetime.now().isoformat()}\n\n"
            except Exception:
                yield f"event: error\ndata: {json.dumps({'error': 'stream error'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/history")
async def get_history(limit: int = 50) -> list[CallHistoryItem]:
    calls = _DB_READER.get_recent_calls(_USER_ID, limit=limit)
    return [CallHistoryItem(**call) for call in calls]


@app.get("/api/entity/{entity_id}")
async def get_entity(entity_id: int) -> EntityProfile:
    profile = _DB_READER.get_entity_profile(entity_id, _USER_ID)
    if not profile:
        return EntityProfile(entity_id=entity_id, canonical_name="?", entity_type="?")
    return EntityProfile(**profile)


@app.get("/api/stats")
async def get_stats() -> DashboardStats:
    stats = _DB_READER.get_stats(_USER_ID)
    return DashboardStats(**stats)


@app.get("/api/shutdown")
async def shutdown():
    """Stop the dashboard server and close the browser."""
    import os, signal
    log.info("Shutdown requested via API")
    # Kill the server process — browser window closes too
    os._exit(0)