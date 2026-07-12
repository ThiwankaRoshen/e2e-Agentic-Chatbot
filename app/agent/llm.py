"""
LLM initialisation.

Centralises model construction so the rest of the agent package
just imports `llm` rather than repeating credentials/config.
"""

import os

from langchain_mistralai import ChatMistralAI
from app.settings import settings
llm = ChatMistralAI(
    model="mistral-large-latest",
    temperature=0,
    max_retries=2,
    mistral_api_key=settings.MISTRAL_API_KEY,
)
