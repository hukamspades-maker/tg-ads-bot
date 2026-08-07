"""
Dashboard runner — starts FastAPI alongside the bot without blocking.
"""
from __future__ import annotations

import asyncio
import logging

import uvicorn

from dashboard.config import settings

log = logging.getLogger("dashboard.runner")


class DashboardServer:
    """Manages the uvicorn server lifecycle as an async background task."""

    def __init__(self) -> None:
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the dashboard server as a non-blocking background task."""
        config = uvicorn.Config(
            app="dashboard.app:app",
            host=settings.host,
            port=settings.port,
            log_level="warning",
            access_log=False,
            ws_max_size=16 * 1024 * 1024,
            # Support reverse proxy headers
            forwarded_allow_ips="*",
            proxy_headers=True,
        )
        self._server = uvicorn.Server(config)

        # Run in background task
        self._task = asyncio.create_task(self._run())
        log.info(
            "Dashboard server starting on http://localhost:%s  (bound to %s)",
            settings.port, settings.host,
        )

    async def _run(self) -> None:
        try:
            await self._server.serve()
        except Exception as e:
            log.error("Dashboard server error: %s", e)

    async def stop(self) -> None:
        """Gracefully stop the dashboard server."""
        if self._server:
            self._server.should_exit = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        log.info("Dashboard server stopped.")


# Global instance
dashboard_server = DashboardServer()
