"""ObeGee Shared DB Reader — read-only access to ObeGee's MongoDB.

Per Dev Agent Contract: MyndLens has READ-ONLY access to:
  - users
  - tenants
  - subscriptions
  - runtime_instances

MyndLens NEVER writes to ObeGee collections.
"""
import logging
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from config.settings import get_settings

logger = logging.getLogger(__name__)

_obegee_client: Optional[AsyncIOMotorClient] = None
_obegee_db: Optional[AsyncIOMotorDatabase] = None


def get_obegee_db() -> Optional[AsyncIOMotorDatabase]:
    """Get ObeGee shared DB (read-only). Returns None if not configured."""
    global _obegee_client, _obegee_db
    settings = get_settings()

    if not settings.OBEGEE_MONGO_URL:
        return None  # Not configured — dev mode, use local

    if _obegee_db is None:
        _obegee_client = AsyncIOMotorClient(settings.OBEGEE_MONGO_URL)
        _obegee_db = _obegee_client[settings.OBEGEE_DB_NAME]
        logger.info("[ObeGeeDB] Connected: %s", settings.OBEGEE_DB_NAME)

    return _obegee_db


async def resolve_tenant_endpoint(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a tenant's OpenClaw runtime endpoint from ObeGee's runtime_instances.
    
    Returns {port, status, endpoint} or None if not found / not configured.
    """
    db = get_obegee_db()
    if db is None:
        return None  # Dev mode — no shared DB

    try:
        doc = await db.runtime_instances.find_one({"tenant_id": tenant_id})
        if doc:
            return {
                "port": doc.get("port"),
                "status": doc.get("status"),
                "endpoint": f"http://{get_settings().CHANNEL_ADAPTER_IP}:8080/v1/dispatch",
            }
    except Exception as e:
        logger.error("[ObeGeeDB] Tenant resolution failed: %s", str(e))

    return None


async def get_subscription_status(obegee_user_id: str) -> Optional[str]:
    """Read subscription status from ObeGee's subscriptions collection."""
    db = get_obegee_db()
    if db is None:
        return None

    try:
        doc = await db.subscriptions.find_one({"obegee_user_id": obegee_user_id})
        if doc:
            return doc.get("status")
    except Exception as e:
        logger.error("[ObeGeeDB] Subscription lookup failed: %s", str(e))

    return None
