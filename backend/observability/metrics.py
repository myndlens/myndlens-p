"""Observability Metrics — B16 full.

Tiered logging: system metrics vs audit events.
Structured metrics for monitoring.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from core.database import get_db
from abuse.circuit_breakers import get_all_breaker_statuses
from gateway.ws_server import get_active_session_count

logger = logging.getLogger(__name__)


async def get_system_metrics() -> Dict[str, Any]:
    """Collect system-wide metrics."""
    db = get_db()

    # Collection counts
    sessions_active = await db.sessions.count_documents({"active": True})
    sessions_total = await db.sessions.count_documents({})
    tenants_active = await db.tenants.count_documents({"status": "ACTIVE"})
    tenants_total = await db.tenants.count_documents({})
    commits_pending = await db.commits.count_documents({"state": {"$in": ["DRAFT", "PENDING_CONFIRMATION", "CONFIRMED"]}})
    dispatches_total = await db.dispatches.count_documents({})
    audit_total = await db.audit_events.count_documents({})
    prompt_snapshots = await db.prompt_snapshots.count_documents({})
    bypass_attempts = await db.audit_events.count_documents({"event_type": "prompt_bypass_attempt"})

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ws_connections": get_active_session_count(),
        "sessions": {"active": sessions_active, "total": sessions_total},
        "tenants": {"active": tenants_active, "total": tenants_total},
        "commits": {"pending": commits_pending},
        "dispatches": {"total": dispatches_total},
        "audit_events": {"total": audit_total},
        "prompt_system": {
            "snapshots": prompt_snapshots,
            "bypass_attempts": bypass_attempts,
        },
        "circuit_breakers": get_all_breaker_statuses(),
    }
