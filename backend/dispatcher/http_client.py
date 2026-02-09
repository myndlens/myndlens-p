"""HTTP Client — secure HTTPS client for OpenClaw calls.

Transport: HTTPS only.
Stub mode: returns success for dev/testing.
"""
import logging
from typing import Any, Dict, Optional

from config.settings import get_settings

logger = logging.getLogger(__name__)


async def call_openclaw(
    endpoint: str,
    payload: Dict[str, Any],
    tenant_key: str,
    mio_id: str,
) -> Dict[str, Any]:
    """Call an OpenClaw tenant endpoint.
    
    In dev/stub mode: returns mock success.
    In prod: makes real HTTPS POST.
    """
    settings = get_settings()

    if not endpoint:
        # Stub mode: no real endpoint configured
        logger.info(
            "[OpenClaw] STUB dispatch: mio=%s action=%s",
            mio_id[:12], payload.get("action"),
        )
        return {
            "status": "completed",
            "stub": True,
            "message": "Stub dispatch (no endpoint configured)",
        }

    # Real HTTPS call (future)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {tenant_key}",
                    "X-MIO-ID": mio_id,
                    "Content-Type": "application/json",
                },
            )
            return {
                "status": "completed" if response.status_code < 400 else "failed",
                "http_status": response.status_code,
                "body": response.text[:500],
            }
    except Exception as e:
        logger.error("[OpenClaw] Call failed: %s", str(e))
        return {"status": "failed", "error": str(e)}
