"""
TaskFlow API — FastAPI application factory.

Startup order:
  1. Load and validate settings (pydantic-settings)
  2. Configure logging
  3. Verify database connectivity
  4. Register routes and exception handlers
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_v1_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.database import close_db, init_db
from app.middleware.error_handlers import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown lifecycle."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    log = get_logger(__name__)

    log.info("Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)
    await init_db()
    log.info("%s ready", settings.APP_NAME)

    yield  # ← application runs here

    log.info("Shutting down %s", settings.APP_NAME)
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Task management API built with FastAPI + Supabase",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    register_error_handlers(app)

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(api_v1_router)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["health"], summary="Health check")
    async def health() -> dict:
        return {"status": "ok", "service": settings.APP_NAME}

    return app


# Entry point for `uvicorn app.main:app`
app = create_app()
