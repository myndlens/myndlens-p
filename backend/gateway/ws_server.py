"""WebSocket server — B1 Gateway.

Handles authenticated WS connections, message routing,
heartbeat tracking, and execute-gate enforcement.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from auth.tokens import validate_token, TokenClaims
from auth.device_binding import create_session, get_session, terminate_session
from core.exceptions import AuthError, PresenceError, MyndLensError
from observability.audit_log import log_audit_event
from observability.redaction import redact_dict
from presence.heartbeat import record_heartbeat, check_presence
from presence.rules import get_heartbeat_interval_ms
from schemas.audit import AuditEventType
from schemas.ws_messages import (
    WSMessageType,
    WSEnvelope,
    AuthPayload,
    AuthOkPayload,
    AuthFailPayload,
    HeartbeatPayload,
    HeartbeatAckPayload,
    ExecuteRequestPayload,
    ExecuteBlockedPayload,
    ErrorPayload,
)

logger = logging.getLogger(__name__)

# Active connections: session_id -> WebSocket
active_connections: Dict[str, WebSocket] = {}


def _make_envelope(msg_type: WSMessageType, payload: dict) -> str:
    """Create a JSON string envelope for sending."""
    envelope = WSEnvelope(type=msg_type, payload=payload)
    return envelope.model_dump_json()


async def _send(ws: WebSocket, msg_type: WSMessageType, payload_model) -> None:
    """Send a typed message to the client."""
    data = _make_envelope(msg_type, payload_model.model_dump())
    await ws.send_text(data)


async def handle_ws_connection(websocket: WebSocket) -> None:
    """Main WebSocket handler. Protocol:
    
    1. Client connects
    2. Client sends AUTH message with token + device_id
    3. Server validates, creates session, sends AUTH_OK
    4. Client sends HEARTBEAT every 5s
    5. Any EXECUTE_REQUEST checks presence freshness
    """
    await websocket.accept()
    session_id = None
    claims: TokenClaims | None = None

    try:
        # ---- Phase 1: Authentication ----
        # Wait for auth message (10s timeout handled by client)
        raw = await websocket.receive_text()
        msg = json.loads(raw)

        if msg.get("type") != WSMessageType.AUTH.value:
            await _send(websocket, WSMessageType.AUTH_FAIL, AuthFailPayload(
                reason="First message must be AUTH",
                code="PROTOCOL_ERROR",
            ))
            await websocket.close(code=4001, reason="Protocol error")
            return

        # Validate token
        try:
            auth_payload = AuthPayload(**msg.get("payload", {}))
            claims = validate_token(auth_payload.token)

            # Verify device_id matches token
            if claims.device_id != auth_payload.device_id:
                raise AuthError("Device ID mismatch")

        except AuthError as e:
            await _send(websocket, WSMessageType.AUTH_FAIL, AuthFailPayload(
                reason=str(e),
                code="AUTH_ERROR",
            ))
            await log_audit_event(
                AuditEventType.AUTH_FAILURE,
                details={"reason": str(e)},
            )
            await websocket.close(code=4003, reason="Auth failed")
            return

        # Create session
        session = await create_session(
            user_id=claims.user_id,
            device_id=claims.device_id,
            env=claims.env,
            client_version=auth_payload.client_version,
        )
        session_id = session.session_id
        active_connections[session_id] = websocket

        # Send AUTH_OK
        await _send(websocket, WSMessageType.AUTH_OK, AuthOkPayload(
            session_id=session_id,
            user_id=claims.user_id,
            heartbeat_interval_ms=get_heartbeat_interval_ms(),
        ))

        await log_audit_event(
            AuditEventType.AUTH_SUCCESS,
            session_id=session_id,
            user_id=claims.user_id,
            details={"device_id": claims.device_id},
        )

        logger.info(
            "WS authenticated: session=%s user=%s device=%s",
            session_id, claims.user_id, claims.device_id,
        )

        # ---- Phase 2: Message Loop ----
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")
            payload = msg.get("payload", {})

            if msg_type == WSMessageType.HEARTBEAT.value:
                await _handle_heartbeat(websocket, session_id, payload)

            elif msg_type == WSMessageType.EXECUTE_REQUEST.value:
                await _handle_execute_request(websocket, session_id, payload)

            elif msg_type == WSMessageType.CANCEL.value:
                logger.info("Cancel received: session=%s", session_id)
                # Future: cancel pending operations

            elif msg_type == WSMessageType.TEXT_INPUT.value:
                logger.info("Text input received: session=%s", session_id)
                # Future: handle text-based input (Batch 2+)

            else:
                await _send(websocket, WSMessageType.ERROR, ErrorPayload(
                    message=f"Unknown message type: {msg_type}",
                    code="UNKNOWN_MSG_TYPE",
                ))

    except WebSocketDisconnect:
        logger.info("WS disconnected: session=%s", session_id)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON received on WS: session=%s", session_id)
    except Exception as e:
        logger.error("WS error: session=%s error=%s", session_id, str(e), exc_info=True)
    finally:
        # Cleanup
        if session_id:
            active_connections.pop(session_id, None)
            await terminate_session(session_id)
            await log_audit_event(
                AuditEventType.SESSION_TERMINATED,
                session_id=session_id,
                user_id=claims.user_id if claims else None,
            )


async def _handle_heartbeat(ws: WebSocket, session_id: str, payload: dict) -> None:
    """Process a heartbeat message."""
    try:
        hb = HeartbeatPayload(**payload)
        server_ts = await record_heartbeat(session_id, hb.seq, hb.client_ts)
        await _send(ws, WSMessageType.HEARTBEAT_ACK, HeartbeatAckPayload(
            seq=hb.seq,
            server_ts=server_ts,
        ))
    except PresenceError as e:
        logger.warning("Heartbeat error: session=%s error=%s", session_id, str(e))
        await _send(ws, WSMessageType.ERROR, ErrorPayload(
            message=str(e),
            code="PRESENCE_ERROR",
        ))


async def _handle_execute_request(ws: WebSocket, session_id: str, payload: dict) -> None:
    """Process an execute request. Gate on presence."""
    try:
        req = ExecuteRequestPayload(**payload)

        # CRITICAL GATE: Check heartbeat freshness
        is_present = await check_presence(session_id)
        if not is_present:
            await _send(ws, WSMessageType.EXECUTE_BLOCKED, ExecuteBlockedPayload(
                reason="Heartbeat stale. Execute blocked per presence policy.",
                code="PRESENCE_STALE",
                draft_id=req.draft_id,
            ))
            await log_audit_event(
                AuditEventType.EXECUTE_BLOCKED,
                session_id=session_id,
                details={"reason": "PRESENCE_STALE", "draft_id": req.draft_id},
            )
            logger.warning(
                "EXECUTE_BLOCKED: session=%s reason=PRESENCE_STALE draft=%s",
                session_id, req.draft_id,
            )
            return

        # Presence OK — in future batches, this continues to MIO signing pipeline.
        # For now (Batch 1), we acknowledge the request.
        await log_audit_event(
            AuditEventType.EXECUTE_REQUESTED,
            session_id=session_id,
            details={"draft_id": req.draft_id, "presence_ok": True},
        )

        # Placeholder: In Batch 1, execute pipeline is not yet built.
        # Send a blocked response with appropriate reason.
        await _send(ws, WSMessageType.EXECUTE_BLOCKED, ExecuteBlockedPayload(
            reason="Execute pipeline not yet available (Batch 1). Presence verified.",
            code="PIPELINE_NOT_READY",
            draft_id=req.draft_id,
        ))

    except Exception as e:
        logger.error("Execute request error: session=%s error=%s", session_id, str(e))
        await _send(ws, WSMessageType.ERROR, ErrorPayload(
            message="Execute request failed",
            code="EXECUTE_ERROR",
        ))


def get_active_session_count() -> int:
    """Return number of active WebSocket connections."""
    return len(active_connections)
