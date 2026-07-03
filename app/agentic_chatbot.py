from __future__ import annotations

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import interrupt, Command
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
import sqlite3
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_tavily import TavilySearch
from typing import TypedDict, Annotated, Literal

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

from nemoguardrails import LLMRails, RailsConfig
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from datetime import datetime
import random
import requests
import math
import os
from dotenv import load_dotenv
load_dotenv() 
 
token = os.environ["OPENAI_EMBEDDING_MODEL_API_KEY"]
endpoint = "https://models.github.ai/inference"
model_name = "text-embedding-3-small"  
embeddings = OpenAIEmbeddings(
    openai_api_base=endpoint,  
    model=model_name,          
    api_key=token,
)


splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
INDEX_PATH = "faiss_index"
def load_pdf_and_create_vector_store(pdf_path: str):
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()
    chunks = splitter.split_documents(docs)
    vector_store = FAISS.from_documents(chunks, embeddings)
    vector_store.save_local(INDEX_PATH)

def get_retriever():
    retriever = FAISS.load_local(
        folder_path=INDEX_PATH,
        embeddings=embeddings,
        allow_dangerous_deserialization=True
        ).as_retriever(search_type="similarity", search_kwargs={'k':4})
    return retriever

@tool
def rag_tool(query: str)->str:
    """
    Retrieve relevant information from the PDF document.
    Use this tool when the user asks factual or conceptual questions that may be answered using the stored PDF dcocuments.

    Args:
        Query: The questions or search query used to retrieve PDF content.
    """
    documents = get_retriever().invoke(query)

    if not documents:
        return "No relevent information was found in the PDF"

    formatted_documents = []

    for i, doc in enumerate(documents, start=1):
        source = doc.metadata.get("source", "Unknown source")
        page = doc.metadata.get("page", "Unknown page")

        formatted_documents.append(
            f"""
            Document: {i}
            Source: {source}
            Page: {page}
            Content: {doc.page_content}
            """
        )
    return "\n\n".join(formatted_documents)

search_tool = TavilySearch(
    max_results=5,
    topic="general",
    search_depth="advanced"
)

@tool
def calculator(expression: str) -> str:
    """
    Useful for simple math calculations.
    Input should be a valid math expression.
    Example: 2+2, sqrt(16), 10*5
    """
    try:
        allowed_names = {
            k: v
            for k, v in math.__dict__.items()
            if not k.startswith("__")
        }

        result = eval(
            expression,
            {"__builtins__": {}},
            allowed_names
        )

        return str(result)

    except Exception as e:
        return f"Calculation error: {str(e)}"


 

