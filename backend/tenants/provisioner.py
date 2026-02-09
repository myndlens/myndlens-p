"""Tenant Provisioner — B21.

Handles full tenant provisioning on subscription:
  1. Create tenant record
  2. Generate tenant API key
  3. Provision OpenClaw Doctor Docker (stub on Emergent)
  4. Preinstall MyndLens ↔ OpenClaw channel
  5. Return connection details
"""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from core.database import get_db

logger = logging.getLogger(__name__)


def generate_tenant_api_key() -> str:
    """Generate a secure tenant API key."""
    return f"mlk_{secrets.token_urlsafe(32)}"


async def provision_openclaw_docker(tenant_id: str) -> dict:
    """Provision a dedicated OpenClaw Doctor Docker instance.
    
    STUB on Emergent platform. In production:
      - Calls Docker API to create container
      - Runs bootstrap/install-channel.sh
      - Runs bootstrap/configure-channel.sh
      - Returns endpoint URL
    """
    # Stub: generate a mock endpoint
    endpoint = f"https://stub-openclaw-{tenant_id[:8]}.myndlens.internal"
    logger.info(
        "[Provisioner] STUB OpenClaw Docker provisioned: tenant=%s endpoint=%s",
        tenant_id[:12], endpoint,
    )
    return {
        "endpoint": endpoint,
        "status": "provisioned",
        "stub": True,
        "docker_id": f"stub-{tenant_id[:12]}",
    }


async def preinstall_channel(tenant_id: str, endpoint: str) -> dict:
    """Preinstall MyndLens ↔ OpenClaw channel on the Docker instance.
    
    STUB: In production runs channel configuration.
    """
    logger.info(
        "[Provisioner] STUB Channel preinstalled: tenant=%s",
        tenant_id[:12],
    )
    return {
        "channel": "myndlens",
        "status": "installed",
        "stub": True,
    }


async def full_provision(tenant_id: str) -> dict:
    """Complete provisioning pipeline for a new tenant."""
    db = get_db()

    # 1. Generate API key
    api_key = generate_tenant_api_key()
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # 2. Provision OpenClaw Docker
    docker_result = await provision_openclaw_docker(tenant_id)
    endpoint = docker_result["endpoint"]

    # 3. Preinstall channel
    channel_result = await preinstall_channel(tenant_id, endpoint)

    # 4. Update tenant record with endpoint + key refs
    await db.tenants.update_one(
        {"tenant_id": tenant_id},
        {"$set": {
            "openclaw_endpoint": endpoint,
            "key_refs": {
                "api_key": api_key,
                "key_hash": key_hash,
                "created_at": datetime.now(timezone.utc),
            },
            "provisioning": {
                "docker": docker_result,
                "channel": channel_result,
                "provisioned_at": datetime.now(timezone.utc),
            },
            "updated_at": datetime.now(timezone.utc),
        }},
    )

    logger.info(
        "[Provisioner] Full provision complete: tenant=%s endpoint=%s",
        tenant_id[:12], endpoint,
    )

    return {
        "tenant_id": tenant_id,
        "openclaw_endpoint": endpoint,
        "api_key_prefix": api_key[:8] + "...",
        "docker": docker_result,
        "channel": channel_result,
    }


async def rotate_tenant_key(tenant_id: str) -> dict:
    """Rotate a tenant's API key. Old key becomes invalid immediately."""
    db = get_db()
    new_key = generate_tenant_api_key()
    key_hash = hashlib.sha256(new_key.encode()).hexdigest()

    await db.tenants.update_one(
        {"tenant_id": tenant_id},
        {"$set": {
            "key_refs.api_key": new_key,
            "key_refs.key_hash": key_hash,
            "key_refs.rotated_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }},
    )

    logger.info("[Provisioner] Key rotated: tenant=%s", tenant_id[:12])
    return {"tenant_id": tenant_id, "key_prefix": new_key[:8] + "...", "rotated": True}


async def revoke_tenant_key(tenant_id: str) -> None:
    """Revoke a tenant's API key entirely."""
    db = get_db()
    await db.tenants.update_one(
        {"tenant_id": tenant_id},
        {"$set": {
            "key_refs.api_key": "",
            "key_refs.revoked_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    logger.info("[Provisioner] Key revoked: tenant=%s", tenant_id[:12])


async def flush_execution_keys(tenant_id: str) -> None:
    """Flush execution keys on suspend (keep Docker running).
    
    STUB: In production calls bootstrap/flush-keys.sh on Docker.
    """
    await revoke_tenant_key(tenant_id)
    logger.info("[Provisioner] Execution keys flushed: tenant=%s", tenant_id[:12])


async def stop_docker(tenant_id: str) -> None:
    """Stop and delete tenant Docker on deprovision.
    
    STUB on Emergent platform.
    """
    db = get_db()
    await db.tenants.update_one(
        {"tenant_id": tenant_id},
        {"$set": {
            "openclaw_endpoint": "",
            "provisioning.docker.status": "stopped",
            "provisioning.stopped_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    logger.info("[Provisioner] STUB Docker stopped: tenant=%s", tenant_id[:12])
