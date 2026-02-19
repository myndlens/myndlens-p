"""Vector Store — ChromaDB semantic layer.

Stores node-documents with embeddings for similarity search.
Digital Self is the SOLE authority for vector access.
"""
import logging
from typing import Any, Dict, List, Optional

import chromadb

logger = logging.getLogger(__name__)

_client: Optional[chromadb.ClientAPI] = None
_collection = None

COLLECTION_NAME = "digital_self"


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.Client()  # In-memory; persistent via MongoDB export
        logger.info("[VectorStore] ChromaDB client initialized (in-memory)")
    return _client


def _get_collection():
    global _collection
    if _collection is None:
        client = _get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("[VectorStore] Collection '%s' ready", COLLECTION_NAME)
    return _collection


def add_document(
    doc_id: str,
    text: str,
    metadata: Dict[str, Any],
) -> None:
    """Add a document to the vector store."""
    coll = _get_collection()
    coll.upsert(
        ids=[doc_id],
        documents=[text],
        metadatas=[metadata],
    )
    logger.debug("[VectorStore] Document added: id=%s", doc_id)


def query(
    query_text: str,
    n_results: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Semantic similarity search."""
    coll = _get_collection()
    # ChromaDB raises if n_results > collection size
    actual_count = coll.count()
    if actual_count == 0:
        return []
    n_results = min(n_results, actual_count)

    kwargs = {
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
    coll = _get_collection()
    coll.delete(ids=[doc_id])


def count() -> int:
    coll = _get_collection()
    return coll.count()
