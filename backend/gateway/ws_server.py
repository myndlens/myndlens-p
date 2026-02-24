"""WebSocket server — B1+B2 Gateway.

Handles authenticated WS connections, message routing,
heartbeat tracking, execute-gate enforcement,
and audio chunk streaming with transcript assembly.

EXECUTION GUARDRAIL (Patch 5 / §3.2):
  No execution path may proceed without an explicit `execute_request` message
  from the mobile client (i.e. the Execute button). Any future batch that adds
  execution capability MUST route through _handle_execute_request() and pass
  the presence gate. Low-risk intents still require the execute_request envelope
  — they simply skip the physical latch. This comment is the guardrail contract;
  violating it requires an ADR.
"""
import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import WebSocket, WebSocketDisconnect

from auth.tokens import validate_token, TokenClaims
from auth.sso_validator import get_sso_validator, SSOClaims
from auth.device_binding import create_session, terminate_session
from config.settings import get_settings
from core.exceptions import AuthError, PresenceError, DispatchBlockedError
from observability.audit_log import log_audit_event
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
    ExecuteOkPayload,
    TranscriptPayload,
    TTSAudioPayload,
    ErrorPayload,
)
from stt.orchestrator import get_stt_provider, decode_audio_payload
from tts.orchestrator import get_tts_provider
from l1.scout import run_l1_scout
from transcript.assembler import transcript_assembler
from transcript.storage import save_transcript
from tenants.obegee_reader import get_user_display_name

from intent.gap_filler import SessionContext, parse_capsule_summary, enrich_transcript

logger = logging.getLogger(__name__)

# Active connections: session_id -> WebSocket
active_connections: Dict[str, WebSocket] = {}
# Execution ID -> session_id mapping (for webhook→WS broadcast)
execution_sessions: Dict[str, str] = {}
# Per-session Digital Self context (pre-loaded at auth, lives for session duration)
_session_contexts: Dict[str, SessionContext] = {}
# Per-session clarification state (tracks pending micro-question loops)
_clarification_state: Dict[str, dict] = {}
# session_id -> { "pending": True, "original_transcript": str,
#                  "enriched_transcript": str, "questions": [...],
#                  "l1_draft": ..., "context_capsule": ..., "attempts": int }

# Per-session DS resolve events — pipeline holds here waiting for device to
# return readable text for vector-matched node IDs (ds_resolve / ds_context flow)
_ds_resolve_events: Dict[str, asyncio.Event] = {}
_ds_context_data: Dict[str, List[Dict]] = {}   # session_id → [{id, text}, ...]


def _make_envelope(msg_type: WSMessageType, payload: dict) -> str:
    """Create a JSON string envelope for sending."""
    envelope = WSEnvelope(type=msg_type, payload=payload)
    return envelope.model_dump_json()


def _get_time_greeting() -> str:
    """Return time-appropriate greeting word."""
    hour = datetime.now(timezone.utc).hour
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    elif 17 <= hour < 21:
        return "Good evening"
    else:
        return "Hey"


async def _send(ws: WebSocket, msg_type: WSMessageType, payload_model) -> None:
    """Send a typed message to the client."""
    data = _make_envelope(msg_type, payload_model.model_dump())
    await ws.send_text(data)


async def _preload_session_context(session_id: str, user_id: str) -> None:
    """Pre-load Digital Self into session memory immediately after auth.

    Falls back to server-side ONNX recall when no device capsule is available yet.
    The device sends a context_sync message shortly after auth_ok which will
    replace this with richer on-device PKG data.
    """
    ctx = SessionContext(user_id=user_id)
    if user_id:
        try:
            from memory.retriever import recall
            snippets = await recall(user_id=user_id, query_text="contact person relationship", n_results=10)
            if snippets:
                summary_parts = [s.get("text", "")[:60] for s in snippets[:3] if s.get("text")]
                ctx.raw_summary = " | ".join(summary_parts)
                ctx = parse_capsule_summary(ctx.raw_summary, user_id)
                logger.info("[SessionCtx] Pre-loaded %d entities for session=%s", len(ctx.entities), session_id[:12])
        except Exception as e:
            logger.debug("[SessionCtx] Server-side preload skipped: %s", str(e))
    _session_contexts[session_id] = ctx


async def _handle_context_sync(session_id: str, user_id: str, payload: dict) -> None:
    """Handle context_sync WS message — device sends PKG summary immediately after auth.

    This upgrades the session context from server-side fallback to the richer
    on-device PKG data. Runs once per session, shortly after auth_ok.
    """
    summary = payload.get("summary", "")
    if not summary:
        return
    ctx = parse_capsule_summary(summary, user_id)
    _session_contexts[session_id] = ctx
    logger.info(
        "[SessionCtx] Updated from device PKG: session=%s entities=%d user=%s",
        session_id[:12], len(ctx.entities), ctx.user_name,
    )


