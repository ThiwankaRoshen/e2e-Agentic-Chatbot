from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.services.agent_runner import serialize_message

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/threads")
async def list_threads(request: Request) -> list[dict]:
    """
    Return metadata for all known threads, ordered by creation time descending.

    Each item contains:
        - ``thread_id``:    UUID string
        - ``created_at``:   ISO-8601 UTC timestamp
        - ``first_message``: first human message text (truncated at 500 chars)
    """
    try:
        rows = await request.app.state.thread_meta_store.list_threads(limit=100)
        return [
            {
                "thread_id": row["thread_id"],
                "created_at": row["created_at"],
                "first_message": row["first_human_message"],
            }
            for row in rows
        ]
    except Exception:
        logger.exception("Error listing threads")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str, request: Request) -> dict:
    """
    Return the full message history for a given thread.

    Raises ``404`` if the thread is not found in the metadata store.

    Response shape::

        {
            "thread_id": "<uuid>",
            "messages": [
                {
                    "id": "<str>",
                    "type": "<str>",
                    "content": "<str>",
                    "tool_calls": [...],
                    "additional_kwargs": {...}
                },
                ...
            ]
        }
    """
    thread = await request.app.state.thread_meta_store.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    config = {"configurable": {"thread_id": thread_id}}
    state = await request.app.state.agent.aget_state(config=config)

    raw_messages = state.values.get("messages", []) if state.values else []
    messages = [serialize_message(msg) for msg in raw_messages]

    return {"thread_id": thread_id, "messages": messages}
