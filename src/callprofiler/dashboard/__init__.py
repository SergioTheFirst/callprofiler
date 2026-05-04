# -*- coding: utf-8 -*-
"""
Dashboard module — real-time web UI for CallProfiler pipeline monitoring.
"""

from __future__ import annotations

__all__ = ["run_dashboard"]


def run_dashboard(user_id: str, port: int = 8765, host: str = "127.0.0.1"):
    """
    Launch the dashboard web server.

    Args:
        user_id: User ID to filter data
        port: HTTP port (default 8765)
        host: Bind address (default 127.0.0.1)
    """
    from callprofiler.dashboard.server import app, set_user_id
    import uvicorn

    set_user_id(user_id)
    uvicorn.run(app, host=host, port=port, log_level="info")
