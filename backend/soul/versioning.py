"""Soul Versioning — B20.

Version pinning for stability. Rollback capability.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db
from soul.store import compute_soul_hash, BASE_SOUL_FRAGMENTS

logger = logging.getLogger(__name__)


async def get_current_version() -> Optional[Dict[str, Any]]:
    """Get the current active soul version."""
    db = get_db()
    doc = await db.soul_versions.find_one(
        {"is_base": True},
        sort=[("created_at", -1)],
    )
    if doc:
        doc.pop("_id", None)
    return doc


async def list_versions() -> List[Dict[str, Any]]:
    """List all soul versions."""
    db = get_db()
    cursor = db.soul_versions.find({}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(100)


async def verify_integrity() -> Dict[str, Any]:
    """Verify current soul matches expected hash."""
    current = await get_current_version()
    if not current:
        return {"valid": False, "reason": "No soul version found"}

    expected_hash = current.get("hash", "")
    actual_hash = compute_soul_hash(BASE_SOUL_FRAGMENTS)

    matches = expected_hash == actual_hash
    return {
        "valid": matches,
        "version": current.get("version"),
        "expected_hash": expected_hash[:16] + "...",
        "actual_hash": actual_hash[:16] + "...",
        "fragment_count": current.get("fragment_count", 0),
    }
