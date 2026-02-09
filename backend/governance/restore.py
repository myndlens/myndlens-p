"""Restore — B19.

Restore from backup snapshot.
Preserves provenance integrity.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from core.database import get_db

logger = logging.getLogger(__name__)


async def restore_from_backup(backup_id: str) -> Dict[str, Any]:
    """Restore a user's data from a backup snapshot.
    
    Provenance preservation:
      - All restored nodes keep their original provenance flags
      - Graph structure preserved via node_link_data format
      - Entity references preserved via canonical IDs
    """
    db = get_db()

    snapshot = await db.backups.find_one({"backup_id": backup_id})
    if not snapshot:
        raise ValueError(f"Backup not found: {backup_id}")

    user_id = snapshot["user_id"]
    data = snapshot["data"]
    counts = {}

    # Restore graphs (provenance preserved in node attributes)
    for graph_doc in data.get("graphs", []):
        await db.graphs.update_one(
            {"user_id": graph_doc["user_id"]},
            {"$set": graph_doc},
            upsert=True,
        )
    counts["graphs"] = len(data.get("graphs", []))

    # Restore entities (canonical IDs preserved)
    for entity_doc in data.get("entities", []):
        await db.entity_registry.update_one(
            {"user_id": entity_doc["user_id"], "canonical_id": entity_doc["canonical_id"]},
            {"$set": entity_doc},
            upsert=True,
        )
    counts["entities"] = len(data.get("entities", []))

    # Restore sessions
    for session_doc in data.get("sessions", []):
        await db.sessions.update_one(
            {"session_id": session_doc["session_id"]},
            {"$set": session_doc},
            upsert=True,
        )
    counts["sessions"] = len(data.get("sessions", []))

    # Restore transcripts
    for trans_doc in data.get("transcripts", []):
        await db.transcripts.update_one(
            {"session_id": trans_doc["session_id"]},
            {"$set": trans_doc},
            upsert=True,
        )
    counts["transcripts"] = len(data.get("transcripts", []))

    # Restore commits
    for commit_doc in data.get("commits", []):
        await db.commits.update_one(
            {"commit_id": commit_doc["commit_id"]},
            {"$set": commit_doc},
            upsert=True,
        )
    counts["commits"] = len(data.get("commits", []))

    # Restore audit events (append, never overwrite)
    for audit_doc in data.get("audit_events", []):
        existing = await db.audit_events.find_one({"event_id": audit_doc.get("event_id")})
        if not existing:
            await db.audit_events.insert_one(audit_doc)
    counts["audit_events"] = len(data.get("audit_events", []))

    logger.info(
        "[Restore] Complete: backup=%s user=%s counts=%s",
        backup_id[:12], user_id, counts,
    )

    return {
        "backup_id": backup_id,
        "user_id": user_id,
        "restored_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "provenance_preserved": True,
    }