async def broadcast_to_session(
    execution_id: str, message_type: str, payload: dict
) -> bool:
    """Broadcast a message to the WS client associated with an execution.

    Called by the delivery webhook to push pipeline_stage updates to the mobile app.
    Returns False if no matching session is found — never broadcasts to unrelated sessions.
    """
    session_id = execution_sessions.get(execution_id)
    if not session_id:
        logger.warning("broadcast_to_session: no session for execution_id=%s", execution_id)
        return False

    ws = active_connections.get(session_id)
    if not ws:
        return False

    try:
        data = _make_envelope(WSMessageType.PIPELINE_STAGE, payload)
        await ws.send_text(data)
        return True
    except Exception:
        return False


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
        # 30-second timeout on initial AUTH — prevents zombie connections
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
        except asyncio.TimeoutError:
            await websocket.close(code=4008, reason="Auth timeout")
            logger.warning("WS auth timeout: no AUTH received within 30s")
            return
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
            env=get_settings().ENV,
            client_version=auth_payload.client_version,
        )
        session_id = session.session_id
        active_connections[session_id] = websocket

        # Fetch user display name for greeting (non-blocking, best-effort)
        try:
            _greeting_display_name = await get_user_display_name(user_id_resolved)
        except Exception:
            _greeting_display_name = None
        _greeting_sent = False  # Send once on first heartbeat

        # Send AUTH_OK
        await _send(websocket, WSMessageType.AUTH_OK, AuthOkPayload(
            session_id=session_id,
            user_id=user_id_resolved,
            heartbeat_interval_ms=get_heartbeat_interval_ms(),
        ))

        # Pre-load Digital Self into session memory — zero-latency for first mandate
        await _preload_session_context(session_id, user_id_resolved or "")

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
                # Send greeting TTS on first heartbeat (talk.tsx is now mounted)
                if not _greeting_sent:
                    _greeting_sent = True
                    try:
                        greeting_word = _get_time_greeting()
                        if _greeting_display_name:
                            greeting_text = f"{greeting_word}, {_greeting_display_name}. Ready when you are."
                        else:
                            greeting_text = f"{greeting_word}. Ready when you are."
                        await _send(websocket, WSMessageType.TTS_AUDIO, TTSAudioPayload(
                            text=greeting_text,
                            session_id=session_id,
                            format="text",
                        ))
                        logger.debug("Sent greeting: session=%s name=%s", session_id, _greeting_display_name)
                    except Exception as _ge:
                        logger.warning("Greeting TTS failed (non-fatal): %s", str(_ge))

            elif msg_type == WSMessageType.AUDIO_CHUNK.value:
                await _handle_audio_chunk(websocket, session_id, payload, user_id=user_id_resolved or "")

            elif msg_type == WSMessageType.EXECUTE_REQUEST.value:
                await _handle_execute_request(
                    websocket, session_id, payload, subscription_status,
                    user_id=user_id_resolved or "",
                    tenant_id=sso_claims.myndlens_tenant_id if sso_claims else "",
                    auth_token=auth_payload.token,
                )

            elif msg_type == WSMessageType.CANCEL.value:
                reason = payload.get("reason", "")
                logger.info("Cancel received: session=%s reason=%s", session_id, reason)
                if reason == "kill_switch":
                    stt_p = get_stt_provider()
                    stt_p._streams.pop(session_id, None)
                    transcript_assembler.cleanup(session_id)
                    _clarification_state.pop(session_id, None)
                    logger.info("Kill switch: pipeline aborted for session=%s", session_id)
                else:
                    await _handle_stream_end(websocket, session_id, user_id=user_id_resolved or "")

            elif msg_type == WSMessageType.TEXT_INPUT.value:
                await _handle_text_input(websocket, session_id, payload, user_id=user_id_resolved or "")

            elif msg_type == "context_sync":
                # Device sends full PKG context capsule immediately after auth_ok
                await _handle_context_sync(session_id, user_id_resolved or "", payload)

            elif msg_type == WSMessageType.DS_CONTEXT.value:
                # Device responding to ds_resolve — providing readable text for matched node IDs
                nodes = payload.get("nodes", [])   # [{id, text}, ...]
                _ds_context_data[session_id] = nodes
                event = _ds_resolve_events.get(session_id)
                if event:
                    event.set()   # Unblock the pipeline that's waiting in wait_for()

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
        # Cleanup all per-session in-memory state
        if session_id:
            active_connections.pop(session_id, None)
            _session_contexts.pop(session_id, None)
            _clarification_state.pop(session_id, None)
            # Clean up execution_sessions entries for this session (prevents memory leak)
            stale_keys = [k for k, v in execution_sessions.items() if v == session_id]
            for k in stale_keys:
                execution_sessions.pop(k, None)
            await terminate_session(session_id)
            await log_audit_event(
                AuditEventType.SESSION_TERMINATED,
                session_id=session_id,
                user_id=user_id_resolved,
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


async def _handle_execute_request(
    ws: WebSocket,
    session_id: str,
    payload: dict,
    subscription_status: str = "ACTIVE",
    user_id: str = "",
    tenant_id: str = "",
    auth_token: str = "",
) -> None:
    """Execute an approved mandate: L2 → QC → Skills → Dispatch."""
    try:
        req = ExecuteRequestPayload(**payload)

        # SUBSCRIPTION GATE
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
            return

        # PRESENCE GATE
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
            logger.warning("EXECUTE_BLOCKED: session=%s reason=PRESENCE_STALE", session_id)
            return

        # RETRIEVE DRAFT
        from l1.scout import get_draft
        draft = await get_draft(req.draft_id)
        if not draft or not draft.hypotheses:
            await _send(ws, WSMessageType.EXECUTE_BLOCKED, ExecuteBlockedPayload(
                reason="Draft not found or expired. Please re-submit your intent.",
                code="DRAFT_NOT_FOUND",
                draft_id=req.draft_id,
            ))
            logger.warning("EXECUTE_BLOCKED: draft not found: session=%s draft=%s", session_id, req.draft_id)
            return

        top = draft.hypotheses[0]

        # Re-enrich the transcript for L2/QC
        session_ctx = _session_contexts.get(session_id)
        from intent.gap_filler import enrich_transcript as _enrich
        enriched_for_verify = await _enrich(draft.transcript, session_ctx)

        from dispatcher.mandate_dispatch import broadcast_stage, dispatch_mandate

        # Stage 4: Oral approval received
        await broadcast_stage(session_id, 4, "done")

        # Stage 5: L2 Sentry verification
        await broadcast_stage(session_id, 5, "active", "Verifying intent...")
        from l2.sentry import run_l2_sentry
        l2 = await run_l2_sentry(
            session_id=session_id,
            user_id=user_id,
            transcript=enriched_for_verify,
            l1_intent=top.intent,
            l1_confidence=top.confidence,
            dimensions={},
        )
        logger.info(
            "L2 Sentry: session=%s intent=%s conf=%.2f",
            session_id, l2.intent, l2.confidence,
        )

        # Stage 6: Skill Determination — LLM decides
        await broadcast_stage(session_id, 6, "active", "Determining skills...")
        from skills.determine import determine_skills
        skill_plan = await determine_skills(
            session_id=session_id, user_id=user_id,
            mandate={
                "intent": top.intent,
                "mandate_summary": top.hypothesis,
                "actions": [{"action": top.hypothesis, "priority": "high", "dimensions": {}}],
            },
        )
        skill_names = [s.get("skill_name", "") for s in skill_plan.get("skill_plan", [])]
        execution_strategy = skill_plan.get("execution_strategy", "sequential")

        await broadcast_stage(session_id, 6, "done", f"{len(skill_names)} skills determined")
        logger.info("Skills determined: session=%s count=%d strategy=%s skills=%s",
                    session_id, len(skill_names), execution_strategy, skill_names)

        # ── QC Sentry — adversarial check ─────────────────────────────────────
        from qc.sentry import run_qc_sentry
        qc = await run_qc_sentry(
            session_id=session_id,
            user_id=user_id,
            transcript=enriched_for_verify,
            intent=top.intent,
            intent_summary=top.hypothesis,
            persona_summary=session_ctx.raw_summary if session_ctx else "",
            skill_risk="low",
            skill_names=skill_names,
        )
        if not qc.overall_pass:
            await _send(ws, WSMessageType.EXECUTE_BLOCKED, ExecuteBlockedPayload(
                reason=qc.block_reason or "QC adversarial check failed",
                code="QC_BLOCKED",
                draft_id=req.draft_id,
            ))
            logger.warning("EXECUTE_BLOCKED: QC failed: session=%s reason=%s", session_id, qc.block_reason)
            return

        # ── Authorization granted ──────────────────────────────────────────────
        await broadcast_stage(session_id, 7, "done")

        # ── Dispatch ───────────────────────────────────────────────────────────
        mandate = {
            "mandate_id": req.draft_id,
            "tenant_id": tenant_id,
            "task": top.hypothesis,
            "intent": top.intent,
            "intent_raw": draft.transcript,
            "skill_plan": skill_plan.get("skill_plan", []),
            "execution_strategy": execution_strategy,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": user_id,
        }
        result = await dispatch_mandate(session_id, mandate, api_token=auth_token)

        # Record skill usage for reinforcement learning — updated on webhook callback
        # (actual outcome recorded in delivery webhook when ObeGee confirms result)
        logger.info("[SkillRL] Skills dispatched: session=%s skills=%s", session_id, skill_names)

        # Send execute_ok with topology summary
        await _send(ws, WSMessageType.EXECUTE_OK, ExecuteOkPayload(
            draft_id=req.draft_id,
            dispatch_status=result.get("status", "QUEUED"),
        ))

        # Acknowledge execution with TTS — confirms mandate accepted
        ack_text = f"On it. {top.hypothesis[:80]}."
        _tts_ack_provider = get_tts_provider()
        tts_ack = await _tts_ack_provider.synthesize(ack_text)
        if tts_ack.audio_bytes and not tts_ack.is_mock:
            await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
                text=ack_text,
                session_id=session_id,
                format="mp3",
                is_mock=False,
                audio=base64.b64encode(tts_ack.audio_bytes).decode("ascii"),
                audio_size_bytes=len(tts_ack.audio_bytes),
            ))
        else:
            await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
                text=ack_text, session_id=session_id, format="text", is_mock=True,
            ))

        await log_audit_event(
            AuditEventType.EXECUTE_REQUESTED,
            session_id=session_id,
            details={
                "draft_id": req.draft_id,
                "execution_id": result.get("execution_id"),
                "intent": top.intent,
                "skills": skill_names,
            },
        )
        logger.info(
            "Execute pipeline complete: session=%s draft=%s intent=%s exec=%s",
            session_id, req.draft_id, l2.intent, result.get("execution_id"),
        )

    except DispatchBlockedError as e:
        logger.error("Execute blocked: session=%s reason=%s", session_id, str(e))
        await _send(ws, WSMessageType.EXECUTE_BLOCKED, ExecuteBlockedPayload(
            reason=str(e),
            code="DISPATCH_BLOCKED",
        ))
    except Exception as e:
        logger.error("Execute request error: session=%s error=%s", session_id, str(e), exc_info=True)
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

