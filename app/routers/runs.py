"""
Run endpoints.

POST /threads/{thread_id}/runs/stream   — start a streaming agent run
POST /threads/{thread_id}/runs/resume   — resume a suspended (HITL) run
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db.repositories import ThreadRepository
from app.services.agent_runner import sse_generator

router = APIRouter()


# ── Request models ────────────────────────────────────────────────────────────

class MessageInput(BaseModel):
    type: str
    content: str


class StreamRequest(BaseModel):
    messages: list[MessageInput]


class DecisionInput(BaseModel):
    type: Literal["approve", "reject", "edit"]
    message: str | None = None
    edited_action: dict | None = None


class ResumeRequest(BaseModel):
    decisions: list[DecisionInput]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/threads/{thread_id}/runs/stream")
async def stream_run(
    thread_id: str,
    request_body: StreamRequest,
    request: Request,
) -> StreamingResponse:
    """
    Start a streaming agent run for the given thread.

    If ``thread_id`` is the literal string ``"new"``, a fresh UUID is
    generated.  The first SSE frame is always ``event: thread_id`` so
    the frontend can bind to the resolved ID.
    """
    session_factory = request.app.state.db_session_factory

    # Resolve "new" → fresh UUID
    if thread_id == "new":
        thread_id = str(uuid.uuid4())
    elif request.app.state.interrupt_bus.is_suspended(thread_id):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Thread {thread_id} is suspended awaiting a HITL decision. "
                "Use the resume endpoint instead."
            ),
        )

    # Derive thread title from the first human message
    title = ""
    for msg in request_body.messages:
        if msg.type == "human":
            title = msg.content[:500]
            break
    if not title and request_body.messages:
        title = request_body.messages[0].content[:500]

    # Persist thread metadata (no-op if already exists)
    async with session_factory() as session:
        async with session.begin():
            repo = ThreadRepository(session)
            await repo.create(thread_id=thread_id, title=title)

    messages = [{"type": m.type, "content": m.content} for m in request_body.messages]

    generator = sse_generator(
        thread_id=thread_id,
        messages=messages,
        agent=request.app.state.agent,
        bus=request.app.state.interrupt_bus,
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/threads/{thread_id}/runs/resume")
async def resume_run(
    thread_id: str,
    request_body: ResumeRequest,
    request: Request,
) -> dict:
    """
    Resume a suspended (HITL-interrupted) agent run.

    The thread must be currently suspended; otherwise a 409 is returned.
    """
    if not request.app.state.interrupt_bus.is_suspended(thread_id):
        raise HTTPException(
            status_code=409,
            detail=f"Thread {thread_id} is not currently suspended at an interrupt",
        )

    decisions_list = [d.model_dump(exclude_none=True) for d in request_body.decisions]
    request.app.state.interrupt_bus.resume(thread_id, decisions_list)

    return {"status": "resumed"}
