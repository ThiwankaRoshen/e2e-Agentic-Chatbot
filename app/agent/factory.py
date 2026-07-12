"""
Agent factory.

create_chatbot_agent()
    Assembles and returns the compiled LangGraph agent with checkpointer,
    tools, and middleware configured.
"""

from __future__ import annotations

import aiosqlite
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent.llm import llm
from app.agent.tools import tools
from app.settings import settings

# Uncomment to enable optional middleware:
# from app.agent.middleware import GuardrailsMiddleware
# from piighost.anonymizer import Anonymizer
# from piighost.detector.gliner2 import Gliner2Detector
# from piighost.middleware import PIIAnonymizationMiddleware
# from piighost.pipeline import ThreadAnonymizationPipeline
# from gliner2 import GLiNER2


async def create_chatbot_agent():
    """
    Create and return the compiled LangGraph chatbot agent.

    Sets up:
    - AsyncSqliteSaver checkpointer for durable thread state
    - HumanInTheLoopMiddleware for HITL approval on purchase_stock
    - (Optional) PIIAnonymizationMiddleware — disabled, uncomment to enable
    - (Optional) GuardrailsMiddleware — disabled, uncomment to enable
    """
    conn = await aiosqlite.connect(settings.SQLITE_DB_PATH)
    checkpointer = AsyncSqliteSaver(conn)

    # Optional: PII anonymization setup
    # model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
    # detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"])
    # pipeline = ThreadAnonymizationPipeline(detector=detector, anonymizer=Anonymizer())

    chatbot = create_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpointer,
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "purchase_stock": True,
                },
                description_prefix="Tool execution pending approval",
            ),
            # PIIAnonymizationMiddleware(pipeline=pipeline),
            # GuardrailsMiddleware(),
        ],
    )

    return chatbot
