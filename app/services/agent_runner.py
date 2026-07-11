"""
Agent runner service: InterruptBus for HITL suspend/resume coordination,
and SSE utility helpers.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

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
        """Suspend the SSE generator until resume() is called.

        Awaits the per-thread event, then cleans up state and returns the
        decisions provided by the Resume endpoint.
        """
        state = self._state[thread_id]
        await state.resume_event.wait()
        decisions = state.decisions
        del self._state[thread_id]
        return decisions

    def resume(self, thread_id: str, decisions: list[dict]) -> bool:
        """Signal the waiting SSE generator with the user's decisions.

        Returns False if the thread is not currently suspended.
        """
        state = self._state.get(thread_id)
        if state is None:
            return False
        state.decisions = decisions
        state.resume_event.set()
        return True

    def is_suspended(self, thread_id: str) -> bool:
        """Return True if the thread is currently awaiting a resume decision."""
        return thread_id in self._state


def format_sse(event_type: str, data: dict) -> str:
    """Format a single SSE frame.

    Returns the standard SSE wire format:
        event: <event_type>\\n
        data: <json>\\n
        \\n
    """
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def serialize_message(msg) -> dict:
    """Convert a LangChain/LangGraph message object to a plain dict.

    The output shape matches the @langchain/langgraph-sdk Message type
    consumed by the frontend:

        {
            "id": "<str>",
            "type": "<str>",
            "content": "<str>",
            "tool_calls": [...],
            "additional_kwargs": {...}
        }

    If ``msg.id`` is None, falls back to ``str(id(msg))`` so the frontend
    always receives a non-null identifier.
    """
    msg_id = msg.id if msg.id is not None else str(id(msg))
    return {
        "id": msg_id,
        "type": msg.type,
        "content": msg.content,
        "tool_calls": getattr(msg, "tool_calls", []),
        "additional_kwargs": getattr(msg, "additional_kwargs", {}),
    }


def _is_complete_message(chunk) -> bool:
    """Return True if *chunk* represents a fully-formed message (not a streaming delta).

    A complete message has a real ``id`` and is one of the concrete message
    types (AIMessage, HumanMessage, ToolMessage) rather than a chunk subtype.
    """
    if not getattr(chunk, "id", None):
        return False
    return isinstance(chunk, (AIMessage, HumanMessage, ToolMessage))


async def _process_stream_events(
    stream,
    thread_id: str,
) -> AsyncGenerator[str, None]:
    """Consume a LangGraph ``astream`` iterator and yield SSE-formatted strings.

    Handles the ``("messages", ...)`` and ``("updates", ...)`` stream modes.
    Returns immediately after yielding all events; does NOT yield the terminal
    ``done`` frame — that is the caller's responsibility so resume flows can
    append more events before the final ``done``.

    Yields ``None`` as a sentinel when an interrupt is detected so the caller
    can handle suspend/resume logic.
    """
    # This function is a plain async generator; it yields SSE strings plus a
    # special sentinel tuple ("__interrupt_sentinel__", interrupt_value) so the
    # outer generator can detect the suspend point without duplicating the
    # event-classification logic.
    async for event in stream:
        # astream with stream_mode=["messages","updates"] yields tuples (mode, data)
        if isinstance(event, tuple) and len(event) == 2:
            mode, data = event
        else:
            # Fallback: treat as an updates event if not a tuple
            mode, data = "updates", event

        if mode == "messages":
            # data is (message_chunk, metadata)
            if isinstance(data, tuple) and len(data) == 2:
                chunk, _metadata = data
            else:
                chunk = data

            # Streaming token: AIMessageChunk with non-empty content, not a tool call
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                # Skip tool-call-only chunks (content is a list of tool call dicts)
                if isinstance(chunk.content, str):
                    yield format_sse("token", {"content": chunk.content})
                    continue
                # content can be a list for multi-part messages; skip if it
                # contains only tool-call dicts
                if isinstance(chunk.content, list):
                    text_parts = [
                        p if isinstance(p, str) else p.get("text", "")
                        for p in chunk.content
                        if isinstance(p, str) or (isinstance(p, dict) and p.get("type") == "text")
                    ]
                    if text_parts:
                        combined = "".join(text_parts)
                        if combined:
                            yield format_sse("token", {"content": combined})
                            continue

            # Complete message: has a real id and is a concrete message type
            if _is_complete_message(chunk):
                yield format_sse("message", serialize_message(chunk))

        elif mode == "updates":
            # Check for interrupt signal from LangGraph
            interrupt_data = None
            if isinstance(data, dict):
                interrupt_data = data.get("__interrupt__")

            if interrupt_data is not None:
                # Yield the sentinel tuple so the outer generator can handle it
                yield ("__interrupt_sentinel__", interrupt_data)
                return  # Stop consuming; outer generator will resume


async def sse_generator(
    thread_id: str,
    messages: list,
    agent,
    bus: "InterruptBus",
) -> AsyncGenerator[str, None]:
    """Core SSE streaming coroutine for a LangGraph agent run.

    Yields SSE-formatted strings for the FastAPI ``StreamingResponse``.

    Frame sequence for a normal (non-interrupted) run::

        event: thread_id   → {"thread_id": "<uuid>"}
        event: token       → {"content": "<delta>"} (zero or more)
        event: message     → {<full message>} (zero or more)
        event: done        → {}

    Frame sequence for an interrupted (HITL) run::

        event: thread_id   → {"thread_id": "<uuid>"}
        ...tokens/messages...
        event: interrupt   → {"value": <HITLRequest>, "id": "<str>"}
        <stream suspends — SSE connection stays open>
        <resume endpoint fires bus.resume()>
        ...tokens/messages (continued)...
        event: done        → {}

    On any unhandled exception (including ``asyncio.TimeoutError``)::

        event: error       → {"message": "<str>"}
    """
    yield format_sse("thread_id", {"thread_id": thread_id})

    try:
        async with asyncio.timeout(300):
            stream = agent.astream(
                {"messages": messages},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode=["messages", "updates"],
            )

            interrupted = False
            interrupt_value = None

            async for item in _process_stream_events(stream, thread_id):
                if isinstance(item, tuple) and item[0] == "__interrupt_sentinel__":
                    # Interrupt detected — extract value and pause
                    interrupted = True
                    raw_interrupt = item[1]

                    # LangGraph surfaces interrupts as a tuple/list of Interrupt objects.
                    # Each Interrupt has a .value attribute holding the interrupt payload.
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

                    # Register this thread as suspended and wait for the
                    # resume endpoint to provide decisions.
                    bus.set_interrupt(thread_id)
                    decisions = await bus.wait_for_resume(thread_id)

                    # Resume the agent — LangGraph accepts None as input when
                    # resuming from an interrupt; decisions are passed via the
                    # "resume" config key.
                    resume_stream = agent.astream(
                        None,
                        config={
                            "configurable": {"thread_id": thread_id},
                            "resume": {"decisions": decisions},
                        },
                        stream_mode=["messages", "updates"],
                    )

                    async for resumed_item in _process_stream_events(
                        resume_stream, thread_id
                    ):
                        if (
                            isinstance(resumed_item, tuple)
                            and resumed_item[0] == "__interrupt_sentinel__"
                        ):
                            # Nested interrupt — handle similarly
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
                            # For simplicity, stop here; further nesting is not
                            # expected in the current agent design.
                            break
                        else:
                            yield resumed_item

                    break  # Done processing the original stream after resume
                else:
                    yield item

        yield format_sse("done", {})

    except TimeoutError as e:
        logger.exception("SSE stream timed out for thread %s", thread_id)
        yield format_sse("error", {"message": f"Stream timeout: {str(e)}"})
    except Exception as e:
        logger.exception("SSE stream error for thread %s", thread_id)
        yield format_sse("error", {"message": str(e)})
