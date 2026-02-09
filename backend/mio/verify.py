"""MIO Verification — complete MIO validation pipeline.

Runs all checks before allowing execution:
  1. Signature valid (ED25519)
  2. TTL not expired
  3. Replay not detected
  4. Touch correlation (Tier >= 2)
  5. Biometric proof (Tier 3)
  6. Presence fresh (heartbeat)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from mio.signer import verify_mio
from mio.ttl import is_expired, check_replay, record_usage, compute_token_hash
from presence.touch_correlation import validate_touch_token
from presence.heartbeat import check_presence
from schemas.mio import RiskTier

logger = logging.getLogger(__name__)


async def verify_mio_for_execution(
    mio_dict: dict,
    signature: str,
    session_id: str,
    device_id: str,
    tier: int,
    touch_token: Optional[str] = None,
    biometric_proof: Optional[str] = None,
) -> tuple[bool, str]:
    """Complete MIO verification pipeline.
    
    Returns (valid: bool, reason: str).
    """
    mio_id = mio_dict.get("header", {}).get("mio_id", "")

    # 1. Signature
    if not verify_mio(mio_dict, signature):
        return False, "MIO signature invalid"

    # 2. TTL
    created_str = mio_dict.get("header", {}).get("timestamp", "")
    ttl = mio_dict.get("header", {}).get("ttl_seconds", 120)
    try:
        created = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
        if is_expired(created, ttl):
            return False, f"MIO expired (TTL={ttl}s)"
    except Exception:
        return False, "Invalid MIO timestamp"

    # 3. Replay
    token_hash = compute_token_hash(mio_id, session_id, device_id)
    if await check_replay(token_hash):
        return False, "MIO replay detected"
    await record_usage(token_hash)

    # 4. Presence
    if not await check_presence(session_id):
        return False, "Heartbeat stale"

    # 5. Touch correlation (Tier >= 2)
    if tier >= RiskTier.PHYSICAL_LATCH.value:
        valid, reason = await validate_touch_token(touch_token or "", session_id, device_id)
        if not valid:
            return False, f"Touch correlation failed: {reason}"

    # 6. Biometric (Tier 3)
    if tier >= RiskTier.BIOMETRIC.value:
        if not biometric_proof:
            return False, "Biometric proof required for Tier 3"
        # TODO: Verify OS-level biometric proof
        logger.info("[MIOVerify] Biometric proof accepted (stub): session=%s", session_id)

    logger.info(
        "[MIOVerify] PASSED: mio=%s session=%s tier=%d",
        mio_id[:12], session_id, tier,
    )
    return True, "MIO verified"