@tool
def get_stock_price(symbol: str) -> dict:
    """
    Fetch the latest stock price for a given symbol (e.g. AAPL, TSLA).

    Returns:
    {
        "symbol": "AAPL",
        "price": "213.55",
        "change": "-1.23",
        "change_percent": "-0.57%",
        "volume": "53492012",
        "latest_trading_day": "2026-06-24"
    }
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
            return {
                "error": f"No data found for symbol '{symbol}'"
            }

        return {
            "symbol": quote.get("01. symbol"),
            "price": quote.get("05. price"),
            "change": quote.get("09. change"),
            "change_percent": quote.get("10. change percent"),
            "volume": quote.get("06. volume"),
            "latest_trading_day": quote.get("07. latest trading day"),
        }

    except requests.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}

    except Exception as e:
        return {"error": str(e)}



@tool
def purchase_stock(symbol: str, quantity: int) -> dict:
    """
    Mock function to simulate purchasing a stock.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'TSLA').
        quantity: Number of shares to purchase.

    Returns:
        A dictionary containing the simulated trade details.
    """

    if quantity <= 0:
        return {
            "success": False,
            "error": "Quantity must be greater than zero."
        }

    # Simulated market price
    mock_price = round(random.uniform(50, 500), 2)

    decision = interrupt(f"Approval for Transaction: amount-{mock_price} to buy {symbol} {quantity} stocks. (yes/no)")

    if decision.lower()=="no":
        return {
            "status": "cancelled",
            "message": f"Declined Transaction: amount-{mock_price} to buy {symbol} {quantity} stocks.",
            "symbol": symbol,
            "quantity": quantity 
        }
    return {
            "status": "success",
            "message": f"Placed Transaction: amount-{mock_price} to buy {symbol} {quantity} stocks.",
            "symbol": symbol,
            "quantity": quantity 
        }

tools = [search_tool, calculator, get_stock_price, rag_tool, purchase_stock]

endpoint = "https://models.github.ai/inference"
llm = ChatOpenAI(base_url=endpoint,model_name = "openai/gpt-4o-mini")
llm_with_tools = llm.bind_tools(tools)




# ========== LOCAL PII DETECTION (No external calls) ==========

provider = NlpEngineProvider(nlp_configuration={
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}]
})
analyzer = AnalyzerEngine(
    nlp_engine=provider.create_engine(),
    supported_languages=["en"]
)

def detect_pii(user_message: str) -> dict:
    """Local PII detection using Presidio - NO external API calls"""
    results = analyzer.analyze(
        text=user_message,
        language="en",
        entities=[
            "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
            "US_SSN", "CREDIT_CARD_NUMBER", "ADDRESS",
            "DATE_OF_BIRTH", "IP_ADDRESS", "IBAN_CODE"
        ]
    )
    
    if results:
        pii_types = list(set([r.entity_type.replace("_", " ").title() for r in results]))
        details = "; ".join([f"{r.entity_type}: '{user_message[r.start:r.end]}'" for r in results])
        return {"has_pii": True, "pii_types": pii_types, "details": details}
    
    return {"has_pii": False, "pii_types": [], "details": ""}


pii_config = RailsConfig.from_path("./config")
pii_rails = LLMRails(pii_config)
pii_rails.register_action(detect_pii, "detect_pii")

# ============ Updated State ============

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    proceed_to_llm: bool


# ============ PII Guardrail Node ============

def pii_guardrail_node(state: ChatState):
    messages = state['messages']
    
    last_human_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human_msg = msg.content
            break

    if not last_human_msg:
        return {'proceed_to_llm': True}

    # Call NeMo (which calls your local detect_pii function)
    result = pii_rails.generate(messages=[{"role": "user", "content": last_human_msg}])
    response_text = result if isinstance(result, str) else str(result)

    if "PII_DETECTED:" in response_text:
        parts = response_text.split("PII_DETECTED:")[1]
        types_str, details = parts.split("|", 1)
        pii_types = [t.strip() for t in types_str.split(",")]

        user_decision = interrupt(
            f"🔒 **PII DETECTED**\n\n"
            f"• **Types:** {', '.join(pii_types)}\n"
            f"• **Details:** {details.strip()}\n\n"
            f"Send to AI? (yes/no)"
        )

        if user_decision and str(user_decision).lower().strip() in ['yes', 'y']:
            return {'messages': [AIMessage(content="✅ Confirmed.")], 'proceed_to_llm': True}
        
        return {
            'messages': [AIMessage(content="🛑 Blocked. Remove PII and try again.")],
            'proceed_to_llm': False
        }

    return {'proceed_to_llm': True}


def route_after_pii_check(state: ChatState) -> Literal["chat_node", "__end__"]:
    """Route to chat_node or END based on PII check result"""
    if state.get('proceed_to_llm', True):
        return "chat_node"
    return "__end__"

def chat_node(state: ChatState):
    messages = state['messages']
    response = llm_with_tools.invoke(messages)
    return {'messages': [response]}

tool_node = ToolNode(tools)



conn = sqlite3.connect('chatbot_state.db', check_same_thread=False)
checkpointer = SqliteSaver(conn)

graph = StateGraph(ChatState)

graph.add_node('pii_guardrail', pii_guardrail_node)
graph.add_node('chat_node', chat_node)
graph.add_node('tools', tool_node)

graph.add_edge(START, 'pii_guardrail')
graph.add_conditional_edges('pii_guardrail', route_after_pii_check)
graph.add_conditional_edges('chat_node', tools_condition)
graph.add_edge('tools', 'chat_node') 

chatbot = graph.compile(checkpointer)
