"""Governance Backup — refactored per Dev Agent Contract.

Backs up ONLY MyndLens-owned data:
  - Digital Self (graphs, entities, vector metadata)
  - Prompt snapshots
  - Audit events (MyndLens side)

Does NOT back up ObeGee-owned data:
  - Tenant records (ObeGee owns)
  - User sessions (tenant lifecycle = ObeGee)
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid

from core.database import get_db

logger = logging.getLogger(__name__)


async def create_backup(user_id: str, include_audit: bool = True) -> Dict[str, Any]:
    """Create a backup of MyndLens-owned data for a user."""
    db = get_db()
    backup_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # MyndLens-owned: Digital Self
    graphs = await db.graphs.find({"user_id": user_id}).to_list(100)
    entities = await db.entity_registry.find({"user_id": user_id}).to_list(1000)

    # MyndLens-owned: Audit events (MyndLens side only)
    audit_events = []
    if include_audit:
        audit_events = await db.audit_events.find({"user_id": user_id}).to_list(10000)

    for collection in [graphs, entities, audit_events]:
        for doc in collection:
            doc.pop("_id", None)

    snapshot = {
        "backup_id": backup_id,
        "user_id": user_id,
        "created_at": now,
        "scope": "myndlens_owned_only",
        "data": {
            "graphs": graphs,
            "entities": entities,
            "audit_events": audit_events,
        },
        "counts": {
            "graphs": len(graphs),
            "entities": len(entities),
            "audit_events": len(audit_events),
        },
    }

    await db.backups.insert_one(snapshot)
    logger.info("[Backup] Created (MyndLens-owned): id=%s user=%s", backup_id[:12], user_id)

    return {
        "backup_id": backup_id,
        "user_id": user_id,
        "scope": "myndlens_owned_only",
        "created_at": now.isoformat(),
        "counts": snapshot["counts"],
    }


async def list_backups(user_id: str) -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db.backups.find(
        {"user_id": user_id},
        {"_id": 0, "backup_id": 1, "user_id": 1, "created_at": 1, "counts": 1, "scope": 1},
    ).sort("created_at", -1)
    return await cursor.to_list(100)
