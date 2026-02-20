"""Commit State Machine — B11.

Durable server-side state machine for intent execution lifecycle.

States:
  DRAFT → PENDING_CONFIRMATION → CONFIRMED → DISPATCHING → COMPLETED
                             → CANCELLED
                             → FAILED

Rules:
  - Persisted durably to MongoDB (not in-memory only)
  - Exactly-once semantics via idempotency keys
  - State transitions are atomic and logged
  - Recovery on BE restart
"""
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from core.database import get_db

logger = logging.getLogger(__name__)


class CommitState(str, Enum):
    DRAFT = "DRAFT"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    DISPATCHING = "DISPATCHING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


# Valid transitions
_VALID_TRANSITIONS = {
    CommitState.DRAFT: {CommitState.PENDING_CONFIRMATION, CommitState.CANCELLED},
    CommitState.PENDING_CONFIRMATION: {CommitState.CONFIRMED, CommitState.CANCELLED},
    CommitState.CONFIRMED: {CommitState.DISPATCHING, CommitState.CANCELLED},
    CommitState.DISPATCHING: {CommitState.COMPLETED, CommitState.FAILED},
    CommitState.COMPLETED: set(),  # terminal
    CommitState.CANCELLED: set(),  # terminal
    CommitState.FAILED: {CommitState.DRAFT},  # can retry from DRAFT
}


async def create_commit(
    session_id: str,
    draft_id: str,
    intent_summary: str,
    intent: str,
    dimensions: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new commit in DRAFT state. Idempotent on idempotency_key."""
    db = get_db()
    idem_key = idempotency_key or f"{session_id}:{draft_id}"

    # Idempotency: check if commit already exists
    existing = await db.commits.find_one({"idempotency_key": idem_key})
    if existing:
        existing.pop("_id", None)
        logger.info("Commit exists (idempotent): key=%s state=%s", idem_key, existing["state"])
        return existing

    commit_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    doc = {
        "commit_id": commit_id,
        "session_id": session_id,
        "draft_id": draft_id,
        "idempotency_key": idem_key,
        "state": CommitState.DRAFT.value,
        "intent_summary": intent_summary,
        "intent": intent,
        "dimensions": dimensions or {},
        "created_at": now,
        "updated_at": now,
        "transitions": [
            {"from": None, "to": CommitState.DRAFT.value, "at": now, "reason": "created"},
        ],
    }

    await db.commits.insert_one(doc)
    logger.info("Commit created: id=%s session=%s draft=%s", commit_id, session_id, draft_id)
    return {k: v for k, v in doc.items() if k != "_id"}


async def transition(
    commit_id: str,
    to_state: CommitState,
    reason: str = "",
) -> Dict[str, Any]:
    """Atomically transition a commit to a new state."""
    db = get_db()
    doc = await db.commits.find_one({"commit_id": commit_id})
    if not doc:
        raise ValueError(f"Commit not found: {commit_id}")

    current = CommitState(doc["state"])
    valid_next = _VALID_TRANSITIONS.get(current, set())

    if to_state not in valid_next:
        raise ValueError(
            f"Invalid transition: {current.value} -> {to_state.value}. "
            f"Valid: {[s.value for s in valid_next]}"
        )

    now = datetime.now(timezone.utc)
    transition_entry = {
        "from": current.value,
        "to": to_state.value,
        "at": now,
        "reason": reason,
    }

    result = await db.commits.update_one(
        {"commit_id": commit_id, "state": current.value},  # optimistic lock
        {
            "$set": {"state": to_state.value, "updated_at": now},
            "$push": {"transitions": transition_entry},
        },
    )

    if result.modified_count == 0:
        raise ValueError(f"Concurrent modification on commit {commit_id}")

    logger.info(
        "Commit transition: id=%s %s -> %s reason=%s",
        commit_id, current.value, to_state.value, reason,
    )

    updated = await db.commits.find_one({"commit_id": commit_id})
    updated.pop("_id", None)
    return updated


async def get_commit(commit_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    doc = await db.commits.find_one({"commit_id": commit_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def get_session_commits(session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Return recent commits for a session. Capped at limit to prevent unbounded results."""
    db = get_db()
    cursor = db.commits.find({"session_id": session_id}).sort("created_at", -1).limit(limit)
    results = []
    async for doc in cursor:
        doc.pop("_id", None)
        results.append(doc)
    return results


async def recover_pending() -> List[Dict[str, Any]]:
    """Recovery on restart: find commits in non-terminal, non-DRAFT states."""
    db = get_db()
    cursor = db.commits.find({
        "state": {"$in": [
            CommitState.PENDING_CONFIRMATION.value,
            CommitState.CONFIRMED.value,
            CommitState.DISPATCHING.value,
        ]}
    })
    results = []
    async for doc in cursor:
        doc.pop("_id", None)
        results.append(doc)
        logger.warning(
            "Recovery: commit=%s state=%s session=%s",
            doc["commit_id"], doc["state"], doc["session_id"],
        )
    return results
