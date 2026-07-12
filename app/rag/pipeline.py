"""
PDF indexing pipeline.

index_pdf(artifact_id, thread_id, filename, file_path)
    Loads a PDF, splits it into chunks, embeds them, and upserts into Chroma.
    Returns the number of chunks indexed.

The pipeline is designed to be called from a background task so the HTTP
response is not blocked by the embedding work.
"""

from __future__ import annotations

import logging
import uuid

from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.chroma import get_collection
from app.settings import settings

logger = logging.getLogger(__name__)

# ── Shared embedding model ────────────────────────────────────────────────────

_embeddings = OpenAIEmbeddings(
    openai_api_base="https://models.github.ai/inference",
    model="text-embedding-3-small",
    api_key=settings.OPENAI_EMBEDDING_MODEL_API_KEY,
)

_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def index_pdf(
    artifact_id: str,
    thread_id: str,
    filename: str,
    file_path: str,
) -> int:
    """
    Load, chunk, embed, and store a PDF in the Chroma collection.

    Parameters
    ----------
    artifact_id:
        UUID of the Artifact row in the database.
    thread_id:
        UUID of the owning Thread.
    filename:
        Original filename (stored as metadata for display).
    file_path:
        Absolute path to the PDF on disk.

    Returns
    -------
    int
        Number of chunks indexed.

    Raises
    ------
    Exception
        Any loader or embedding error is propagated so the caller can update
        the artifact status to ``failed``.
    """
    logger.info("Indexing %s (artifact=%s, thread=%s)", filename, artifact_id, thread_id)

    # 1. Load
    loader = PyPDFLoader(file_path)
    docs = loader.load()

    # 2. Split
    chunks = _splitter.split_documents(docs)
    if not chunks:
        logger.warning("No chunks produced from %s", filename)
        return 0

    # 3. Embed
    texts = [chunk.page_content for chunk in chunks]
    embeddings = await _embeddings.aembed_documents(texts)

    # 4. Upsert into Chroma
    collection = get_collection()
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [
        {
            "thread_id": thread_id,
            "artifact_id": artifact_id,
            "filename": filename,
            "page": int(chunk.metadata.get("page", 0)),
            "chunk_index": i,
        }
        for i, chunk in enumerate(chunks)
    ]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    logger.info("Indexed %d chunks for artifact %s", len(chunks), artifact_id)
    return len(chunks)
