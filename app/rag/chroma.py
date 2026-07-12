"""
Chroma vector store client.

One persistent collection named ``documents`` holds all chunks across all
threads.  Every chunk carries metadata so queries can be filtered by
thread_id and/or artifact_id without needing separate collections.

Metadata schema per chunk
--------------------------
{
    "thread_id":   "<str>",
    "artifact_id": "<str>",
    "filename":    "<str>",
    "page":        <int>,
    "chunk_index": <int>,
}
"""

from __future__ import annotations

import chromadb
from chromadb import Collection
from chromadb.config import Settings as ChromaSettings

from app.settings import settings

# ── Client (module-level singleton) ──────────────────────────────────────────

_client: chromadb.PersistentClient | None = None
_collection: Collection | None = None

COLLECTION_NAME = "documents"


def get_client() -> chromadb.PersistentClient:
    """Return (or lazily create) the persistent Chroma client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_collection() -> Collection:
    """Return (or lazily create) the shared ``documents`` collection."""
    global _collection
    if _collection is None:
        _collection = get_client().get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def query(
    query_texts: list[str],
    thread_id: str,
    artifact_id: str | None = None,
    n_results: int = 4,
) -> list[dict]:
    """
    Query the collection filtered to a specific thread (and optionally a
    specific artifact).

    Returns a list of result dicts, each with ``document`` and ``metadata``
    keys, ordered by relevance.
    """
    collection = get_collection()

    where: dict = {"thread_id": thread_id}
    if artifact_id:
        where = {"$and": [{"thread_id": thread_id}, {"artifact_id": artifact_id}]}

    # Guard: Chroma raises if n_results > number of stored docs
    count = collection.count()
    safe_n = min(n_results, count) if count > 0 else 0
    if safe_n == 0:
        return []

    results = collection.query(
        query_texts=query_texts,
        n_results=safe_n,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for doc, meta in zip(
        results["documents"][0],
        results["metadatas"][0],
    ):
        output.append({"document": doc, "metadata": meta})

    return output


def delete_thread(thread_id: str) -> None:
    """Remove all chunks belonging to a thread from the collection."""
    collection = get_collection()
    collection.delete(where={"thread_id": thread_id})


def delete_artifact(artifact_id: str) -> None:
    """Remove all chunks belonging to a single artifact."""
    collection = get_collection()
    collection.delete(where={"artifact_id": artifact_id})
