"""
Agent package — re-exports the public API so existing callers
(api_server.py, streamlit_app.py) don't need import changes.
"""

from app.agent.factory import create_chatbot_agent
from app.agent.tools import load_pdf_and_create_vector_store, INDEX_PATH

__all__ = [
    "create_chatbot_agent",
    "load_pdf_and_create_vector_store",
    "INDEX_PATH",
]
