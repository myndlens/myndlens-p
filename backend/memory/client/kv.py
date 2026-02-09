"""KV Entity Registry — maps human references to canonical entity IDs.

Prevents wrong-entity execution (e.g., wrong contact).
Stored in MongoDB `entity_registry` collection.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db

logger = logging.getLogger(__name__)


async def register_entity(
    user_id: str,
    canonical_id: str,
    entity_type: str,
    human_refs: List[str],
    data: Optional[Dict[str, Any]] = None,
    provenance: str = "EXPLICIT",
) -> None:
    """Register an entity with its human-readable references."""
    db = get_db()
    doc = {
        "user_id": user_id,
        "canonical_id": canonical_id,
        "entity_type": entity_type,
        "human_refs": [r.lower() for r in human_refs],
        "data": data or {},
        "provenance": provenance,
        "updated_at": datetime.now(timezone.utc),
    }
    await db.entity_registry.update_one(
        {"user_id": user_id, "canonical_id": canonical_id},
        {"$set": doc},
        upsert=True,
    )
    logger.debug("[KV] Entity registered: user=%s id=%s refs=%s", user_id, canonical_id, human_refs)


async def resolve_entity(
    user_id: str,
    human_ref: str,
) -> Optional[Dict[str, Any]]:
    """Resolve a human reference to a canonical entity."""
    db = get_db()
    doc = await db.entity_registry.find_one({
        "user_id": user_id,
        "human_refs": human_ref.lower(),
    })
    if doc:
        doc.pop("_id", None)
        return doc
    return None


async def resolve_entities(
    user_id: str,
    human_ref: str,
) -> List[Dict[str, Any]]:
    """Find all entities matching a reference (for disambiguation)."""
    db = get_db()
    cursor = db.entity_registry.find({
        "user_id": user_id,
        "human_refs": human_ref.lower(),
    })
    results = []
    async for doc in cursor:
        doc.pop("_id", None)
        results.append(doc)
    return results
