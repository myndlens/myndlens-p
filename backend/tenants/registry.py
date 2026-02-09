"""Tenant Registry — CRUD for tenant records in MongoDB."""
import logging
from datetime import datetime, timezone
from typing import Optional

from core.database import get_db
from schemas.tenant import Tenant, TenantStatus

logger = logging.getLogger(__name__)


async def get_tenant_by_id(tenant_id: str) -> Optional[Tenant]:
    db = get_db()
    doc = await db.tenants.find_one({"tenant_id": tenant_id})
    if doc:
        doc.pop("_id", None)
        return Tenant(**doc)
    return None


async def get_tenant_by_obegee_user(obegee_user_id: str) -> Optional[Tenant]:
    db = get_db()
    doc = await db.tenants.find_one({"obegee_user_id": obegee_user_id})
    if doc:
        doc.pop("_id", None)
        return Tenant(**doc)
    return None


async def create_or_get_tenant(obegee_user_id: str, openclaw_endpoint: Optional[str] = None) -> Tenant:
    """Idempotent: create tenant if not exists, else return existing."""
    existing = await get_tenant_by_obegee_user(obegee_user_id)
    if existing:
        logger.info("Tenant already exists: tenant=%s user=%s", existing.tenant_id, obegee_user_id)
        return existing

    tenant = Tenant(
        obegee_user_id=obegee_user_id,
        status=TenantStatus.ACTIVE,
        openclaw_endpoint=openclaw_endpoint,
    )
    db = get_db()
    await db.tenants.insert_one(tenant.to_doc())
    logger.info("Tenant created: tenant=%s user=%s", tenant.tenant_id, obegee_user_id)
    return tenant


async def update_tenant_status(tenant_id: str, status: TenantStatus) -> bool:
    db = get_db()
    result = await db.tenants.update_one(
        {"tenant_id": tenant_id},
        {"$set": {"status": status.value, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count:
        logger.info("Tenant status updated: tenant=%s status=%s", tenant_id, status.value)
        return True
    return False
