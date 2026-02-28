"""Durable mandate lifecycle store (H1).

Persists pending mandates to MongoDB with state machine transitions.
Replaces the process-local _pending_mandates dict for crash safety.
"""
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from core.database import get_db

logger = logging.getLogger(__name__)


class MandateState(str, Enum):
    DIMENSIONS_EXTRACTED = "DIMENSIONS_EXTRACTED"
    GUARDRAILS_PASSED = "GUARDRAILS_PASSED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    PROVISIONING = "PROVISIONING"
    DISPATCHED = "DISPATCHED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


_VALID_TRANSITIONS = {
    MandateState.DIMENSIONS_EXTRACTED: {MandateState.GUARDRAILS_PASSED, MandateState.APPROVAL_PENDING, MandateState.FAILED},
    MandateState.GUARDRAILS_PASSED: {MandateState.APPROVAL_PENDING, MandateState.FAILED},
    MandateState.APPROVAL_PENDING: {MandateState.APPROVED, MandateState.FAILED},
    MandateState.APPROVED: {MandateState.PROVISIONING, MandateState.FAILED},
    MandateState.PROVISIONING: {MandateState.DISPATCHED, MandateState.FAILED},
    MandateState.DISPATCHED: {MandateState.COMPLETED, MandateState.FAILED},
}


async def save_mandate(
    draft_id: str,
    mandate_data: dict,
    state: MandateState,
    session_id: str,
    user_id: str,
    cycle_id: str = "",
) -> None:
    """Persist or update a mandate. Idempotent upsert keyed on draft_id."""
    db = get_db()
    now = datetime.now(timezone.utc)
    clean_data = {k: v for k, v in mandate_data.items() if not k.startswith("_")} if mandate_data else {}
    doc = {
        "draft_id": draft_id,
        "state": state.value,
        "session_id": session_id,
        "user_id": user_id,
        "cycle_id": cycle_id,
        "mandate_data": clean_data,
        "updated_at": now,
    }
    await db.pending_mandates.update_one(
        {"draft_id": draft_id},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    logger.info("[MANDATE_STORE] saved draft=%s state=%s cycle=%s", draft_id, state.value, cycle_id[:12])


async def get_mandate(draft_id: str) -> Optional[dict]:
    """Retrieve a pending mandate by draft_id. Returns mandate_data dict or None."""
    db = get_db()
    doc = await db.pending_mandates.find_one({"draft_id": draft_id}, {"_id": 0})
    if not doc:
        return None
    result = dict(doc.get("mandate_data", {}))
    result["_session_id"] = doc.get("session_id", "")
    result["_user_id"] = doc.get("user_id", "")
    result["_created_at"] = doc.get("created_at", "")
    result["_state"] = doc.get("state", "")
    result["_cycle_id"] = doc.get("cycle_id", "")
    return result


async def transition_state(draft_id: str, new_state: MandateState) -> bool:
    """Transition mandate to a new state with validation."""
    db = get_db()
    doc = await db.pending_mandates.find_one({"draft_id": draft_id}, {"_id": 0, "state": 1})
    if not doc:
        logger.warning("[MANDATE_STORE] transition failed: draft=%s not found", draft_id)
        return False

    current = MandateState(doc["state"])
    allowed = _VALID_TRANSITIONS.get(current, set())
    if new_state not in allowed:
        logger.warning(
            "[MANDATE_STORE] invalid transition: draft=%s %s -> %s",
            draft_id, current.value, new_state.value,
        )
        return False

    await db.pending_mandates.update_one(
        {"draft_id": draft_id},
        {"$set": {"state": new_state.value, "updated_at": datetime.now(timezone.utc)}},
    )
    logger.info("[MANDATE_STORE] transition draft=%s %s -> %s", draft_id, current.value, new_state.value)
    return True


async def delete_mandate(draft_id: str) -> None:
    """Remove a mandate after successful dispatch."""
    db = get_db()
    await db.pending_mandates.delete_one({"draft_id": draft_id})
    logger.info("[MANDATE_STORE] deleted draft=%s", draft_id)


async def cleanup_session_mandates(session_id: str) -> int:
    """Remove non-resumable mandates for a session (disconnect cleanup).

    Mandates in APPROVAL_PENDING, DIMENSIONS_EXTRACTED, or GUARDRAILS_PASSED
    are kept — they can be resumed on reconnect via get_pending_for_user().
    """
    db = get_db()
    resumable = [
        MandateState.APPROVAL_PENDING.value,
        MandateState.DIMENSIONS_EXTRACTED.value,
        MandateState.GUARDRAILS_PASSED.value,
    ]
    result = await db.pending_mandates.delete_many({
        "session_id": session_id,
        "state": {"$nin": resumable},
    })
    if result.deleted_count:
        logger.info("[MANDATE_STORE] cleaned %d non-resumable mandates for session=%s", result.deleted_count, session_id)
    return result.deleted_count


async def get_pending_for_user(user_id: str) -> Optional[dict]:
    """Find the most recent resumable mandate for a user (survives reconnect).

    Returns the full DB doc (not just mandate_data) so the caller can
    restore session state from it. Returns None if nothing resumable.
    """
    db = get_db()
    resumable_states = [
        MandateState.APPROVAL_PENDING.value,
        MandateState.DIMENSIONS_EXTRACTED.value,
        MandateState.GUARDRAILS_PASSED.value,
    ]
    doc = await db.pending_mandates.find_one(
        {"user_id": user_id, "state": {"$in": resumable_states}},
        {"_id": 0},
        sort=[("updated_at", -1)],
    )
    return doc
