"""
Tool definitions and RAG utilities.

Exports
-------
tools
    List of all LangChain tools passed to create_agent().
load_pdf_and_create_vector_store(pdf_path)
    Index a PDF into the FAISS vector store.
INDEX_PATH
    Filesystem path of the FAISS index directory.
"""

from __future__ import annotations

import os
import random

import requests
from langchain.tools import tool
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_tavily import TavilySearch
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── Embeddings ────────────────────────────────────────────────────────────────

_embeddings = OpenAIEmbeddings(
    openai_api_base="https://models.github.ai/inference",
    model="text-embedding-3-small",
    api_key=os.environ["OPENAI_EMBEDDING_MODEL_API_KEY"],
)

# ── RAG utilities ─────────────────────────────────────────────────────────────

INDEX_PATH = "faiss_index"

_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)


def load_pdf_and_create_vector_store(pdf_path: str) -> None:
    """Load a PDF, split it into chunks, and save a FAISS index to disk."""
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()
    chunks = _splitter.split_documents(docs)
    vector_store = FAISS.from_documents(chunks, _embeddings)
    vector_store.save_local(INDEX_PATH)


def _get_retriever():
    return FAISS.load_local(
        folder_path=INDEX_PATH,
        embeddings=_embeddings,
        allow_dangerous_deserialization=True,
    ).as_retriever(search_type="similarity", search_kwargs={"k": 4})


# ── Tool: RAG ─────────────────────────────────────────────────────────────────

@tool
def rag_tool(query: str) -> str:
    """
    Retrieve relevant information from the PDF document.
    Use this tool when the user asks factual or conceptual questions that may
    be answered using the stored PDF documents.

    Args:
        query: The question or search query used to retrieve PDF content.
    """
    documents = _get_retriever().invoke(query)

    if not documents:
        return "No relevant information was found in the PDF."

    formatted = []
    for i, doc in enumerate(documents, start=1):
        source = doc.metadata.get("source", "Unknown source")
        page = doc.metadata.get("page", "Unknown page")
        formatted.append(
            f"\nDocument: {i}\nSource: {source}\nPage: {page}\nContent: {doc.page_content}"
        )

    return "\n\n".join(formatted)


# ── Tool: web search ──────────────────────────────────────────────────────────

search_tool = TavilySearch(
    max_results=5,
    topic="general",
    search_depth="advanced",
)


# ── Tool: stock price ─────────────────────────────────────────────────────────

@tool
def get_stock_price(symbol: str) -> dict:
    """
    Fetch the latest stock price for a given symbol (e.g. AAPL, TSLA).

    Returns a dict with symbol, price, change, change_percent, volume,
    and latest_trading_day fields.
    """
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
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
