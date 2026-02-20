"""
Skills Reinforcement Learning -- Skills Library is a living document.

Inspired by the ClawHub `self-improving-agent` skill:
  ERRORS.md   → record_skill_outcome(outcome=FAILED, error_details={...})
  LEARNINGS.md → record_skill_outcome(outcome=COMPLETED, learnings={...})
  TOOLS.md    → promoted patterns after 3+ recurring failures

When a mandate executes, outcomes feed back into skill relevance scores.
COMPLETED -> skill gains relevance for this action_class pattern
FAILED    -> skill loses relevance, error details logged for diagnosis
PARTIAL   -> neutral, tracked for trend analysis

Called from the delivery webhook (ObeGee confirms execution outcome).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db

logger = logging.getLogger(__name__)

_OUTCOME_DELTA = {
    "COMPLETED": 0.08,
    "PARTIAL": 0.0,
    "FAILED": -0.12,
    "CANCELLED": -0.04,
}
_MIN_MODIFIER = 0.5
_MAX_MODIFIER = 2.5


async def record_skill_outcome(
    skill_names: List[str],
    intent: str,
    outcome: str,
    error_details: Optional[Dict[str, Any]] = None,
    learnings: Optional[Dict[str, Any]] = None,
) -> None:
    """Update skill relevance scores based on mandate execution outcome.

    error_details: {"error_type": "...", "error_message": "...", "suggested_fix": "..."}
    learnings: {"category": "best_practice|correction|knowledge_gap", "note": "..."}

    These mirror the self-improving-agent ERRORS.md / LEARNINGS.md pattern.
    Recurring errors (3+ occurrences of same error_type) are flagged for TOOLS.md promotion.
    """
    db = get_db()
    delta = _OUTCOME_DELTA.get(outcome.upper(), 0.0)
    now = datetime.now(timezone.utc)

    for name in skill_names:
        if not name:
            continue

        # M1 fix: match by slug OR name — new skills have slug, old skills have name only
        skill_filter = {"$or": [{"slug": name}, {"name": name}]}

        usage_entry: Dict[str, Any] = {
            "intent": intent[:60],
            "outcome": outcome,
            "ts": now,
        }

        # Attach error details (self-improving-agent ERRORS.md pattern)
        if error_details and outcome.upper() == "FAILED":
            usage_entry["error"] = {
                "type": error_details.get("error_type", "unknown"),
                "message": error_details.get("error_message", "")[:200],
                "suggested_fix": error_details.get("suggested_fix", ""),
            }
            logger.info(
                "[SkillRL] FAILURE logged: skill=%s error_type=%s",
                name, error_details.get("error_type"),
            )

        # Attach learnings (self-improving-agent LEARNINGS.md pattern)
        if learnings and outcome.upper() == "COMPLETED":
            usage_entry["learning"] = {
                "category": learnings.get("category", "best_practice"),
                "note": learnings.get("note", "")[:300],
            }

        # Atomic relevance_modifier update + usage log
        await db.skills_library.update_one(
            skill_filter,
            [
                {
                    "$set": {
                        "relevance_modifier": {
                            "$max": [_MIN_MODIFIER, {
                                "$min": [_MAX_MODIFIER, {
                                    "$add": [{"$ifNull": ["$relevance_modifier", 1.0]}, delta]
                                }]
                            }]
                        },
                        "last_used": now,
                    }
                },
            ],
        )
        await db.skills_library.update_one(
            skill_filter,
            {
                "$inc": {f"outcomes.{outcome.lower()}": 1},
                "$push": {
                    "usage_log": {
                        "$each": [usage_entry],
                        "$slice": -100,   # keep last 100 (up from 50 for richer history)
                    }
                },
            },
        )

        # Check for recurring errors — flag if same error_type appeared 3+ times
        if error_details and outcome.upper() == "FAILED":
            await _check_recurring_failure(db, name, error_details.get("error_type", "unknown"))

        logger.info("[SkillRL] skill=%s outcome=%s delta=%.2f", name, outcome, delta)


async def _check_recurring_failure(db: Any, skill_name: str, error_type: str) -> None:
    """Flag skills with 3+ recurring errors of the same type for TOOLS.md promotion."""
    doc = await db.skills_library.find_one({"name": skill_name}, {"_id": 0, "usage_log": 1})
    if not doc:
        return
    recent = doc.get("usage_log", [])[-20:]
    same_error_count = sum(
        1 for e in recent
        if e.get("error", {}).get("type") == error_type
    )
    if same_error_count >= 3:
        logger.warning(
            "[SkillRL] RECURRING FAILURE: skill=%s error_type=%s count=%d — "
            "candidate for TOOLS.md promotion in self-improving-agent",
            skill_name, error_type, same_error_count,
        )
        await db.skills_library.update_one(
            {"name": skill_name},
            {"$addToSet": {"recurring_errors": error_type}},
        )


async def get_skill_stats(skill_name: str) -> dict:
    """Return outcome statistics for a skill."""
    db = get_db()
    doc = await db.skills_library.find_one(
        {"name": skill_name},
        {"_id": 0, "outcomes": 1, "relevance_modifier": 1, "last_used": 1, "recurring_errors": 1}
    )
    if not doc:
        return {}
    outcomes = doc.get("outcomes", {})
    total = sum(outcomes.values())
    return {
        "skill": skill_name,
        "relevance_modifier": doc.get("relevance_modifier", 1.0),
        "total_uses": total,
        "success_rate": round(outcomes.get("completed", 0) / total, 3) if total > 0 else 0.0,
        "outcomes": outcomes,
        "recurring_errors": doc.get("recurring_errors", []),
        "last_used": doc.get("last_used"),
    }
