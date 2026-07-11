from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agentic_chatbot import create_chatbot_agent
from app.services.agent_runner import InterruptBus
from app.services.thread_meta_store import ThreadMetaStore
from app.settings import settings

from app.routers.health import router as health_router  
from app.routers.threads import router as threads_router  
from app.routers.runs import router as runs_router  

logger = logging.getLogger(__name__)





# ---------------------------------------------------------------------------
# Lifespan handler
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan handler.

    On startup:
      - Validates environment variables
      - Initialises the LangGraph agent (FAISS, SQLite, GLiNER2)
      - Creates the ThreadMetaStore and InterruptBus
      - Stores everything on app.state for use by route handlers

    On shutdown:
      - Closes the aiosqlite connection
    """
    try:  

        app.state.agent = await create_chatbot_agent()

        db_conn = await aiosqlite.connect(settings.SQLITE_DB_PATH)
        app.state.db_conn = db_conn

        store = ThreadMetaStore(db_conn)
        await store.ensure_table()
        app.state.thread_meta_store = store

        app.state.interrupt_bus = InterruptBus()

        logger.info("API server startup complete.")
    except Exception as exc:
        logger.error("Startup failed: %s", exc)
        raise

    yield

    if getattr(app.state, "db_conn", None) is not None:
        await app.state.db_conn.close()
        logger.info("Database connection closed.")
    logger.info("API server shutdown complete.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    application = FastAPI(
        title="Agentic Chatbot API",
        description="FastAPI backend wrapping the LangGraph agentic chatbot.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # --- CORS --- 
    cors_origins_raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
    cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Router registration ---
    application.include_router(health_router)

    application.include_router(threads_router)

    application.include_router(runs_router)

    return application


# Module-level app instance used by uvicorn
app = create_app()
