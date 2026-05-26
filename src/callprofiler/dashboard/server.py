"""CallProfiler Dashboard — v3.0.0 Glass-Industrial Command Center.

SSE backbone + ECharts + 5-tab shell (Overview, Calls, Search, Entities, System).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from callprofiler.dashboard.config import POLL_INTERVAL_SEC, SSE_KEEPALIVE_SEC, THEME
from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.dashboard.tools import DashboardTools

logger = logging.getLogger(__name__)

_APP: FastAPI | None = None
_USER_ID: str | None = None
_CONFIG: Any = None
_SSE_SUBSCRIBERS: set[asyncio.Queue[str]] = set()

VERSION = "3.0.0"


def _build_app(user_id: str = "test_user", config: Any = None) -> FastAPI:
    global _APP, _USER_ID, _CONFIG
    _USER_ID = user_id
    _CONFIG = config

    fa = FastAPI(title="CallProfiler Dashboard", version=VERSION)

    static_dir = Path(__file__).with_suffix("").parent / "static"
    templates_dir = Path(__file__).with_suffix("").parent / "templates"

    if static_dir.exists():
        fa.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    tpl = Jinja2Templates(directory=str(templates_dir))

    async def _broadcast(payload: str) -> None:
        dead: set[asyncio.Queue[str]] = set()
        for q in _SSE_SUBSCRIBERS:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.add(q)
        _SSE_SUBSCRIBERS.difference_update(dead)

    async def _poller() -> None:
        while True:
            await asyncio.sleep(POLL_INTERVAL_SEC)
            if _CONFIG is None:
                continue
            try:
                reader = DashboardDBReader(_CONFIG.data_dir)
                tools = DashboardTools(_CONFIG, _USER_ID)
                status = tools.get_status()
                by_stage = reader.get_calls_by_stage(_USER_ID)
                payload = json.dumps(
                    {"type": "tick", "status": status, "by_stage": by_stage},
                    ensure_ascii=False,
                )
                await _broadcast(payload)
            except Exception:
                logger.warning("Dashboard poller error", exc_info=True)

    @fa.on_event("startup")
    async def _startup() -> None:
        if _CONFIG is not None:
            asyncio.create_task(_poller())

    @fa.get("/", response_class=HTMLResponse)
    async def _index(request: Request) -> Any:
        template = tpl.get_template("index.html")
        html = template.render(version=VERSION, user_id=_USER_ID)
        return HTMLResponse(html)

    @fa.get("/api/overview")
    async def _overview() -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({
                "version": VERSION, "status": {}, "by_stage": {},
                "calls_total": 0, "pending": 0, "error": 0, "processed": 0,
                "daily_counts": [],
            })
        reader = DashboardDBReader(_CONFIG.data_dir)
        tools = DashboardTools(_CONFIG, _USER_ID)
        status = tools.get_status()
        by_stage = reader.get_calls_by_stage(_USER_ID)
        daily_counts = reader.get_daily_counts(_USER_ID, days=7)
        return JSONResponse({
            "version": VERSION, "status": status, "by_stage": by_stage,
            "calls_total": status.get("processed", 0) + status.get("pending", 0) + status.get("error", 0),
            "pending": status.get("pending", 0), "error": status.get("error", 0),
            "processed": status.get("processed", 0),
            "daily_counts": daily_counts,
        })

    @fa.get("/api/calls")
    async def _calls(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                     status: str = Query(""), days: int = Query(0, ge=0, le=365)) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"calls": [], "limit": limit, "offset": offset})
        reader = DashboardDBReader(_CONFIG.data_dir)
        rows = reader.get_calls_filtered(_USER_ID, limit=limit, offset=offset,
                                         status=status, days=days)
        return JSONResponse({"calls": rows, "limit": limit, "offset": offset})

    @fa.get("/api/calls/{call_id}")
    async def _call_detail(call_id: int) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"call_id": call_id, "error": "no config"}, status_code=404)
        reader = DashboardDBReader(_CONFIG.data_dir)
        detail = reader.get_call_detail(call_id, _USER_ID)
        if detail is None:
            return JSONResponse({"call_id": call_id, "error": "not found"}, status_code=404)
        return JSONResponse(detail)

    @fa.get("/api/search")
    async def _search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"query": q, "results": []})
        reader = DashboardDBReader(_CONFIG.data_dir)
        rows = reader.search_calls(_USER_ID, q, limit=limit)
        return JSONResponse({"query": q, "results": rows})

    @fa.get("/api/entities")
    async def _entities(limit: int = Query(100, ge=1, le=1000)) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"entities": []})
        reader = DashboardDBReader(_CONFIG.data_dir)
        rows = reader.get_contacts(_USER_ID, limit=limit)
        return JSONResponse({"entities": rows})

    @fa.get("/api/system")
    async def _system() -> JSONResponse:
        import psutil
        mem = psutil.virtual_memory()
        disk_path = str(_CONFIG.data_dir) if _CONFIG else "."
        disk = psutil.disk_usage(disk_path)
        db_stats = {}
        if _CONFIG is not None:
            reader = DashboardDBReader(_CONFIG.data_dir)
            db_stats = reader.get_db_stats(_USER_ID)
        return JSONResponse({
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram": {"used_gb": round(mem.used / (1024**3), 2), "total_gb": round(mem.total / (1024**3), 2)},
            "disk": {"used_gb": round(disk.used / (1024**3), 2), "total_gb": round(disk.total / (1024**3), 2)},
            "db_stats": db_stats,
            "db_path": str(_CONFIG.data_dir) if _CONFIG else "",
            "version": VERSION,
        })

    @fa.get("/api/sse")
    async def _sse(request: Request) -> StreamingResponse:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=4)
        _SSE_SUBSCRIBERS.add(q)
        async def _stream() -> Any:
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=SSE_KEEPALIVE_SEC)
                        yield f"data: {msg}\n\n"
                    except asyncio.TimeoutError:
                        yield ":keepalive\n\n"
            finally:
                _SSE_SUBSCRIBERS.discard(q)
        return StreamingResponse(_stream(), media_type="text/event-stream")

    @fa.get("/api/system/logs")
    async def _system_logs(lines: int = Query(200, ge=10, le=2000), level: str = Query("")) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"lines": [], "count": 0})
        reader = DashboardDBReader(_CONFIG.data_dir)
        log_lines = reader.read_logs(lines=lines, level=level)
        return JSONResponse({"lines": log_lines, "count": len(log_lines)})

    @fa.post("/api/tools/retry-failed")
    async def _tools_retry_failed() -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"status": "ok", "count": 0})
        tools = DashboardTools(_CONFIG, _USER_ID)
        result = await tools.run_reprocess()
        return JSONResponse(result)

    # ── v2-compat routes ───────────────────────────────────────────────
    @fa.get("/favicon.ico")
    async def _favicon() -> JSONResponse:
        return JSONResponse({"ok": True})

    @fa.get("/api/stats")
    async def _stats() -> JSONResponse:
        if _DB_READER is not None and hasattr(_DB_READER, "get_stats"):
            return JSONResponse(_DB_READER.get_stats())
        if _CONFIG is not None:
            reader = DashboardDBReader(_CONFIG.data_dir)
            return JSONResponse(reader.get_stats(_USER_ID))
        return JSONResponse({"total_calls": 0})

    def _get_reader() -> DashboardDBReader | None:
        if _DB_READER is not None:
            return _DB_READER
        if _CONFIG is not None:
            return DashboardDBReader(_CONFIG.data_dir)
        return None

    def _get_tools() -> DashboardTools | None:
        if _TOOLS is not None:
            return _TOOLS
        if _CONFIG is not None:
            return DashboardTools(_CONFIG, _USER_ID)
        return None

    @fa.get("/api/history")
    async def _history(limit: int = Query(50, ge=1, le=100)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_recent_calls"):
            return JSONResponse(dbr.get_recent_calls(_USER_ID, limit=limit))
        return JSONResponse([])

    @fa.get("/api/tools/status")
    async def _tools_status() -> JSONResponse:
        tools = _get_tools()
        if tools is not None and hasattr(tools, "get_status"):
            return JSONResponse(tools.get_status())
        return JSONResponse({"status": "ok"})

    @fa.get("/api/tools/history")
    async def _tools_history() -> JSONResponse:
        tools = _get_tools()
        if tools is not None and hasattr(tools, "get_history"):
            return JSONResponse(tools.get_history())
        return JSONResponse([])

    @fa.post("/api/tools/reprocess")
    async def _tools_reprocess() -> JSONResponse:
        tools = _get_tools()
        if tools is not None and hasattr(tools, "run_reprocess"):
            result = tools.run_reprocess()
            if asyncio.iscoroutine(result):
                result = await result
            return JSONResponse(result)
        return JSONResponse({"status": "ok"})

    @fa.post("/api/tools/extract-names")
    async def _tools_extract_names() -> JSONResponse:
        tools = _get_tools()
        if tools is not None and hasattr(tools, "run_extract_names"):
            result = tools.run_extract_names()
            if asyncio.iscoroutine(result):
                result = await result
            return JSONResponse(result)
        return JSONResponse({"status": "ok"})

    @fa.post("/api/tools/rebuild-cards")
    async def _tools_rebuild_cards() -> JSONResponse:
        tools = _get_tools()
        if tools is not None and hasattr(tools, "run_rebuild_cards"):
            result = tools.run_rebuild_cards()
            if asyncio.iscoroutine(result):
                result = await result
            return JSONResponse(result)
        return JSONResponse({"status": "ok"})

    @fa.get("/api/characters")
    async def _characters() -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_all_characters"):
            return JSONResponse(dbr.get_all_characters(_USER_ID))
        return JSONResponse([])

    @fa.get("/api/character/{entity_id}")
    async def _character(entity_id: int) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_character_profile"):
            profile = dbr.get_character_profile(entity_id, _USER_ID)
            if profile is not None:
                return JSONResponse(profile)
        return JSONResponse({"entity_id": entity_id, "canonical_name": "?"})

    @fa.get("/api/contact/{contact_id}")
    async def _contact(contact_id: int) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_contact_profile"):
            profile = dbr.get_contact_profile(contact_id, _USER_ID)
            if profile is not None:
                return JSONResponse(profile)
        return JSONResponse({"contact_id": contact_id, "not_found": True})

    @fa.get("/api/analytics")
    async def _analytics() -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_analytics"):
            return JSONResponse(dbr.get_analytics(_USER_ID))
        return JSONResponse({})

    _APP = fa
    return fa


# ── Module-level initialization (v2-compat) ─────────────────────────
app: FastAPI = _build_app()
_DB_READER: Any = None
_TOOLS: Any = None


def get_app(user_id: str, config: Any) -> FastAPI:
    """Reinitialize the app with real config."""
    global _APP, _USER_ID, _CONFIG, app
    _USER_ID = user_id
    _CONFIG = config
    fa = _build_app(user_id, config)
    app = fa
    _APP = fa
    return fa
