"""Per-User Optimization Profiles — personalized prompt tuning.

Learns from each user's interaction patterns to optimize prompt
behavior: section preferences, token budgets, communication style,
and accuracy thresholds.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from core.database import get_db

logger = logging.getLogger(__name__)


DEFAULT_PROFILE = {
    "token_budget_modifier": 1.0,
    "verbosity": "normal",
    "preferred_sections": [],
    "excluded_sections": [],
    "accuracy_threshold": 0.7,
    "correction_sensitivity": "medium",
    "communication_style": "",
    "expertise_level": "intermediate",
    "interaction_count": 0,
    "last_accuracy": 0.0,
}


async def get_user_profile(user_id: str) -> Dict[str, Any]:
    """Get the optimization profile for a user. Creates default if none exists."""
    db = get_db()
    doc = await db.user_profiles.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return {"user_id": user_id, **DEFAULT_PROFILE}
    return doc


async def update_user_profile(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update specific fields of a user's optimization profile."""
    db = get_db()
    updates["updated_at"] = datetime.now(timezone.utc)

    await db.user_profiles.update_one(
        {"user_id": user_id},
        {"$set": updates, "$setOnInsert": {"user_id": user_id, "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    doc = await db.user_profiles.find_one({"user_id": user_id}, {"_id": 0})
    logger.info("User profile updated: user=%s fields=%s", user_id, list(updates.keys()))
    return doc


async def learn_from_outcomes(user_id: str, days: int = 30) -> Dict[str, Any]:
    """Analyze a user's outcome data and generate profile recommendations."""
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    pipeline = [
        {"$match": {"user_id": user_id, "created_at": {"$gte": since}}},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "avg_accuracy": {"$avg": "$accuracy_score"},
            "avg_latency": {"$avg": "$latency_ms"},
            "avg_tokens": {"$avg": "$tokens_used"},
            "corrections": {"$sum": {"$cond": ["$user_corrected", 1, 0]}},
        }},
    ]
    results = await db.prompt_outcomes.aggregate(pipeline).to_list(1)

    if not results:
        return {"user_id": user_id, "recommendations": [], "data_points": 0}

    stats = results[0]
    total = stats["total"]
    avg_acc = stats.get("avg_accuracy", 0)
    correction_rate = stats["corrections"] / total if total else 0

    recommendations = []
    profile_updates = {"interaction_count": total, "last_accuracy": round(avg_acc, 3)}

    # Verbosity adjustment
    if correction_rate > 0.3:
        recommendations.append({
            "field": "verbosity",
            "current": "normal",
            "suggested": "detailed",
            "reason": f"High correction rate ({correction_rate:.0%}) suggests more context needed",
        })
        profile_updates["verbosity"] = "detailed"

    # Token budget adjustment
    avg_tokens = stats.get("avg_tokens", 0)
    if avg_acc < 0.6 and avg_tokens < 3000:
        modifier = 1.3
        recommendations.append({
            "field": "token_budget_modifier",
            "current": 1.0,
            "suggested": modifier,
            "reason": f"Low accuracy ({avg_acc:.2f}) with low token usage — increase budget",
        })
        profile_updates["token_budget_modifier"] = modifier
    elif avg_acc > 0.9 and avg_tokens > 5000:
        modifier = 0.8
        recommendations.append({
            "field": "token_budget_modifier",
            "current": 1.0,
            "suggested": modifier,
            "reason": f"High accuracy ({avg_acc:.2f}) with high tokens — reduce for efficiency",
        })
        profile_updates["token_budget_modifier"] = modifier

    # Expertise level
    if total > 50 and avg_acc > 0.85:
        profile_updates["expertise_level"] = "advanced"
        recommendations.append({
            "field": "expertise_level",
            "current": "intermediate",
            "suggested": "advanced",
            "reason": f"High accuracy ({avg_acc:.2f}) over {total} interactions",
        })
    elif total < 10:
        profile_updates["expertise_level"] = "beginner"

    # Section effectiveness per user
    section_pipeline = [
        {"$match": {"user_id": user_id, "created_at": {"$gte": since}}},
        {"$unwind": "$sections_used"},
        {"$group": {
            "_id": "$sections_used",
            "uses": {"$sum": 1},
            "avg_acc": {"$avg": "$accuracy_score"},
        }},
        {"$sort": {"avg_acc": -1}},
    ]
    sections = await db.prompt_outcomes.aggregate(section_pipeline).to_list(20)

    preferred = [s["_id"] for s in sections if s.get("avg_acc", 0) > 0.8 and s["uses"] >= 3]
    weak = [s["_id"] for s in sections if s.get("avg_acc", 0) < 0.5 and s["uses"] >= 3]

    if preferred:
        profile_updates["preferred_sections"] = preferred
    if weak:
        recommendations.append({
            "field": "section_review",
            "sections": weak,
            "reason": "These sections have low accuracy for this user",
        })

    # Apply updates
    if profile_updates:
        await update_user_profile(user_id, profile_updates)

    logger.info(
        "User optimization: user=%s points=%d accuracy=%.2f recommendations=%d",
        user_id, total, avg_acc, len(recommendations),
    )

    return {
        "user_id": user_id,
        "data_points": total,
        "avg_accuracy": round(avg_acc, 3),
        "correction_rate": round(correction_rate, 3),
        "recommendations": recommendations,
        "profile_updates_applied": list(profile_updates.keys()),
    }


async def get_prompt_adjustments(user_id: str) -> Dict[str, Any]:
    """Get prompt adjustments to apply for a specific user.

    Called by the orchestrator to personalize prompt construction.
    """
    profile = await get_user_profile(user_id)
    return {
        "token_budget_modifier": profile.get("token_budget_modifier", 1.0),
        "verbosity": profile.get("verbosity", "normal"),
        "preferred_sections": profile.get("preferred_sections", []),
        "excluded_sections": profile.get("excluded_sections", []),
        "expertise_level": profile.get("expertise_level", "intermediate"),
    }
