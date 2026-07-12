"""
Agent package — public API.

Existing callers only need ``create_chatbot_agent``.
PDF indexing is now handled by the artifact upload pipeline in app/rag/.
"""

from app.agent.factory import create_chatbot_agent

__all__ = ["create_chatbot_agent"]
