"""MIO TTL + Replay Protection.

Spec §9.3:
  - TTL is SHORT (120 seconds default)
  - Replay cache enforced server-side
  - Touch tokens are single-use
  - Tokens bound to: mio_id + session_id + device_id
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from config.settings import get_settings
from core.database import get_db

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 120


def is_expired(created_at: datetime, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    """Check if a MIO has expired."""
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age = (now - created_at).total_seconds()
    return age > ttl_seconds


async def check_replay(token_hash: str) -> bool:
    """Check if a token/MIO has been used before. Returns True if replay detected."""
    db = get_db()
    existing = await db.replay_cache.find_one({"token_hash": token_hash})
    return existing is not None


async def record_usage(token_hash: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
    """Record a token/MIO usage in the replay cache."""
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.replay_cache.insert_one({
        "token_hash": token_hash,
        "used_at": now,
        "expires_at": now + timedelta(seconds=ttl_seconds * 2),  # Keep longer than TTL
    })
    logger.debug("[Replay] Token recorded: hash=%s", token_hash[:16])


def compute_token_hash(mio_id: str, session_id: str, device_id: str) -> str:
    """Compute a unique hash for replay detection."""
    combined = f"{mio_id}:{session_id}:{device_id}"
    return hashlib.sha256(combined.encode()).hexdigest()


def compute_touch_token_hash(touch_token: str) -> str:
    """Hash a touch token for replay cache."""
    return hashlib.sha256(touch_token.encode()).hexdigest()
