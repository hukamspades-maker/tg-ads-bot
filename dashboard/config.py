# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  dashboard/config.py — Dashboard configuration
#  All values are env-var overridable. To deploy on a new host, just
#  change WEB_PORT (and WEB_PASSWORD / WEB_SECRET_KEY in production).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from typing import List


def _envb(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _envi(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw is not None and raw.strip() else default
    except ValueError:
        return default


def _split_csv(name: str) -> List[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _default_secret() -> str:
    """A randomly-generated key used only if WEB_SECRET_KEY isn't set.

    NOTE: this means all sessions/tokens are invalidated whenever the
    process restarts. That's fine for dev — in production set
    WEB_SECRET_KEY to a long static string.
    """
    return secrets.token_urlsafe(48)


@dataclass
class DashboardSettings:
    # ── Server ────────────────────────────────────────────────────
    host: str = field(default_factory=lambda: os.getenv("WEB_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _envi("WEB_PORT", _envi("PORT", 30031)))

    # ── Auth ──────────────────────────────────────────────────────
    admin_user:     str = field(default_factory=lambda: os.getenv("WEB_USERNAME", "admin"))
    admin_password: str = field(default_factory=lambda: os.getenv("WEB_PASSWORD", "admin"))
    secret_key:     str = field(default_factory=lambda: os.getenv("WEB_SECRET_KEY") or _default_secret())
    jwt_secret:     str = field(default_factory=lambda: os.getenv("WEB_JWT_SECRET") or os.getenv("WEB_SECRET_KEY") or _default_secret())
    jwt_algorithm:  str = field(default_factory=lambda: os.getenv("WEB_JWT_ALGORITHM", "HS256"))
    jwt_expire_minutes: int = field(default_factory=lambda: _envi("WEB_JWT_EXPIRE_MINUTES", 1440))

    # ── CORS ──────────────────────────────────────────────────────
    # The frontend talks to the API on the same origin (same host:port),
    # so by default we don't enable CORS. Only set WEB_CORS_ORIGINS if
    # you host the API on a different origin than the frontend (e.g.
    # behind a separate domain). Comma-separated full URLs:
    #   WEB_CORS_ORIGINS="https://panel.example.com,https://staging.example.com"
    cors_origins: List[str] = field(default_factory=lambda: _split_csv("WEB_CORS_ORIGINS"))

    # ── Cookie security ───────────────────────────────────────────
    # Force "Secure; SameSite=None" cookies behind HTTPS. Off by
    # default because the panel ships on plain HTTP for VPS deployment.
    cookie_secure: bool = field(default_factory=lambda: _envb("WEB_COOKIE_SECURE", False))

    # ── Database ──────────────────────────────────────────────────
    # Default: local SQLite (no setup). Override with WEB_DATABASE_URL
    # to point at PostgreSQL / MySQL / etc.
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "WEB_DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db",
        )
    )

    # ── Performance ───────────────────────────────────────────────
    max_concurrent_sends: int = field(default_factory=lambda: _envi("WEB_MAX_CONCURRENT_SENDS", 10))
    queue_max_size:       int = field(default_factory=lambda: _envi("WEB_QUEUE_MAX_SIZE", 10_000))
    worker_count:         int = field(default_factory=lambda: _envi("WEB_WORKER_COUNT", 4))
    batch_size:           int = field(default_factory=lambda: _envi("WEB_BATCH_SIZE", 50))


# ── Single shared instance — import this everywhere ───────────────
settings = DashboardSettings()
