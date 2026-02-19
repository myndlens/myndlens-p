"""Dispatcher — B14 (refactored per Dev Agent Contract).

Per Contract §7: MyndLens → Signed MIO → ObeGee Channel Adapter → OpenClaw
MyndLens NEVER calls OpenClaw directly.

The dispatcher:
  1. Verifies MIO (signature, TTL, replay, presence, latch)
  2. Checks idempotency
  3. Submits signed MIO to ObeGee Adapter
  4. Records dispatch + audit
"""
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from core.exceptions import DispatchBlockedError
from config.settings import get_settings
from mio.verify import verify_mio_for_execution
from dispatcher.idempotency import check_idempotency, record_dispatch
from dispatcher.http_client import submit_mio_to_adapter
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
    """Dispatch a signed MIO via ObeGee Adapter.

    MyndLens sends: signed MIO + evidence hashes + latch proofs.
    MyndLens never sends: transcripts, memory, prompts, secrets.
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

    # 2. Verify MIO (6-gate pipeline)
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

    # 4. Submit to ObeGee Adapter (NOT OpenClaw — per Dev Agent Contract §7)
    grounding = mio_dict.get("grounding", {})
    evidence_hashes = {
        "transcript_hash": grounding.get("transcript_hash", ""),
        "l1_hash": grounding.get("l1_hash", ""),
        "l2_audit_hash": grounding.get("l2_audit_hash", ""),
    }
    latch_proofs = {}
    if touch_token:
        latch_proofs["touch_token"] = "present"
    if biometric:
        latch_proofs["biometric"] = "present"

    params = mio_dict.get("intent_envelope", {}).get("params", {})
    action_class = mio_dict.get("intent_envelope", {}).get("action_class", "")
    expires_at = str(mio_dict.get("header", {}).get("timestamp", ""))

    adapter_result = await submit_mio_to_adapter(
        mio_id=mio_id,
        signature=signature,
        action=action,
        action_class=action_class,
        params=params,
        tier=tier,
        tenant_id=tenant_id,
        session_id=session_id,
        expires_at=expires_at,
        evidence_hashes=evidence_hashes,
        latch_proofs=latch_proofs,
    )

    latency_ms = (time.monotonic() - start) * 1000

    # 5. Record dispatch
    dispatch_record = {
        "dispatch_id": str(uuid.uuid4()),
        "idempotency_key": idem_key,
        "mio_id": mio_id,
        "session_id": session_id,
        "tenant_id": tenant_id,
        "action": action,
        "status": adapter_result.get("status", "submitted"),
        "latency_ms": latency_ms,
        "timestamp": datetime.now(timezone.utc),
    }
    await record_dispatch(idem_key, dispatch_record)

    # 6. Audit
    await log_audit_event(
        AuditEventType.EXECUTE_COMPLETED,
        session_id=session_id,
        details={
            "mio_id": mio_id,
            "action": action,
            "tenant_id": tenant_id,
            "adapter_status": adapter_result.get("status"),
            "latency_ms": latency_ms,
        },
    )

    logger.info(
        "DISPATCH via adapter: mio=%s action=%s tenant=%s status=%s latency=%.0fms",
        mio_id[:12], action, tenant_id[:12], adapter_result.get("status"), latency_ms,
    )

    return dispatch_record
