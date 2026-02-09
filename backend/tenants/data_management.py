"""Tenant Data Management — export/delete for deprovision.

Spec §18.3 + S3:
  - Support export on request
  - Support deletion on request
  - Preserve legally-required audit metadata
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from core.database import get_db

logger = logging.getLogger(__name__)


async def export_user_data(user_id: str) -> Dict[str, Any]:
    """Export all user data for GDPR/data rights compliance."""
    db = get_db()

    # Collect from all collections
    sessions = await db.sessions.find({"user_id": user_id}).to_list(1000)
    transcripts = await db.transcripts.find({"session_id": {"$in": [s["session_id"] for s in sessions]}}).to_list(1000)
    entities = await db.entity_registry.find({"user_id": user_id}).to_list(1000)
    graphs = await db.graphs.find({"user_id": user_id}).to_list(10)

    # Clean _id fields
    for collection in [sessions, transcripts, entities, graphs]:
        for doc in collection:
            doc.pop("_id", None)

    export = {
        "user_id": user_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "sessions": sessions,
        "transcripts": transcripts,
        "entities": entities,
        "graphs": graphs,
        "session_count": len(sessions),
        "transcript_count": len(transcripts),
    }

    logger.info(
        "[DataMgmt] Export: user=%s sessions=%d transcripts=%d entities=%d",
        user_id, len(sessions), len(transcripts), len(entities),
    )
    return export


async def delete_user_data(user_id: str, preserve_audit: bool = True) -> Dict[str, int]:
    """Delete all user data. Preserves audit metadata if required."""
    db = get_db()
    counts = {}

    # Get session IDs for cascade
    sessions = await db.sessions.find({"user_id": user_id}, {"session_id": 1}).to_list(1000)
    session_ids = [s["session_id"] for s in sessions]

    # Delete sessions
    r = await db.sessions.delete_many({"user_id": user_id})
    counts["sessions"] = r.deleted_count

    # Delete transcripts
    r = await db.transcripts.delete_many({"session_id": {"$in": session_ids}})
    counts["transcripts"] = r.deleted_count

    # Delete entity registry
    r = await db.entity_registry.delete_many({"user_id": user_id})
    counts["entities"] = r.deleted_count

    # Delete graphs
    r = await db.graphs.delete_many({"user_id": user_id})
    counts["graphs"] = r.deleted_count

    # Delete commits
    r = await db.commits.delete_many({"session_id": {"$in": session_ids}})
    counts["commits"] = r.deleted_count

    # Preserve audit events if legally required
    if not preserve_audit:
        r = await db.audit_events.delete_many({"user_id": user_id})
        counts["audit_events"] = r.deleted_count
    else:
        counts["audit_events_preserved"] = await db.audit_events.count_documents({"user_id": user_id})

    logger.info(
        "[DataMgmt] Delete: user=%s counts=%s preserve_audit=%s",
        user_id, counts, preserve_audit,
    )
    return counts


async def invalidate_user_sessions(user_id: str) -> int:
    """Invalidate all active sessions for a user."""
    db = get_db()
    r = await db.sessions.update_many(
        {"user_id": user_id, "active": True},
        {"$set": {"active": False}},
    )
    logger.info("[DataMgmt] Sessions invalidated: user=%s count=%d", user_id, r.modified_count)
    return r.modified_count


async def detach_device_bindings(user_id: str) -> int:
    """Detach all device bindings for a user."""
    # Sessions already invalidated above; this is for any additional device records
    return await invalidate_user_sessions(user_id)
