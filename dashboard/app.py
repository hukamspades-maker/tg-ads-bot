"""
FastAPI application — production-grade dashboard server.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.api.auth import (
    LoginRequest,
    authenticate_user,
    create_access_token,
    get_current_user,
)
from dashboard.api.routes import router as api_router
from dashboard.config import settings
from dashboard.core.logger import dashboard_handler
from dashboard.core.metrics import metrics
from dashboard.models.base import init_db

log = logging.getLogger("dashboard.app")

# Paths
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Telegram Bot Dashboard",
        description="Production-grade monitoring & control panel",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    # CORS — by default the frontend lives on the same origin as the
    # API (same host + port served by this app), so no CORS middleware
    # is needed. Only enable it when the operator explicitly sets
    # WEB_CORS_ORIGINS, which avoids baking any host/port into source.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Static files
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Templates
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Include API routes
    app.include_router(api_router)

    # Install dashboard log handler on root logger
    root_logger = logging.getLogger()
    if dashboard_handler not in root_logger.handlers:
        root_logger.addHandler(dashboard_handler)

    # ── Startup/Shutdown ──
    @app.on_event("startup")
    async def on_startup():
        # Ensure data directory exists for SQLite
        data_dir = Path("data")
        data_dir.mkdir(parents=True, exist_ok=True)
        await init_db()
        log.info("Dashboard server started on %s:%s", settings.host, settings.port)

        # Start metrics collection background task
        asyncio.create_task(_metrics_collector())

    # ── Auth endpoints ──
    @app.post("/api/login")
    async def login(request: LoginRequest) -> JSONResponse:
        if not authenticate_user(request.username, request.password):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid credentials"},
            )
        token = create_access_token(request.username)
        response = JSONResponse(content={"access_token": token, "token_type": "bearer"})
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            samesite="none" if settings.cookie_secure else "lax",
            secure=settings.cookie_secure,
            max_age=settings.jwt_expire_minutes * 60,
        )
        return response

    @app.post("/api/logout")
    async def logout() -> JSONResponse:
        response = JSONResponse(content={"status": "ok"})
        response.delete_cookie("access_token")
        return response

    # ── Page routes (SPA-style with auth check) ──
    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse(request, "login.html")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        token = request.cookies.get("access_token")
        if not token:
            return RedirectResponse("/login")
        from dashboard.api.auth import decode_token
        if not decode_token(token):
            return RedirectResponse("/login")
        return templates.TemplateResponse(request, "index.html")

    @app.get("/{page}", response_class=HTMLResponse)
    async def page_route(request: Request, page: str):
        # Serve the SPA for known pages
        known_pages = {
            "accounts", "logs", "analytics", "imports",
            "exports", "scheduler", "settings", "monitor",
            "premium", "forcejoin", "broadcast",
        }
        if page not in known_pages:
            return RedirectResponse("/")
        token = request.cookies.get("access_token")
        if not token:
            return RedirectResponse("/login")
        from dashboard.api.auth import decode_token
        if not decode_token(token):
            return RedirectResponse("/login")
        return templates.TemplateResponse(request, "index.html")

    return app


async def _metrics_collector():
    """Background task to periodically collect system metrics."""
    from dashboard.core.events import Event, EventType, event_bus

    while True:
        try:
            system = await metrics.get_system_metrics()
            await event_bus.publish(Event(
                type=EventType.SYSTEM_METRIC,
                data=system,
            ))
        except Exception as e:
            log.error("Metrics collection error: %s", e)
        await asyncio.sleep(5)


# Create the app instance
app = create_app()
