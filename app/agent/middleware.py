"""
Custom agent middleware.

GuardrailsMiddleware
    Runs NeMo Guardrails input/output checks around every model call.
    Disabled by default — uncomment in factory.py to enable.
"""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from nemoguardrails import LLMRails, RailsConfig


# Initialise rails once at import time (loads YAML config from ./guardrails/).
_rails_config = RailsConfig.from_path("./guardrails")
_guardrails = LLMRails(_rails_config)


class GuardrailsMiddleware(AgentMiddleware):
    """Runs NeMo Guardrails input/output checks around the agent's model call."""

    async def abefore_model(self, state, runtime):
        last_user_msg = state["messages"][-1].content

        result = await _guardrails.generate_async(
            messages=[{"role": "user", "content": last_user_msg}]
        )

        # Guardrails returns its own blocked response when a rail fires.
        if result.get("content", "").strip().lower().startswith("i'm sorry"):
            return {
                "messages": [AIMessage(content=result["content"])],
                "jump_to": "end",
            }
        return None

    async def aafter_model(self, state, runtime):
        last_ai_msg = state["messages"][-1].content

        result = await _guardrails.generate_async(
            messages=[{"role": "assistant", "content": last_ai_msg}]
        )

        new_content = result.get("content")
        if new_content and new_content != last_ai_msg:
            return {"messages": [AIMessage(content=new_content)]}
        return None
