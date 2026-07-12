"""
Data-access layer — thin async repository classes over the ORM models.

Each method takes an AsyncSession injected by the caller (router or
lifespan handler) so transaction boundaries stay outside this layer.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artifact, ArtifactStatus, Thread


# ── Thread repository ─────────────────────────────────────────────────────────

class ThreadRepository:
    """CRUD operations for the threads table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, thread_id: str, title: str = "") -> Thread:
        """Insert a new thread row (no-op if it already exists)."""
        existing = await self._session.get(Thread, thread_id)
        if existing:
            return existing

        thread = Thread(id=thread_id, title=title)
        self._session.add(thread)
        await self._session.flush()
        return thread

    async def get(self, thread_id: str) -> Thread | None:
        return await self._session.get(Thread, thread_id)

    async def list_all(self, limit: int = 100) -> list[Thread]:
        result = await self._session.execute(
            select(Thread).order_by(Thread.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def delete(self, thread_id: str) -> bool:
        """Delete a thread and cascade-delete its artifacts. Returns True if found."""
        thread = await self._session.get(Thread, thread_id)
        if not thread:
            return False
        await self._session.delete(thread)
        await self._session.flush()
        return True


# ── Artifact repository ───────────────────────────────────────────────────────

class ArtifactRepository:
    """CRUD operations for the artifacts table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        artifact_id: str,
        thread_id: str,
        filename: str,
        storage_path: str,
        mime_type: str = "application/octet-stream",
    ) -> Artifact:
        artifact = Artifact(
            id=artifact_id,
            thread_id=thread_id,
            filename=filename,
            storage_path=storage_path,
            mime_type=mime_type,
            status=ArtifactStatus.uploaded,
        )
        self._session.add(artifact)
        await self._session.flush()
        return artifact

    async def get(self, artifact_id: str) -> Artifact | None:
        return await self._session.get(Artifact, artifact_id)

    async def list_for_thread(self, thread_id: str) -> list[Artifact]:
        result = await self._session.execute(
            select(Artifact)
            .where(Artifact.thread_id == thread_id)
            .order_by(Artifact.created_at)
        )
        return list(result.scalars().all())

    async def set_status(
        self,
        artifact_id: str,
        status: ArtifactStatus,
        error_message: str | None = None,
    ) -> Artifact | None:
        artifact = await self._session.get(Artifact, artifact_id)
        if not artifact:
            return None
        artifact.status = status
        artifact.error_message = error_message
        await self._session.flush()
        return artifact

    async def delete(self, artifact_id: str) -> bool:
        artifact = await self._session.get(Artifact, artifact_id)
        if not artifact:
            return False
        await self._session.delete(artifact)
        await self._session.flush()
        return True
