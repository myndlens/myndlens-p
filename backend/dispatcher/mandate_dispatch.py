"""Mandate Dispatch — sends approved mandates to ObeGee and tracks execution.

Implements real-time progress updates via WebSocket pipeline_stage events.
Stages 1-5 are MyndLens-internal, stages 6-8 fire on dispatch,
stage 9 is active during execution, stage 10 on webhook delivery.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.database import get_db
from config.settings import get_settings

logger = logging.getLogger(__name__)

STAGE_NAMES = {
    0: "Intent captured",
    1: "Enriched with Digital Self",
    2: "Dimensions extracted",
    3: "Mandate created",
    4: "Oral approval received",
    5: "Agents assigned",
    6: "Skills & tools defined",
    7: "Authorization granted",
    8: "OpenClaw executing",
    9: "Results delivered",
}


async def broadcast_stage(
    session_id: str,
    stage_index: int,
    status: str = "active",
    sub_status: str = "",
    progress: int = 0,
    execution_id: str = "",
) -> None:
    """Broadcast a pipeline stage update via WebSocket + persist to DB."""
    from gateway.ws_server import active_connections, _make_envelope, execution_sessions
    from schemas.ws_messages import WSMessageType

    stage_name = STAGE_NAMES.get(stage_index, f"Stage {stage_index}")

    payload = {
        "stage_id": list(STAGE_NAMES.keys())[stage_index] if stage_index < len(STAGE_NAMES) else str(stage_index),
        "stage_index": stage_index,
        "total_stages": 10,
        "status": status,
        "stage_name": stage_name,
        "sub_status": sub_status,
        "progress": progress,
        "execution_id": execution_id,
    }

    # Persist to DB
    db = get_db()
    await db.pipeline_progress.update_one(
        {"session_id": session_id},
        {"$set": {
            f"stages.{stage_index}": {"status": status, "updated_at": datetime.now(timezone.utc)},
            "current_stage": stage_index,
            "execution_id": execution_id,
        }},
        upsert=True,
    )

    # Broadcast to WS client
    ws = active_connections.get(session_id)
    if ws:
        try:
            data = _make_envelope(WSMessageType.PIPELINE_STAGE, payload)
            await ws.send_text(data)
        except Exception as e:
            logger.warning("Failed to broadcast stage %d to session %s: %s", stage_index, session_id, e)

    # Map execution_id → session_id for webhook routing
    if execution_id:
        execution_sessions[execution_id] = session_id


async def dispatch_mandate(
    session_id: str,
    mandate: Dict[str, Any],
    api_token: str = "",
) -> Dict[str, Any]:
    """Send mandate to ObeGee and start tracking execution progress.

    In dev mode (no OBEGEE_API_URL), simulates the dispatch with mock stages.
    In production, sends to ObeGee and polls for status.
    """
    settings = get_settings()
    obegee_url = getattr(settings, 'OBEGEE_API_URL', '')
    execution_id = f"exec_{mandate.get('mandate_id', 'unknown')}"

    # Stage 5: Agents assigned
    await broadcast_stage(session_id, 5, "done", execution_id=execution_id)

    # Stage 6: Skills & tools defined
    await broadcast_stage(session_id, 6, "done", execution_id=execution_id)

    # Stage 7: Authorization granted
    await broadcast_stage(session_id, 7, "done", execution_id=execution_id)

    if obegee_url:
        # Production: send to ObeGee
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{obegee_url}/dispatch/mandate",
                json=mandate,
                headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
            )
            result = response.json()
            execution_id = result.get("execution_id", execution_id)

        # Stage 8: OpenClaw executing
        await broadcast_stage(session_id, 8, "active", "Queued for execution", 10, execution_id)

        # Start polling in background
        asyncio.create_task(_poll_execution(session_id, execution_id, api_token, obegee_url))

        logger.info("Mandate dispatched to ObeGee: exec=%s session=%s", execution_id, session_id)
    else:
        # Dev mode: simulate execution stages
        asyncio.create_task(_simulate_execution(session_id, execution_id))
        logger.info("Mandate dispatched (simulated): exec=%s session=%s", execution_id, session_id)

    # Store mandate dispatch
    db = get_db()
    await db.mandate_dispatches.insert_one({
        "execution_id": execution_id,
        "session_id": session_id,
        "mandate": mandate,
        "dispatched_at": datetime.now(timezone.utc),
        "mode": "production" if obegee_url else "simulated",
    })

    return {"execution_id": execution_id, "status": "QUEUED"}


async def _poll_execution(
    session_id: str,
    execution_id: str,
    api_token: str,
    obegee_url: str,
) -> None:
    """Poll ObeGee for execution status. Max 5 minutes (150 polls * 2s)."""
    import httpx

    progress = 15
    for i in range(150):
        await asyncio.sleep(2)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{obegee_url}/dispatch/status/{execution_id}",
                    headers={"Authorization": f"Bearer {api_token}"},
                )
                data = response.json()
        except Exception as e:
            logger.warning("Poll failed for exec=%s: %s", execution_id, e)
            continue

        status = data.get("status", "")
        sub_status = data.get("sub_status", "")

        # Update progress based on status
        if status == "EXECUTING":
            progress = min(progress + 5, 90)
            await broadcast_stage(session_id, 8, "active", sub_status or "OpenClaw executing...", progress, execution_id)
        elif status == "DELIVERING":
            await broadcast_stage(session_id, 8, "done", "Execution complete", 95, execution_id)
            await broadcast_stage(session_id, 9, "active", "Delivering results...", 95, execution_id)
        elif status in ("COMPLETED", "FAILED"):
            # Webhook should handle stage 9 done, but update here as backup
            final_status = "done" if status == "COMPLETED" else "failed"
            await broadcast_stage(session_id, 9, final_status, data.get("summary", ""), 100, execution_id)
            logger.info("Execution %s: exec=%s", status, execution_id)
            return

    # Timeout
    logger.warning("Execution polling timeout: exec=%s", execution_id)
    await broadcast_stage(session_id, 8, "failed", "Execution timed out", 0, execution_id)


async def _simulate_execution(session_id: str, execution_id: str) -> None:
    """Simulate ObeGee execution stages in dev mode."""
    stages = [
        (8, "active", "Agent started", 10),
        (8, "active", "Using web search tool...", 30),
        (8, "active", "Analyzing results...", 50),
        (8, "active", "Generating response...", 70),
        (8, "active", "Preparing delivery...", 85),
        (8, "done", "Execution complete", 95),
        (9, "done", "Results delivered", 100),
    ]

    for stage_idx, status, sub_status, progress in stages:
        await asyncio.sleep(1.5)
        await broadcast_stage(session_id, stage_idx, status, sub_status, progress, execution_id)

    logger.info("Simulated execution complete: exec=%s", execution_id)
