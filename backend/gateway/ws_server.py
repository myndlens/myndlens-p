"""WebSocket server — B1+B2 Gateway.

Handles authenticated WS connections, message routing,
heartbeat tracking, execute-gate enforcement,
and audio chunk streaming with transcript assembly.

EXECUTION GUARDRAIL (Patch 5 / §3.2):
  No execution path may proceed without an explicit `execute_request` message
  from the mobile client (i.e. the Execute button). Any future batch that adds
  execution capability MUST route through _handle_execute_request() and pass
  the presence gate. Tier 0 (INFO_RETRIEVE / DRAFT_ONLY) is the sole exception
  and still requires the execute_request envelope — it simply skips the physical
  latch.  This comment is the guardrail contract; violating it requires an ADR.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from auth.tokens import validate_token, TokenClaims
from auth.sso_validator import get_sso_validator, SSOClaims
from auth.device_binding import create_session, get_session, terminate_session
from config.settings import get_settings
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
    TranscriptPayload,
    TTSAudioPayload,
    ErrorPayload,
)
from stt.orchestrator import get_stt_provider, decode_audio_payload
from tts.orchestrator import get_tts_provider
from transcript.assembler import transcript_assembler
from transcript.storage import save_transcript

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
    user_id_resolved: str | None = None
    subscription_status: str = "ACTIVE"
    sso_claims: SSOClaims | None = None
    legacy_claims: TokenClaims | None = None

    try:
        # ---- Phase 1: Authentication ----
        raw = await websocket.receive_text()
        msg = json.loads(raw)

        if msg.get("type") != WSMessageType.AUTH.value:
            await _send(websocket, WSMessageType.AUTH_FAIL, AuthFailPayload(
                reason="First message must be AUTH",
                code="PROTOCOL_ERROR",
            ))
            await websocket.close(code=4001, reason="Protocol error")
            return

        # Validate token — try SSO first, fall back to legacy JWT
        try:
            auth_payload = AuthPayload(**msg.get("payload", {}))

            # Try SSO token validation first
            try:
                validator = get_sso_validator()
                sso_claims = validator.validate(auth_payload.token)
                user_id_resolved = sso_claims.obegee_user_id
                subscription_status = sso_claims.subscription_status

                await log_audit_event(
                    AuditEventType.SSO_AUTH_SUCCESS,
                    user_id=user_id_resolved,
                    details={
                        "tenant_id": sso_claims.myndlens_tenant_id,
                        "subscription": subscription_status,
                    },
                )
            except AuthError:
                # Fall back to legacy MyndLens JWT (dev/pair flow)
                legacy_claims = validate_token(auth_payload.token)
                user_id_resolved = legacy_claims.user_id
                if legacy_claims.device_id != auth_payload.device_id:
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
            user_id=user_id_resolved,
            device_id=auth_payload.device_id,
            env=get_settings().ENV if not sso_claims else "dev",
            client_version=auth_payload.client_version,
        )
        session_id = session.session_id
        active_connections[session_id] = websocket

        # Send AUTH_OK
        await _send(websocket, WSMessageType.AUTH_OK, AuthOkPayload(
            session_id=session_id,
            user_id=user_id_resolved,
            heartbeat_interval_ms=get_heartbeat_interval_ms(),
        ))

        await log_audit_event(
            AuditEventType.AUTH_SUCCESS,
            session_id=session_id,
            user_id=user_id_resolved,
            details={
                "device_id": auth_payload.device_id,
                "sso": sso_claims is not None,
                "subscription": subscription_status,
            },
        )

        logger.info(
            "WS authenticated: session=%s user=%s device=%s sso=%s sub=%s",
            session_id, user_id_resolved, auth_payload.device_id,
            sso_claims is not None, subscription_status,
        )

        # ---- Phase 2: Message Loop ----
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")
            payload = msg.get("payload", {})

            if msg_type == WSMessageType.HEARTBEAT.value:
                await _handle_heartbeat(websocket, session_id, payload)

            elif msg_type == WSMessageType.AUDIO_CHUNK.value:
                await _handle_audio_chunk(websocket, session_id, payload)

            elif msg_type == WSMessageType.EXECUTE_REQUEST.value:
                await _handle_execute_request(websocket, session_id, payload, subscription_status)

            elif msg_type == WSMessageType.CANCEL.value:
                logger.info("Cancel received: session=%s", session_id)
                # End any active STT stream
                await _handle_stream_end(websocket, session_id)

            elif msg_type == WSMessageType.TEXT_INPUT.value:
                await _handle_text_input(websocket, session_id, payload)

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
                user_id=legacy_claims.user_id if legacy_claims else None,
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


async def _handle_execute_request(ws: WebSocket, session_id: str, payload: dict, subscription_status: str = "ACTIVE") -> None:
    """Process an execute request. Gate on presence AND subscription."""
    try:
        req = ExecuteRequestPayload(**payload)

        # SUBSCRIPTION GATE: Block if not ACTIVE
        if subscription_status != "ACTIVE":
            await _send(ws, WSMessageType.EXECUTE_BLOCKED, ExecuteBlockedPayload(
                reason=f"Subscription status is {subscription_status}. Execute blocked.",
                code="SUBSCRIPTION_INACTIVE",
                draft_id=req.draft_id,
            ))
            await log_audit_event(
                AuditEventType.SUBSCRIPTION_INACTIVE_BLOCK,
                session_id=session_id,
                details={"subscription": subscription_status, "draft_id": req.draft_id},
            )
            logger.warning(
                "EXECUTE_BLOCKED: session=%s reason=SUBSCRIPTION_INACTIVE sub=%s",
                session_id, subscription_status,
            )
            return

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


# =====================================================
#  Batch 2: Audio Chunk + Transcript + TTS Handlers
# =====================================================

async def _handle_audio_chunk(ws: WebSocket, session_id: str, payload: dict) -> None:
    """Process an audio chunk: validate → STT → transcript → respond."""
    try:
        audio_bytes, seq, error = decode_audio_payload(payload)

        if error:
            await _send(ws, WSMessageType.ERROR, ErrorPayload(
                message=error,
                code="AUDIO_INVALID",
            ))
            return

        # Feed to STT provider
        stt = get_stt_provider()
        fragment = await stt.feed_audio(session_id, audio_bytes, seq)

        if fragment:
            # Add to transcript assembler
            state, span = transcript_assembler.add_fragment(session_id, fragment)

            # Send transcript partial to client
            await _send(ws, WSMessageType.TRANSCRIPT_PARTIAL, TranscriptPayload(
                text=state.get_current_text(),
                is_final=False,
                fragment_count=len(state.fragments),
                confidence=fragment.confidence,
                span_ids=[span.span_id],
            ))

            # If STT declares final (end of utterance), send transcript_final
            if fragment.is_final:
                await _send(ws, WSMessageType.TRANSCRIPT_FINAL, TranscriptPayload(
                    text=state.get_current_text(),
                    is_final=True,
                    fragment_count=len(state.fragments),
                    confidence=fragment.confidence,
                    span_ids=[s.span_id for s in state.get_spans()],
                ))
                # Save transcript to DB
                await save_transcript(state)
                # Send a mock TTS response
                await _send_mock_tts_response(ws, session_id, state.get_current_text())

    except Exception as e:
        logger.error("Audio chunk error: session=%s error=%s", session_id, str(e), exc_info=True)
        await _send(ws, WSMessageType.ERROR, ErrorPayload(
            message="Audio processing failed",
            code="AUDIO_ERROR",
        ))


async def _handle_stream_end(ws: WebSocket, session_id: str) -> None:
    """Handle end of audio stream (user stopped speaking or cancelled)."""
    try:
        stt = get_stt_provider()
        final_fragment = await stt.end_stream(session_id)

        if final_fragment:
            state, span = transcript_assembler.add_fragment(session_id, final_fragment)

            # Send transcript_final
            await _send(ws, WSMessageType.TRANSCRIPT_FINAL, TranscriptPayload(
                text=state.get_current_text(),
                is_final=True,
                fragment_count=len(state.fragments),
                confidence=final_fragment.confidence,
                span_ids=[s.span_id for s in state.get_spans()],
            ))
            # Save and respond with TTS
            await save_transcript(state)
            await _send_mock_tts_response(ws, session_id, state.get_current_text())

        # Cleanup transcript state
        transcript_assembler.cleanup(session_id)

    except Exception as e:
        logger.error("Stream end error: session=%s error=%s", session_id, str(e))


async def _handle_text_input(ws: WebSocket, session_id: str, payload: dict) -> None:
    """Handle text input as an alternative to voice (STT fallback)."""
    text = payload.get("text", "").strip()
    if not text:
        return

    logger.info("Text input: session=%s text='%s'", session_id, text[:50])

    # Create a synthetic transcript fragment
    from stt.provider.interface import TranscriptFragment
    import uuid

    fragment = TranscriptFragment(
        text=text,
        confidence=1.0,
        is_final=True,
        latency_ms=0,
        fragment_id=str(uuid.uuid4()),
    )

    state, span = transcript_assembler.add_fragment(session_id, fragment)

    # Send transcript_final
    await _send(ws, WSMessageType.TRANSCRIPT_FINAL, TranscriptPayload(
        text=state.get_current_text(),
        is_final=True,
        fragment_count=len(state.fragments),
        confidence=1.0,
        span_ids=[span.span_id],
    ))

    await save_transcript(state)
    await _send_mock_tts_response(ws, session_id, text)


async def _send_mock_tts_response(ws: WebSocket, session_id: str, transcript: str) -> None:
    """Send a TTS response based on the transcript.

    Uses ElevenLabs when MOCK_TTS=false, otherwise falls back to text-only.
    Audio is sent as base64-encoded MP3 in the payload.
    """
    import base64

    # Generate contextual response text
    response_text = _generate_mock_response(transcript)

    # Use TTS provider to synthesize
    tts = get_tts_provider()
    result = await tts.synthesize(response_text)

    if result.audio_bytes and not result.is_mock:
        # Real audio: send as base64 MP3
        audio_b64 = base64.b64encode(result.audio_bytes).decode("ascii")
        payload = TTSAudioPayload(
            text=response_text,
            session_id=session_id,
            format="mp3",
            is_mock=False,
        )
        # Include audio in the raw payload
        payload_dict = payload.model_dump()
        payload_dict["audio"] = audio_b64
        payload_dict["audio_size_bytes"] = len(result.audio_bytes)

        data = _make_envelope(WSMessageType.TTS_AUDIO, payload_dict)
        await ws.send_text(data)
    else:
        # Mock/fallback: send text only (client uses local TTS)
        await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
            text=response_text,
            session_id=session_id,
            format="text",
            is_mock=True,
        ))

    logger.info(
        "TTS response sent: session=%s response='%s'",
        session_id, response_text[:60],
    )


def _generate_mock_response(transcript: str) -> str:
    """Generate a deterministic mock response for testing."""
    lower = transcript.lower()

    if "hello" in lower:
        return "Hello! How can I help you today?"
    elif "send" in lower and "message" in lower:
        return "I understand you'd like to send a message. Who would you like to send it to?"
    elif "meeting" in lower:
        return "I see you're thinking about a meeting. When would you like to schedule it?"
    elif "tomorrow" in lower:
        return "Got it, tomorrow. What time works best for you?"
    elif "confirm" in lower:
        return "I'll prepare that for your review. Please check the draft card."
    else:
        return f"I heard: '{transcript[:50]}'. Could you tell me more about what you'd like to do?"
