"""
Agent runner service: InterruptBus for HITL suspend/resume coordination,
and SSE utility helpers.

Streaming protocol
------------------
The SSE stream emitted by ``sse_generator`` follows the LangGraph V2
stream-mode wire format so the frontend can use it reliably:

  event: thread_id  → {"thread_id": "<uuid>"}

  (per-token, zero or more)
  event: messages   → [<message_dict>, <metadata_dict>]
                       message_dict has type/id/content/tool_calls fields
                       metadata_dict has langgraph_node / langgraph_step

  (after every graph super-step, one or more)
  event: values     → {"messages": [<full_msg>, ...]}
                       Complete authoritative message list including ALL
                       messages (human + AI + tool). Frontend replaces its
                       state with this on every values event.

  event: interrupt  → {"value": <HITLRequest>, "id": "<str>"}
                       Stream stays open; client resumes via /runs/resume.

  event: done       → {}   (always the last frame)

  event: error      → {"message": "<str>"}  (on unhandled exceptions)

Using ``values`` events for final state means the frontend never has to
manually merge optimistic human messages with backend-emitted messages.
The ``messages`` events drive token-by-token streaming bubbles.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)


@dataclass
class InterruptState:
    """Holds the suspend/resume state for a single thread."""

    resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    decisions: list[dict] | None = None


class InterruptBus:
    """Per-process in-memory store for thread interrupt state.

    Coordinates between the SSE generator coroutine (which suspends awaiting
    human decisions) and the Resume endpoint handler (which fires the event
    once decisions arrive).

    Note: This in-memory approach works for a single-process deployment.
    Multi-worker deployments would need a shared-state mechanism (e.g. Redis).
    """

    def __init__(self) -> None:
        self._state: dict[str, InterruptState] = {}

    def set_interrupt(self, thread_id: str) -> None:
        """Register thread as suspended. Called by SSE generator before awaiting."""
        self._state[thread_id] = InterruptState()

    async def wait_for_resume(self, thread_id: str) -> list[dict]:
        """Suspend the SSE generator until resume() is called."""
        state = self._state[thread_id]
        await state.resume_event.wait()
        decisions = state.decisions
        del self._state[thread_id]
        return decisions

    def resume(self, thread_id: str, decisions: list[dict]) -> bool:
        """Signal the waiting SSE generator with the user's decisions."""
        state = self._state.get(thread_id)
        if state is None:
            return False
        state.decisions = decisions
        state.resume_event.set()
        return True

    def is_suspended(self, thread_id: str) -> bool:
        """Return True if the thread is currently awaiting a resume decision."""
        return thread_id in self._state


def format_sse(event_type: str, data) -> str:
    """Format a single SSE frame.

    Returns the standard SSE wire format::

        event: <event_type>\\n
        data: <json>\\n
        \\n
    """
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def serialize_message(msg) -> dict:
    """Convert a LangChain/LangGraph message object to a serialisable dict.

    Shape matches the @langchain/langgraph-sdk Message type::

        {
            "id": "<str>",
            "type": "<str>",          # "human" | "ai" | "tool"
            "content": "<str>",
            "tool_calls": [...],
            "additional_kwargs": {...}
        }
    """
    msg_id = msg.id if msg.id is not None else str(id(msg))
    return {
        "id": msg_id,
        "type": msg.type,
        "content": msg.content,
        "tool_calls": getattr(msg, "tool_calls", []),
        "additional_kwargs": getattr(msg, "additional_kwargs", {}),
    }


