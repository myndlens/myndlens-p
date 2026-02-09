"""Audit logging — persists structured audit events to MongoDB."""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from core.database import get_db
from schemas.audit import AuditEvent, AuditEventType
from observability.redaction import redact_dict

logger = logging.getLogger(__name__)


async def log_audit_event(
    event_type: AuditEventType,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    env: str = "dev",
) -> str:
    """Create and persist an audit event. Returns event_id."""
    event = AuditEvent(
        event_type=event_type,
        session_id=session_id,
        user_id=user_id,
        details=details or {},
        env=env,
    )
    doc = event.to_doc()
    db = get_db()
    await db.audit_events.insert_one(doc)

    # Log with redacted details
    safe_details = redact_dict(details or {})
    logger.info(
        "AUDIT event=%s session=%s user=%s details=%s",
        event_type.value,
        session_id,
        user_id,
        safe_details,
    )
    return event.event_id
