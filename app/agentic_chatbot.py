from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
import sqlite3
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_tavily import TavilySearch
from typing import TypedDict, Annotated

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

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

tools = [search_tool, calculator, get_stock_price, rag_tool]

endpoint = "https://models.github.ai/inference"
llm = ChatOpenAI(base_url=endpoint,model_name = "openai/gpt-4o-mini")
llm_with_tools = llm.bind_tools(tools)

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def chat_node(state: ChatState):
    messages = state['messages']
    response = llm_with_tools.invoke(messages)
    return {'messages': [response]}

tool_node = ToolNode(tools)



conn = sqlite3.connect('chatbot_state.db', check_same_thread=False)
checkpointer = SqliteSaver(conn)
graph = StateGraph(ChatState)
graph.add_node('chat_node', chat_node)
graph.add_node('tools', tool_node)
graph.add_edge(START, 'chat_node')
graph.add_conditional_edges('chat_node', tools_condition)
graph.add_edge('tools', 'chat_node')
graph.add_edge('chat_node', END)
chatbot = graph.compile(checkpointer)

 