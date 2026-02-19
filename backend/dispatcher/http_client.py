"""ObeGee Channel Adapter Client — the ONLY outbound execution path.

Per Dev Agent Contract §7:
  MyndLens → Signed MIO → ObeGee Channel Adapter → OpenClaw

Endpoint: POST http://{CHANNEL_ADAPTER_IP}:{tenant_port}/v1/dispatch
Auth: X-MYNDLENS-DISPATCH-TOKEN
Idempotency: Idempotency-Key: {session_id}:{mio_id}

MyndLens sends ONLY: signed MIO + metadata + tenant binding.
MyndLens NEVER sends: transcripts, memory, prompts, secrets.
"""
import logging
import time
from typing import Any, Dict

from core.exceptions import DispatchBlockedError
from config.settings import get_settings
from tenants.obegee_reader import resolve_tenant_endpoint

logger = logging.getLogger(__name__)


async def submit_mio_to_adapter(
    mio_id: str,
    signature: str,
    action: str,
    action_class: str,
    params: Dict[str, Any],
    tier: int,
    tenant_id: str,
    session_id: str,
    expires_at: str,
    evidence_hashes: Dict[str, str],
    latch_proofs: Dict[str, str],
) -> Dict[str, Any]:
    """Submit a signed MIO to ObeGee's Channel Adapter.

    Resolves tenant endpoint from ObeGee's runtime_instances.
    Falls back to stub in dev when adapter not available.
    """
    settings = get_settings()
    start = time.monotonic()

    # Construct payload per integration spec schema
    submission = {
        "mio": {
            "mio_id": mio_id,
            "action_class": action_class,
            "params": params,
            "session_id": session_id,
            "expires_at": expires_at,
        },
        "signature": signature,
        "tenant_id": tenant_id,
        "session_id": session_id,
    }

    # Resolve tenant endpoint from ObeGee shared DB
    endpoint_info = await resolve_tenant_endpoint(tenant_id)

    if endpoint_info and endpoint_info.get("endpoint"):
        endpoint = endpoint_info["endpoint"]
        return await _call_adapter(endpoint, submission, mio_id, session_id, start)

    # Fall back to configured CHANNEL_ADAPTER_IP
    if settings.CHANNEL_ADAPTER_IP:
        endpoint = f"http://{settings.CHANNEL_ADAPTER_IP}:8080/v1/dispatch"
        return await _call_adapter(endpoint, submission, mio_id, session_id, start)

    # No adapter endpoint — fail fast
    raise DispatchBlockedError(
        "No ObeGee Channel Adapter endpoint configured for this tenant. "
        "Set CHANNEL_ADAPTER_IP in backend/.env or ensure tenant is provisioned in ObeGee."
    )


async def _call_adapter(
    endpoint: str,
    submission: dict,
    mio_id: str,
    session_id: str,
    start: float,
) -> Dict[str, Any]:
    """Make the real HTTPS POST to ObeGee's Channel Adapter."""
    settings = get_settings()

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                endpoint,
                json=submission,
                headers={
                    "Content-Type": "application/json",
                    "X-MYNDLENS-DISPATCH-TOKEN": settings.MYNDLENS_DISPATCH_TOKEN,
                    "Idempotency-Key": f"{session_id}:{mio_id}",
                },
            )
            latency_ms = (time.monotonic() - start) * 1000

            if response.status_code < 400:
                logger.info(
                    "[Adapter] Submitted: mio=%s endpoint=%s status=%d latency=%.0fms",
                    mio_id[:12], endpoint, response.status_code, latency_ms,
                )
                return {
                    "status": "submitted",
                    "http_status": response.status_code,
                    "mio_id": mio_id,
                    "latency_ms": latency_ms,
                }
            else:
                logger.warning(
                    "[Adapter] Rejected: mio=%s status=%d body=%s",
                    mio_id[:12], response.status_code, response.text[:200],
                )
                return {
                    "status": "rejected",
                    "http_status": response.status_code,
                    "mio_id": mio_id,
                    "latency_ms": latency_ms,
                }

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("[Adapter] Submit failed: mio=%s error=%s", mio_id[:12], str(e))
        return {"status": "failed", "error": str(e), "mio_id": mio_id, "latency_ms": latency_ms}
