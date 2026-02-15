"""Prompt Analytics — aggregation queries for optimization insights.

Provides metrics on prompt accuracy, section effectiveness, and
purpose-level performance to drive the learning engine.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from core.database import get_db

logger = logging.getLogger(__name__)


async def get_purpose_accuracy(
    purpose: str,
    days: int = 30,
) -> Dict[str, Any]:
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"purpose": purpose, "created_at": {"$gte": since}}},
        {"$group": {
            "_id": "$purpose",
            "total": {"$sum": 1},
            "avg_accuracy": {"$avg": "$accuracy_score"},
            "success_count": {"$sum": {"$cond": [{"$eq": ["$result", "SUCCESS"]}, 1, 0]}},
            "correction_count": {"$sum": {"$cond": ["$user_corrected", 1, 0]}},
            "avg_latency": {"$avg": "$latency_ms"},
            "avg_tokens": {"$avg": "$tokens_used"},
        }},
    ]
    results = await db.prompt_outcomes.aggregate(pipeline).to_list(1)
    if not results:
        return {"purpose": purpose, "total": 0, "avg_accuracy": 0, "success_rate": 0}
    r = results[0]
    return {
        "purpose": purpose,
        "total": r["total"],
        "avg_accuracy": round(r.get("avg_accuracy", 0), 3),
        "success_rate": round(r["success_count"] / r["total"], 3) if r["total"] else 0,
        "correction_rate": round(r["correction_count"] / r["total"], 3) if r["total"] else 0,
        "avg_latency_ms": round(r.get("avg_latency", 0), 1),
        "avg_tokens": round(r.get("avg_tokens", 0)),
    }


async def get_section_effectiveness(days: int = 30) -> List[Dict[str, Any]]:
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$unwind": "$sections_used"},
        {"$group": {
            "_id": "$sections_used",
            "total_uses": {"$sum": 1},
            "avg_accuracy_with": {"$avg": "$accuracy_score"},
            "success_with": {"$sum": {"$cond": [{"$eq": ["$result", "SUCCESS"]}, 1, 0]}},
        }},
        {"$sort": {"avg_accuracy_with": -1}},
    ]
    results = await db.prompt_outcomes.aggregate(pipeline).to_list(50)
    return [
        {
            "section": r["_id"],
            "total_uses": r["total_uses"],
            "avg_accuracy": round(r.get("avg_accuracy_with", 0), 3),
            "success_rate": round(r["success_with"] / r["total_uses"], 3) if r["total_uses"] else 0,
        }
        for r in results
    ]


async def get_optimization_insights(days: int = 30) -> Dict[str, Any]:
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Overall stats
    total = await db.prompt_outcomes.count_documents({"created_at": {"$gte": since}})
    corrections = await db.user_corrections.count_documents({"created_at": {"$gte": since}})

    # Per-purpose breakdown
    purpose_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": "$purpose",
            "count": {"$sum": 1},
            "avg_accuracy": {"$avg": "$accuracy_score"},
            "corrections": {"$sum": {"$cond": ["$user_corrected", 1, 0]}},
        }},
        {"$sort": {"avg_accuracy": 1}},
    ]
    purposes = await db.prompt_outcomes.aggregate(purpose_pipeline).to_list(20)

    # Find struggling purposes
    struggling = [p for p in purposes if p.get("avg_accuracy", 0) < 0.7]

    return {
        "period_days": days,
        "total_outcomes": total,
        "total_corrections": corrections,
        "correction_rate": round(corrections / total, 3) if total else 0,
        "purposes": [
            {
                "purpose": p["_id"],
                "count": p["count"],
                "avg_accuracy": round(p.get("avg_accuracy", 0), 3),
                "correction_rate": round(p["corrections"] / p["count"], 3) if p["count"] else 0,
            }
            for p in purposes
        ],
        "struggling_purposes": [p["_id"] for p in struggling],
    }
