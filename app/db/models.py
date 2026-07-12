"""
SQLAlchemy ORM models.

Tables
------
threads
    One row per LangGraph thread.  Stores display metadata only —
    the actual message history lives in the LangGraph SQLite checkpointer.

artifacts
    One row per uploaded file attached to a thread.
    status lifecycle: uploaded → indexing → indexed | failed
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Threads ───────────────────────────────────────────────────────────────────

class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    """UUID string — matches the LangGraph thread_id."""

    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    """First human message (truncated), used as the sidebar label."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    artifacts: Mapped[list[Artifact]] = relationship(
        "Artifact", back_populates="thread", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "thread_id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ── Artifacts ─────────────────────────────────────────────────────────────────

class ArtifactStatus(str, enum.Enum):
    uploaded = "uploaded"
    indexing = "indexing"
    indexed = "indexed"
    failed = "failed"


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    """UUID string."""

    thread_id: Mapped[str] = mapped_column(
        String, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    """Original filename as uploaded by the user."""

    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    """Absolute or relative path where the file is stored on disk."""

    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")

    status: Mapped[ArtifactStatus] = mapped_column(
        Enum(ArtifactStatus), nullable=False, default=ArtifactStatus.uploaded
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Populated when status == failed."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    thread: Mapped[Thread] = relationship("Thread", back_populates="artifacts")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "status": self.status.value,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
        }
