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
import asyncio
import json
import logging
from typing import Dict

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
from dimensions.engine import get_dimension_state, cleanup_dimensions
from guardrails.engine import check_guardrails
from transcript.assembler import transcript_assembler
from transcript.storage import save_transcript

from intent.gap_filler import SessionContext, parse_capsule_summary, enrich_transcript, check_extraction_coherence

logger = logging.getLogger(__name__)

# Active connections: session_id -> WebSocket
active_connections: Dict[str, WebSocket] = {}
# Execution ID -> session_id mapping (for webhook→WS broadcast)
execution_sessions: Dict[str, str] = {}
# Per-session Digital Self context (pre-loaded at auth, lives for session duration)
_session_contexts: Dict[str, SessionContext] = {}


def _make_envelope(msg_type: WSMessageType, payload: dict) -> str:
    """Create a JSON string envelope for sending."""
    envelope = WSEnvelope(type=msg_type, payload=payload)
    return envelope.model_dump_json()


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
                logger.info("Cancel received: session=%s", session_id)
                await _handle_stream_end(websocket, session_id, user_id=user_id_resolved or "")

            elif msg_type == WSMessageType.TEXT_INPUT.value:
                await _handle_text_input(websocket, session_id, payload, user_id=user_id_resolved or "")

            elif msg_type == "context_sync":
                # Device sends full PKG context capsule immediately after auth_ok
                await _handle_context_sync(session_id, user_id_resolved or "", payload)

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
            cleanup_dimensions(session_id)
            _session_contexts.pop(session_id, None)  # Release session Digital Self context
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
        dim_state = get_dimension_state(session_id)

        # Re-enrich the transcript for L2/QC — session context is still alive
        session_ctx = _session_contexts.get(session_id)
        from intent.gap_filler import enrich_transcript as _enrich
        enriched_for_verify = await _enrich(draft.transcript, session_ctx)

        from dispatcher.mandate_dispatch import broadcast_stage, dispatch_mandate

        # Stage 4: Oral approval received — done
        await broadcast_stage(session_id, 4, "done")

        # Stage 5: L2 Sentry verification (with enriched transcript + DS context)
        await broadcast_stage(session_id, 5, "active", "Verifying intent...")
        from l2.sentry import run_l2_sentry
        l2 = await run_l2_sentry(
            session_id=session_id,
            user_id=user_id,
            transcript=enriched_for_verify,
            l1_action_class=top.action_class,
            l1_confidence=top.confidence,
            dimensions=dim_state.to_dict(),
        )
        logger.info(
            "L2 Sentry: session=%s action=%s conf=%.2f agrees=%s",
            session_id, l2.action_class, l2.confidence, l2.shadow_agrees_with_l1,
        )

        # L1/L2 disagreement — use L2 as authoritative (shadow derivation principle)
        effective_action = l2.action_class
        if not l2.shadow_agrees_with_l1 and l2.conflicts:
            logger.warning(
                "L1/L2 disagreement: session=%s L1=%s L2=%s conflicts=%s",
                session_id, top.action_class, l2.action_class, l2.conflicts,
            )
            # L2 (independent derivation) overrides L1 for dispatch
            # The user confirmed the intent — L2 resolves the ambiguity silently

        # QC Sentry (with enriched transcript + Digital Self persona baseline)
        from qc.sentry import run_qc_sentry
        qc = await run_qc_sentry(
            session_id=session_id,
            user_id=user_id,
            transcript=enriched_for_verify,
            action_class=effective_action,
            intent_summary=top.hypothesis,
            persona_summary=session_ctx.raw_summary if session_ctx else "",
        )
        if not qc.overall_pass:
            await _send(ws, WSMessageType.EXECUTE_BLOCKED, ExecuteBlockedPayload(
                reason=qc.block_reason or "QC adversarial check failed",
                code="QC_BLOCKED",
                draft_id=req.draft_id,
            ))
            logger.warning("EXECUTE_BLOCKED: QC failed: session=%s reason=%s", session_id, qc.block_reason)
            return

        # Stage 5: Agent assignment (L2/QC complete, now assign agent)
        assigned_agent_id = None
        if tenant_id:
            from agents.builder import AgentBuilder
            builder = AgentBuilder()
            tenant_agents = await builder.list_agents(tenant_id)
            if tenant_agents:
                assigned_agent_id = tenant_agents[0]["agent_id"]
                agent_name = tenant_agents[0].get("name", assigned_agent_id)
                logger.info("Agent assigned: session=%s agent=%s", session_id, assigned_agent_id)
                await broadcast_stage(session_id, 5, "done", f"Agent: {agent_name}")
            else:
                await broadcast_stage(session_id, 5, "done", "Default agent")
        else:
            await broadcast_stage(session_id, 5, "done", "Agent assigned")

        # Stage 6: Skills matching
        await broadcast_stage(session_id, 6, "active", "Matching skills...")
        from skills.library import match_skills_to_intent
        matched_skills = await match_skills_to_intent(draft.transcript, top_n=3)
        skill_names = [s.get("name", "") for s in matched_skills if s.get("name")]
        await broadcast_stage(session_id, 6, "done", f"{len(skill_names)} skills matched")
        logger.info("Skills matched: session=%s count=%d skills=%s", session_id, len(skill_names), skill_names)

        # Stage 7: Authorization granted
        await broadcast_stage(session_id, 7, "done")

        # Dispatch mandate
        mandate = {
            "mandate_id": req.draft_id,
            "tenant_id": tenant_id,
            "intent": top.hypothesis,
            "action_class": l2.action_class,
            "dimensions": dim_state.to_dict(),
            "generated_skills": skill_names,
            "assigned_agent_id": assigned_agent_id,
        }
        result = await dispatch_mandate(session_id, mandate, api_token=auth_token)

        # Send execute_ok
        await _send(ws, WSMessageType.EXECUTE_OK, ExecuteOkPayload(
            draft_id=req.draft_id,
            dispatch_status=result.get("status", "QUEUED"),
        ))

        await log_audit_event(
            AuditEventType.EXECUTE_REQUESTED,
            session_id=session_id,
            details={
                "draft_id": req.draft_id,
                "execution_id": result.get("execution_id"),
                "action_class": l2.action_class,
                "skills": skill_names,
            },
        )
        logger.info(
            "Execute pipeline complete: session=%s draft=%s action=%s exec=%s",
            session_id, req.draft_id, l2.action_class, result.get("execution_id"),
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
    import base64

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

    # ── STEP 0.5: Gap filling — enrich fragment with Digital Self ───────────
    session_ctx = _session_contexts.get(session_id)
    if session_ctx:
        enriched_transcript = await enrich_transcript(transcript, session_ctx)
        if enriched_transcript != transcript:
            logger.info("[MANDATE:0:GAPFILL] session=%s enriched (DS entities=%d)", session_id, len(session_ctx.entities))
    else:
        enriched_transcript = transcript

    # Update context_capsule from session if not provided per-request
    if not context_capsule and session_ctx and session_ctx.raw_summary:
        import json as _json
        context_capsule = _json.dumps({"summary": session_ctx.raw_summary})

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
            top_h.action_class, top_h.confidence, top_h.hypothesis[:60],
            l1_draft.latency_ms,
        )
    else:
        logger.warning("[MANDATE:1:L1_SCOUT] session=%s DONE — NO hypotheses returned", session_id)

    await _emit_stage("digital_self", 1, "done")

    # ── STEP 1.5: Extraction-time coherence check (no LLM, zero latency) ───
    if l1_draft.hypotheses:
        top_check = l1_draft.hypotheses[0]
        coherent, adjusted_conf = check_extraction_coherence(
            transcript, top_check.action_class, top_check.confidence
        )
        if not coherent:
            top_check.confidence = adjusted_conf
            logger.info(
                "[MANDATE:1.5:COHERENCE] session=%s action=%s downgraded to conf=%.2f",
                session_id, top_check.action_class, adjusted_conf,
            )

    # ── STEP 2: Dimensions extraction ───────────────────────────────────────
    logger.info("[MANDATE:2:DIMENSIONS] session=%s updating A-set + B-set", session_id)
    await _emit_stage("dimensions", 2, "active", "Extracting dimensions...")

    dim_state = get_dimension_state(session_id)
    if l1_draft.hypotheses:
        top = l1_draft.hypotheses[0]
        dim_state.update_from_suggestions(top.dimension_suggestions)

    logger.info(
        "[MANDATE:2:DIMENSIONS] session=%s DONE a_set=%s "
        "ambiguity=%.2f urgency=%.2f emotional_load=%.2f turn=%d",
        session_id, dim_state.a_set.to_dict(),
        dim_state.b_set.ambiguity, dim_state.b_set.urgency,
        dim_state.b_set.emotional_load, dim_state.turn_count,
    )
    await _emit_stage("dimensions", 2, "done")

    # ── STEP 3: Guardrails check ─────────────────────────────────────────────
    logger.info("[MANDATE:3:GUARDRAILS] session=%s running checks", session_id)
    await _emit_stage("mandate", 3, "active", "Creating mandate artefact...")

    guardrail = check_guardrails(transcript, dim_state, l1_draft)

    logger.info(
        "[MANDATE:3:GUARDRAILS] session=%s result=%s block=%s reason='%s'",
        session_id, guardrail.result.value, guardrail.block_execution, guardrail.reason,
    )

    if guardrail.block_execution:
        response_text = guardrail.nudge or "I need a bit more clarity before proceeding."
        logger.warning(
            "[MANDATE:3:GUARDRAILS] BLOCKED session=%s result=%s nudge='%s'",
            session_id, guardrail.result.value, response_text[:60],
        )
    elif l1_draft.hypotheses and not l1_draft.is_mock:
        top = l1_draft.hypotheses[0]
        response_text = _generate_l1_response(top, dim_state)
        logger.info(
            "[MANDATE:4:RESPONSE] session=%s source=llm action=%s confidence=%.2f response='%s'",
            session_id, top.action_class, top.confidence, response_text[:60],
        )
    else:
        response_text = _generate_mock_response(transcript)
        logger.info(
            "[MANDATE:4:RESPONSE] session=%s source=mock response='%s'",
            session_id, response_text[:60],
        )

    await _emit_stage("mandate", 3, "done")

    # ── STEP 4: Draft update ─────────────────────────────────────────────────
    if l1_draft.hypotheses:
        top = l1_draft.hypotheses[0]
        draft_payload = {
            "draft_id": l1_draft.draft_id,
            "hypothesis": top.hypothesis,
            "action_class": top.action_class,
            "confidence": top.confidence,
            "dimensions": dim_state.to_dict(),
            "is_mock": l1_draft.is_mock,
        }
        logger.info(
            "[MANDATE:4:DRAFT] session=%s draft_id=%s action=%s confidence=%.2f",
            session_id, l1_draft.draft_id[:8], top.action_class, top.confidence,
        )
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
        "[MANDATE:COMPLETE] session=%s guardrail=%s l1_mock=%s hypotheses=%d response='%s'",
        session_id, guardrail.result.value, l1_draft.is_mock,
        len(l1_draft.hypotheses), response_text[:60],
    )


