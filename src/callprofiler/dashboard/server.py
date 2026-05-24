# -*- coding: utf-8 -*-
"""
FastAPI server for CallProfiler dashboard — real-time pipeline monitoring.
Read-only, zero-impact on workflow. Polls SQLite every 2s for new analysis data.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from callprofiler.dashboard.config import POLL_INTERVAL_SEC, SSE_KEEPALIVE_SEC
from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.dashboard.models import (
    CallHistoryItem, DashboardStats, EntityProfile,
    CharacterSummary, CharacterProfile, ContactProfile,
)
from callprofiler.dashboard.tools import DashboardTools

log = logging.getLogger(__name__)

app = FastAPI(title="CallProfiler Dashboard", version="2.1.0")

_USER_ID: str | None = None
_DB_READER: DashboardDBReader | None = None
_TOOLS: DashboardTools | None = None
_sse_queue: asyncio.Queue = asyncio.Queue()
_poller_running = False

DASHBOARD_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR / "static")), name="static")


def set_user_id(user_id: str, config=None):
    global _USER_ID, _DB_READER, _TOOLS
    _USER_ID = user_id
    db_path = Path(config.data_dir) / "db" / "callprofiler.db" if config else Path("C:/calls/data/db/callprofiler.db")
    _DB_READER = DashboardDBReader(str(db_path))
    _TOOLS = DashboardTools(config, user_id)
    log.info("Dashboard initialized: user_id=%s", user_id)



@app.get("/api/audio/{call_id}")
def audio_endpoint(call_id: int):
    """Serve normalized audio file with user_id isolation."""
    if _DB_READER is None or _USER_ID is None:
        return Response(status_code=503)
    call = _DB_READER.get_call(call_id)
    if not call or call.get("user_id") != _USER_ID:
        return Response(status_code=404)
    norm_path = call.get("norm_path")
    if not norm_path or not Path(norm_path).is_file():
        return Response(status_code=404)
    return FileResponse(norm_path, media_type="audio/wav")


@app.on_event("startup")
async def start_poller():
    global _poller_running
    if not _poller_running:
        _poller_running = True
        asyncio.create_task(_event_poller())
        log.info("Event poller started")


async def _event_poller():
    last_analysis_id = 0
    global_stats_sent_at = 0.0
    poll_tick = 0

    while True:
        await asyncio.sleep(POLL_INTERVAL_SEC)
        if not _DB_READER or not _USER_ID:
            continue
        poll_tick += 1

        try:
            batch_limit = 50 if last_analysis_id == 0 else 20
            rows = _DB_READER.get_new_analyses(_USER_ID, since_id=last_analysis_id, limit=batch_limit)
            for row in rows:
                aid = row.get("analysis_id", 0)
                if aid > last_analysis_id:
                    last_analysis_id = aid
                await _sse_queue.put({
                    "type": "analysis", "ts": datetime.now().isoformat(),
                    "call_id": row.get("call_id"), "contact": row.get("contact_name") or "?",
                    "phone": row.get("phone_e164") or "", "parse_status": row.get("parse_status"),
                    "summary": (row.get("summary") or "")[:200], "risk_score": row.get("risk_score"),
                    "call_type": row.get("call_type"), "schema_version": row.get("schema_version"),
                    "created_at": row.get("created_at"), "call_datetime": row.get("call_datetime"),
                    "direction": row.get("direction"), "duration_sec": row.get("duration_sec"),
                    "model": row.get("model"), "source_filename": row.get("source_filename"),
                })

            await _sse_queue.put({
                "type": "heartbeat", "ts": datetime.now().isoformat(),
                "poll_tick": poll_tick, "last_id": last_analysis_id,
                "pending": bool(rows and len(rows) == batch_limit),
            })

            now = time.monotonic()
            if now - global_stats_sent_at > 30:
                global_stats_sent_at = now
                stats = _DB_READER.get_stats(_USER_ID)
                await _sse_queue.put({"type": "stats", "ts": datetime.now().isoformat(), "data": stats})

        except Exception as exc:
            log.error("[poller] error: %s", exc)


@app.get("/favicon.ico")
async def favicon():
    ico = b'\x00\x00\x01\x00\x01\x00\x01\x01\x00\x00\x01\x00\x18\x00\x0b\x00\x00\x00\x16\x00\x00\x00\x28\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x01\x00\x18\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x10\xb9\x81\x00\x00\x00\x00'
    return Response(content=ico, media_type="image/x-icon")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/events/stream")
async def event_stream(request: Request):
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



@app.get("/api/characters")
async def get_all_characters(request: Request) -> list[CharacterSummary]:
    if not _DB_READER or not _USER_ID:
        return []
    try:
        characters = _DB_READER.get_all_characters(_USER_ID)
        return [CharacterSummary(**c) for c in characters]
    except Exception as e:
        log.error("Failed to load characters: %s", e)
        return []


@app.get("/api/character/{entity_id}")
async def get_character(entity_id: int) -> CharacterProfile:
    if not _DB_READER or not _USER_ID:
        return CharacterProfile(
            entity_id=entity_id, canonical_name="?", entity_type="?",
            character_summary="Dashboard not initialized"
        )
    try:
        profile = _DB_READER.get_character_profile(entity_id, _USER_ID)
        if not profile:
            return CharacterProfile(
                entity_id=entity_id, canonical_name="?", entity_type="?",
                character_summary="Character not found"
            )
        return CharacterProfile(**profile)
    except Exception as e:
        log.error("Failed to load character %d: %s", entity_id, e)
        return CharacterProfile(
            entity_id=entity_id, canonical_name="error", entity_type="?",
            character_summary=str(e)
        )


@app.get("/api/contact/{contact_id}")
async def get_contact(contact_id: int) -> ContactProfile:
    if not _DB_READER or not _USER_ID:
        return ContactProfile(contact_id=contact_id)
    try:
        profile = _DB_READER.get_contact_profile(contact_id, _USER_ID)
        if not profile:
            return ContactProfile(contact_id=contact_id)
        return ContactProfile(**profile)
    except Exception as e:
        log.error("Failed to load contact %d: %s", contact_id, e)
        return ContactProfile(contact_id=contact_id)


@app.get("/api/analytics")
async def get_analytics(request: Request):
    if not _DB_READER or not _USER_ID:
        return {}
    try:
        return _DB_READER.get_analytics(_USER_ID)
    except Exception as e:
        log.error("Failed to load analytics: %s", e)
        return {}


@app.get("/api/tools/status")
async def tools_status():
    if not _TOOLS:
        return {"by_status": {}, "pending": 0, "error": 0, "processed": 0}
    try:
        return _TOOLS.get_status()
    except Exception as e:
        log.error("tools/status: %s", e)
        return {"error": str(e)}


@app.post("/api/tools/reprocess")
async def tools_reprocess():
    if not _TOOLS:
        return {"status": "error", "message": "Not initialized"}
    try:
        return await _TOOLS.run_reprocess()
    except Exception as e:
        log.error("tools/reprocess: %s", e)
        return {"status": "error", "message": str(e)}


@app.post("/api/tools/rebuild-summaries")
async def tools_rebuild_summaries():
    if not _TOOLS:
        return {"status": "error", "message": "Not initialized"}
    try:
        return await _TOOLS.run_rebuild_summaries()
    except Exception as e:
        log.error("tools/rebuild-summaries: %s", e)
        return {"status": "error", "message": str(e)}


@app.post("/api/tools/extract-names")
async def tools_extract_names():
    if not _TOOLS:
        return {"status": "error", "message": "Not initialized"}
    try:
        return await _TOOLS.run_extract_names()
    except Exception as e:
        log.error("tools/extract-names: %s", e)
        return {"status": "error", "message": str(e)}


@app.post("/api/tools/rebuild-cards")
async def tools_rebuild_cards():
    if not _TOOLS:
        return {"status": "error", "message": "Not initialized"}
    try:
        return await _TOOLS.run_rebuild_cards()
    except Exception as e:
        log.error("tools/rebuild-cards: %s", e)
        return {"status": "error", "message": str(e)}


@app.get("/api/tools/history")
async def tools_history():
    if not _TOOLS:
        return []
    return _TOOLS.get_history()

@app.get("/api/shutdown")
async def shutdown():
    import os
    log.info("Shutdown requested via API")
    os._exit(0)