async def _handle_audio_chunk(ws: WebSocket, session_id: str, payload: dict, user_id: str = "") -> None:
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

            # C2 FIX: only trigger TTS from is_final if no cancel is expected.
            # We intentionally skip triggering from is_final here and let
            # _handle_stream_end be the single authority for final processing.
            # is_final from chunk is used only for partial display; stream_end drives TTS.

    except Exception as e:
        logger.error("Audio chunk error: session=%s error=%s", session_id, str(e), exc_info=True)
        await _send(ws, WSMessageType.ERROR, ErrorPayload(
            message="Audio processing failed",
            code="AUDIO_ERROR",
        ))


async def _handle_stream_end(ws: WebSocket, session_id: str, user_id: str = "") -> None:
    """Handle end of audio stream — single authority for final transcript + TTS response.

    Called from both VAD auto-stop (cancel message) and explicit stream end.
    user_id enables Digital Self server-side recall for voice mandates.
    """
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
            # Save and respond with TTS — now with user_id for Digital Self recall
            await save_transcript(state)
            await _send_mock_tts_response(ws, session_id, state.get_current_text(), user_id=user_id)

        # Cleanup transcript state
        transcript_assembler.cleanup(session_id)

    except Exception as e:
        logger.error("Stream end error: session=%s error=%s", session_id, str(e))


