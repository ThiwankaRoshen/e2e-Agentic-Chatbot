"""
Agent factory.

create_chatbot_agent()
    Assembles and returns the compiled LangGraph agent with checkpointer,
    tools, and middleware configured.

Note on AsyncPostgresSaver:
    from_conn_string() is an async context manager. To keep the connection
    pool alive for the full app lifetime we use AsyncConnectionPool directly,
    which gives us an explicit object we can open/close in the lifespan.

Note on checkpointer.setup():
    LangGraph's setup() runs CREATE INDEX CONCURRENTLY which PostgreSQL
    forbids inside a transaction block. psycopg opens transactions by default,
    so we run setup() through a dedicated autocommit pool, then use a normal
    pool for runtime queries.
"""

from __future__ import annotations

import psycopg
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

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


async def create_chatbot_agent() -> tuple:
    """
    Create and return (agent, connection_pool).

    The caller (lifespan) is responsible for closing the pool on shutdown:
        await pool.close()

    Sets up:
    - AsyncPostgresSaver checkpointer backed by PostgreSQL
    - HumanInTheLoopMiddleware for HITL approval on purchase_stock
    - (Optional) PIIAnonymizationMiddleware — disabled, uncomment to enable
    - (Optional) GuardrailsMiddleware — disabled, uncomment to enable
    """
    # ── Step 1: run setup() via autocommit pool ───────────────────────────────
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block, so we
    # use a temporary single-connection autocommit pool purely for DDL setup.
    setup_pool = AsyncConnectionPool(
        conninfo=settings.DATABASE_URL_FOR_CHECKPOINTER,
        min_size=1,
        max_size=1,
        open=False,
        kwargs={"autocommit": True},  # disables implicit transaction wrapping
    )
    await setup_pool.open()
    try:
        setup_checkpointer = AsyncPostgresSaver(setup_pool)
        await setup_checkpointer.setup()
    finally:
        await setup_pool.close()

    # ── Step 2: runtime pool (normal transactional connections) ───────────────
    pool = AsyncConnectionPool(
        conninfo=settings.DATABASE_URL_FOR_CHECKPOINTER,
        min_size=2,
        max_size=10,
        open=False,
    )
    await pool.open()

    checkpointer = AsyncPostgresSaver(pool)

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

    return chatbot, pool
