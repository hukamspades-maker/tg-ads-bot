"""
SQLAlchemy async engine and session factory.
Supports PostgreSQL (asyncpg) and SQLite (aiosqlite) as fallback.
"""
from __future__ import annotations

import logging
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from dashboard.config import settings

log = logging.getLogger("dashboard.db")


class Base(DeclarativeBase):
    pass


# SQLite and PostgreSQL need different pool strategies.
# SQLite can't handle concurrent connections — use NullPool (one connection per operation).
# PostgreSQL uses a proper async connection pool.
if "sqlite" in settings.database_url:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=10,
    )

async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db() -> None:
    """Create all tables (non-destructive)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("Database initialized successfully.")
