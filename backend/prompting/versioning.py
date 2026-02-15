"""Prompt Versioning — version control for prompt configurations with rollback.

Every policy change, section update, or configuration modification is
tracked as a version. Rollback restores a previous version as active.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db

logger = logging.getLogger(__name__)


async def create_version(
    purpose: str,
    config: Dict[str, Any],
    author: str = "system",
    change_description: str = "",
) -> Dict[str, Any]:
    """Create a new version of a prompt configuration for a given purpose."""
    db = get_db()

    # Get current latest version number
    latest = await db.prompt_versions.find_one(
        {"purpose": purpose},
        sort=[("version", -1)],
    )
    version_num = (latest["version"] + 1) if latest else 1

    doc = {
        "version_id": str(uuid.uuid4()),
        "purpose": purpose,
        "version": version_num,
        "config": config,
        "author": author,
        "change_description": change_description,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "stable_hash": _hash_config(config),
    }

    # Deactivate previous active version
    await db.prompt_versions.update_many(
        {"purpose": purpose, "is_active": True},
        {"$set": {"is_active": False}},
    )

    await db.prompt_versions.insert_one(doc)
    doc.pop("_id", None)

    logger.info(
        "Prompt version created: purpose=%s v%d hash=%s by=%s",
        purpose, version_num, doc["stable_hash"][:12], author,
    )
    return doc


async def get_active_version(purpose: str) -> Optional[Dict[str, Any]]:
    """Get the currently active version for a purpose."""
    db = get_db()
    doc = await db.prompt_versions.find_one(
        {"purpose": purpose, "is_active": True},
        {"_id": 0},
    )
    return doc


async def get_version(version_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific version by ID."""
    db = get_db()
    doc = await db.prompt_versions.find_one({"version_id": version_id}, {"_id": 0})
    return doc


async def list_versions(purpose: str, limit: int = 20) -> List[Dict[str, Any]]:
    """List all versions for a purpose, newest first."""
    db = get_db()
    cursor = db.prompt_versions.find(
        {"purpose": purpose},
        {"_id": 0},
    ).sort("version", -1).limit(limit)
    return await cursor.to_list(limit)


async def rollback_to_version(version_id: str, author: str = "system") -> Dict[str, Any]:
    """Rollback to a specific version. Creates a new version from the target's config."""
    db = get_db()

    target = await db.prompt_versions.find_one({"version_id": version_id}, {"_id": 0})
    if not target:
        return {"status": "FAILURE", "message": f"Version '{version_id}' not found"}

    purpose = target["purpose"]
    target_ver = target["version"]

    # Create a new version with the rollback target's config
    new_version = await create_version(
        purpose=purpose,
        config=target["config"],
        author=author,
        change_description=f"Rollback to v{target_ver} ({version_id[:8]})",
    )

    logger.info(
        "Prompt rollback: purpose=%s from=current to=v%d new=v%d",
        purpose, target_ver, new_version["version"],
    )

    return {
        "status": "SUCCESS",
        "rolled_back_to": version_id,
        "original_version": target_ver,
        "new_version": new_version["version"],
        "new_version_id": new_version["version_id"],
        "purpose": purpose,
    }


async def compare_versions(version_id_a: str, version_id_b: str) -> Dict[str, Any]:
    """Compare two versions and return the diff."""
    db = get_db()

    a = await db.prompt_versions.find_one({"version_id": version_id_a}, {"_id": 0})
    b = await db.prompt_versions.find_one({"version_id": version_id_b}, {"_id": 0})

    if not a or not b:
        return {"status": "FAILURE", "message": "One or both versions not found"}

    config_a = a.get("config", {})
    config_b = b.get("config", {})

    added = {k: config_b[k] for k in config_b if k not in config_a}
    removed = {k: config_a[k] for k in config_a if k not in config_b}
    changed = {
        k: {"from": config_a[k], "to": config_b[k]}
        for k in config_a
        if k in config_b and config_a[k] != config_b[k]
    }

    return {
        "version_a": {"id": version_id_a, "version": a["version"], "purpose": a["purpose"]},
        "version_b": {"id": version_id_b, "version": b["version"], "purpose": b["purpose"]},
        "diff": {
            "added": added,
            "removed": removed,
            "changed": changed,
        },
        "identical": len(added) == 0 and len(removed) == 0 and len(changed) == 0,
    }


def _hash_config(config: Dict[str, Any]) -> str:
    import hashlib
    import json
    raw = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
