"""
Artifact endpoints.

POST /threads/{thread_id}/artifacts
    Upload a file, save it to disk, create an Artifact row, then kick off
    background indexing into Chroma.

GET /threads/{thread_id}/artifacts
    List all artifacts for a thread.

DELETE /threads/{thread_id}/artifacts/{artifact_id}
    Remove an artifact row and delete its Chroma chunks.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile

from app.db.models import ArtifactStatus
from app.db.repositories import ArtifactRepository, ThreadRepository
from app.rag import chroma as rag_chroma
from app.rag.pipeline import index_pdf
from app.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_MIME_TYPES = {"application/pdf"}


async def _run_indexing(
    artifact_id: str,
    thread_id: str,
    filename: str,
    file_path: str,
    session_factory,
) -> None:
    """
    Background task: index the PDF into Chroma and update artifact status.
    """
    async with session_factory() as session:
        async with session.begin():
            repo = ArtifactRepository(session)
            await repo.set_status(artifact_id, ArtifactStatus.indexing)

    try:
        await index_pdf(
            artifact_id=artifact_id,
            thread_id=thread_id,
            filename=filename,
            file_path=file_path,
        )
        async with session_factory() as session:
            async with session.begin():
                repo = ArtifactRepository(session)
                await repo.set_status(artifact_id, ArtifactStatus.indexed)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Indexing failed for artifact %s", artifact_id)
        async with session_factory() as session:
            async with session.begin():
                repo = ArtifactRepository(session)
                await repo.set_status(
                    artifact_id,
                    ArtifactStatus.failed,
                    error_message=str(exc),
                )


@router.post("/threads/{thread_id}/artifacts", status_code=201)
async def upload_artifact(
    thread_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict:
    """
    Upload a file and start background indexing.

    Accepted types: application/pdf

    Returns the artifact metadata immediately with status ``uploaded``.
    The status transitions to ``indexing`` then ``indexed`` (or ``failed``)
    asynchronously.
    """
    session_factory = request.app.state.db_session_factory

    # Validate thread exists
    async with session_factory() as session:
        thread_repo = ThreadRepository(session)
        thread = await thread_repo.get(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

    # Validate MIME type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{content_type}'. Accepted: PDF",
        )

    # Save file to disk
    uploads_dir = Path(settings.UPLOADS_DIR) / thread_id
    uploads_dir.mkdir(parents=True, exist_ok=True)

    artifact_id = str(uuid.uuid4())
    safe_filename = Path(file.filename or "upload.pdf").name
    storage_path = str(uploads_dir / f"{artifact_id}_{safe_filename}")

    contents = await file.read()
    with open(storage_path, "wb") as f:
        f.write(contents)

    # Create artifact row
    async with session_factory() as session:
        async with session.begin():
            artifact_repo = ArtifactRepository(session)
            artifact = await artifact_repo.create(
                artifact_id=artifact_id,
                thread_id=thread_id,
                filename=safe_filename,
                storage_path=storage_path,
                mime_type=content_type,
            )
            result = artifact.to_dict()

    # Kick off background indexing
    background_tasks.add_task(
        _run_indexing,
        artifact_id=artifact_id,
        thread_id=thread_id,
        filename=safe_filename,
        file_path=storage_path,
        session_factory=session_factory,
    )

    return result


@router.get("/threads/{thread_id}/artifacts")
async def list_artifacts(thread_id: str, request: Request) -> list[dict]:
    """Return all artifacts for a thread ordered by creation time."""
    session_factory = request.app.state.db_session_factory

    async with session_factory() as session:
        repo = ArtifactRepository(session)
        artifacts = await repo.list_for_thread(thread_id)

    return [a.to_dict() for a in artifacts]


@router.delete("/threads/{thread_id}/artifacts/{artifact_id}", status_code=204)
async def delete_artifact(
    thread_id: str,
    artifact_id: str,
    request: Request,
) -> None:
    """Delete an artifact row and remove its Chroma chunks."""
    session_factory = request.app.state.db_session_factory

    async with session_factory() as session:
        async with session.begin():
            repo = ArtifactRepository(session)
            artifact = await repo.get(artifact_id)

            if not artifact or artifact.thread_id != thread_id:
                raise HTTPException(status_code=404, detail="Artifact not found")

            storage_path = artifact.storage_path
            await repo.delete(artifact_id)

    # Remove Chroma chunks
    rag_chroma.delete_artifact(artifact_id)

    # Remove file from disk (best effort)
    try:
        os.remove(storage_path)
    except OSError:
        logger.warning("Could not delete file %s", storage_path)