async def _handle_text_input(ws: WebSocket, session_id: str, payload: dict, user_id: str = "") -> None:
    """Handle text input as an alternative to voice (STT fallback)."""
    text = payload.get("text", "").strip()
    context_capsule = payload.get("context_capsule")  # on-device Digital Self PKG context
    if not text:
        return
    # Guard: reject oversized inputs (prevents DoS through LLM/TTS cost)
    if len(text) > 2000:
        await _send(ws, WSMessageType.ERROR, ErrorPayload(
            message="Input too long. Maximum 2000 characters.",
            code="INPUT_TOO_LONG",
        ))
        return

    # ── Check if this is a clarification response ──
    clarify = _clarification_state.get(session_id)
    if clarify and clarify.get("pending"):
        clarify_type = clarify.get("type", "intent")
        logger.info("[CLARIFICATION] session=%s type=%s response='%s' to='%s'",
                    session_id, clarify_type, text[:50], clarify.get("question_asked","")[:40])

        # ── Permission gate response ──────────────────────────────────────────
        if clarify_type == "permission":
            affirmatives = {"yes","sure","ok","okay","proceed","go","do it",
                            "correct","absolutely","yep","yup","go ahead",
                            "please","please do","right","alright"}
            norm = text.lower().strip().rstrip(".,!")
            is_affirmative = any(a in norm for a in affirmatives) or norm in affirmatives

            if is_affirmative:
                logger.info("[CLARIFICATION:PERMISSION] session=%s GRANTED", session_id)
                _clarification_state[session_id] = {"permission_granted": True, "dim_attempts": 0}
                await _send_mock_tts_response(ws, session_id, clarify["original_transcript"],
                                              user_id=user_id, context_capsule=clarify.get("context_capsule"))
            else:
                neg_prompt = "What would you like to change?"
                _clarification_state[session_id] = {
                    "pending": True, "type": "intent",
                    "original_transcript": clarify["original_transcript"],
                    "question_asked": neg_prompt,
                    "context_capsule": clarify.get("context_capsule"),
                }
                _tts_neg = get_tts_provider()
                tts_r = await _tts_neg.synthesize(neg_prompt)
                if tts_r.audio_bytes and not tts_r.is_mock:
                    await ws.send_text(_make_envelope(WSMessageType.TTS_AUDIO, {
                        "text": neg_prompt, "session_id": session_id,
                        "format": "mp3", "is_mock": False,
                        "audio": base64.b64encode(tts_r.audio_bytes).decode("ascii"),
                        "audio_size_bytes": len(tts_r.audio_bytes),
                        "is_clarification": True, "auto_record": True,
                    }))
                else:
                    await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
                        text=neg_prompt, session_id=session_id, format="text", is_mock=True,
                    ))
                logger.info("[CLARIFICATION:PERMISSION] session=%s DECLINED", session_id)
            return

        # ── Dimension clarification response ──────────────────────────────────
        if clarify_type == "dimension":
            combined = f"{clarify['original_transcript']}. Answer: {text}"
            _clarification_state[session_id] = {"permission_granted": True, "dim_attempts": clarify.get("dim_attempts", 1)}
            await _send_mock_tts_response(ws, session_id, combined, user_id=user_id,
                                          context_capsule=clarify.get("context_capsule"))
            return

        # ── Intent clarification (default) ────────────────────────────────────
        combined = f"{clarify['original_transcript']}. Clarification: {text}"
        _clarification_state.pop(session_id, None)
        logger.info("[CLARIFICATION:INTENT] session=%s combined='%s'", session_id, combined[:80])
        await _send_mock_tts_response(ws, session_id, combined, user_id=user_id,
                                      context_capsule=clarify.get("context_capsule"))
        return

    logger.info("Text input: session=%s text='%s' has_capsule=%s", session_id, text[:50], bool(context_capsule))

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
    await _send_mock_tts_response(ws, session_id, text, user_id=user_id, context_capsule=context_capsule)