async def _process_stream_events(
    stream,
    thread_id: str,
) -> AsyncGenerator[str, None]:
    """Consume a LangGraph ``astream`` iterator and yield SSE-formatted strings.

    Handles ``("messages", ...)`` chunks for token streaming and
    ``("values", ...)`` chunks for full-state snapshots.
    Detects interrupts from ``("updates", ...)`` chunks and yields a sentinel
    tuple so the caller can suspend/resume without duplicating logic.

    Does NOT yield the terminal ``done`` frame — callers do that.
    """
    async for event in stream:
        # astream with stream_mode=["messages","values","updates"] yields
        # (mode, data) tuples.
        if isinstance(event, tuple) and len(event) == 2:
            mode, data = event
        else:
            mode, data = "updates", event

        if mode == "messages":
            # data is (message_chunk, metadata_dict)
            if isinstance(data, tuple) and len(data) == 2:
                chunk, metadata = data
            else:
                chunk = data
                metadata = {}

            # Only stream AI text tokens — skip tool-call-only chunks
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                if isinstance(chunk.content, str):
                    # Emit [message_dict, metadata] so the frontend can use
                    # the message id for per-message streaming bubbles
                    msg_dict = {
                        "id": chunk.id or "__streaming__",
                        "type": "ai",
                        "content": chunk.content,
                        "tool_calls": [],
                    }
                    yield format_sse("messages", [msg_dict, metadata])
                    continue

                if isinstance(chunk.content, list):
                    text_parts = [
                        p if isinstance(p, str) else p.get("text", "")
                        for p in chunk.content
                        if isinstance(p, str)
                        or (isinstance(p, dict) and p.get("type") == "text")
                    ]
                    combined = "".join(text_parts)
                    if combined:
                        msg_dict = {
                            "id": chunk.id or "__streaming__",
                            "type": "ai",
                            "content": combined,
                            "tool_calls": [],
                        }
                        yield format_sse("messages", [msg_dict, metadata])
                        continue

        elif mode == "values":
            # Full state snapshot — includes ALL messages (human + AI + tool).
            # Emit as a "values" SSE event; frontend replaces its message list.
            if isinstance(data, dict) and "messages" in data:
                serialized = [serialize_message(m) for m in data["messages"]]
                yield format_sse("values", {"messages": serialized})

        elif mode == "updates":
            # Check for interrupt signal from LangGraph
            if isinstance(data, dict):
                interrupt_data = data.get("__interrupt__")
                if interrupt_data is not None:
                    yield ("__interrupt_sentinel__", interrupt_data)
                    return


async def sse_generator(
    thread_id: str,
    messages: list,
    agent,
    bus: "InterruptBus",
) -> AsyncGenerator[str, None]:
    """Core SSE streaming coroutine for a LangGraph agent run.

    Yields SSE-formatted strings for the FastAPI ``StreamingResponse``.

    Frame sequence for a normal run::

        event: thread_id
        event: messages   (token chunks, zero or more)
        event: values     (full state after each step, one or more)
        event: done

    Frame sequence for an interrupted run::

        event: thread_id
        ...messages/values...
        event: interrupt
        <stream suspends>
        <resume endpoint fires bus.resume()>
        ...messages/values (continued)...
        event: done

    On error::

        event: error → {"message": "<str>"}
    """
    yield format_sse("thread_id", {"thread_id": thread_id})

    try:
        async with asyncio.timeout(300):
            stream = agent.astream(
                {"messages": messages},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode=["messages", "values", "updates"],
            )

            async for item in _process_stream_events(stream, thread_id):
                if isinstance(item, tuple) and item[0] == "__interrupt_sentinel__":
                    raw_interrupt = item[1]

                    if isinstance(raw_interrupt, (list, tuple)) and raw_interrupt:
                        interrupt_obj = raw_interrupt[0]
                        interrupt_value = (
                            interrupt_obj.value
                            if hasattr(interrupt_obj, "value")
                            else interrupt_obj
                        )
                    else:
                        interrupt_value = raw_interrupt

                    yield format_sse(
                        "interrupt",
                        {
                            "value": interrupt_value,
                            "id": str(id(interrupt_value)),
                        },
                    )

                    bus.set_interrupt(thread_id)
                    decisions = await bus.wait_for_resume(thread_id)

                    resume_stream = agent.astream(
                        Command(resume={"decisions": decisions}),
                        config={"configurable": {"thread_id": thread_id}},
                        stream_mode=["messages", "values", "updates"],
                    )

                    async for resumed_item in _process_stream_events(
                        resume_stream, thread_id
                    ):
                        if (
                            isinstance(resumed_item, tuple)
                            and resumed_item[0] == "__interrupt_sentinel__"
                        ):
                            nested_raw = resumed_item[1]
                            if isinstance(nested_raw, (list, tuple)) and nested_raw:
                                nested_obj = nested_raw[0]
                                nested_value = (
                                    nested_obj.value
                                    if hasattr(nested_obj, "value")
                                    else nested_obj
                                )
                            else:
                                nested_value = nested_raw

                            yield format_sse(
                                "interrupt",
                                {
                                    "value": nested_value,
                                    "id": str(id(nested_value)),
                                },
                            )
                            break
                        else:
                            yield resumed_item

                    break
                else:
                    yield item

        yield format_sse("done", {})

    except TimeoutError as e:
        logger.exception("SSE stream timed out for thread %s", thread_id)
        yield format_sse("error", {"message": f"Stream timeout: {str(e)}"})
    except Exception as e:
        logger.exception("SSE stream error for thread %s", thread_id)
        yield format_sse("error", {"message": str(e)})
