"""Dispatcher — B14.

Translates signed MIO → OpenClaw REST API call.
Injects tenant API key. Enforces idempotency.
Logs CEO-level observability trace.

Execution Guardrail: No execution without valid signed MIO.
"""
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.database import get_db
from core.exceptions import DispatchBlockedError
from config.settings import get_settings
from envguard.env_separation import assert_dispatch_allowed
from mio.verify import verify_mio_for_execution
from dispatcher.idempotency import check_idempotency, record_dispatch
from dispatcher.http_client import call_openclaw
from observability.audit_log import log_audit_event
from schemas.audit import AuditEventType

logger = logging.getLogger(__name__)


async def dispatch(
    mio_dict: dict,
    signature: str,
    session_id: str,
    device_id: str,
    tenant_id: str,
) -> Dict[str, Any]:
    """Dispatch a signed MIO to the tenant's OpenClaw endpoint.
    
    Pipeline:
      1. Verify MIO (signature, TTL, replay, presence, touch, biometric)
      2. Check idempotency
      3. Look up tenant endpoint + key
      4. Translate MIO → OpenClaw schema
      5. Execute HTTPS call
      6. Log trace
    """
    start = time.monotonic()
    mio_id = mio_dict.get("header", {}).get("mio_id", "")
    action = mio_dict.get("intent_envelope", {}).get("action", "")
    tier = mio_dict.get("intent_envelope", {}).get("constraints", {}).get("tier", 0)
    touch_token = mio_dict.get("security_proof", {}).get("touch_event_token")
    biometric = mio_dict.get("security_proof", {}).get("signature")

    # 1. Env guard
    settings = get_settings()
    try:
        assert_dispatch_allowed(settings.ENV)
    except Exception as e:
        raise DispatchBlockedError(str(e))

    # 2. Verify MIO
    valid, reason = await verify_mio_for_execution(
        mio_dict=mio_dict,
        signature=signature,
        session_id=session_id,
        device_id=device_id,
        tier=tier,
        touch_token=touch_token,
        biometric_proof=biometric,
    )
    if not valid:
        raise DispatchBlockedError(f"MIO verification failed: {reason}")

    # 3. Idempotency
    idem_key = f"{session_id}:{mio_id}"
    existing = await check_idempotency(idem_key)
    if existing:
        logger.info("Dispatch idempotent (duplicate): key=%s", idem_key)
        return existing

    # 4. Look up tenant
    db = get_db()
    tenant = await db.tenants.find_one({"tenant_id": tenant_id})
    if not tenant:
        raise DispatchBlockedError(f"Tenant not found: {tenant_id}")
    if tenant.get("status") != "ACTIVE":
        raise DispatchBlockedError(f"Tenant not active: {tenant.get('status')}")

    endpoint = tenant.get("openclaw_endpoint", "")
    tenant_key = tenant.get("key_refs", {}).get("api_key", "")

    # 5. Translate MIO → OpenClaw schema
    openclaw_payload = _translate_mio(mio_dict, action)

    # 6. Execute
    result = await call_openclaw(
        endpoint=endpoint,
        payload=openclaw_payload,
        tenant_key=tenant_key,
        mio_id=mio_id,
    )

    latency_ms = (time.monotonic() - start) * 1000

    # 7. Record dispatch
    dispatch_record = {
        "dispatch_id": str(uuid.uuid4()),
        "idempotency_key": idem_key,
        "mio_id": mio_id,
        "session_id": session_id,
        "tenant_id": tenant_id,
        "action": action,
        "status": result.get("status", "completed"),
        "latency_ms": latency_ms,
        "timestamp": datetime.now(timezone.utc),
    }
    await record_dispatch(idem_key, dispatch_record)

    # 8. Audit
    await log_audit_event(
        AuditEventType.EXECUTE_COMPLETED,
        session_id=session_id,
        details={
            "mio_id": mio_id,
            "action": action,
            "tenant_id": tenant_id,
            "latency_ms": latency_ms,
        },
    )

    logger.info(
        "DISPATCH: mio=%s action=%s tenant=%s latency=%.0fms status=%s",
        mio_id[:12], action, tenant_id[:12], latency_ms, result.get("status"),
    )

    return dispatch_record


def _translate_mio(mio_dict: dict, action: str) -> dict:
    """Translate MIO → OpenClaw REST payload (zero-change bridge)."""
    params = mio_dict.get("intent_envelope", {}).get("params", {})
    return {
        "action": action,
        "params": params,
        "source": "myndlens",
        "mio_id": mio_dict.get("header", {}).get("mio_id", ""),
    }