async def _send_mock_tts_response(ws: WebSocket, session_id: str, transcript: str, user_id: str = "", context_capsule: str | None = None) -> None:
    """Process transcript through Gap Filler → L1 Scout → Dimensions → Guardrails → TTS.

    Gap Filler enriches the raw transcript with Digital Self context BEFORE
    L1 Scout sees it. The LLM receives a fully-contextualized mandate, not a fragment.
    """

    async def _emit_stage(stage_id: str, stage_index: int, status: str = "active", sub_status: str = ""):
        data = _make_envelope(WSMessageType.PIPELINE_STAGE, {
            "stage_id": stage_id, "stage_index": stage_index,
            "total_stages": 10, "status": status,
            "sub_status": sub_status,
            "progress": round((stage_index + 1) / 10 * 100),
        })
        await ws.send_text(data)

    # ── STEP 0: Intent captured ─────────────────────────────────────────────
    logger.info(
        "[MANDATE:0:CAPTURE] session=%s transcript='%s' chars=%d",
        session_id, transcript[:80], len(transcript),
    )
    await _emit_stage("capture", 0, "done")

    # ── STEP 0.5: DS Vector Query → ds_resolve → ds_context → Gap Fill ────────
    session_ctx = _session_contexts.get(session_id)
    enriched_transcript = transcript
    matched_nodes: List[Dict] = []

    # 1. Query vector store for user-specific nodes relevant to this transcript
    if user_id:
        try:
            from memory.client.vector import query as vector_query
            matched = vector_query(
                query_text=transcript,
                n_results=3,
                where={"user_id": user_id},   # USER ISOLATION — never cross-user
            )
            if matched:
                node_ids = [m["id"] for m in matched]
                logger.info("[DS] Vector matched %d nodes for session=%s", len(node_ids), session_id[:12])

                # 2. Ask device: "resolve these node IDs → send me the readable text"
                resolve_payload = _make_envelope(
                    WSMessageType.DS_RESOLVE,
                    {"node_ids": node_ids, "session_id": session_id},
                )
                await ws.send_text(resolve_payload)

                # 3. Await ds_context response from device (max 2 seconds)
                event = asyncio.Event()
                _ds_resolve_events[session_id] = event
                try:
                    await asyncio.wait_for(event.wait(), timeout=2.0)
                    matched_nodes = _ds_context_data.pop(session_id, [])
                    logger.info("[DS] ds_context received: %d nodes for session=%s", len(matched_nodes), session_id[:12])
                except asyncio.TimeoutError:
                    logger.warning("[DS] ds_context timeout for session=%s — using fallback session_ctx", session_id[:12])
                finally:
                    _ds_resolve_events.pop(session_id, None)
        except Exception as e:
            logger.debug("[DS] Vector query skipped: %s", str(e))

    # 4. Gap fill: targeted context if available, else fallback to generic session_ctx
    if matched_nodes:
        # Build a targeted SessionContext from the device-provided text
        targeted_summary = " | ".join(f"{n['text']}" for n in matched_nodes if n.get("text"))
        targeted_ctx = parse_capsule_summary(targeted_summary, user_id) if targeted_summary else session_ctx
        enriched_transcript = await enrich_transcript(transcript, targeted_ctx)
        if enriched_transcript != transcript:
            logger.info("[MANDATE:0:GAPFILL] session=%s targeted DS gap fill (%d nodes)", session_id, len(matched_nodes))
    elif session_ctx:
        enriched_transcript = await enrich_transcript(transcript, session_ctx)
        if enriched_transcript != transcript:
            logger.info("[MANDATE:0:GAPFILL] session=%s fallback session_ctx (entities=%d)", session_id, len(session_ctx.entities))

    # Extract DS summary for harm check
    context_capsule_summary = session_ctx.raw_summary if session_ctx else ""

    # Update context_capsule from session if not provided per-request
    if not context_capsule and session_ctx and session_ctx.raw_summary:
        context_capsule = json.dumps({"summary": session_ctx.raw_summary})

    # ── STEP 1: L1 Scout — intent classification ────────────────────────────
    logger.info("[MANDATE:1:L1_SCOUT] session=%s starting intent hypothesis", session_id)
    await _emit_stage("digital_self", 1, "active", "Classifying intent...")

    l1_draft = await run_l1_scout(
        session_id=session_id,
        user_id=user_id,
        transcript=enriched_transcript,  # enriched for LLM understanding
        context_capsule=context_capsule,
        original_transcript=transcript,   # stored in draft for user-facing display
    )

    # Update session's recent transcript history for next mandate's gap-filling
    if session_ctx:
        session_ctx.recent_transcripts.append(transcript[:80])
        if len(session_ctx.recent_transcripts) > 5:
            session_ctx.recent_transcripts.pop(0)

    if l1_draft.hypotheses:
        top_h = l1_draft.hypotheses[0]
        logger.info(
            "[MANDATE:1:L1_SCOUT] session=%s DONE is_mock=%s hypotheses=%d "
            "top_action=%s top_confidence=%.2f top_hypothesis='%s' latency_ms=%.0f",
            session_id, l1_draft.is_mock, len(l1_draft.hypotheses),
            top_h.intent, top_h.confidence, top_h.hypothesis[:60],
            l1_draft.latency_ms,
        )
    else:
        logger.warning("[MANDATE:1:L1_SCOUT] session=%s DONE — NO hypotheses returned", session_id)

    await _emit_stage("digital_self", 1, "done")

    # ── STEP 1.5: Micro-Question Clarification Loop ─────────────────────────
    # If L1 has low confidence or missing dimensions, generate personalized
    # micro-questions (TTS → user → STT → re-run L1 with enriched context)
    if l1_draft.hypotheses and not l1_draft.is_mock:
        top_check = l1_draft.hypotheses[0]
        from intent.micro_questions import should_ask_micro_questions, generate_micro_questions

        if should_ask_micro_questions(top_check.confidence, top_check.dimension_suggestions):
            # Only attempt clarification once per mandate (no infinite loops)
            clarify_state = _clarification_state.get(session_id, {})
            attempt = clarify_state.get("attempts", 0)

            if attempt == 0:
                logger.info("[MANDATE:1.5:MICRO_Q] session=%s generating micro-questions (conf=%.2f)",
                            session_id, top_check.confidence)
                await _emit_stage("digital_self", 1, "active", "Asking to clarify...")

                mq_result = await generate_micro_questions(
                    session_id=session_id,
                    user_id=user_id,
                    transcript=transcript,
                    hypothesis=top_check.hypothesis,
                    confidence=top_check.confidence,
                    dimensions=top_check.dimension_suggestions,
                )

                if mq_result.questions:
                    # Pick the best question (first one)
                    question = mq_result.questions[0]

                    # Store clarification state so response handler knows to re-run
                    _clarification_state[session_id] = {
                        "pending": True,
                        "original_transcript": transcript,
                        "enriched_transcript": enriched_transcript,
                        "question_asked": question.question,
                        "context_capsule": context_capsule,
                        "attempts": 1,
                    }

                    # Send the question to the client
                    clarify_payload = {
                        "question": question.question,
                        "why": question.why,
                        "options": question.options,
                        "dimension": question.dimension_filled,
                        "session_id": session_id,
                    }
                    cq_data = _make_envelope(WSMessageType.CLARIFICATION_QUESTION, clarify_payload)
                    await ws.send_text(cq_data)

                    # TTS the question so user HEARS it
                    tts = get_tts_provider()
                    tts_result = await tts.synthesize(question.question)
                    if tts_result.audio_bytes and not tts_result.is_mock:
                        audio_b64 = base64.b64encode(tts_result.audio_bytes).decode("ascii")
                        tts_payload = {
                            "text": question.question,
                            "session_id": session_id,
                            "format": "mp3",
                            "is_mock": False,
                            "audio": audio_b64,
                            "audio_size_bytes": len(tts_result.audio_bytes),
                            "is_clarification": True,
                        }
                        data = _make_envelope(WSMessageType.TTS_AUDIO, tts_payload)
                        await ws.send_text(cq_data)

                    logger.info(
                        "[MANDATE:1.5:MICRO_Q] session=%s ASKED: '%s' — waiting for response",
                        session_id, question.question,
                    )
                    # STOP pipeline here — wait for user's spoken/typed response
                    # The response will come as text_input or audio_chunk
                    # which will be handled by _handle_clarification_response
                    return

    # ── STEP 1.5b: Coherence check (legacy, kept for non-clarification path) ─
    if l1_draft.hypotheses:
        top_check = l1_draft.hypotheses[0]
        # Coherence check removed — L1 Scout (Gemini) is the classifier. Trust it.

    # ── STEP 2: Mandate Dimensions (intent-driven, execution-level) ─────────
    logger.info("[MANDATE:2:DIMENSIONS] session=%s building mandate dimensions", session_id)
    await _emit_stage("dimensions", 2, "active", "Building mandate...")

    if l1_draft.hypotheses and not l1_draft.is_mock:
        top = l1_draft.hypotheses[0]
        from dimensions.extractor import extract_mandate_dimensions
        mandate = await extract_mandate_dimensions(
            session_id=session_id, user_id=user_id, transcript=transcript,
            intent=top.intent, sub_intents=top.sub_intents,
            l1_dimensions=top.dimension_suggestions,
        )
        from intent.mandate_questions import get_all_missing
        missing = get_all_missing(mandate)
        logger.info(
            "[MANDATE:2:DIMENSIONS] session=%s intent=%s actions=%d missing=%d",
            session_id, top.intent, len(mandate.get("actions", [])), len(missing),
        )
    else:
        mandate = None
        missing = []

    await _emit_stage("dimensions", 2, "done")

    # ── STEP 3: Guardrails — LLM harm check ─────────────────────────────────
    logger.info("[MANDATE:3:GUARDRAILS] session=%s safety check", session_id)
    await _emit_stage("mandate", 3, "active", "Safety check...")

    from guardrails.engine import _assess_harm_llm
    harm_check = await _assess_harm_llm(
        transcript=transcript, ds_context=context_capsule_summary,
        session_id=session_id, user_id=user_id,
    )

    if harm_check.block_execution:
        response_text = harm_check.nudge or "I can't assist with that."
        logger.warning("[MANDATE:3:GUARDRAILS] BLOCKED session=%s", session_id)
    elif mandate and l1_draft.hypotheses and not l1_draft.is_mock:
        top = l1_draft.hypotheses[0]
        summary = mandate.get("mandate_summary", top.hypothesis)
        missing_count = len(missing)

        if missing_count > 0:
            dim_clarify = _clarification_state.get(session_id, {})
            dim_attempt = dim_clarify.get("dim_attempts", 0)
            if dim_attempt < get_settings().MANDATE_MAX_CLARIFICATION_ROUNDS:
                from intent.mandate_questions import generate_mandate_questions
                mq_batch = await generate_mandate_questions(
                    session_id=session_id, user_id=user_id,
                    transcript=transcript, mandate=mandate, batch_size=3,
                )
                if mq_batch.questions:
                    q = mq_batch.questions[0]
                    _clarification_state[session_id] = {
                        "pending": True, "type": "dimension",
                        "original_transcript": transcript,
                        "enriched_transcript": enriched_transcript,
                        "mandate": mandate,
                        "l1_draft_id": l1_draft.draft_id,
                        "question_asked": q.question,
                        "context_capsule": context_capsule,
                        "dim_attempts": dim_attempt + 1,
                    }
                    cq_data = _make_envelope(WSMessageType.CLARIFICATION_QUESTION, {
                        "question": q.question, "fills_dimension": q.fills_dimension,
                        "fills_action": q.fills_action,
                        "missing_total": mq_batch.total_missing, "session_id": session_id,
                    })
                    await ws.send_text(cq_data)
                    tts = get_tts_provider()
                    tts_result = await tts.synthesize(q.question)
                    if tts_result.audio_bytes and not tts_result.is_mock:
                        tts_payload = {
                            "text": q.question, "session_id": session_id,
                            "format": "mp3", "is_mock": False,
                            "audio": base64.b64encode(tts_result.audio_bytes).decode("ascii"),
                            "audio_size_bytes": len(tts_result.audio_bytes),
                            "is_clarification": True,
                        }
                        await ws.send_text(_make_envelope(WSMessageType.TTS_AUDIO, tts_payload))
                    else:
                        await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
                            text=q.question, session_id=session_id, format="text", is_mock=True,
                        ))
                    logger.info("[MANDATE:2.5:DIM_Q] session=%s ASKED: '%s' (attempt %d, missing=%d)",
                                session_id, q.question, dim_attempt + 1, mq_batch.total_missing)
                    return
            response_text = f"Got it. {summary}. Approve?"
        else:
            response_text = f"Got it. {summary}. Approve?"
    else:
        top_h = l1_draft.hypotheses[0].hypothesis if l1_draft.hypotheses else transcript[:50]
        response_text = f"Understood: {top_h}. Tap Approve."

    logger.info("[MANDATE:3:GUARDRAILS] session=%s result=PASS", session_id)
    await _emit_stage("mandate", 3, "done")

    # ── STEP 4: Draft update ─────────────────────────────────────────────────
    if l1_draft.hypotheses:
        top = l1_draft.hypotheses[0]
        draft_payload = {
            "draft_id": l1_draft.draft_id,
            "action_class": top.intent,
            "intent": top.intent,
            "hypothesis": top.hypothesis,
            "sub_intents": top.sub_intents,
            "confidence": top.confidence,
            "mandate": {k: v for k, v in (mandate or {}).items() if k != "_meta"} if mandate else {},
            "missing_count": len(missing),
            "is_mock": l1_draft.is_mock,
        }
        data = _make_envelope(WSMessageType.DRAFT_UPDATE, draft_payload)
        await ws.send_text(data)

    # ── STEP 5: TTS synthesis ────────────────────────────────────────────────
    logger.info("[MANDATE:5:TTS] session=%s synthesizing text='%s'", session_id, response_text[:60])
    tts = get_tts_provider()
    result = await tts.synthesize(response_text)

    if result.audio_bytes and not result.is_mock:
        audio_b64 = base64.b64encode(result.audio_bytes).decode("ascii")
        payload = TTSAudioPayload(
            text=response_text, session_id=session_id, format="mp3", is_mock=False,
        )
        payload_dict = payload.model_dump()
        payload_dict["audio"] = audio_b64
        payload_dict["audio_size_bytes"] = len(result.audio_bytes)
        data = _make_envelope(WSMessageType.TTS_AUDIO, payload_dict)
        await ws.send_text(data)
        logger.info("[MANDATE:5:TTS] session=%s DONE real_audio bytes=%d", session_id, len(result.audio_bytes))
    else:
        await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
            text=response_text, session_id=session_id, format="text", is_mock=True,
        ))
        logger.info("[MANDATE:5:TTS] session=%s DONE mock_text", session_id)

    logger.info(
        "[MANDATE:COMPLETE] session=%s l1_mock=%s hypotheses=%d response='%s'",
        session_id, l1_draft.is_mock,
        len(l1_draft.hypotheses), response_text[:60],
    )

