"""Device binding — user-device-session linking.

Each session is bound to a specific user_id + device_id.
Reconnection requires re-validation.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
import uuid

from core.database import get_db
from core.exceptions import AuthError, SessionError
from schemas.session import Session

logger = logging.getLogger(__name__)


async def create_session(
    user_id: str,
    device_id: str,
    env: str = "dev",
    client_version: str = "1.0.0",
) -> Session:
    """Create a new session binding user+device."""
    db = get_db()

    # Invalidate any existing active sessions for this user+device
    await db.sessions.update_many(
        {"user_id": user_id, "device_id": device_id, "active": True},
        {"$set": {"active": False}},
    )

    session = Session(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        device_id=device_id,
        env=env,
        client_version=client_version,
        created_at=datetime.now(timezone.utc),
    )
    await db.sessions.insert_one(session.to_doc())
    logger.info(
        "Session created: session=%s user=%s device=%s",
        session.session_id, user_id, device_id,
    )
    return session


async def get_session(session_id: str) -> Optional[Session]:
    """Retrieve an active session."""
    db = get_db()
    doc = await db.sessions.find_one({"session_id": session_id, "active": True})
    if doc is None:
        return None
    doc.pop("_id", None)
    return Session(**doc)


async def terminate_session(session_id: str) -> None:
    """Mark a session as inactive."""
    db = get_db()
    result = await db.sessions.update_one(
        {"session_id": session_id},
        {"$set": {"active": False}},
    )
    if result.modified_count:
        logger.info("Session terminated: session=%s", session_id)
    else:
        logger.warning("Session not found for termination: session=%s", session_id)


async def validate_device_session(
    user_id: str,
    device_id: str,
    session_id: str,
) -> Session:
    """Validate that session matches user+device. Raises on mismatch."""
    session = await get_session(session_id)
    if session is None:
        raise SessionError(f"Session not found: {session_id}")
    if session.user_id != user_id:
        raise AuthError("Session user mismatch")
    if session.device_id != device_id:
        raise AuthError("Session device mismatch")
    return session
