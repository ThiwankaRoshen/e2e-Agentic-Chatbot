from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.agent_runner import format_sse

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


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


async def _stub_sse_generator(thread_id, messages, agent, bus):
    yield format_sse("thread_id", {"thread_id": thread_id})
    yield format_sse("done", {})


@router.post("/threads/{thread_id}/runs/stream")
async def stream_run(
    thread_id: str,
    request_body: StreamRequest,
    request: Request,
) -> StreamingResponse:
    """
    Start a streaming agent run for the given thread.

    If ``thread_id`` is the literal string ``"new"``, a fresh UUID4 is
    generated before the run begins.

    The response is a text/event-stream SSE stream.  The first frame is
    always ``event: thread_id`` so the frontend can bind to the resolved ID.
    """
    # Resolve "new" → fresh UUID
    if thread_id == "new":
        thread_id = str(uuid.uuid4())

    # Extract first human message for metadata storage
    first_human_message: str = ""
    for msg in request_body.messages:
        if msg.type == "human":
            first_human_message = msg.content
            break
    else:
        # Fallback: use content of the very first message
        if request_body.messages:
            first_human_message = request_body.messages[0].content

    # Persist thread metadata
    await request.app.state.thread_meta_store.insert(
        thread_id,
        datetime.utcnow().isoformat(),
        first_human_message,
    )

    # Convert messages to plain dicts for the generator
    messages = [{"type": m.type, "content": m.content} for m in request_body.messages]

    # Use real sse_generator when available (Task 7.2), otherwise stub
    try:
        from app.services.agent_runner import sse_generator  # noqa: PLC0415

        generator = sse_generator(
            thread_id=thread_id,
            messages=messages,
            agent=request.app.state.agent,
            bus=request.app.state.interrupt_bus,
        )
    except ImportError:
        generator = _stub_sse_generator(
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
    Resume a suspended (HITL-interrupted) agent run for the given thread.

    The thread must currently be suspended at an interrupt; if it is not,
    a 409 Conflict is returned.  Once decisions are delivered via the
    ``InterruptBus``, the waiting SSE generator is unblocked and continues
    streaming to the original client.
    """
    if not request.app.state.interrupt_bus.is_suspended(thread_id):
        raise HTTPException(
            status_code=409,
            detail=f"Thread {thread_id} is not currently suspended at an interrupt",
        )

    decisions_list = [d.model_dump(exclude_none=True) for d in request_body.decisions]
    request.app.state.interrupt_bus.resume(thread_id, decisions_list)

    return {"status": "resumed"}
