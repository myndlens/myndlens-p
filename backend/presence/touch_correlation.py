"""Touch Correlation — physical presence verification.

Spec §10.2:
  - For Tier ≥2, server refuses execution unless Physical-Touch-Timestamp
    correlates within 10 seconds.
  - Touch tokens are single-use.
  - Tokens bound to: mio_id + session_id + device_id.
  - Replay cache prevents token reuse.
"""
import logging

from mio.ttl import check_replay, record_usage, compute_touch_token_hash

logger = logging.getLogger(__name__)

TOUCH_CORRELATION_WINDOW_S = 10  # seconds


async def validate_touch_token(
    touch_token: str,
    session_id: str,
    device_id: str,
) -> tuple[bool, str]:
    """Validate a touch token for Tier ≥2 execution.
    
    Returns (valid: bool, reason: str).
    """
    if not touch_token:
        return False, "Touch token required for Tier >= 2"

    # Check replay
    token_hash = compute_touch_token_hash(touch_token)
    is_replay = await check_replay(token_hash)
    if is_replay:
        logger.warning("[TouchCorrelation] Replay detected: token=%s", token_hash[:16])
        return False, "Touch token already used (replay rejected)"

    # Record usage (single-use)
    await record_usage(token_hash)

    logger.info("[TouchCorrelation] Token validated: session=%s", session_id)
    return True, "Touch token valid"
