from langchain.agents import create_agent
from langchain.tools import tool
from langchain.agents.middleware import HumanInTheLoopMiddleware 

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import aiosqlite


from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_tavily import TavilySearch

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.pipeline import ThreadAnonymizationPipeline
from piighost.middleware import PIIAnonymizationMiddleware
from gliner2 import GLiNER2

from nemoguardrails import LLMRails, RailsConfig
from langchain.agents.middleware import AgentMiddleware 



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

    return {
            "status": "success",
            "message": f"Placed Transaction: amount-{mock_price} to buy {symbol} {quantity} stocks.",
            "symbol": symbol,
            "quantity": quantity 
        }

tools = [search_tool, get_stock_price, rag_tool, purchase_stock]

endpoint = "https://models.github.ai/inference"
llm = ChatOpenAI(base_url=endpoint,model_name = "openai/gpt-4o-mini")

rails_config = RailsConfig.from_path("./guardrails")
guardrails = LLMRails(rails_config)


class GuardrailsMiddleware(AgentMiddleware):
    """Runs NeMo Guardrails input/output checks around the agent's model call."""

    async def before_model(self, state, config):
        last_user_msg = state["messages"][-1].content

        result = await guardrails.generate_async(
            messages=[{"role": "user", "content": last_user_msg}]
        )

        # Guardrails returns its own "blocked" canned response when a rail fires
        if result.get("content", "").strip().lower().startswith("i'm sorry"):
            return {
                "messages": [
                    {"role": "assistant", "content": result["content"]}
                ],
                "jump_to": "end",  # short-circuit, skip the actual LLM/tool call
            }
        return None

    async def after_model(self, state, config):
        last_ai_msg = state["messages"][-1].content

        result = await guardrails.generate_async(
            messages=[{"role": "assistant", "content": last_ai_msg}]
        )

        if result.get("content") != last_ai_msg:
            # output rail rewrote or blocked it
            state["messages"][-1].content = result["content"]
        return None
    

async def create_chatbot_agent():
    conn = await aiosqlite.connect("chatbot_state.db")
    checkpointer = AsyncSqliteSaver(conn)

    model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
    detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"])
    pipeline = ThreadAnonymizationPipeline(detector=detector, anonymizer=Anonymizer())


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
            PIIAnonymizationMiddleware(
                pipeline=pipeline
            ),
            GuardrailsMiddleware(),
        ]
    )
    
    return chatbot