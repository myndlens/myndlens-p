"""Rate Limiter — B17.

Per user/device/tenant rate limits.
Uses MongoDB for distributed state with TTL cleanup.

Limits:
  - WS messages per minute per session
  - Execute requests per hour per user
  - Audio chunks per second per session
  - API calls per minute per tenant
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.database import get_db

logger = logging.getLogger(__name__)


# Rate limit configurations
LIMITS = {
    "ws_messages": {"max": 120, "window_seconds": 60},       # 120 msgs/min
    "execute_requests": {"max": 30, "window_seconds": 3600},  # 30 executes/hour
    "audio_chunks": {"max": 10, "window_seconds": 1},         # 10 chunks/sec
    "api_calls": {"max": 300, "window_seconds": 60},           # 300 calls/min
    "auth_attempts": {"max": 10, "window_seconds": 300},       # 10 auth attempts/5min
}


async def check_rate_limit(
    key: str,
    limit_type: str,
) -> tuple[bool, Optional[str]]:
    """Check if a rate limit is exceeded.
    
    Args:
        key: Unique key (e.g., user_id, session_id, tenant_id)
        limit_type: One of the LIMITS keys
    
    Returns:
        (allowed: bool, reason: str | None)
    """
    config = LIMITS.get(limit_type)
    if not config:
        return True, None  # Unknown limit type = allow

    db = get_db()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=config["window_seconds"])
    bucket_key = f"rl:{limit_type}:{key}"

    # Count events in window
    count = await db.rate_limits.count_documents({
        "bucket": bucket_key,
        "timestamp": {"$gte": window_start},
    })

    if count >= config["max"]:
        logger.warning(
            "RATE_LIMITED: type=%s key=%s count=%d max=%d",
            limit_type, key[:20], count, config["max"],
        )
        return False, f"Rate limit exceeded: {limit_type} ({count}/{config['max']} in {config['window_seconds']}s)"

    # Record event
    await db.rate_limits.insert_one({
        "bucket": bucket_key,
        "timestamp": now,
        "expires_at": now + timedelta(seconds=config["window_seconds"] * 2),
    })

    return True, None


async def get_rate_status(key: str, limit_type: str) -> dict:
    """Get current rate limit status."""
    config = LIMITS.get(limit_type, {})
    if not config:
        return {"limit_type": limit_type, "error": "unknown"}

    db = get_db()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=config["window_seconds"])
    bucket_key = f"rl:{limit_type}:{key}"

    count = await db.rate_limits.count_documents({
        "bucket": bucket_key,
        "timestamp": {"$gte": window_start},
    })

    return {
        "limit_type": limit_type,
        "key": key[:20],
        "current": count,
        "max": config["max"],
        "window_seconds": config["window_seconds"],
        "remaining": max(0, config["max"] - count),
    }
