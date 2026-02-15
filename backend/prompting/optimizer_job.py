"""Automated Optimization Job — scheduled background task for continuous improvement.

Runs periodically to:
  1. Compute per-purpose accuracy metrics
  2. Score section effectiveness
  3. Generate and apply policy recommendations
  4. Learn user profiles from recent outcomes
  5. Promote winning experiments
  6. Log run results to MongoDB
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from core.database import get_db

logger = logging.getLogger(__name__)

_running = False
_task = None
_last_run = None


async def run_optimization_cycle(days: int = 7) -> Dict[str, Any]:
    """Execute a single optimization cycle. Returns run report."""
    global _last_run
    db = get_db()
    start = datetime.now(timezone.utc)
    report = {
        "run_id": start.isoformat(),
        "started_at": start,
        "steps": {},
        "errors": [],
    }

    # Step 1: Purpose accuracy
    try:
        from prompting.analytics import get_optimization_insights
        insights = await get_optimization_insights(days)
        report["steps"]["insights"] = {
            "total_outcomes": insights.get("total_outcomes", 0),
            "struggling_purposes": insights.get("struggling_purposes", []),
        }
    except Exception as e:
        report["errors"].append(f"insights: {e}")

    # Step 2: Section effectiveness
    try:
        from prompting.analytics import get_section_effectiveness
        sections = await get_section_effectiveness(days)
        report["steps"]["section_scores"] = {
            "sections_analyzed": len(sections),
            "top_section": sections[0]["section"] if sections else None,
        }
    except Exception as e:
        report["errors"].append(f"sections: {e}")

    # Step 3: Policy recommendations
    try:
        from prompting.policy.adaptive import generate_policy_recommendations
        recs = await generate_policy_recommendations(days)
        report["steps"]["recommendations"] = {
            "count": len(recs),
            "high_priority": sum(1 for r in recs if r.get("priority") == "HIGH"),
        }
    except Exception as e:
        report["errors"].append(f"recommendations: {e}")

    # Step 4: User profile learning (top active users)
    try:
        from prompting.user_profiles import learn_from_outcomes
        since = datetime.now(timezone.utc) - timedelta(days=days)
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gte": 3}}},
            {"$sort": {"count": -1}},
            {"$limit": 20},
        ]
        active_users = await db.prompt_outcomes.aggregate(pipeline).to_list(20)
        users_updated = 0
        for u in active_users:
            uid = u["_id"]
            if uid and not uid.startswith("TEST_") and not uid.startswith("diagnostic"):
                await learn_from_outcomes(uid, days)
                users_updated += 1
        report["steps"]["user_learning"] = {
            "active_users_found": len(active_users),
            "profiles_updated": users_updated,
        }
    except Exception as e:
        report["errors"].append(f"user_learning: {e}")

    # Step 5: Experiment promotion
    try:
        promoted = 0
        experiments = await db.prompt_experiments.find({"status": "RUNNING"}).to_list(50)
        for exp in experiments:
            ctrl = exp.get("metrics", {}).get("control", {})
            var = exp.get("metrics", {}).get("variant", {})
            if ctrl.get("count", 0) >= 30 and var.get("count", 0) >= 30:
                ctrl_acc = ctrl.get("avg_accuracy", 0)
                var_acc = var.get("avg_accuracy", 0)
                if var_acc > ctrl_acc * 1.05:
                    await db.prompt_experiments.update_one(
                        {"experiment_id": exp["experiment_id"]},
                        {"$set": {"status": "VARIANT_WINS", "concluded_at": datetime.now(timezone.utc)}},
                    )
                    promoted += 1
                elif ctrl_acc >= var_acc:
                    await db.prompt_experiments.update_one(
                        {"experiment_id": exp["experiment_id"]},
                        {"$set": {"status": "CONTROL_WINS", "concluded_at": datetime.now(timezone.utc)}},
                    )
        report["steps"]["experiments"] = {
            "running": len(experiments),
            "promoted": promoted,
        }
    except Exception as e:
        report["errors"].append(f"experiments: {e}")

    # Finalize
    end = datetime.now(timezone.utc)
    report["completed_at"] = end
    report["duration_ms"] = (end - start).total_seconds() * 1000
    report["success"] = len(report["errors"]) == 0

    # Persist run
    await db.optimization_runs.insert_one(report)
    report.pop("_id", None)
    _last_run = report

    logger.info(
        "Optimization cycle complete: duration=%.0fms steps=%d errors=%d",
        report["duration_ms"], len(report["steps"]), len(report["errors"]),
    )
    return report


async def _scheduler_loop(interval_seconds: int):
    """Background loop that runs optimization at fixed intervals."""
    global _running
    logger.info("Optimization scheduler started: interval=%ds", interval_seconds)
    while _running:
        try:
            await run_optimization_cycle()
        except Exception as e:
            logger.error("Optimization cycle failed: %s", e)
        await asyncio.sleep(interval_seconds)
    logger.info("Optimization scheduler stopped")


def start_scheduler(interval_seconds: int = 3600):
    """Start the background optimization scheduler."""
    global _running, _task
    if _running:
        return {"status": "ALREADY_RUNNING"}
    _running = True
    _task = asyncio.create_task(_scheduler_loop(interval_seconds))
    logger.info("Optimization scheduler launched: interval=%ds", interval_seconds)
    return {"status": "STARTED", "interval_seconds": interval_seconds}


def stop_scheduler():
    """Stop the background optimization scheduler."""
    global _running, _task
    if not _running:
        return {"status": "NOT_RUNNING"}
    _running = False
    if _task:
        _task.cancel()
        _task = None
    logger.info("Optimization scheduler stopped")
    return {"status": "STOPPED"}


def get_scheduler_status() -> Dict[str, Any]:
    return {
        "running": _running,
        "last_run": _last_run.get("run_id") if _last_run else None,
        "last_success": _last_run.get("success") if _last_run else None,
        "last_duration_ms": _last_run.get("duration_ms") if _last_run else None,
    }


async def list_runs(limit: int = 10) -> list:
    db = get_db()
    cursor = db.optimization_runs.find(
        {}, {"_id": 0, "run_id": 1, "success": 1, "duration_ms": 1, "steps": 1, "errors": 1}
    ).sort("started_at", -1).limit(limit)
    return await cursor.to_list(limit)
