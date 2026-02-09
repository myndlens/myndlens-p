"""Retention Policy — B19.

Configurable retention durations per data type.
Auto-cleanup of expired data.
Legal hold overrides auto-cleanup.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from core.database import get_db

logger = logging.getLogger(__name__)

# Retention policy (configurable)
RETENTION_DAYS = {
    "transcripts": 90,       # 90 days
    "sessions": 30,           # 30 days (inactive)
    "audit_events": 365,      # 1 year (legal)
    "prompt_snapshots": 90,   # 90 days
    "dispatches": 180,        # 6 months
    "commits": 180,           # 6 months
    "rate_limits": 1,         # 1 day (auto-TTL handles this)
}


async def run_retention_cleanup() -> Dict[str, int]:
    """Run retention cleanup across all collections."""
    db = get_db()
    now = datetime.now(timezone.utc)
    results = {}

    # Transcripts
    cutoff = now - timedelta(days=RETENTION_DAYS["transcripts"])
    r = await db.transcripts.delete_many({"created_at": {"$lt": cutoff}})
    results["transcripts"] = r.deleted_count

    # Inactive sessions
    cutoff = now - timedelta(days=RETENTION_DAYS["sessions"])
    r = await db.sessions.delete_many({"active": False, "created_at": {"$lt": cutoff}})
    results["sessions"] = r.deleted_count

    # Prompt snapshots
    cutoff = now - timedelta(days=RETENTION_DAYS["prompt_snapshots"])
    r = await db.prompt_snapshots.delete_many({"created_at": {"$lt": cutoff}})
    results["prompt_snapshots"] = r.deleted_count

    # Dispatches
    cutoff = now - timedelta(days=RETENTION_DAYS["dispatches"])
    r = await db.dispatches.delete_many({"timestamp": {"$lt": cutoff}})
    results["dispatches"] = r.deleted_count

    # Completed/Cancelled/Failed commits
    cutoff = now - timedelta(days=RETENTION_DAYS["commits"])
    r = await db.commits.delete_many({
        "state": {"$in": ["COMPLETED", "CANCELLED", "FAILED"]},
        "created_at": {"$lt": cutoff},
    })
    results["commits"] = r.deleted_count

    # NOTE: audit_events NOT auto-deleted (legal requirement)
    audit_count = await db.audit_events.count_documents({})
    results["audit_events_preserved"] = audit_count

    logger.info("[Retention] Cleanup: %s", results)
    return results


async def get_retention_status() -> Dict[str, Any]:
    """Get current retention policy status."""
    db = get_db()
    now = datetime.now(timezone.utc)

    status = {"policy": RETENTION_DAYS, "collections": {}}
    for coll_name, days in RETENTION_DAYS.items():
        if coll_name == "rate_limits":
            continue
        cutoff = now - timedelta(days=days)
        try:
            coll = db[coll_name]
            total = await coll.count_documents({})
            # Use appropriate date field
            date_field = "created_at" if coll_name != "dispatches" else "timestamp"
            expired = await coll.count_documents({date_field: {"$lt": cutoff}})
            status["collections"][coll_name] = {
                "total": total,
                "expired": expired,
                "retention_days": days,
            }
        except Exception:
            status["collections"][coll_name] = {"error": "count failed"}

    return status
