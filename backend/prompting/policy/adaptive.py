"""Adaptive Policy Engine — dynamically adjusts prompt policies based on outcome data.

Phase 3: Continuous optimization. Analyzes historical outcomes and
automatically suggests or applies policy adjustments.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from core.database import get_db

logger = logging.getLogger(__name__)


async def generate_policy_recommendations(days: int = 30) -> List[Dict[str, Any]]:
    """Analyze outcome data and generate policy adjustment recommendations."""
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    recommendations = []

    # Find purposes with low accuracy
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": "$purpose",
            "count": {"$sum": 1},
            "avg_accuracy": {"$avg": "$accuracy_score"},
            "avg_tokens": {"$avg": "$tokens_used"},
            "correction_rate": {"$avg": {"$cond": ["$user_corrected", 1, 0]}},
        }},
        {"$match": {"count": {"$gte": 5}}},
        {"$sort": {"avg_accuracy": 1}},
    ]
    purposes = await db.prompt_outcomes.aggregate(pipeline).to_list(20)

    for p in purposes:
        avg_acc = p.get("avg_accuracy", 0)
        correction_rate = p.get("correction_rate", 0)

        if avg_acc < 0.6:
            recommendations.append({
                "type": "INCREASE_CONTEXT",
                "purpose": p["_id"],
                "reason": f"Low accuracy ({avg_acc:.2f}) — suggest adding MEMORY_RECALL_SNIPPETS if not included",
                "priority": "HIGH",
                "suggested_action": "Add optional sections to required set",
            })

        if correction_rate > 0.3:
            recommendations.append({
                "type": "INCREASE_TOKEN_BUDGET",
                "purpose": p["_id"],
                "reason": f"High correction rate ({correction_rate:.2f}) — may need more context",
                "priority": "MEDIUM",
                "suggested_action": f"Increase token budget from current to {int(p.get('avg_tokens', 4096) * 1.5)}",
            })

    # Find underperforming sections
    section_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$unwind": "$sections_used"},
        {"$group": {
            "_id": "$sections_used",
            "count": {"$sum": 1},
            "avg_accuracy": {"$avg": "$accuracy_score"},
        }},
        {"$match": {"count": {"$gte": 10}, "avg_accuracy": {"$lt": 0.5}}},
    ]
    sections = await db.prompt_outcomes.aggregate(section_pipeline).to_list(20)

    for s in sections:
        recommendations.append({
            "type": "REVIEW_SECTION",
            "section": s["_id"],
            "reason": f"Section has low effectiveness ({s['avg_accuracy']:.2f} avg accuracy over {s['count']} uses)",
            "priority": "LOW",
            "suggested_action": "Review and potentially rewrite section generator",
        })

    logger.info("Generated %d policy recommendations", len(recommendations))
    return recommendations


async def get_adaptive_insights() -> Dict[str, Any]:
    """Get comprehensive adaptive policy insights."""
    recommendations = await generate_policy_recommendations()

    db = get_db()
    total_outcomes = await db.prompt_outcomes.count_documents({})
    total_corrections = await db.user_corrections.count_documents({})
    total_experiments = await db.prompt_experiments.count_documents({"status": "RUNNING"})

    return {
        "total_outcomes_tracked": total_outcomes,
        "total_user_corrections": total_corrections,
        "active_experiments": total_experiments,
        "recommendations": recommendations,
        "recommendation_count": len(recommendations),
        "system_health": "HEALTHY" if not any(r["priority"] == "HIGH" for r in recommendations) else "NEEDS_ATTENTION",
    }
