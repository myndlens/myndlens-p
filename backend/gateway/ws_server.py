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

from intent.gap_filler import SessionContext, parse_capsule_summary, enrich_transcript
from gateway.conversation_state import (
    get_or_create_conversation, reset_conversation, cleanup_conversation,
)

logger = logging.getLogger(__name__)

# Active connections: session_id -> WebSocket
active_connections: Dict[str, WebSocket] = {}
# Execution ID -> session_id mapping (for webhook→WS broadcast)
execution_sessions: Dict[str, str] = {}
# Per-session Digital Self context (pre-loaded at auth, lives for session duration)
_session_contexts: Dict[str, SessionContext] = {}
# Per-session clarification state (tracks pending micro-question loops)
_clarification_state: Dict[str, dict] = {}
# Per-session question counter — hard cap at 3 questions per mandate
_session_question_count: Dict[str, int] = {}

# Max concurrent sessions — prevent unbounded memory growth
MAX_CONCURRENT_SESSIONS = 500
# Track ALL open sockets (including pre-auth) to prevent resource exhaustion
_open_connections = 0
# Per-session auth context — stored at WS auth to allow execute_request from
# within audio_chunk handler (permission grant path needs subscription/tenant/token)
_session_auth: Dict[str, dict] = {}
# Full enriched mandate — stored after extract_mandate_dimensions() in Phase 1.
# Keyed by draft_id so _handle_execute_request() can retrieve real dimensions.
# Without this, determine_skills() and OC only see the hypothesis summary string.
_pending_mandates: Dict[str, dict] = {}
# Biometric auth events — session_id -> {"event": asyncio.Event, "result": dict}
_biometric_events: Dict[str, dict] = {}
# Per-session fragment processing lock — ensures fragments are processed sequentially
_fragment_locks: Dict[str, asyncio.Lock] = {}



async def _session_cleanup_loop():
    """Periodic cleanup of stale session maps — runs every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        try:
            active_ids = set(_session_auth.keys())
            # Clean maps for sessions that no longer have auth (disconnected)
            total_stale = 0
            for map_dict in [_session_contexts, _clarification_state, _session_question_count, _fragment_locks]:
                stale = [k for k in map_dict if k not in active_ids]
                for k in stale:
                    map_dict.pop(k, None)
                total_stale += len(stale)
            if total_stale:
                logger.info("[CLEANUP] Removed %d stale session entries", total_stale)
        except Exception as e:
            logger.debug("[CLEANUP] error: %s", str(e)[:60])



# ── Intent → Result Schema mapping (C5) ─────────────────────────────────────
# Each intent category maps to a result_type and the JSON fields OC must return.
# AGENTS.md is generated from this at mandate time — OC returns structured JSON.
_INTENT_SCHEMAS: Dict[str, dict] = {
    "Software Development":  {"result_type": "code_execution",
        "fields": '  "language": "python|js|bash",\n  "code": "the full source code",\n  "output": "stdout from running the code",\n  "success": true,\n  "error": null'},
    "Data Analysis":         {"result_type": "data_report",
        "fields": '  "summary": "one-sentence finding",\n  "insights": ["key insight 1", "..."],\n  "data": {}'},
    "Travel Concierge":      {"result_type": "travel_itinerary",
        "fields": '  "legs": [{"from":"","to":"","date":"","carrier":"","ref":""}],\n  "hotels": [{"name":"","checkin":"","checkout":"","ref":""}],\n  "total_cost": "",\n  "currency": ""'},
    "Content Creation":      {"result_type": "creative_output",
        "fields": '  "content_type": "song|video|image|poster|text",\n  "title": "...",\n  "content": "the created content",\n  "url": null,\n  "thumbnail": null'},
    "Financial Operations":  {"result_type": "transaction",
        "fields": '  "action": "payment|transfer|subscription|cancellation",\n  "amount": 0,\n  "currency": "GBP",\n  "status": "completed|pending|failed",\n  "reference": ""'},
    "Customer Success":      {"result_type": "support_action",
        "fields": '  "action_taken": "...",\n  "outcome": "resolved|escalated|pending",\n  "reference": ""'},
    "Event Planning":        {"result_type": "event_plan",
        "fields": '  "event": "...",\n  "date": "...",\n  "venue": "...",\n  "attendees": [],\n  "schedule": []'},
    "Weekly Planning":       {"result_type": "schedule",
        "fields": '  "period": "week of ...",\n  "items": [{"time":"","task":"","priority":""}]'},
    "Vendor Management":     {"result_type": "vendor_action",
        "fields": '  "vendor": "...",\n  "action": "...",\n  "outcome": "...",\n  "reference": ""'},
    "Conflict Resolution":   {"result_type": "resolution",
        "fields": '  "parties": [],\n  "resolution": "...",\n  "next_steps": []'},
    "Automation Setup":      {"result_type": "automation",
        "fields": '  "automation_name": "...",\n  "trigger": "...",\n  "actions": [],\n  "status": "created|updated"'},
}
_DEFAULT_SCHEMA = {"result_type": "generic",
    "fields": '  "summary": "concise summary of what was done",\n  "details": "full details or output"'}


def _build_agents_md(intent: str, task: str, skill_name: str, dimensions: dict) -> str:
    """Generate mandate-specific AGENTS.md — the output format contract for OC.

    This is written to the agent's workspace before every execution.
    It tells OC:
      1. What task to complete
      2. Which installed skill to invoke (from ~/.openclaw/skills/)
      3. Exactly what JSON structure to return

    OC injects AGENTS.md into the agent context at session start, making
    its behaviour deterministic for this specific mandate.
    """
    schema = _INTENT_SCHEMAS.get(intent, _DEFAULT_SCHEMA)
    result_type = schema["result_type"]
    fields = schema["fields"]

    # Build constraint lines from dimensions
    constraint_lines = ""
    if dimensions:
        constraints = []
        for k, v in dimensions.items():
            val = v.get("value", v) if isinstance(v, dict) else v
            if val and val not in ("missing", "unknown", ""):
                constraints.append(f"- {k}: {val}")
        if constraints:
            constraint_lines = "\n## Constraints\n" + "\n".join(constraints[:8])

    skill_section = f"\n## Skill to invoke\nUse the `{skill_name}` skill." if skill_name else ""

    return f"""# Mandate Operating Instructions

