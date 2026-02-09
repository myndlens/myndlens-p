"""Tenant Lifecycle — activate, suspend, deprovision.

Called by ObeGee via service-to-service APIs.
"""
import logging
from typing import Optional

from core.exceptions import MyndLensError
from observability.audit_log import log_audit_event
from schemas.audit import AuditEventType
from schemas.tenant import TenantStatus
from tenants.registry import (
    create_or_get_tenant,
    get_tenant_by_id,
    update_tenant_status,
)

logger = logging.getLogger(__name__)


async def activate_tenant(obegee_user_id: str, openclaw_endpoint: Optional[str] = None) -> dict:
    """Idempotent tenant activation."""
    tenant = await create_or_get_tenant(obegee_user_id, openclaw_endpoint)

    # If was suspended/cancelled, reactivate
    if tenant.status != TenantStatus.ACTIVE:
        await update_tenant_status(tenant.tenant_id, TenantStatus.ACTIVE)

    await log_audit_event(
        AuditEventType.TENANT_ACTIVATED,
        user_id=obegee_user_id,
        details={"tenant_id": tenant.tenant_id},
    )
    return {"tenant_id": tenant.tenant_id, "status": "ACTIVE"}


async def suspend_tenant(tenant_id: str, reason: str = "subscription_suspended") -> dict:
    """Suspend: read-only mode, flush execution keys, block dispatch."""
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        raise MyndLensError(f"Tenant not found: {tenant_id}", code="TENANT_NOT_FOUND")

    await update_tenant_status(tenant_id, TenantStatus.SUSPENDED)

    # TODO: Flush execution keys to OpenClaw docker (keep docker running)

    await log_audit_event(
        AuditEventType.TENANT_SUSPENDED,
        user_id=tenant.obegee_user_id,
        details={"tenant_id": tenant_id, "reason": reason},
    )
    return {"tenant_id": tenant_id, "status": "SUSPENDED"}


async def deprovision_tenant(tenant_id: str, reason: str = "subscription_cancelled") -> dict:
    """Deprovision: stop docker, revoke keys, detach bindings, preserve audit."""
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        raise MyndLensError(f"Tenant not found: {tenant_id}", code="TENANT_NOT_FOUND")

    await update_tenant_status(tenant_id, TenantStatus.DEPROVISIONED)

    # TODO: Stop/delete tenant docker, revoke keys, detach device bindings

    await log_audit_event(
        AuditEventType.TENANT_DEPROVISIONED,
        user_id=tenant.obegee_user_id,
        details={"tenant_id": tenant_id, "reason": reason},
    )
    return {"tenant_id": tenant_id, "status": "DEPROVISIONED"}
