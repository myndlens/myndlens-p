"""Prompt Experiments — A/B testing framework for prompt variants.

Enables controlled experimentation to validate prompt improvements
before full deployment.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from core.database import get_db

logger = logging.getLogger(__name__)


async def create_experiment(data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    experiment = {
        "experiment_id": str(uuid.uuid4()),
        "name": data.get("name", "Unnamed"),
        "purpose": data.get("purpose", ""),
        "description": data.get("description", ""),
        "control": data.get("control", {}),
        "variant": data.get("variant", {}),
        "traffic_split": data.get("traffic_split", 0.1),
        "status": "RUNNING",
        "created_at": datetime.now(timezone.utc),
        "outcomes": {"control": [], "variant": []},
        "metrics": {"control": {"count": 0, "avg_accuracy": 0}, "variant": {"count": 0, "avg_accuracy": 0}},
    }
    await db.prompt_experiments.insert_one(experiment)
    experiment.pop("_id", None)
    logger.info("Experiment created: %s (%s)", experiment["experiment_id"], experiment["name"])
    return experiment


async def list_experiments() -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db.prompt_experiments.find({}, {"_id": 0}).sort("created_at", -1).limit(20)
    return await cursor.to_list(20)


async def get_experiment_results(experiment_id: str) -> Dict[str, Any]:
    db = get_db()
    exp = await db.prompt_experiments.find_one({"experiment_id": experiment_id}, {"_id": 0})
    if not exp:
        return {"error": "Experiment not found"}
    # Calculate significance
    ctrl = exp.get("metrics", {}).get("control", {})
    var = exp.get("metrics", {}).get("variant", {})
    ctrl_n = ctrl.get("count", 0)
    var_n = var.get("count", 0)
    significant = ctrl_n >= 30 and var_n >= 30
    winner = None
    if significant:
        ctrl_acc = ctrl.get("avg_accuracy", 0)
        var_acc = var.get("avg_accuracy", 0)
        if var_acc > ctrl_acc * 1.05:
            winner = "variant"
        elif ctrl_acc > var_acc * 1.05:
            winner = "control"
    exp["analysis"] = {
        "significant": significant,
        "winner": winner,
        "control_samples": ctrl_n,
        "variant_samples": var_n,
    }
    return exp


async def assign_variant(experiment_id: str, session_id: str) -> str:
    """Assign a session to control or variant."""
    db = get_db()
    exp = await db.prompt_experiments.find_one({"experiment_id": experiment_id})
    if not exp or exp.get("status") != "RUNNING":
        return "control"
    # Deterministic assignment based on session hash
    split = exp.get("traffic_split", 0.1)
    h = hash(session_id) % 100
    return "variant" if h < split * 100 else "control"


async def record_experiment_outcome(
    experiment_id: str,
    group: str,
    accuracy: float,
) -> None:
    db = get_db()
    await db.prompt_experiments.update_one(
        {"experiment_id": experiment_id},
        {
            "$push": {f"outcomes.{group}": accuracy},
            "$inc": {f"metrics.{group}.count": 1},
        },
    )
    # Recalculate average
    exp = await db.prompt_experiments.find_one({"experiment_id": experiment_id})
    if exp:
        outcomes = exp.get("outcomes", {}).get(group, [])
        if outcomes:
            avg = sum(outcomes) / len(outcomes)
            await db.prompt_experiments.update_one(
                {"experiment_id": experiment_id},
                {"$set": {f"metrics.{group}.avg_accuracy": round(avg, 4)}},
            )