## Task
{task}
{skill_section}

## Output Contract
You MUST return ONLY a JSON object as your final response. No prose, no explanation before or after the JSON.

```json
{{
  "result_type": "{result_type}",
{fields}
}}
```

If a required value is unavailable, use `null`. If an action fails, include `"error": "<reason>"` in the object.
{constraint_lines}
"""

# Per-session DS resolve events — pipeline holds here waiting for device to
# return readable text for vector-matched node IDs (ds_resolve / ds_context flow)
_ds_resolve_events: Dict[str, asyncio.Event] = {}
_ds_context_data: Dict[str, List[Dict]] = {}   # session_id → [{id, text}, ...]


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

    Called by the delivery webhook to push pipeline_stage/tts_audio updates to the mobile app.
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
        msg_type = WSMessageType[message_type.upper()] if message_type != "pipeline_stage" else WSMessageType.PIPELINE_STAGE
    except KeyError:
        msg_type = WSMessageType.PIPELINE_STAGE

    try:
        data = _make_envelope(msg_type, payload)
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

    # Connection cap — count ALL open sockets (including pre-auth)
    global _open_connections
    _open_connections += 1
    if _open_connections > MAX_CONCURRENT_SESSIONS:
        _open_connections -= 1
        await websocket.close(code=1013, reason="Server at capacity")
        logger.warning("[WS] Connection rejected — at capacity (%d open)", _open_connections)
        return

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

        # Store per-session auth context + user prefs for mandate enforcement
        _session_auth[session_id] = {
            "subscription_status": subscription_status,
            "tenant_id":           sso_claims.myndlens_tenant_id if sso_claims else "",
            "auth_token":          auth_payload.token,
            "user_id":             user_id_resolved or "",
            "delegation_mode":     auth_payload.delegation_mode,
            "ds_paused":           auth_payload.ds_paused,
            "data_residency":      auth_payload.data_residency,
        }

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

        # Register for proactive intelligence + deliver pending nudges
        from proactive.scheduler import register_session, deliver_nudges_on_connect
        if user_id_resolved:
            register_session(user_id_resolved, websocket)
            session_ctx = _session_contexts.get(session_id)
            first_name = session_ctx.user_name.split()[0] if session_ctx and session_ctx.user_name else ""
            asyncio.create_task(deliver_nudges_on_connect(user_id_resolved, websocket, first_name))

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
                reason = payload.get("reason", "")
                logger.info("Cancel received: session=%s reason=%s", session_id, reason)
                if reason == "kill_switch":
                    stt_p = get_stt_provider()
                    stt_p._streams.pop(session_id, None)
                    transcript_assembler.cleanup(session_id)
                    _clarification_state.pop(session_id, None)
                    logger.info("Kill switch: pipeline aborted for session=%s", session_id)
                elif reason == "fragment_captured":
                    # Path A — Capture Cycle: lightweight fragment processing
                    await _handle_fragment_captured(websocket, session_id, user_id=user_id_resolved or "")
                else:
                    # Path B (legacy) — full pipeline on single utterance
                    await _handle_stream_end(websocket, session_id, user_id=user_id_resolved or "")

            elif msg_type == WSMessageType.THOUGHT_STREAM_END.value:
                # Path B — Full Pipeline: user finished thinking, run mandate pipeline
                logger.info("Thought stream end: session=%s", session_id)
                await _handle_thought_stream_end(websocket, session_id, user_id=user_id_resolved or "")

            elif msg_type == WSMessageType.TEXT_INPUT.value:
                await _handle_text_input(websocket, session_id, payload, user_id=user_id_resolved or "")

            elif msg_type == WSMessageType.COMMAND_INPUT.value:
                await _handle_command_input(websocket, session_id, payload, user_id=user_id_resolved or "")

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

            elif msg_type == WSMessageType.BIOMETRIC_RESPONSE.value:
                # Device responding to biometric_request
                bio = _biometric_events.get(session_id)
                if bio:
                    bio["result"] = payload
                    bio["event"].set()

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
        # Decrement global connection counter
        _open_connections = max(0, _open_connections - 1)
        # Cleanup all per-session in-memory state
        if session_id:
            active_connections.pop(session_id, None)
            _session_contexts.pop(session_id, None)
            _session_auth.pop(session_id, None)
            # Clean up pending mandates for this session to prevent memory leak
            stale_drafts = [k for k, v in _pending_mandates.items()
                            if isinstance(v, dict) and v.get("_session_id") == session_id]
            for k in stale_drafts:
                _pending_mandates.pop(k, None)
            _clarification_state.pop(session_id, None)
            _session_question_count.pop(session_id, None)
            _fragment_locks.pop(session_id, None)
            cleanup_conversation(session_id)
            # Unregister from proactive scheduler
            from proactive.scheduler import unregister_session
            if user_id_resolved:
                unregister_session(user_id_resolved)
            # Clean self-awareness mode state
            from guardrails.self_awareness import cleanup_mode
            cleanup_mode(session_id)
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

        # BIOMETRIC GATE (E6) — request device-side biometric auth before execution
        # Send biometric request, wait up to 30s for response.
        # If device doesn't support biometrics, it responds immediately with success.
        bio_event = asyncio.Event()
        _biometric_events[session_id] = {"event": bio_event, "result": None}
        await ws.send_text(_make_envelope(WSMessageType.BIOMETRIC_REQUEST, {
            "session_id": session_id,
            "draft_id": req.draft_id,
            "reason": "Confirm execution with biometric authentication",
        }))
        try:
            await asyncio.wait_for(bio_event.wait(), timeout=30.0)
            bio_result = _biometric_events.get(session_id, {}).get("result")
            if bio_result and bio_result.get("success"):
                logger.info("BIOMETRIC: session=%s PASSED", session_id)
            else:
                await _send(ws, WSMessageType.EXECUTE_BLOCKED, ExecuteBlockedPayload(
                    reason="Biometric authentication failed or was cancelled.",
                    code="BIOMETRIC_FAILED",
                    draft_id=req.draft_id,
                ))
                logger.warning("BIOMETRIC: session=%s FAILED", session_id)
                return
        except asyncio.TimeoutError:
            # Timeout = device doesn't support biometrics or user didn't respond
            # FAIL CLOSED for confidential/sensitive actions. Allow only for non-sensitive.
            logger.warning("BIOMETRIC: session=%s timeout — blocking execution (fail-closed)", session_id)
            await _send(ws, WSMessageType.EXECUTE_BLOCKED, ExecuteBlockedPayload(
                reason="Biometric authentication timed out. Please try again.",
                code="BIOMETRIC_TIMEOUT",
                draft_id=req.draft_id,
            ))
            return
        finally:
            _biometric_events.pop(session_id, None)

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

        # L1/L2 conflict enforcement — block or warn on disagreement
        if l2.intent != top.intent:
            intent_mismatch = True  # noqa: F841 — used for audit logging
            confidence_delta = abs(top.confidence - l2.confidence)
            if confidence_delta > 0.4:
                # Severe mismatch — block execution
                logger.warning("L1/L2 SEVERE mismatch: session=%s L1=%s L2=%s delta=%.2f",
                              session_id, top.intent, l2.intent, confidence_delta)
                await _send(ws, WSMessageType.EXECUTE_BLOCKED, ExecuteBlockedPayload(
                    reason="Intent verification conflict. Please clarify your request.",
                    code="L1_L2_CONFLICT",
                    draft_id=req.draft_id,
                ))
                return
            elif confidence_delta > 0.2:
                # Moderate mismatch — log warning, proceed with caution
                logger.warning("L1/L2 moderate mismatch: session=%s L1=%s L2=%s", session_id, top.intent, l2.intent)

        # Stage 6: Skill Determination — LLM decides
        await broadcast_stage(session_id, 6, "active", "Determining skills...")
        from skills.determine import determine_skills
        # ── Retrieve the full enriched mandate stored during Phase 1 ──────────
        # Phase 1 (voice → approval) extracted real dimensions: where, when, who, budget etc.
        # Without this, determine_skills and OC only see the hypothesis summary string.
        # Non-destructive read — keep mandate until dispatch succeeds (retry-safe)
        full_mandate = _pending_mandates.get(req.draft_id, None)

        skill_plan = await determine_skills(
            session_id=session_id, user_id=user_id,
            mandate=full_mandate if full_mandate else {
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
        # Detect "display in chat" — only explicit phrases, not single common words.
        DISPLAY_IN_CHAT_PHRASES = {
            "display in chat", "show in chat", "show me in chat",
            "put it in chat", "put in chat", "show on screen", "display on screen",
        }
        transcript_lower = (draft.transcript or "").lower()
        display_in_chat = any(phrase in transcript_lower for phrase in DISPLAY_IN_CHAT_PHRASES)
        delivery_channels = ["in_app", "chat_display"] if display_in_chat else ["in_app"]

        # Build task string from dimensions
        if full_mandate and full_mandate.get("actions"):
            dim_lines = []
            for action in full_mandate["actions"][:5]:
                dims = {
                    k: v.get("value", v) if isinstance(v, dict) else v
                    for k, v in action.get("dimensions", {}).items()
                    if (v.get("value") if isinstance(v, dict) else v) not in (None, "", "missing", "unknown")
                }
                if dims:
                    dim_lines.append(f"  {action.get('action','')}: {dims}")
            task = (
                f"{full_mandate.get('mandate_summary', top.hypothesis)}"
                + ("\nActions:\n" + "\n".join(dim_lines) if dim_lines else "")
            )
        else:
            task = top.hypothesis

        # C5: Build AGENTS.md — the output format contract for OC
        # This tells OC exactly which JSON schema to return for this intent.
        # Written by the channel service into the agent workspace before execution.
        primary_skill = skill_names[0] if skill_names else ""
        agents_md = _build_agents_md(
            intent=top.intent,
            task=task,
            skill_name=primary_skill,
            dimensions=full_mandate.get("actions", [{}])[0].get("dimensions", {}) if full_mandate else {},
        )

        # C3: Include skill status hint for channel service
        # agents[0].agents_md carries the AGENTS.md content to write
        agents_payload = [{
            "id":        f"myndlens-{req.draft_id[:8]}",
            "agents_md": agents_md,
        }] if agents_md else []

        mandate = {
            "mandate_id": req.draft_id,
            "tenant_id": tenant_id,
            "task": task,
            "intent": top.intent,
            "intent_raw": draft.transcript,
            "skill_plan": skill_plan.get("skill_plan", []),
            "execution_strategy": skill_plan.get("execution_strategy", "sequential"),
            "agents": agents_payload,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": user_id,
            "delivery_channels": delivery_channels,
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

        # Clean up mandate only AFTER successful dispatch (retry-safe)
        _pending_mandates.pop(req.draft_id, None)

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
        # If there's a pending permission clarification, clean any stale transcript
        # from previous cycles so "Yes" doesn't get appended to old text
        if _clarification_state.get(session_id, {}).get("pending"):
            transcript_assembler.cleanup(session_id)

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

    CRITICAL: Route through _handle_text_input so that pending clarification
    state (e.g. "Shall I proceed?" → user says "Yes") is checked BEFORE the
    full pipeline runs. Previously this called _send_mock_tts_response directly,
    bypassing the clarification check and causing an infinite approval loop.
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
            # Save transcript
            await save_transcript(state)

            # Route through _handle_text_input which checks _clarification_state
            # for pending approval/clarification before running the full pipeline.
            final_text = state.get_current_text()
            await _handle_text_input(ws, session_id, {"text": final_text}, user_id=user_id)

        # Cleanup transcript state
        transcript_assembler.cleanup(session_id)

    except Exception as e:
        logger.error("Stream end error: session=%s error=%s", session_id, str(e))



async def _handle_fragment_captured(ws: WebSocket, session_id: str, user_id: str = "") -> None:
    """PATH A — Capture Cycle: lightweight fragment processing.

    Called when frontend VAD detects a sentence-level pause (1.5s).
    Extracts sub-intents + dimensions from the fragment, updates the
    ConversationState checklist, and sends FRAGMENT_ACK back.
    Does NOT run the full mandate pipeline.

    Uses a per-session lock to ensure fragments are processed sequentially
    even when the user speaks faster than processing time.
    """
    # Get or create per-session lock for sequential processing
    if session_id not in _fragment_locks:
        _fragment_locks[session_id] = asyncio.Lock()
    async with _fragment_locks[session_id]:
        await _process_fragment(ws, session_id, user_id)


async def _process_fragment(ws: WebSocket, session_id: str, user_id: str = "") -> None:
    """Inner fragment processor — called under the per-session lock."""
    try:
        stt = get_stt_provider()
        final_fragment = await stt.end_stream(session_id)

        if not final_fragment:
            # No audio captured — send ACK anyway so frontend keeps listening
            await ws.send_text(_make_envelope(WSMessageType.FRAGMENT_ACK, {
                "session_id": session_id, "status": "empty",
                "sub_intents": [], "checklist_progress": 0,
            }))
            return

        state, span = transcript_assembler.add_fragment(session_id, final_fragment)
        fragment_text = state.get_current_text()

        # Send transcript partial so user sees what was captured
        await _send(ws, WSMessageType.TRANSCRIPT_PARTIAL, TranscriptPayload(
            text=fragment_text, is_final=False,
            fragment_count=len(state.fragments),
            confidence=final_fragment.confidence,
            span_ids=[span.span_id],
        ))

        # Get conversation state + DS context
        session_ctx = _session_contexts.get(session_id)
        ds_summary = session_ctx.raw_summary if session_ctx else ""
        conv = get_or_create_conversation(session_id, user_id=user_id)

        # Route: classify utterance before running expensive LLM fragment analyzer
        from intent.router import route_fragment
        route = await route_fragment(session_id, user_id, fragment_text)

        if route.route == "command":
            cmd = route.normalized_command
            if cmd == "HOLD":
                conv.phase = "HELD"
                await ws.send_text(_make_envelope(WSMessageType.FRAGMENT_ACK, {
                    "session_id": session_id, "status": "held",
                    "sub_intents": [], "checklist_progress": 0,
                }))
            elif cmd == "RESUME":
                conv.phase = "ACTIVE_CAPTURE"
                await ws.send_text(_make_envelope(WSMessageType.FRAGMENT_ACK, {
                    "session_id": session_id, "status": "resumed",
                    "sub_intents": [], "checklist_progress": 0,
                }))
            elif cmd in ("CANCEL", "KILL"):
                conv.reset()
                await ws.send_text(_make_envelope(WSMessageType.FRAGMENT_ACK, {
                    "session_id": session_id, "status": "cancelled",
                    "sub_intents": [], "checklist_progress": 0,
                }))
            transcript_assembler.cleanup(session_id)
            return

        if route.route in ("noise", "interruption"):
            await ws.send_text(_make_envelope(WSMessageType.FRAGMENT_ACK, {
                "session_id": session_id, "status": "ignored",
                "sub_intents": [], "checklist_progress": 0,
            }))
            transcript_assembler.cleanup(session_id)
            return

        # If conversation is HELD, don't process intent fragments
        if conv.phase == "HELD":
            await ws.send_text(_make_envelope(WSMessageType.FRAGMENT_ACK, {
                "session_id": session_id, "status": "held_ignored",
                "sub_intents": [], "checklist_progress": 0,
            }))
            transcript_assembler.cleanup(session_id)
            return

        conv.phase = "ACTIVE_CAPTURE"

        # Route is intent_fragment — run lightweight sub-intent extraction
        from intent.fragment_analyzer import analyze_fragment
        analysis = await analyze_fragment(
            session_id=session_id,
            user_id=user_id,
            fragment_text=fragment_text,
            accumulated_context=conv.combined_transcript,
            ds_summary=ds_summary,
        )

        # Update conversation state
        conv.add_fragment(fragment_text, sub_intents=analysis.sub_intents, confidence=analysis.confidence)
        for dim, val in analysis.dimensions_found.items():
            conv.fill_checklist(dim, val, source="user_said")

        # Calculate checklist progress
        total_items = len(conv.checklist)
        filled_items = len([c for c in conv.checklist if c.filled])
        progress = round(filled_items / max(total_items, 1) * 100)

        # Send FRAGMENT_ACK — tells frontend "got it, keep talking"
        await ws.send_text(_make_envelope(WSMessageType.FRAGMENT_ACK, {
            "session_id": session_id,
            "status": "captured",
            "fragment_index": len(conv.fragments),
            "fragment_text": fragment_text[:80],
            "sub_intents": analysis.sub_intents,
            "dimensions_found": analysis.dimensions_found,
            "checklist_progress": progress,
            "latency_ms": round(analysis.latency_ms),
        }))

        # Cleanup STT assembler for next fragment
        transcript_assembler.cleanup(session_id)

        logger.info(
            "[CAPTURE:FRAGMENT] session=%s frag=%d text='%s' sub_intents=%s dims=%d progress=%d%% %.0fms",
            session_id, len(conv.fragments), fragment_text[:40],
            analysis.sub_intents, len(analysis.dimensions_found), progress, analysis.latency_ms,
        )

    except Exception as e:
        logger.error("[CAPTURE:FRAGMENT] error: session=%s %s", session_id, str(e))
        # Still send ACK so frontend doesn't hang
        await ws.send_text(_make_envelope(WSMessageType.FRAGMENT_ACK, {
            "session_id": session_id, "status": "error", "error": str(e),
            "sub_intents": [], "checklist_progress": 0,
        }))


async def _handle_thought_stream_end(ws: WebSocket, session_id: str, user_id: str = "") -> None:
    """PATH B — Full Pipeline: user finished thinking, run mandate pipeline.

    Called when frontend detects extended silence (5-8s) or user taps "Done".
    Uses the accumulated ConversationState (all fragments, checklist) to run
    the full L1 → Dimensions → Guardrails → TTS pipeline.
    """
    conv = get_or_create_conversation(session_id, user_id=user_id)

    if not conv.fragments:
        logger.warning("[CAPTURE:STREAM_END] session=%s no fragments accumulated", session_id)
        return

    # Use the combined transcript from all accumulated fragments
    combined = conv.get_combined_transcript()
    logger.info(
        "[CAPTURE:STREAM_END] session=%s fragments=%d combined='%s'",
        session_id, len(conv.fragments), combined[:80],
    )

    # Clean transcript assembler so auto-record after TTS starts fresh
    transcript_assembler.cleanup(session_id)

    # Transition conversation phase
    conv.phase = "PROCESSING"

    # Get context capsule
    session_ctx = _session_contexts.get(session_id)
    context_capsule = None
    if session_ctx and session_ctx.raw_summary:
        context_capsule = json.dumps({"summary": session_ctx.raw_summary})

    # Route through _handle_text_input which checks clarification state
    # and then runs _send_mock_tts_response with the FULL combined transcript
    await _handle_text_input(ws, session_id, {"text": combined, "context_capsule": context_capsule}, user_id=user_id)



async def _handle_command_input(ws: WebSocket, session_id: str, payload: dict, user_id: str = "") -> None:
    """Handle explicit command_input from FE — deterministic routing, no intent pipeline."""
    command = payload.get("command", "").upper()
    source = payload.get("source", "button")
    draft_id = payload.get("draft_id", "")

    logger.info("[COMMAND] session=%s cmd=%s source=%s", session_id, command, source)

    conv = get_or_create_conversation(session_id, user_id=user_id)
    clarify = _clarification_state.get(session_id, {})
    has_pending = clarify.get("pending", False)
    clarify_type = clarify.get("type", "")

    if command == "APPROVE":
        if has_pending and clarify_type == "permission":
            # Execute the approved mandate
            stored_draft_id = clarify.get("draft_id", "") or draft_id
            if stored_draft_id:
                from schemas.ws_messages import ExecuteRequestPayload
                await _handle_execute_request(ws, session_id, ExecuteRequestPayload(
                    draft_id=stored_draft_id, approved=True,
                ), user_id=user_id)
                _clarification_state.pop(session_id, None)
            else:
                await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
                    text="I don't have a pending action to approve.", session_id=session_id,
                    format="text", is_mock=True,
                ))
        elif has_pending:
            # Treat as affirmative answer to clarification
            await _handle_text_input(ws, session_id, {"text": "Yes"}, user_id=user_id)
        else:
            await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
                text="Nothing to approve right now.", session_id=session_id,
                format="text", is_mock=True,
            ))

    elif command == "DECLINE_CHANGE":
        if has_pending:
            _clarification_state.pop(session_id, None)
            session_ctx = _session_contexts.get(session_id)
            name = session_ctx.user_name.split()[0] if session_ctx and session_ctx.user_name else ""
            await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
                text=f"{'Sure ' + name + '. ' if name else ''}What would you like to change?",
                session_id=session_id, format="text", is_mock=True,
                is_clarification=True, auto_record=True,
            ))
        else:
            await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
                text="Nothing active to change.", session_id=session_id,
                format="text", is_mock=True,
            ))

    elif command == "END_THOUGHT":
        if conv.phase in ("ACTIVE_CAPTURE", "LISTENING"):
            conv.phase = "PROCESSING"
            combined = conv.get_combined_transcript()
            if combined:
                transcript_assembler.cleanup(session_id)
                await _handle_text_input(ws, session_id, {"text": combined}, user_id=user_id)

    elif command == "HOLD":
        conv.phase = "HELD"
        logger.info("[COMMAND] session=%s HELD", session_id)

    elif command == "RESUME":
        conv.phase = "ACTIVE_CAPTURE"
        logger.info("[COMMAND] session=%s RESUMED", session_id)

    elif command == "CANCEL":
        conv.reset()
        _clarification_state.pop(session_id, None)
        logger.info("[COMMAND] session=%s CANCELLED", session_id)

    else:
        logger.warning("[COMMAND] session=%s unknown command: %s", session_id, command)


async def _handle_text_input(ws: WebSocket, session_id: str, payload: dict, user_id: str = "") -> None:
    """Handle text input as an alternative to voice (STT fallback)."""
    from guardrails.sanitizer import sanitize_for_llm
    text = sanitize_for_llm(payload.get("text", "").strip(), context="text_input")
    context_capsule = payload.get("context_capsule")  # on-device Digital Self PKG context

    if not text:
        # Empty transcript — STT returned nothing (short audio, noise, TTS echo).
        # Send a recovery TTS so the frontend exits THINKING state and the user
        # knows to try again. If a clarification is pending, re-ask the question.
        clarify = _clarification_state.get(session_id)
        if clarify and clarify.get("pending") and clarify.get("question_asked"):
            # Re-ask the pending clarification — user hasn't answered yet
            tts = get_tts_provider()
            result = await tts.synthesize(clarify["question_asked"])
            if result.audio_bytes and not result.is_mock:
                import base64
                await ws.send_text(_make_envelope(WSMessageType.TTS_AUDIO, {
                    "text": clarify["question_asked"], "session_id": session_id,
                    "format": "mp3", "is_mock": False, "auto_record": True,
                    "audio": base64.b64encode(result.audio_bytes).decode("ascii"),
                    "audio_size_bytes": len(result.audio_bytes),
                }))
            else:
                await ws.send_text(_make_envelope(WSMessageType.TTS_AUDIO, {
                    "text": clarify["question_asked"], "session_id": session_id,
                    "format": "text", "is_mock": True, "auto_record": True,
                }))
        else:
            # No pending clarification — generic "try again" recovery
            recovery = "I didn't catch that. Could you try again?"
            await ws.send_text(_make_envelope(WSMessageType.TTS_AUDIO, {
                "text": recovery, "session_id": session_id,
                "format": "text", "is_mock": True, "auto_record": True,
            }))
        logger.info("[STT_EMPTY] session=%s — sent recovery prompt", session_id)
        return
    # Note: oversized inputs are silently truncated to 2000 chars by sanitize_for_llm().
    # This is intentional — we accept what the user said, just cap the LLM context length.

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
                logger.info("[CLARIFICATION:PERMISSION] session=%s GRANTED → executing draft",
                            session_id)
                _clarification_state.pop(session_id, None)

                # Execute the draft directly — do NOT re-run the pipeline.
                # Re-running _send_mock_tts_response would re-process the original
                # transcript, rebuild the mandate, and ask for approval again → infinite loop.
                draft_id = clarify.get("draft_id")
                auth_ctx = _session_auth.get(session_id, {})
                if draft_id:
                    await _handle_execute_request(
                        ws, session_id,
                        {"draft_id": draft_id},
                        subscription_status=auth_ctx.get("subscription_status", "ACTIVE"),
                        user_id=auth_ctx.get("user_id", user_id),
                        tenant_id=auth_ctx.get("tenant_id", ""),
                        auth_token=auth_ctx.get("auth_token", ""),
                    )
                else:
                    # Fallback: no draft_id stored — re-run pipeline (old path)
                    logger.warning("[CLARIFICATION:PERMISSION] session=%s no draft_id stored — fallback re-run",
                                   session_id)
                    _clarification_state[session_id] = {"permission_granted": True, "dim_attempts": 0}
                    await _send_mock_tts_response(ws, session_id, clarify["original_transcript"],
                                                  user_id=user_id, context_capsule=clarify.get("context_capsule"))
            else:
                _ctx_neg = _session_contexts.get(session_id)
                _fn = (_ctx_neg.user_name.split()[0] if _ctx_neg and _ctx_neg.user_name else "")
                neg_prompt = f"Sure{' ' + _fn if _fn else ''}. What would you like to change?"
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
                        is_clarification=True, auto_record=True,
                    ))
                logger.info("[CLARIFICATION:PERMISSION] session=%s DECLINED", session_id)
            return

        # ── Dimension clarification response ──────────────────────────────────
        if clarify_type == "dimension":
            combined = f"{clarify['original_transcript']}. Answer: {text}"
            _clarification_state[session_id] = {"dim_attempts": clarify.get("dim_attempts", 1)}
            await _send_mock_tts_response(ws, session_id, combined, user_id=user_id,
                                          context_capsule=clarify.get("context_capsule"))
            return

        # ── Micro-question response — enrich and re-run L1 with combined context ──
        if clarify_type == "micro":
            combined = f"{clarify['original_transcript']}. {text}"
            carried_questions = clarify.get("questions_asked", [])
            # Carry forward attempts so micro-questions don't re-fire
            _clarification_state[session_id] = {
                "questions_asked": carried_questions,
                "attempts": clarify.get("attempts", 1),
            }
            await _send_mock_tts_response(ws, session_id, combined, user_id=user_id,
                                          context_capsule=clarify.get("context_capsule"))
            return

        # ── Intent clarification (default) ────────────────────────────────────
        combined = f"{clarify['original_transcript']}. Clarification: {text}"
        carried_questions = clarify.get("questions_asked", [])
        _clarification_state[session_id] = {
            "questions_asked": carried_questions,
            "attempts": clarify.get("attempts", 1),  # carry forward to prevent re-asking
        }
        logger.info("[CLARIFICATION:INTENT] session=%s combined='%s' asked_so_far=%d",
                    session_id, combined[:80], len(carried_questions))
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

    RULES:
    1. Max 3 questions total per mandate — tracked via ConversationState
    2. NO questions during or after mandate processing — all Q&A happens in Step 1.5
    3. TTS uses user's first name sparingly (start of summary only)
    """

    # Get user's first name from session context (for friendly TTS)
    session_ctx_name = _session_contexts.get(session_id)
    _user_first_name = ""
    if session_ctx_name and session_ctx_name.user_name:
        _user_first_name = session_ctx_name.user_name.split()[0]

    # Get or create conversation state for this session
    conv = get_or_create_conversation(session_id, user_id=user_id, user_first_name=_user_first_name)

    # Reset conversation for fresh mandates (no pending clarification)
    if not _clarification_state.get(session_id, {}).get("pending"):
        conv.reset()
        conv.questions_remaining = 3  # Hard cap per mandate lifecycle

    # Add this transcript as a fragment
    conv.add_fragment(transcript)

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

    # ── STEP 0: Self-Awareness Router — two-mode interaction model ──────────
    from guardrails.self_awareness import route_self_awareness
    self_answer = await route_self_awareness(session_id, transcript, _user_first_name)
    if self_answer:
        response_text = self_answer
        # Skip the entire pipeline — just speak the answer
        tts = get_tts_provider()
        tts_result = await tts.synthesize(response_text)
        if tts_result.audio_bytes and not tts_result.is_mock:
            tts_payload = {
                "text": response_text, "session_id": session_id,
                "format": "mp3", "is_mock": False,
                "audio": base64.b64encode(tts_result.audio_bytes).decode("ascii"),
                "audio_size_bytes": len(tts_result.audio_bytes),
                "auto_record": False,
            }
            await ws.send_text(_make_envelope(WSMessageType.TTS_AUDIO, tts_payload))
        else:
            await _send(ws, WSMessageType.TTS_AUDIO, TTSAudioPayload(
                text=response_text, session_id=session_id, format="text", is_mock=True,
            ))
        logger.info("[SELF_AWARENESS] session=%s answered meta-question", session_id)
        return

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
    # RULES: Max 3 questions total. No questions after mandate processing starts.
    if l1_draft.hypotheses and not l1_draft.is_mock:
        top_check = l1_draft.hypotheses[0]
        from intent.micro_questions import should_ask_micro_questions, generate_micro_questions

        if conv.can_ask_question() and should_ask_micro_questions(top_check.confidence, top_check.dimension_suggestions, top_check.hypothesis):
            clarify_state = _clarification_state.get(session_id, {})
            attempt = clarify_state.get("attempts", 0)
            questions_asked: list = clarify_state.get("questions_asked", [])

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
                    already_asked=questions_asked,
                )

                if mq_result.questions:
                    question = mq_result.questions[0]
                    conv.record_question(question.question)

                    _clarification_state[session_id] = {
                        "pending": True,
                        "type": "micro",
                        "original_transcript": transcript,
                        "enriched_transcript": enriched_transcript,
                        "question_asked": question.question,
                        "questions_asked": questions_asked + [question.question],
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
                            "auto_record": True,
                        }
                        await ws.send_text(_make_envelope(WSMessageType.TTS_AUDIO, tts_payload))
                    else:
                        # Mock TTS — still need auto_record so mic opens after question
                        mock_payload = {
                            "text": question.question, "session_id": session_id,
                            "format": "text", "is_mock": True,
                            "is_clarification": True, "auto_record": True,
                        }
                        await ws.send_text(_make_envelope(WSMessageType.TTS_AUDIO, mock_payload))

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
        # Store full enriched mandate so _handle_execute_request can retrieve it.
        # This is the ONLY place where real dimensions exist — if not stored here,
        # determine_skills() and OC will only see the hypothesis summary string.
        _pending_mandates[l1_draft.draft_id] = {
            **(mandate if isinstance(mandate, dict) else {"raw": mandate}),
            "_session_id": session_id,
            "_user_id": user_id,
        }
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
        name_prefix = f"{_user_first_name}, " if _user_first_name else ""
        response_text = name_prefix + (harm_check.nudge or "I can't assist with that.")
        logger.warning("[MANDATE:3:GUARDRAILS] BLOCKED session=%s result=%s reason=%s",
                       session_id, harm_check.result, harm_check.reason)
    elif mandate and l1_draft.hypotheses and not l1_draft.is_mock:
        top = l1_draft.hypotheses[0]
        summary = mandate.get("mandate_summary", top.hypothesis)
        missing_count = len(missing)

        if missing_count > 0:
            # RULE: No questions during mandate processing. All data collection
            # must happen BEFORE mandate (in Step 1.5 micro-questions).
            # Log the missing dimensions for debugging but proceed with defaults.
            logger.info("[MANDATE:2:DIMS] session=%s %d missing dimensions — proceeding with defaults (no questions during mandate)",
                        session_id, missing_count)
            # Build TTS response: friendly, concise mandate summary with user name
            name_prefix = f"{_user_first_name}, " if _user_first_name else ""
            sub_intents = top.sub_intents if top.sub_intents else []
            if sub_intents and len(sub_intents) > 0:
                sub_list = ". ".join(str(s) for s in sub_intents[:3] if s)
                response_text = (
                    f"{name_prefix}got it. {summary}. "
                    f"This covers: {sub_list}. "
                    f"Shall I proceed?"
                )
            else:
                response_text = f"{name_prefix}got it. {summary}. Shall I proceed?"
        else:
            name_prefix = f"{_user_first_name}, " if _user_first_name else ""
            sub_intents = top.sub_intents if top.sub_intents else []
            if sub_intents and len(sub_intents) > 0:
                sub_list = ". ".join(str(s) for s in sub_intents[:3] if s)
                response_text = (
                    f"{name_prefix}got it. {summary}. "
                    f"This covers: {sub_list}. "
                    f"Shall I proceed?"
                )
            else:
                response_text = f"{name_prefix}got it. {summary}. Shall I proceed?"
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

    # ── STEP 5: TTS synthesis + Delegation Mode enforcement ─────────────────
    logger.info("[MANDATE:5:TTS] session=%s synthesizing text='%s'", session_id, response_text[:60])
    tts = get_tts_provider()
    result = await tts.synthesize(response_text)

    # Delegation Mode enforcement:
    #   advisory   → ALWAYS ask for approval ("shall i proceed?")
    #   assisted   → ask when mandate confidence < threshold (current behaviour)
    #   delegated  → auto-execute, NEVER ask for approval
    delegation_mode = (_session_auth.get(session_id) or {}).get("delegation_mode", "assisted")

    if delegation_mode == "delegated":
        needs_approval = False
        logger.info("[MANDATE:5:DELEGATION] session=%s mode=delegated → auto-execute", session_id)
    elif delegation_mode == "advisory":
        needs_approval = True
    else:
        # Assisted: always ask for approval (explicit policy, not text matching)
        needs_approval = True

    # Store mandate with session_id for cleanup
    _pending_mandates[l1_draft.draft_id] = {
        **(mandate if isinstance(mandate, dict) else {"mandate": mandate}),
        "_session_id": session_id,
        "_user_id": user_id,
        "_created_at": datetime.now(timezone.utc).isoformat(),
    } if isinstance(_pending_mandates.get(l1_draft.draft_id), dict) or l1_draft.draft_id not in _pending_mandates else _pending_mandates[l1_draft.draft_id]

    if needs_approval:
        _clarification_state[session_id] = {
            "pending":             True,
            "type":                "permission",
            "original_transcript": transcript,
            "question_asked":      response_text,
            "context_capsule":     context_capsule,
            "draft_id":            l1_draft.draft_id,
        }
        logger.info("[MANDATE:5:APPROVAL_GATE] session=%s draft_id=%s — awaiting Yes/No",
                    session_id, l1_draft.draft_id)
    else:
        # Delegated mode: auto-execute immediately
        from schemas.ws_messages import ExecuteRequestPayload
        asyncio.create_task(_handle_execute_request(
            ws, session_id,
            ExecuteRequestPayload(draft_id=l1_draft.draft_id, approved=True),
            user_id=user_id,
        ))
        logger.info("[MANDATE:5:AUTO_EXECUTE] session=%s draft_id=%s", session_id, l1_draft.draft_id)

    if result.audio_bytes and not result.is_mock:
        audio_b64 = base64.b64encode(result.audio_bytes).decode("ascii")
        payload_dict = {
            "text": response_text, "session_id": session_id,
            "format": "mp3", "is_mock": False,
            "audio": audio_b64,
            "audio_size_bytes": len(result.audio_bytes),
            "auto_record": needs_approval,
            "is_clarification": needs_approval,
            "ui_mode": "approval" if needs_approval else "executing" if delegation_mode == "delegated" else "idle",
            "awaiting_command": "approve_or_change" if needs_approval else "none",
            "draft_id": l1_draft.draft_id if needs_approval else "",
            "requires_approval": needs_approval,
        }
        await ws.send_text(_make_envelope(WSMessageType.TTS_AUDIO, payload_dict))
        logger.info("[MANDATE:5:TTS] session=%s DONE real_audio bytes=%d", session_id, len(result.audio_bytes))
    else:
        payload_dict = {
            "text": response_text, "session_id": session_id,
            "format": "text", "is_mock": True,
            "auto_record": needs_approval,
            "is_clarification": needs_approval,
            "ui_mode": "approval" if needs_approval else "executing" if delegation_mode == "delegated" else "idle",
            "awaiting_command": "approve_or_change" if needs_approval else "none",
            "draft_id": l1_draft.draft_id if needs_approval else "",
            "requires_approval": needs_approval,
        }
        await ws.send_text(_make_envelope(WSMessageType.TTS_AUDIO, payload_dict))
        logger.info("[MANDATE:5:TTS] session=%s DONE mock_text", session_id)

    logger.info(
        "[MANDATE:COMPLETE] session=%s l1_mock=%s hypotheses=%d response='%s'",
        session_id, l1_draft.is_mock,
        len(l1_draft.hypotheses), response_text[:60],
    )

