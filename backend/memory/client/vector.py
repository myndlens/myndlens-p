"""Vector Store — ChromaDB with ONNX embeddings + MongoDB persistence.

Stores node-documents with ONNX-generated embeddings for similarity search.
Digital Self is the SOLE authority for vector access.

Persistence layer:
  - ChromaDB (in-memory): fast similarity search during runtime
  - MongoDB `vector_store` collection: durable storage across restarts

On startup: reload_from_mongodb() rehydrates ChromaDB from MongoDB.
On write:   add_document() writes to both ChromaDB and MongoDB atomically.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings

from memory.client.embedder import embed
from core.database import get_db

logger = logging.getLogger(__name__)

_client: Optional[chromadb.ClientAPI] = None
_collection = None

COLLECTION_NAME = "digital_self"


class ONNXEmbeddingFunction(EmbeddingFunction):
    """ChromaDB-compatible embedding function backed by ONNX Runtime via fastembed."""

    def __call__(self, input: Documents) -> Embeddings:
        return embed(list(input))


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.Client()
        logger.info("[VectorStore] ChromaDB client initialized (ONNX embeddings)")
    return _client


def _get_collection():
    global _collection
    if _collection is None:
        client = _get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ONNXEmbeddingFunction(),
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("[VectorStore] Collection '%s' ready (ONNX)", COLLECTION_NAME)
    return _collection


def add_document(
    doc_id: str,
    text: str,
    metadata: Dict[str, Any],
) -> None:
    """Add a document to the vector store and persist to MongoDB.
    The ONNX embedding function generates the vector from `text`.
    """
    coll = _get_collection()
    coll.upsert(
        ids=[doc_id],
        documents=[text],
        metadatas=[metadata],
    )
    # Persist to MongoDB immediately
    _persist_one(doc_id, text, metadata)
    logger.debug("[VectorStore] Document added+persisted: id=%s", doc_id)


def add_document_with_embedding(
    doc_id: str,
    embedding: List[float],
    metadata: Dict[str, Any],
) -> None:
    """Add a pre-computed embedding to the vector store (bypasses ONNX re-embedding).

    Used when the embedding is generated server-side from device-provided text.
    Text is NOT stored — only the vector + metadata.
    """
    coll = _get_collection()
    coll.upsert(
        ids=[doc_id],
        embeddings=[embedding],
        documents=[""],   # Empty — text was discarded after embedding
        metadatas=[metadata],
    )
    _persist_one(doc_id, "", metadata)
    logger.debug("[VectorStore] Embedding added (no text): id=%s dim=%d", doc_id, len(embedding))


def _persist_one(doc_id: str, text: str, metadata: Dict[str, Any]) -> None:
    """Write a single vector document to MongoDB (fire-and-forget via sync)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_async_persist_one(doc_id, text, metadata))
        else:
            loop.run_until_complete(_async_persist_one(doc_id, text, metadata))
    except Exception as e:
        logger.warning("[VectorStore] MongoDB persist failed: %s", str(e))


async def _async_persist_one(doc_id: str, text: str, metadata: Dict[str, Any]) -> None:
    db = get_db()
    await db.vector_store.update_one(
        {"doc_id": doc_id},
        {"$set": {"doc_id": doc_id, "text": text, "metadata": metadata}},
        upsert=True,
    )


async def reload_from_mongodb() -> int:
    """Reload all vector documents from MongoDB into ChromaDB on startup.

    Fixes the restart-wipe bug: ChromaDB is in-memory; this restores
    all previously stored Digital Self facts after a server restart.
    Returns number of documents reloaded.

    PRODUCTION NOTE:
    - This collection must contain ONLY real user vectors synced from devices.
    - Never seed or pre-populate with test/demo data in production.
    - Test data must be scoped to test_user_* user_ids and cleared after tests.
    - All queries MUST filter by user_id (pass where={"user_id": uid} to query()).
    """
    db = get_db()
    coll = _get_collection()

    docs = await db.vector_store.find({}, {"_id": 0}).to_list(10000)
    if not docs:
        logger.info("[VectorStore] No persisted vectors found — fresh start")
        return 0

    coll.upsert(
        ids=[d["doc_id"] for d in docs],
        documents=[d["text"] for d in docs],
        metadatas=[d["metadata"] for d in docs],
    )
    logger.info("[VectorStore] Reloaded %d vectors from MongoDB", len(docs))
    return len(docs)


def query(
    query_text: str,
    n_results: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Semantic similarity search using ONNX embeddings."""
    coll = _get_collection()
    actual_count = coll.count()
    if actual_count == 0:
        return []
    n_results = min(n_results, actual_count)

    kwargs: Dict[str, Any] = {
        "query_texts": [query_text],
        "n_results": n_results,
    }
    if where:
        kwargs["where"] = where

    results = coll.query(**kwargs)

    docs = []
    if results and results["ids"]:
        for i, doc_id in enumerate(results["ids"][0]):
            docs.append({
                "id": doc_id,
                "text": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })
    return docs


def delete_document(doc_id: str) -> None:
    """Delete a document from ChromaDB and MongoDB."""
    coll = _get_collection()
    coll.delete(ids=[doc_id])
    # Also remove from MongoDB so it doesn't reload on restart
    try:
        import asyncio
        from core.database import get_db
        async def _del():
            db = get_db()
            await db.vector_store.delete_one({"doc_id": doc_id})
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_del())
        else:
            loop.run_until_complete(_del())
    except Exception as e:
        logger.warning("[VectorStore] MongoDB delete failed for %s: %s", doc_id, e)


def count() -> int:
    coll = _get_collection()
    return coll.count()

