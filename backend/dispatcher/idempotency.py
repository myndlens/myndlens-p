"""Idempotency — prevents duplicate dispatch.

Key = {session_id}:{mio_id}
Duplicate requests with same key MUST NOT re-execute.
"""
import logging
from typing import Any, Dict, Optional

from core.database import get_db

logger = logging.getLogger(__name__)


async def check_idempotency(key: str) -> Optional[Dict[str, Any]]:
    """Check if a dispatch already exists. Returns record if duplicate."""
    db = get_db()
    doc = await db.dispatches.find_one({"idempotency_key": key})
    if doc:
        doc.pop("_id", None)
        return doc
    return None


async def record_dispatch(key: str, record: Dict[str, Any]) -> None:
    """Record a completed dispatch."""
    db = get_db()
    record["idempotency_key"] = key
    await db.dispatches.update_one(
        {"idempotency_key": key},
        {"$set": record},
        upsert=True,
    )
    logger.info("Dispatch recorded: key=%s", key)
