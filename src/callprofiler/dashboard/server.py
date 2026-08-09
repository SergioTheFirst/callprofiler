"""CallProfiler Dashboard — v3.0.0 Glass-Industrial Command Center.

SSE backbone + ECharts + 5-tab shell (Overview, Calls, Search, Entities, System).

T-18 (request-scoped loopback dashboard): the active profile used to live in a
module-global (``_USER_ID``) mutated by ``/api/users/select`` — two browser
tabs on different profiles corrupted each other's reads/writes (P-TEN-05).
Profile is now resolved PER REQUEST from an ``cp_profile`` cookie via
``_current_user`` (Depends); ``_USER_ID`` remains only as the *startup
default* used when no cookie is present (never mutated by a request handler).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from callprofiler.dashboard.config import POLL_INTERVAL_SEC, SSE_KEEPALIVE_SEC, THEME
from callprofiler.dashboard.db_reader import DashboardDBReader
from callprofiler.dashboard.tools import DashboardTools
from callprofiler.doctor import run_checks

logger = logging.getLogger(__name__)

_APP: FastAPI | None = None
_USER_ID: str | None = None  # startup DEFAULT profile only — never mutated per-request
_CONFIG: Any = None
# Subscribers are (queue, user_id) pairs so a profile switch in one tab never
# leaks ticks from another tab's profile into this one (P-TEN-05 for SSE).
_SSE_SUBSCRIBERS: set[tuple["asyncio.Queue[str]", str]] = set()

_CSRF_COOKIE = "cp_csrf"
_PROFILE_COOKIE = "cp_profile"
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_CSRF_TOKEN = ""  # generated fresh per process in _build_app

VERSION = "3.0.0"


def _known_user(candidate: str | None) -> bool:
    """Существует ли такой профиль (форма слага + запись в БД)."""
    if not candidate:
        return False
    try:
        from callprofiler.identity import validate_user_id

        validate_user_id(candidate)
    except Exception:
        return False
    if candidate == _USER_ID:
        return True  # стартовый профиль задан сервером, не клиентом
    if _CONFIG is None:
        return True  # тестовое приложение без БД: проверять не по чему
    try:
        return DashboardDBReader(_CONFIG.data_dir).user_exists(candidate)
    except Exception:  # noqa: BLE001 — недоступность БД не должна ронять запрос
        return False


def _current_user(cp_profile: str | None = Cookie(default=None, alias=_PROFILE_COOKIE)) -> str:
    """Resolve the profile for THIS request only (no shared mutable state).

    Значение cookie ВАЛИДИРУЕТСЯ: она приходит от клиента, и без проверки
    браузер (или любая страница, дотянувшаяся до loopback) диктовал бы
    tenant-идентичность произвольной строкой. Неизвестный/кривой профиль
    не принимается — откат на стартовый дефолт, а не доверие вводу.
    """
    if _known_user(cp_profile):
        return cp_profile  # type: ignore[return-value]
    if cp_profile:
        logger.warning("Отклонён неизвестный профиль из cookie: %r", cp_profile)
    return _USER_ID or "test_user"


def _build_app(user_id: str = "test_user", config: Any = None) -> FastAPI:
    global _APP, _USER_ID, _CONFIG, _CSRF_TOKEN
    _USER_ID = user_id
    _CONFIG = config
    _CSRF_TOKEN = secrets.token_urlsafe(32)

    poller_task: asyncio.Task | None = None

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        nonlocal poller_task
        if _CONFIG is not None:
            poller_task = asyncio.create_task(_poller())
        yield
        if poller_task is not None:
            poller_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poller_task

    fa = FastAPI(title="CallProfiler Dashboard", version=VERSION, lifespan=_lifespan)

    static_dir = Path(__file__).with_suffix("").parent / "static"
    templates_dir = Path(__file__).with_suffix("").parent / "templates"

    if static_dir.exists():
        fa.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    tpl = Jinja2Templates(directory=str(templates_dir))

    @fa.middleware("http")
    async def _security_guard(request: Request, call_next):
        # Loopback-only dashboard still needs CSRF: any site open in the same
        # browser can fetch() localhost. Origin (when browsers send it) must
        # match Host, and mutating requests need a double-submit CSRF token
        # that a cross-site page cannot read (SameSite=Strict, non-HttpOnly
        # so our own JS can echo it back as a header).
        if request.method in _MUTATING_METHODS:
            origin = request.headers.get("origin")
            if origin is not None:
                host = request.headers.get("host", "")
                if origin not in (f"http://{host}", f"https://{host}"):
                    return JSONResponse({"error": "cross-origin request blocked"}, status_code=403)
            header_token = request.headers.get("x-csrf-token")
            cookie_token = request.cookies.get(_CSRF_COOKIE)
            if not header_token or header_token != cookie_token or header_token != _CSRF_TOKEN:
                return JSONResponse({"error": "csrf token missing or invalid"}, status_code=403)
        response = await call_next(request)
        if _CSRF_COOKIE not in request.cookies:
            response.set_cookie(_CSRF_COOKIE, _CSRF_TOKEN, samesite="strict", httponly=False, path="/")
        return response

    async def _broadcast(payload: str, user_id: str) -> None:
        dead: set[tuple[asyncio.Queue[str], str]] = set()
        for entry in _SSE_SUBSCRIBERS:
            q, uid = entry
            if uid != user_id:
                continue
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.add(entry)
        _SSE_SUBSCRIBERS.difference_update(dead)

    async def _poller() -> None:
        # Change-driven SSE: broadcast only when the DB actually changes, and
        # only to subscribers watching THAT profile. Cross-process safe —
        # SQLite MAX(updated_at) is the event source.
        last_ts_by_user: dict[str, str | None] = {}
        while True:
            await asyncio.sleep(POLL_INTERVAL_SEC)
            if _CONFIG is None:
                continue
            active_users = {uid for _, uid in _SSE_SUBSCRIBERS}
            for uid in active_users:
                reader = DashboardDBReader(_CONFIG.data_dir)
                try:
                    current_ts = reader.get_latest_timestamp(uid)
                    if current_ts == last_ts_by_user.get(uid):
                        continue
                    last_ts_by_user[uid] = current_ts
                    tools = DashboardTools(_CONFIG, uid)
                    status = tools.get_status()
                    by_stage = reader.get_calls_by_stage(uid)
                    recent = reader.get_recent_calls(uid, limit=10)
                    payload = json.dumps(
                        {"type": "tick", "status": status, "by_stage": by_stage,
                         "recent": recent, "ts": current_ts},
                        ensure_ascii=False, default=str,
                    )
                except Exception:
                    logger.warning("Dashboard poller error (user=%s)", uid, exc_info=True)
                    continue
                finally:
                    reader.close()
                await _broadcast(payload, uid)

    @fa.get("/", response_class=HTMLResponse)
    async def _index(request: Request, user_id: str = Depends(_current_user)) -> Any:
        template = tpl.get_template("index.html")
        html = template.render(version=VERSION, user_id=user_id)
        return HTMLResponse(html)

    @fa.get("/api/users")
    async def _users(user_id: str = Depends(_current_user)) -> JSONResponse:
        """List profiles for the switcher; mark the active one."""
        items: list[dict[str, Any]] = []
        if _CONFIG is not None:
            reader = DashboardDBReader(_CONFIG.data_dir)
            items = reader.get_user_ids()
        return JSONResponse({"users": items, "active": user_id})

    @fa.post("/api/users/select")
    async def _users_select(user: str = Query(..., min_length=1)) -> JSONResponse:
        """Select the active profile for THIS client only (P-TEN-05 fix).

        Sets a per-browser cookie instead of mutating process-global state —
        two tabs on different profiles no longer contaminate each other.
        """
        if not _known_user(user):
            # Не выдаём cookie на несуществующий профиль: иначе клиент сам
            # назначает себе tenant-идентичность произвольной строкой.
            return JSONResponse({"error": "unknown profile"}, status_code=404)
        resp = JSONResponse({"active": user})
        resp.set_cookie(_PROFILE_COOKIE, user, httponly=True, samesite="strict",
                         path="/", max_age=3600 * 24 * 365)
        return resp

    @fa.get("/api/overview")
    async def _overview(user_id: str = Depends(_current_user)) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({
                "version": VERSION, "status": {}, "by_stage": {},
                "calls_total": 0, "pending": 0, "error": 0, "processed": 0,
                "daily_counts": [],
            })
        reader = DashboardDBReader(_CONFIG.data_dir)
        tools = DashboardTools(_CONFIG, user_id)
        status = tools.get_status()
        by_stage = reader.get_calls_by_stage(user_id)
        daily_counts = reader.get_daily_counts(user_id, days=7)
        return JSONResponse({
            "version": VERSION, "status": status, "by_stage": by_stage,
            "calls_total": status.get("processed", 0) + status.get("pending", 0) + status.get("error", 0),
            "pending": status.get("pending", 0), "error": status.get("error", 0),
            "processed": status.get("processed", 0),
            "daily_counts": daily_counts,
        })

    @fa.get("/api/calls")
    async def _calls(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                     status: str = Query(""), days: int = Query(0, ge=0, le=365),
                     call_kind: str = Query(""), user_id: str = Depends(_current_user)) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"calls": [], "limit": limit, "offset": offset})
        reader = DashboardDBReader(_CONFIG.data_dir)
        rows = reader.get_calls_filtered(user_id, limit=limit, offset=offset,
                                         status=status, days=days, call_kind=call_kind)
        return JSONResponse({"calls": rows, "limit": limit, "offset": offset})

    @fa.get("/api/calls/{call_id}")
    async def _call_detail(call_id: int, user_id: str = Depends(_current_user)) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"call_id": call_id, "error": "no config"}, status_code=404)
        reader = DashboardDBReader(_CONFIG.data_dir)
        detail = reader.get_call_detail(call_id, user_id)
        if detail is None:
            return JSONResponse({"call_id": call_id, "error": "not found"}, status_code=404)
        return JSONResponse(detail)

    @fa.get("/api/audio/{call_id}")
    async def _audio(call_id: int, user_id: str = Depends(_current_user)):
        # M2: слушать звонок из дашборда, seek по сегменту транскрипта.
        if _CONFIG is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        reader = DashboardDBReader(_CONFIG.data_dir)
        path = reader.get_call_audio_path(call_id, user_id)
        if path is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        resolved = Path(path).resolve()
        data_root = Path(_CONFIG.data_dir).resolve()
        try:
            resolved.relative_to(data_root)
        except ValueError:
            # Защита от выхода за пределы data_dir (defense-in-depth) — путь
            # приходит из БД, но нельзя доверять ему без проверки.
            return JSONResponse({"error": "not found"}, status_code=404)
        suffix = resolved.suffix.lower()
        media_type = (
            "audio/mpeg" if suffix == ".mp3"
            else "audio/wav" if suffix == ".wav"
            else "application/octet-stream"
        )
        return FileResponse(str(resolved), media_type=media_type)

    @fa.get("/api/search")
    async def _search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100),
                       user_id: str = Depends(_current_user)) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"query": q, "results": []})
        reader = DashboardDBReader(_CONFIG.data_dir)
        rows = reader.search_calls(user_id, q, limit=limit)
        return JSONResponse({"query": q, "results": rows})

    @fa.get("/api/entities")
    async def _entities(limit: int = Query(100, ge=1, le=1000),
                         user_id: str = Depends(_current_user)) -> JSONResponse:
        # Persona-centric (B.1): list graph entities (entity_id) so the entity
        # modal's /api/character/{entity_id} resolves in the SAME id-space.
        # Previously this returned contacts (contact_id) → modal looked up the
        # wrong record. get_all_characters joins metrics + psychology label.
        reader = _get_reader()
        if reader is None or not hasattr(reader, "get_all_characters"):
            return JSONResponse({"entities": []})
        rows = reader.get_all_characters(user_id)
        return JSONResponse({"entities": rows[:limit]})

    @fa.get("/api/system")
    async def _system(user_id: str = Depends(_current_user)) -> JSONResponse:
        import psutil
        mem = psutil.virtual_memory()
        disk_path = str(_CONFIG.data_dir) if _CONFIG else "."
        disk = psutil.disk_usage(disk_path)
        db_stats = {}
        role_unknown = {"share": 0.0, "n": 0}
        if _CONFIG is not None:
            reader = DashboardDBReader(_CONFIG.data_dir)
            db_stats = reader.get_db_stats(user_id)
            role_unknown = reader.get_role_unknown_share(user_id, days=30)
        return JSONResponse({
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram": {"used_gb": round(mem.used / (1024**3), 2), "total_gb": round(mem.total / (1024**3), 2)},
            "disk": {"used_gb": round(disk.used / (1024**3), 2), "total_gb": round(disk.total / (1024**3), 2)},
            "db_stats": db_stats,
            "db_path": str(_CONFIG.data_dir) if _CONFIG else "",
            "role_unknown_share": role_unknown,
            "version": VERSION,
        })

    @fa.get("/api/health-report")
    async def _health_report() -> JSONResponse:
        # F7: тот же doctor-отчёт (F6), что уходит в Telegram, видно в дашборде
        # без бота. doctor уже side-effect-free — вызываем напрямую, никакой
        # записи в БД. Threadpool — чеки быстрые, но llm-чек делает сетевой
        # запрос (timeout=2s) и не должен блокировать event loop.
        if _CONFIG is None:
            return JSONResponse({"checks": []})
        reader = _get_reader()
        conn = None
        if reader is not None:
            if hasattr(reader, "connect"):
                reader.connect()
            conn = getattr(reader, "_conn", None)
        loop = asyncio.get_event_loop()
        checks = await loop.run_in_executor(None, run_checks, _CONFIG, conn)
        return JSONResponse({
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in checks],
        })

    @fa.get("/api/sse")
    async def _sse(request: Request, user_id: str = Depends(_current_user)) -> StreamingResponse:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=4)
        entry = (q, user_id)
        _SSE_SUBSCRIBERS.add(entry)
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
                _SSE_SUBSCRIBERS.discard(entry)
        return StreamingResponse(_stream(), media_type="text/event-stream")

    @fa.get("/api/system/logs")
    async def _system_logs(lines: int = Query(200, ge=10, le=2000), level: str = Query("")) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"lines": [], "count": 0})
        reader = DashboardDBReader(_CONFIG.data_dir)
        log_lines = reader.read_logs(lines=lines, level=level)
        return JSONResponse({"lines": log_lines, "count": len(log_lines)})

    @fa.post("/api/tools/retry-failed")
    async def _tools_retry_failed(user_id: str = Depends(_current_user)) -> JSONResponse:
        if _CONFIG is None:
            return JSONResponse({"status": "ok", "count": 0})
        tools = DashboardTools(_CONFIG, user_id)
        result = await tools.run_reprocess()
        return JSONResponse(result)

    # ── v2-compat routes ───────────────────────────────────────────────
    @fa.get("/favicon.ico")
    async def _favicon() -> JSONResponse:
        return JSONResponse({"ok": True})

    @fa.get("/api/stats")
    async def _stats(user_id: str = Depends(_current_user)) -> JSONResponse:
        if _DB_READER is not None and hasattr(_DB_READER, "get_stats"):
            return JSONResponse(_DB_READER.get_stats())
        if _CONFIG is not None:
            reader = DashboardDBReader(_CONFIG.data_dir)
            return JSONResponse(reader.get_stats(user_id))
        return JSONResponse({"total_calls": 0})

    def _get_reader() -> DashboardDBReader | None:
        if _DB_READER is not None:
            return _DB_READER
        if _CONFIG is not None:
            return DashboardDBReader(_CONFIG.data_dir)
        return None

    def _get_tools(user_id: str) -> DashboardTools | None:
        if _TOOLS is not None:
            return _TOOLS
        if _CONFIG is not None:
            return DashboardTools(_CONFIG, user_id)
        return None

    @fa.get("/api/export/calls.csv")
    async def _export_calls_csv(status: str = Query(""), days: int = Query(0, ge=0, le=365),
                                 user_id: str = Depends(_current_user)) -> StreamingResponse:
        import csv
        import io
        reader = _get_reader()
        rows: list[dict[str, Any]] = []
        if reader is not None and hasattr(reader, "export_calls"):
            rows = reader.export_calls(user_id, status=status, days=days)
        cols = ["call_id", "call_datetime", "direction", "duration_sec", "status",
                "contact_label", "phone_e164", "call_type", "risk_score", "summary"]

        def _row(values: list[Any]) -> str:
            sbuf = io.StringIO()
            csv.writer(sbuf).writerow(values)
            return sbuf.getvalue()

        def _gen() -> Any:
            yield "﻿" + _row(cols)  # UTF-8 BOM so Excel reads Cyrillic correctly
            for r in rows:
                yield _row([r.get(c, "") for c in cols])

        return StreamingResponse(
            _gen(), media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=calls.csv"},
        )

    @fa.get("/api/export/book.md")
    async def _export_book_md(user_id: str = Depends(_current_user)) -> StreamingResponse:
        reader = _get_reader()
        md = "# Биография\n\n_Книга ещё не сгенерирована._\n"
        if reader is not None and hasattr(reader, "export_book_markdown"):
            md = reader.export_book_markdown(user_id)

        def _gen() -> Any:
            yield md

        return StreamingResponse(
            _gen(), media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=biography.md"},
        )

    @fa.get("/api/history")
    async def _history(limit: int = Query(50, ge=1, le=100),
                        user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_recent_calls"):
            return JSONResponse(dbr.get_recent_calls(user_id, limit=limit))
        return JSONResponse([])

    @fa.get("/api/tools/status")
    async def _tools_status(user_id: str = Depends(_current_user)) -> JSONResponse:
        tools = _get_tools(user_id)
        if tools is not None and hasattr(tools, "get_status"):
            return JSONResponse(tools.get_status())
        return JSONResponse({"status": "ok"})

    @fa.get("/api/tools/history")
    async def _tools_history(user_id: str = Depends(_current_user)) -> JSONResponse:
        tools = _get_tools(user_id)
        if tools is not None and hasattr(tools, "get_history"):
            return JSONResponse(tools.get_history())
        return JSONResponse([])

    @fa.post("/api/tools/reprocess")
    async def _tools_reprocess(user_id: str = Depends(_current_user)) -> JSONResponse:
        tools = _get_tools(user_id)
        if tools is not None and hasattr(tools, "run_reprocess"):
            result = tools.run_reprocess()
            if asyncio.iscoroutine(result):
                result = await result
            return JSONResponse(result)
        return JSONResponse({"status": "ok"})

    @fa.post("/api/tools/extract-names")
    async def _tools_extract_names(user_id: str = Depends(_current_user)) -> JSONResponse:
        tools = _get_tools(user_id)
        if tools is not None and hasattr(tools, "run_extract_names"):
            result = tools.run_extract_names()
            if asyncio.iscoroutine(result):
                result = await result
            return JSONResponse(result)
        return JSONResponse({"status": "ok"})

    @fa.post("/api/tools/rebuild-cards")
    async def _tools_rebuild_cards(user_id: str = Depends(_current_user)) -> JSONResponse:
        tools = _get_tools(user_id)
        if tools is not None and hasattr(tools, "run_rebuild_cards"):
            result = tools.run_rebuild_cards()
            if asyncio.iscoroutine(result):
                result = await result
            return JSONResponse(result)
        return JSONResponse({"status": "ok"})

    @fa.post("/api/tools/age-recompute")
    async def _tools_age_recompute(contact_id: int = Query(...),
                                    user_id: str = Depends(_current_user)) -> JSONResponse:
        tools = _get_tools(user_id)
        if tools is not None and hasattr(tools, "run_age_recompute"):
            result = tools.run_age_recompute(contact_id)
            if asyncio.iscoroutine(result):
                result = await result
            return JSONResponse(result)
        return JSONResponse({"status": "ok"})

    @fa.post("/api/tools/import-audio")
    async def _tools_import_audio(request: Request, name: str = Query(...),
                                   user_id: str = Depends(_current_user)) -> JSONResponse:
        # M5/P-WEB-02, security-sensitive: stream the body — never materialize
        # the full upload in memory before the size check (request.stream()
        # is consumed chunk-by-chunk and the size cap is enforced as it reads).
        tools = _get_tools(user_id)
        if tools is None or not hasattr(tools, "run_import_audio_stream"):
            return JSONResponse({"status": "ok"})
        result = tools.run_import_audio_stream(name, request.stream())
        if asyncio.iscoroutine(result):
            result = await result
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return JSONResponse(result)

    @fa.post("/api/tools/contact-note")
    async def _tools_contact_note(request: Request, user_id: str = Depends(_current_user)) -> JSONResponse:
        tools = _get_tools(user_id)
        if tools is None or not hasattr(tools, "run_contact_note"):
            return JSONResponse({"status": "ok"})
        body = await request.json()
        contact_id = body.get("contact_id")
        note = body.get("note", "")
        if not isinstance(contact_id, int):
            return JSONResponse({"error": "contact_id required"}, status_code=400)
        result = tools.run_contact_note(contact_id, note)
        if asyncio.iscoroutine(result):
            result = await result
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return JSONResponse(result)

    @fa.post("/api/tools/fact-verdict")
    async def _tools_fact_verdict(request: Request, user_id: str = Depends(_current_user)) -> JSONResponse:
        tools = _get_tools(user_id)
        if tools is None or not hasattr(tools, "run_fact_verdict"):
            return JSONResponse({"status": "ok"})
        body = await request.json()
        item_kind = body.get("item_kind")
        item_key = body.get("item_key")
        verdict = body.get("verdict")
        if not item_kind or not item_key or verdict not in ("confirmed", "rejected"):
            return JSONResponse({"error": "item_kind, item_key, verdict required"}, status_code=400)
        result = tools.run_fact_verdict(item_kind, str(item_key), verdict)
        if asyncio.iscoroutine(result):
            result = await result
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return JSONResponse(result)

    @fa.get("/api/mirror")
    async def _mirror(user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_mirror"):
            mirror = dbr.get_mirror(user_id)
            if mirror is not None:
                return JSONResponse(mirror)
        return JSONResponse({})

    @fa.get("/api/characters")
    async def _characters(user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_all_characters"):
            return JSONResponse(dbr.get_all_characters(user_id))
        return JSONResponse([])

    @fa.get("/api/character/{entity_id}")
    async def _character(entity_id: int, user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_character_profile"):
            profile = dbr.get_character_profile(entity_id, user_id)
            if profile is not None:
                return JSONResponse(profile)
        return JSONResponse({"entity_id": entity_id, "canonical_name": "?"})

    @fa.get("/api/contact/{contact_id}")
    async def _contact(contact_id: int, user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_contact_profile"):
            profile = dbr.get_contact_profile(contact_id, user_id)
            if profile is not None:
                return JSONResponse(profile)
        return JSONResponse({"contact_id": contact_id, "not_found": True})

    @fa.get("/api/people")
    async def _people(limit: int = Query(500, ge=1, le=2000),
                       user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_people"):
            return JSONResponse({"people": dbr.get_people(user_id, limit=limit)})
        return JSONResponse({"people": []})

    @fa.get("/api/person/{contact_id}")
    async def _person(contact_id: int, user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_person_dossier"):
            dossier = dbr.get_person_dossier(contact_id, user_id)
            if dossier is not None:
                return JSONResponse(dossier)
        return JSONResponse({"contact_id": contact_id, "not_found": True})

    @fa.get("/api/analytics")
    async def _analytics(user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_analytics"):
            return JSONResponse(dbr.get_analytics(user_id))
        return JSONResponse({})

    # ── Insight Engine visualizations (Phase 7) ─────────────────────────
    @fa.get("/api/insight/pca")
    async def _insight_pca(user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_insight_pca"):
            return JSONResponse(dbr.get_insight_pca(user_id))
        return JSONResponse({"points": [], "clusters": [], "k": 0,
                             "silhouette": None, "version": None})

    @fa.get("/api/insight/network")
    async def _insight_network(limit: int = Query(40, ge=1, le=200),
                                user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_insight_network"):
            return JSONResponse(dbr.get_insight_network(user_id, limit=limit))
        return JSONResponse({"owner_label": "Ты", "nodes": []})

    @fa.get("/api/insight/circadian")
    async def _insight_circadian(contact_id: int = Query(0, ge=0),
                                  user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_insight_circadian"):
            return JSONResponse(dbr.get_insight_circadian(user_id, contact_id or None))
        return JSONResponse({"cells": [], "max": 0,
                             "days": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]})

    @fa.get("/api/insight/ecg")
    async def _insight_ecg(contact_id: int = Query(0, ge=0),
                            user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_insight_ecg"):
            return JSONResponse(dbr.get_insight_ecg(user_id, contact_id or None))
        return JSONResponse({"series": [], "contact_id": contact_id or None})

    @fa.get("/api/insight/lifeline")
    async def _insight_lifeline(user_id: str = Depends(_current_user)) -> JSONResponse:
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_lifeline"):
            return JSONResponse({"arcs": dbr.get_lifeline(user_id)})
        return JSONResponse({"arcs": []})

    @fa.get("/api/insight/contacts")
    async def _insight_contacts(limit: int = Query(60, ge=1, le=500),
                                 user_id: str = Depends(_current_user)) -> JSONResponse:
        """Top contacts (by call volume) for the ECG/circadian picker."""
        dbr = _get_reader()
        if dbr is not None and hasattr(dbr, "get_contacts"):
            return JSONResponse({"contacts": dbr.get_contacts(user_id, limit=limit)})
        return JSONResponse({"contacts": []})

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
