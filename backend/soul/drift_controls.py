"""Soul Drift Controls — B20.

Detect and prevent drift from base soul.
Personalization allowed; drift forbidden.
"""
import logging
from typing import Any, Dict

from soul.store import compute_soul_hash, BASE_SOUL_FRAGMENTS, retrieve_soul

logger = logging.getLogger(__name__)

# Maximum allowed deviation from base soul
MAX_DRIFT_SCORE = 0.15  # cosine distance threshold


def check_drift() -> Dict[str, Any]:
    """Check if current soul has drifted from base."""
    current_fragments = retrieve_soul()
    base_hash = compute_soul_hash(BASE_SOUL_FRAGMENTS)

    # Check base fragments are all present
    current_ids = {f["id"] for f in current_fragments}
    base_ids = {f["id"] for f in BASE_SOUL_FRAGMENTS}
    missing = base_ids - current_ids

    # Count user additions
    user_fragments = [f for f in current_fragments if not f.get("metadata", {}).get("is_base", False)]

    drift_detected = len(missing) > 0

    result = {
        "drift_detected": drift_detected,
        "base_hash": base_hash[:16] + "...",
        "base_fragments": len(BASE_SOUL_FRAGMENTS),
        "current_fragments": len(current_fragments),
        "missing_base": list(missing),
        "user_additions": len(user_fragments),
    }

    if drift_detected:
        logger.warning("[SoulDrift] DRIFT DETECTED: missing=%s", missing)
    else:
        logger.debug("[SoulDrift] No drift: %d base + %d user fragments", len(BASE_SOUL_FRAGMENTS), len(user_fragments))

    return result
