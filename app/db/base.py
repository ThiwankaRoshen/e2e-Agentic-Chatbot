"""
SQLAlchemy async engine and session factory.

Uses SQLite + aiosqlite by default.  Swap DATABASE_URL in .env to a
Postgres async URL (postgresql+asyncpg://...) to migrate with zero
code changes.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.settings import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def build_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine from settings."""
    return create_async_engine(
        settings.DATABASE_URL,
        echo=False,          # set True for SQL query logging during dev
        future=True,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to the given engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def create_tables(engine: AsyncEngine) -> None:
    """Create all tables that don't already exist (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