def _generate_l1_response(hypothesis, dim_state) -> str:
    """Generate TTS confirmation based on L1 hypothesis. Never asks for clarification."""
    action = hypothesis.action_class
    dims = dim_state.a_set

    if action == "COMM_SEND":
        who = dims.who or "the recipient"
        return f"Got it. I'll prepare a message to {who}. Tap Approve to send."
    elif action == "SCHED_MODIFY":
        when = dims.when or "the requested time"
        return f"Understood. I'll schedule that for {when}. Tap Approve to confirm."
    elif action == "INFO_RETRIEVE":
        return "On it. I'll look that up for you. Tap Approve to proceed."
    elif action == "DOC_EDIT":
        return "Ready to make those changes. Tap Approve to apply."
    elif action == "FIN_TRANS":
        return "Financial action understood. Tap Approve to authorise."
    elif action == "SYS_CONFIG":
        return "Configuration change ready. Tap Approve to apply."
    else:
        what = dims.what or hypothesis.hypothesis[:60]
        return f"Understood: {what}. Tap Approve to execute."


def _generate_mock_response(transcript: str) -> str:
    """Generate a deterministic mock response for testing. Never asks clarification."""
    lower = transcript.lower()

    if "hello" in lower or "hi " in lower:
        return "Hello! I'm ready. Tap Approve to proceed."
    elif "send" in lower and "message" in lower:
        return "I'll prepare that message now. Tap Approve to send."
    elif "meeting" in lower or "schedule" in lower:
        return "I'll schedule that for you. Tap Approve to confirm."
    elif "email" in lower:
        return "I'll draft that email. Tap Approve to send."
    elif "tomorrow" in lower:
        return "Understood, tomorrow. Tap Approve to execute."
    else:
        return f"I heard you. Tap Approve to execute: {transcript[:50]}."
