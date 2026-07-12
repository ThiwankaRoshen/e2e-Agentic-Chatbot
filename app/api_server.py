"""
FastAPI application factory and lifespan handler.

Startup
-------
1. Create SQLAlchemy async engine and run DDL (create tables if needed)
2. Initialise the LangGraph agent (LLM, tools, checkpointer, middleware)
3. Create the InterruptBus for HITL suspend/resume coordination
4. Ensure the uploads directory exists

Shutdown
--------
1. Dispose the SQLAlchemy engine (closes connection pool)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent import create_chatbot_agent
from app.db.base import build_engine, build_session_factory, create_tables
from app.services.agent_runner import InterruptBus
from app.settings import settings

from app.routers.health import router as health_router
from app.routers.threads import router as threads_router
from app.routers.runs import router as runs_router
from app.routers.artifacts import router as artifacts_router

logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown logic."""
    try:
        # 1. SQLAlchemy — metadata database
        engine = build_engine()
        await create_tables(engine)
        app.state.db_engine = engine
        app.state.db_session_factory = build_session_factory(engine)

        # 2. LangGraph agent
        app.state.agent = await create_chatbot_agent()

        # 3. HITL interrupt bus
        app.state.interrupt_bus = InterruptBus()

        # 4. Ensure uploads directory exists
        os.makedirs(settings.UPLOADS_DIR, exist_ok=True)

        logger.info("API server startup complete.")
    except Exception as exc:
        logger.error("Startup failed: %s", exc)
        raise

    yield

    # Shutdown
    if getattr(app.state, "db_engine", None) is not None:
        await app.state.db_engine.dispose()
        logger.info("Database engine disposed.")

    logger.info("API server shutdown complete.")


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="Agentic Chatbot API",
        description="FastAPI backend for the LangGraph agentic chatbot.",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS
    cors_origins = [
        o.strip()
        for o in settings.CORS_ORIGINS.split(",")
        if o.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    application.include_router(health_router)
    application.include_router(threads_router)
    application.include_router(runs_router)
    application.include_router(artifacts_router)

    return application


app = create_app()
