"""
Tool definitions.

All tools are registered in the ``tools`` list at the bottom of this module
and passed to ``create_agent()`` in factory.py.

RAG tool
--------
``rag_tool`` is thread-scoped.  The backend injects ``thread_id`` via a
LangChain RunnableConfig so the LLM never has access to it and cannot
accidentally search another thread's documents.

Usage inside the agent graph (set in the config at runtime)::

    config = {"configurable": {"thread_id": "<uuid>"}}

The tool reads ``thread_id`` from the config at call time.
"""

from __future__ import annotations

import os
import random

import requests
from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_tavily import TavilySearch

from app.settings import settings
from app.rag import chroma as rag_chroma

# ── Tool: RAG (thread-scoped via Chroma) ─────────────────────────────────────

@tool
def rag_tool(query: str, config: RunnableConfig) -> str:
    """
    Retrieve relevant information from the documents attached to this
    conversation thread.

    Use this tool when the user asks factual or conceptual questions that
    may be answered by files they have uploaded.

    Args:
        query: The question or search query.
    """
    thread_id: str | None = config.get("configurable", {}).get("thread_id")
    if not thread_id:
        return "No thread context available — cannot search documents."

    results = rag_chroma.query(
        query_texts=[query],
        thread_id=thread_id,
        n_results=4,
    )

    if not results:
        return "No relevant information was found in the uploaded documents."

    formatted = []
    for i, item in enumerate(results, start=1):
        meta = item["metadata"]
        formatted.append(
            f"Document {i}\n"
            f"File: {meta.get('filename', 'unknown')}  "
            f"Page: {meta.get('page', '?')}\n"
            f"{item['document']}"
        )

    return "\n\n---\n\n".join(formatted)


# ── Tool: web search ──────────────────────────────────────────────────────────

search_tool = TavilySearch(
    max_results=5,
    topic="general",
    search_depth="advanced",
    tavily_api_key=settings.TAVILY_API_KEY
)


# ── Tool: stock price ─────────────────────────────────────────────────────────

@tool
def get_stock_price(symbol: str) -> dict:
    """
    Fetch the latest stock price for a given symbol (e.g. AAPL, TSLA).

    Returns a dict with symbol, price, change, change_percent, volume,
    and latest_trading_day fields.
    """
    api_key = settings.ALPHA_VANTAGE_API_KEY
    if not api_key:
        return {"error": "ALPHA_VANTAGE_API_KEY not configured"}

    url = (
        "https://www.alphavantage.co/query"
        f"?function=GLOBAL_QUOTE"
        f"&symbol={symbol.upper()}"
        f"&apikey={api_key}"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        quote = data.get("Global Quote")
        if not quote:
            return {"error": f"No data found for symbol '{symbol}'"}

        return {
            "symbol": quote.get("01. symbol"),
            "price": quote.get("05. price"),
            "change": quote.get("09. change"),
            "change_percent": quote.get("10. change percent"),
            "volume": quote.get("06. volume"),
            "latest_trading_day": quote.get("07. latest trading day"),
        }
    except requests.RequestException as exc:
        return {"error": f"Request failed: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ── Tool: purchase stock (mock) ───────────────────────────────────────────────

@tool
def purchase_stock(symbol: str, quantity: int) -> dict:
    """
    Mock function to simulate purchasing a stock.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'TSLA').
        quantity: Number of shares to purchase (must be > 0).

    Returns a dict with the simulated trade details.
    """
    if quantity <= 0:
        return {"success": False, "error": "Quantity must be greater than zero."}

    mock_price = round(random.uniform(50, 500), 2)
    return {
        "status": "success",
        "message": f"Placed Transaction: amount-{mock_price} to buy {symbol} {quantity} stocks.",
        "symbol": symbol,
        "quantity": quantity,
    }


# ── Tool registry ─────────────────────────────────────────────────────────────

tools = [search_tool, get_stock_price, rag_tool, purchase_stock]
