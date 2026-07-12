"""
Thread endpoints.

GET  /threads                      — list all threads
GET  /threads/{thread_id}/state    — full message history from LangGraph
DELETE /threads/{thread_id}        — delete thread + artifacts + Chroma chunks
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.db.repositories import ThreadRepository
from app.rag import chroma as rag_chroma
from app.services.agent_runner import serialize_message

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/threads")
async def list_threads(request: Request) -> list[dict]:
    """Return metadata for all threads, newest first."""
    session_factory = request.app.state.db_session_factory

    try:
        async with session_factory() as session:
            repo = ThreadRepository(session)
            threads = await repo.list_all(limit=100)
        return [t.to_dict() for t in threads]
    except Exception:
        logger.exception("Error listing threads")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str, request: Request) -> dict:
    """
    Return the full message history for a thread from the LangGraph
    checkpointer, plus the artifact list from the metadata database.
    """
    session_factory = request.app.state.db_session_factory

    async with session_factory() as session:
        repo = ThreadRepository(session)
        thread = await repo.get(thread_id)

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    config = {"configurable": {"thread_id": thread_id}}
    state = await request.app.state.agent.aget_state(config=config)

    raw_messages = state.values.get("messages", []) if state.values else []
    messages = [serialize_message(msg) for msg in raw_messages]

    return {
        "thread_id": thread_id,
        "title": thread.title,
        "messages": messages,
    }


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: str, request: Request) -> None:
    """
    Delete a thread, all its artifacts (files + Chroma chunks), and the
    thread row from the metadata database.

    Note: The LangGraph checkpoint data in the separate SQLite file is NOT
    deleted here because the checkpointer does not expose a delete API.
    """
    session_factory = request.app.state.db_session_factory

    async with session_factory() as session:
        async with session.begin():
            repo = ThreadRepository(session)
            deleted = await repo.delete(thread_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Remove all Chroma chunks for this thread
    rag_chroma.delete_thread(thread_id)
