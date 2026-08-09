# -*- coding: utf-8 -*-
"""
Dashboard module — real-time web UI for CallProfiler pipeline monitoring.
"""

from __future__ import annotations

import ipaddress

__all__ = ["run_dashboard", "assert_loopback_host"]

# T-18/P-WEB-01: no auth, no CSRF-only-web (mutating /api/tools/* exist) — the
# ONLY thing standing between "local operator" and "anyone on the LAN" is the
# bind address. Non-loopback binding is a hard startup error, not a warning —
# no env-var override (explicitly rejected, see docs/sintezdiharea.md §14).
_LOOPBACK_NAMES = {"localhost"}


def assert_loopback_host(host: str) -> None:
    h = (host or "").strip()
    if h.lower() in _LOOPBACK_NAMES:
        return
    try:
        ip = ipaddress.ip_address(h)
    except ValueError as exc:
        raise RuntimeError(
            f"Dashboard host {host!r} is not a loopback address or 'localhost' — refusing to start. "
            "Non-loopback binding is disallowed (P-WEB-01); no env-var override exists."
        ) from exc
    if not ip.is_loopback:
        raise RuntimeError(
            f"Dashboard host {host!r} is not loopback (127.0.0.0/8 or ::1) — refusing to start. "
            "Non-loopback binding is disallowed (P-WEB-01); no env-var override exists."
        )


def run_dashboard(user_id: str, config, port: int = 8765, host: str = "127.0.0.1"):
    """
    Launch the dashboard web server.

    Args:
        user_id: User ID to filter data
        port: HTTP port (default 8765)
        host: Bind address (default 127.0.0.1) — MUST be loopback, enforced.
    """
    assert_loopback_host(host)

    import uvicorn

    from callprofiler.dashboard.server import _build_app

    app = _build_app(user_id, config)
    uvicorn.run(app, host=host, port=port, log_level="info")
