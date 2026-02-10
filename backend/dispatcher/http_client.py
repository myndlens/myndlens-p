"""ObeGee Adapter Client — the ONLY outbound path for execution.

Per Dev Agent Contract §7:
  MyndLens → Signed MIO → ObeGee Channel Adapter → OpenClaw

MyndLens NEVER calls OpenClaw directly.
MyndLens sends only: signed MIO + intent metadata + tier constraints.
MyndLens NEVER sends: raw transcripts, Digital Self memory, prompt contents, secrets.
"""
import logging
import time
from typing import Any, Dict

from config.settings import get_settings

logger = logging.getLogger(__name__)


async def submit_mio_to_adapter(
    mio_id: str,
    signature: str,
    action: str,
    tier: int,
    tenant_id: str,
    evidence_hashes: Dict[str, str],
    latch_proofs: Dict[str, str],
) -> Dict[str, Any]:
    """Submit a signed MIO to ObeGee's Channel Adapter.

    This is a one-way submission. ObeGee decides how/when to execute.
    MyndLens does not know OpenClaw endpoints, IPs, or secrets.

    In dev/stub: returns acknowledgement.
    In prod: POSTs to ObeGee's adapter endpoint.
    """
    settings = get_settings()
    start = time.monotonic()

    # Construct the submission payload (MIO metadata only — no cognitive internals)
    submission = {
        "mio_id": mio_id,
        "signature": signature,
        "action": action,
        "tier": tier,
        "tenant_id": tenant_id,
        "evidence_hashes": evidence_hashes,
        "latch_proofs": latch_proofs,
        "source": "myndlens",
    }

    # In dev: stub response (ObeGee adapter not available)
    # In prod: HTTPS POST to ObeGee's adapter endpoint
    adapter_url = settings.OBEGEE_ADAPTER_URL if hasattr(settings, 'OBEGEE_ADAPTER_URL') else ""

    if not adapter_url:
        latency_ms = (time.monotonic() - start) * 1000
        logger.info(
            "[Adapter] STUB submit: mio=%s action=%s tenant=%s (no adapter configured)",
            mio_id[:12], action, tenant_id[:12],
        )
        return {
            "status": "submitted",
            "stub": True,
            "mio_id": mio_id,
            "latency_ms": latency_ms,
        }

    # Real adapter call (production)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                adapter_url,
                json=submission,
                headers={
                    "X-MIO-ID": mio_id,
                    "X-Source": "myndlens",
                    "Content-Type": "application/json",
                },
            )
            latency_ms = (time.monotonic() - start) * 1000
            return {
                "status": "submitted" if response.status_code < 400 else "rejected",
                "http_status": response.status_code,
                "mio_id": mio_id,
                "latency_ms": latency_ms,
            }
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("[Adapter] Submit failed: mio=%s error=%s", mio_id[:12], str(e))
        return {"status": "failed", "error": str(e), "mio_id": mio_id, "latency_ms": latency_ms}
