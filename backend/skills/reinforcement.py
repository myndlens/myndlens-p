"""Skills Reinforcement Learning -- Skills Library is a living document.

When a mandate executes, outcomes feed back into skill relevance scores.
COMPLETED -> skill gains relevance for this action_class pattern
FAILED    -> skill loses relevance, flagged for review
PARTIAL   -> neutral, tracked for trend analysis

Called from the delivery webhook (ObeGee confirms execution outcome).
"""
import logging
from datetime import datetime, timezone
from typing import List

from core.database import get_db

logger = logging.getLogger(__name__)

# Outcome delta applied to relevance_modifier (capped 0.5 -- 2.5)
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
    action_class: str,
    outcome: str,
) -> None:
    """Update skill relevance scores based on mandate execution outcome."""
    db = get_db()
    delta = _OUTCOME_DELTA.get(outcome.upper(), 0.0)
    now = datetime.now(timezone.utc)

    for name in skill_names:
        if not name:
            continue
        # Atomic read-modify-write using MongoDB aggregation pipeline update.
        # Avoids race condition when two webhooks arrive simultaneously for the same skill.
        await db.skills_library.update_one(
            {"name": name},
            [
                {
                    "$set": {
                        "relevance_modifier": {
                            "$max": [
                                _MIN_MODIFIER,
                                {
                                    "$min": [
                                        _MAX_MODIFIER,
                                        {"$add": [{"$ifNull": ["$relevance_modifier", 1.0]}, delta]},
                                    ]
                                },
                            ]
                        },
                        "last_used": now,
                    }
                },
            ],
        )
        await db.skills_library.update_one(
            {"name": name},
            {
                "$inc": {f"outcomes.{outcome.lower()}": 1},
                "$push": {
                    "usage_log": {
                        "$each": [{"intent": intent[:60], "action_class": action_class, "outcome": outcome, "ts": now}],
                        "$slice": -50,
                    }
                },
            },
        )
        logger.info("[SkillRL] skill=%s outcome=%s delta=%.2f", name, outcome, delta)


async def get_skill_stats(skill_name: str) -> dict:
    """Return outcome statistics for a skill (for monitoring / library review)."""
    db = get_db()
    doc = await db.skills_library.find_one({"name": skill_name}, {"_id": 0, "outcomes": 1, "relevance_modifier": 1, "last_used": 1})
    if not doc:
        return {}
    outcomes = doc.get("outcomes", {})
    total = sum(outcomes.values())
    success_rate = outcomes.get("completed", 0) / total if total > 0 else 0.0
    return {
        "skill": skill_name,
        "relevance_modifier": doc.get("relevance_modifier", 1.0),
        "total_uses": total,
        "success_rate": round(success_rate, 3),
        "outcomes": outcomes,
        "last_used": doc.get("last_used"),
    }
