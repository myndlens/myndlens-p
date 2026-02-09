"""Tenant Lifecycle — activate, suspend, deprovision.

Complete implementation with provisioning, key management,
session invalidation, data export/delete.
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
from tenants.provisioner import (
    full_provision,
    flush_execution_keys,
    revoke_tenant_key,
    rotate_tenant_key,
    stop_docker,
)
from tenants.data_management import (
    invalidate_user_sessions,
    detach_device_bindings,
    delete_user_data,
    export_user_data,
)

logger = logging.getLogger(__name__)


async def activate_tenant(obegee_user_id: str, openclaw_endpoint: Optional[str] = None) -> dict:
    """Idempotent tenant activation with full provisioning."""
    tenant = await create_or_get_tenant(obegee_user_id, openclaw_endpoint)

    # If was suspended/cancelled, reactivate
    if tenant.status != TenantStatus.ACTIVE:
        await update_tenant_status(tenant.tenant_id, TenantStatus.ACTIVE)

    # Full provision if not yet provisioned (no endpoint = new tenant)
    if not tenant.openclaw_endpoint:
        provision_result = await full_provision(tenant.tenant_id)
        logger.info(
            "Tenant provisioned: tenant=%s endpoint=%s",
            tenant.tenant_id[:12], provision_result.get("openclaw_endpoint", ""),
        )

    await log_audit_event(
        AuditEventType.TENANT_ACTIVATED,
        user_id=obegee_user_id,
        details={"tenant_id": tenant.tenant_id},
    )
    return {"tenant_id": tenant.tenant_id, "status": "ACTIVE"}


async def suspend_tenant(tenant_id: str, reason: str = "subscription_suspended") -> dict:
    """Suspend: read-only mode, flush execution keys, invalidate sessions."""
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        raise MyndLensError(f"Tenant not found: {tenant_id}", code="TENANT_NOT_FOUND")

    # 1. Update status
    await update_tenant_status(tenant_id, TenantStatus.SUSPENDED)

    # 2. Flush execution keys (keep Docker running)
    await flush_execution_keys(tenant_id)

    # 3. Invalidate all active sessions
    invalidated = await invalidate_user_sessions(tenant.obegee_user_id)

    await log_audit_event(
        AuditEventType.TENANT_SUSPENDED,
        user_id=tenant.obegee_user_id,
        details={
            "tenant_id": tenant_id,
            "reason": reason,
            "sessions_invalidated": invalidated,
            "keys_flushed": True,
        },
    )

    logger.info(
        "Tenant suspended: tenant=%s sessions_invalidated=%d keys_flushed=true",
        tenant_id[:12], invalidated,
    )
    return {"tenant_id": tenant_id, "status": "SUSPENDED", "sessions_invalidated": invalidated}


async def deprovision_tenant(tenant_id: str, reason: str = "subscription_cancelled") -> dict:
    """Deprovision: stop docker, revoke keys, detach bindings, delete data, preserve audit."""
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        raise MyndLensError(f"Tenant not found: {tenant_id}", code="TENANT_NOT_FOUND")

    # 1. Update status
    await update_tenant_status(tenant_id, TenantStatus.DEPROVISIONED)

    # 2. Stop and delete tenant Docker
    await stop_docker(tenant_id)

    # 3. Revoke all keys
    await revoke_tenant_key(tenant_id)

    # 4. Detach device bindings + invalidate sessions
    detached = await detach_device_bindings(tenant.obegee_user_id)

    # 5. Delete user data (preserve audit per legal requirement)
    delete_counts = await delete_user_data(tenant.obegee_user_id, preserve_audit=True)

    await log_audit_event(
        AuditEventType.TENANT_DEPROVISIONED,
        user_id=tenant.obegee_user_id,
        details={
            "tenant_id": tenant_id,
            "reason": reason,
            "devices_detached": detached,
            "data_deleted": delete_counts,
            "audit_preserved": True,
        },
    )

    logger.info(
        "Tenant deprovisioned: tenant=%s data_deleted=%s audit_preserved=true",
        tenant_id[:12], delete_counts,
    )
    return {
        "tenant_id": tenant_id,
        "status": "DEPROVISIONED",
        "data_deleted": delete_counts,
        "audit_preserved": True,
    }
