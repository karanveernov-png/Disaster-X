"""
Database layer: Supabase client + async SQLAlchemy engine.

Two access patterns are available:

1. Supabase SDK  — use `get_supabase()` for PostgREST / Storage / Auth
   helper methods and when you want the managed Supabase client.

2. Async SQLAlchemy — use `get_db()` (FastAPI dependency) for raw async
   SQL queries via asyncpg. This mirrors the original sqlite3 pattern
   but is fully non-blocking and works with Supabase's PostgreSQL.

Choose whichever fits the operation. Services in this repo use
SQLAlchemy for full-control queries and Supabase SDK for convenience.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from supabase import Client, create_client

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# ── SQLAlchemy async engine ───────────────────────────────────────────────────

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=settings.DEBUG,
        )
        log.info("AsyncEngine created for %s", settings.DATABASE_URL.split("@")[-1])
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields an async SQLAlchemy session.

    Usage::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_conn() -> AsyncGenerator[AsyncConnection, None]:
    """
    FastAPI dependency — yields a raw async connection.
    Prefer `get_db()` unless you need core-level SQL.
    """
    async with get_engine().connect() as conn:
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


# ── Supabase SDK client ───────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """
    Return a cached Supabase client using the service-role key.

    Use this for server-side operations that bypass Row Level Security.
    Never expose the service-role key to the frontend.
    """
    settings = get_settings()
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    log.info("Supabase client initialised for %s", settings.SUPABASE_URL)
    return client


def get_supabase_anon() -> Client:
    """
    Return a Supabase client using the anon (public) key.

    Use this when you want RLS policies to be enforced.
    """
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


# ── Startup / shutdown ────────────────────────────────────────────────────────

async def init_db() -> None:
    """
    Run at application startup to verify DB connectivity.
    Schema is managed via Supabase migrations (see /migrations/).
    """
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        row = result.fetchone()
        log.info("Database connectivity check: %s", row)
    log.info("Database ready")


async def close_db() -> None:
    """Dispose the engine on application shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        log.info("Database engine disposed")
