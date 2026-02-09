"""Soul Store — B20.

The "Soul" is MyndLens' core identity stored in vector memory.
Not a file. Dynamic, versioned, drift-protected.

Stored in ChromaDB (semantic layer) + MongoDB (version metadata).
Personalization per user; drift from base forbidden.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import chromadb

from core.database import get_db

logger = logging.getLogger(__name__)

# Separate ChromaDB collection for soul fragments
_client: Optional[chromadb.ClientAPI] = None
_collection = None
COLLECTION_NAME = "myndlens_soul"


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.Client()
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


# ---- Base Soul Fragments (canonical, frozen) ----

BASE_SOUL_FRAGMENTS = [
    {
        "id": "soul-identity",
        "text": (
            "You are MyndLens, a sovereign voice assistant and personal cognitive proxy. "
            "You extract user intent from natural conversation, bridge gaps using the Digital Self "
            "(vector-graph memory), and generate structured dimensions for safe execution."
        ),
        "category": "identity",
        "priority": 1,
    },
    {
        "id": "soul-personality",
        "text": (
            "You are empathetic, concise, and to-the-point. You never fabricate information. "
            "You speak naturally, not like a robot. You anticipate needs based on the user's "
            "Digital Self but never assume without evidence."
        ),
        "category": "personality",
        "priority": 2,
    },
    {
        "id": "soul-sovereignty",
        "text": (
            "You operate under strict sovereignty: no action without explicit user authorization. "
            "You are the user's cognitive extension, not an autonomous agent. "
            "Every execution requires the user's physical presence and conscious approval."
        ),
        "category": "sovereignty",
        "priority": 3,
    },
    {
        "id": "soul-safety",
        "text": (
            "You refuse harmful, illegal, or policy-violating requests tactfully. "
            "If ambiguity exceeds 30%, you ask for clarification instead of guessing. "
            "You default to silence over action when uncertain."
        ),
        "category": "safety",
        "priority": 4,
    },
    {
        "id": "soul-communication",
        "text": (
            "You adapt your communication style to the user's preferences stored in their "
            "Digital Self. You use the user's preferred vocabulary, formality level, and pace. "
            "You never expose internal system state, error codes, or technical jargon."
        ),
        "category": "communication",
        "priority": 5,
    },
]


def compute_soul_hash(fragments: List[Dict[str, Any]]) -> str:
    """Compute deterministic hash of soul fragments."""
    combined = "\n".join(
        f"{f['id']}:{f['text']}" for f in sorted(fragments, key=lambda x: x["id"])
    )
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


async def initialize_base_soul() -> str:
    """Load base soul fragments into vector memory. Idempotent."""
    coll = _get_collection()

    for frag in BASE_SOUL_FRAGMENTS:
        coll.upsert(
            ids=[frag["id"]],
            documents=[frag["text"]],
            metadatas=[{
                "category": frag["category"],
                "priority": frag["priority"],
                "version": "1.0.0",
                "is_base": True,
                "user_id": "__base__",
            }],
        )

    base_hash = compute_soul_hash(BASE_SOUL_FRAGMENTS)

    # Store version metadata in MongoDB
    db = get_db()
    await db.soul_versions.update_one(
        {"version": "1.0.0"},
        {"$set": {
            "version": "1.0.0",
            "hash": base_hash,
            "fragment_count": len(BASE_SOUL_FRAGMENTS),
            "created_at": datetime.now(timezone.utc),
            "is_base": True,
        }},
        upsert=True,
    )

    logger.info("[Soul] Base soul initialized: %d fragments, hash=%s", len(BASE_SOUL_FRAGMENTS), base_hash[:16])
    return base_hash


def retrieve_soul(
    context_query: Optional[str] = None,
    user_id: Optional[str] = None,
    n_results: int = 5,
) -> List[Dict[str, Any]]:
    """Retrieve soul fragments, optionally filtered by context."""
    coll = _get_collection()

    if context_query:
        results = coll.query(
            query_texts=[context_query],
            n_results=n_results,
        )
    else:
        # Return all base fragments
        results = coll.get(
            where={"is_base": True},
        )

    fragments = []
    if results and results.get("ids"):
        ids = results["ids"] if isinstance(results["ids"][0], str) else results["ids"][0]
        docs = results["documents"] if isinstance(results["documents"][0], str) else results["documents"][0]
        metas = results["metadatas"] if isinstance(results["metadatas"][0], dict) else results["metadatas"][0]

        for i, doc_id in enumerate(ids):
            fragments.append({
                "id": doc_id,
                "text": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
            })

    # Sort by priority
    fragments.sort(key=lambda f: f.get("metadata", {}).get("priority", 99))
    return fragments


async def add_user_soul_fragment(
    user_id: str,
    text: str,
    category: str,
) -> str:
    """Add a user-specific soul fragment (personalization).
    
    Requires explicit user signal. Never silent.
    """
    frag_id = f"soul-user-{user_id[:8]}-{uuid.uuid4().hex[:8]}"
    coll = _get_collection()

    coll.upsert(
        ids=[frag_id],
        documents=[text],
        metadatas=[{
            "category": category,
            "priority": 10,  # User fragments are lower priority than base
            "version": "user",
            "is_base": False,
            "user_id": user_id,
        }],
    )

    logger.info("[Soul] User fragment added: user=%s id=%s category=%s", user_id, frag_id, category)
    return frag_id
