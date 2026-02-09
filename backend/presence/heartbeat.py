"""Heartbeat tracking — presence verification.

Mobile sends heartbeat every 5s.
BE refuses MIO generation if heartbeat lost > 15s.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from config.settings import get_settings
from core.database import get_db
from core.exceptions import PresenceError

logger = logging.getLogger(__name__)


async def record_heartbeat(session_id: str, seq: int, client_ts: Optional[datetime] = None) -> datetime:
    """Record a heartbeat for the given session. Returns server timestamp."""
    db = get_db()
    now = datetime.now(timezone.utc)

    result = await db.sessions.update_one(
        {"session_id": session_id, "active": True},
        {
            "$set": {
                "last_heartbeat_at": now,
                "heartbeat_seq": seq,
            }
        },
    )
    if result.matched_count == 0:
        raise PresenceError(f"No active session for heartbeat: {session_id}")

    logger.debug("Heartbeat recorded: session=%s seq=%d", session_id, seq)
    return now


async def check_presence(session_id: str) -> bool:
    """Check if session heartbeat is fresh (within HEARTBEAT_TIMEOUT_S).
    
    Returns True if presence is valid (fresh heartbeat).
    Returns False if heartbeat is stale or missing.
    """
    settings = get_settings()
    db = get_db()

    doc = await db.sessions.find_one(
        {"session_id": session_id, "active": True},
        {"last_heartbeat_at": 1},
    )

    if doc is None:
        logger.warning("Presence check: no active session %s", session_id)
        return False

    last_hb = doc.get("last_heartbeat_at")
    if last_hb is None:
        logger.warning("Presence check: no heartbeat ever received for session %s", session_id)
        return False

    # Ensure timezone-aware comparison
    if last_hb.tzinfo is None:
        last_hb = last_hb.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age_seconds = (now - last_hb).total_seconds()

    if age_seconds > settings.HEARTBEAT_TIMEOUT_S:
        logger.warning(
            "Presence STALE: session=%s age=%.1fs threshold=%ds",
            session_id, age_seconds, settings.HEARTBEAT_TIMEOUT_S,
        )
        return False

    logger.debug("Presence OK: session=%s age=%.1fs", session_id, age_seconds)
    return True


async def assert_presence(session_id: str) -> None:
    """Assert presence is valid. Raises PresenceError if stale."""
    if not await check_presence(session_id):
        raise PresenceError(
            f"Heartbeat stale for session {session_id}. "
            f"Execute blocked per presence policy (>{get_settings().HEARTBEAT_TIMEOUT_S}s)."
        )
