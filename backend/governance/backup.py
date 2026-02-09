"""Backup — B19.

Backup Digital Self (vector + graph), audit trails, and system state.
Stored as MongoDB snapshots.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid

from core.database import get_db

logger = logging.getLogger(__name__)


async def create_backup(user_id: str, include_audit: bool = True) -> Dict[str, Any]:
    """Create a backup snapshot for a user's data."""
    db = get_db()
    backup_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Collect data
    graphs = await db.graphs.find({"user_id": user_id}).to_list(100)
    entities = await db.entity_registry.find({"user_id": user_id}).to_list(1000)
    sessions = await db.sessions.find({"user_id": user_id}).to_list(1000)
    session_ids = [s["session_id"] for s in sessions]
    transcripts = await db.transcripts.find({"session_id": {"$in": session_ids}}).to_list(1000)
    commits = await db.commits.find({"session_id": {"$in": session_ids}}).to_list(1000)

    audit_events = []
    if include_audit:
        audit_events = await db.audit_events.find({"user_id": user_id}).to_list(10000)

    # Clean _id fields
    for collection in [graphs, entities, sessions, transcripts, commits, audit_events]:
        for doc in collection:
            doc.pop("_id", None)

    snapshot = {
        "backup_id": backup_id,
        "user_id": user_id,
        "created_at": now,
        "include_audit": include_audit,
        "data": {
            "graphs": graphs,
            "entities": entities,
            "sessions": sessions,
            "transcripts": transcripts,
            "commits": commits,
            "audit_events": audit_events,
        },
        "counts": {
            "graphs": len(graphs),
            "entities": len(entities),
            "sessions": len(sessions),
            "transcripts": len(transcripts),
            "commits": len(commits),
            "audit_events": len(audit_events),
        },
    }

    # Store snapshot
    await db.backups.insert_one(snapshot)

    logger.info(
        "[Backup] Created: id=%s user=%s counts=%s",
        backup_id[:12], user_id, snapshot["counts"],
    )

    return {
        "backup_id": backup_id,
        "user_id": user_id,
        "created_at": now.isoformat(),
        "counts": snapshot["counts"],
    }


async def list_backups(user_id: str) -> List[Dict[str, Any]]:
    """List all backups for a user."""
    db = get_db()
    cursor = db.backups.find(
        {"user_id": user_id},
        {"_id": 0, "backup_id": 1, "user_id": 1, "created_at": 1, "counts": 1},
    ).sort("created_at", -1)
    return await cursor.to_list(100)
