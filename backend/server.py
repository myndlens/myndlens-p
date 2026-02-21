"""MyndLens Backend — Command Plane entry point.

Batch 0-3.5: Foundations, Identity, Audio Pipeline, STT, TTS
SSO: ObeGee SSO consumer + Tenant activation wiring
"""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import uuid

import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, WebSocket, HTTPException, Header, Request
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

# Load env before anything else
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from config.settings import get_settings
from core.logging_config import setup_logging
from core.database import get_db, init_indexes, close_db
from core.exceptions import DispatchBlockedError
from auth.device_binding import get_session
from gateway.ws_server import handle_ws_connection, get_active_session_count
from presence.heartbeat import check_presence
from stt.orchestrator import get_stt_provider
from tts.orchestrator import get_tts_provider as get_tts
from prompting.orchestrator import PromptOrchestrator
from prompting.types import PromptContext, PromptPurpose, PromptMode
from prompting.storage.mongo import save_prompt_snapshot
from memory import retriever as digital_self
from commit.state_machine import (
    create_commit, transition as commit_transition,
    get_commit, get_session_commits, recover_pending,
    CommitState,
)
from l2.sentry import run_l2_sentry
from qc.sentry import run_qc_sentry
from mio.signer import sign_mio, get_public_key_hex
from mio.verify import verify_mio_for_execution
from abuse.rate_limit import check_rate_limit, get_rate_status
from abuse.circuit_breakers import get_all_breaker_statuses
from observability.metrics import get_system_metrics

# ---- Setup logging ----
setup_logging()
logger = logging.getLogger(__name__)


# ---- Lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: startup validation → init → serve → shutdown."""
    settings = get_settings()

    # ── Startup: Fail fast on missing critical configuration ────────────────
    _required_vars = {
        "MIO_KEY_ENCRYPTION_KEY": settings.MIO_KEY_ENCRYPTION_KEY,
        "MYNDLENS_BASE_URL": settings.MYNDLENS_BASE_URL,
    }
    _missing = [k for k, v in _required_vars.items() if not v]
    if _missing:
        raise RuntimeError(
            f"STARTUP FAILED — missing required env vars in backend/.env: {', '.join(_missing)}\n"
            "Set them and restart the server."
        )

    _warned_vars = {
        "OBEGEE_API_URL": settings.OBEGEE_API_URL,
        "CHANNEL_ADAPTER_IP": settings.CHANNEL_ADAPTER_IP,
    }
    for k, v in _warned_vars.items():
        if not v:
            logger.warning("CONFIG WARNING: %s is not set — mandate dispatch will fail", k)
    settings = get_settings()
    logger.info("MyndLens BE starting — env=%s", settings.ENV)
    await init_indexes()
    # Initialize base soul in vector memory
    from soul.store import initialize_base_soul
    await initialize_base_soul()
    # Pre-load MIO signing keys from DB (persists across restarts)
    from mio.signer import _load_or_generate_keys
    await _load_or_generate_keys()
    # Reload Digital Self vectors from MongoDB (fixes restart-wipe bug)
    from memory.client.vector import reload_from_mongodb
    reloaded = await reload_from_mongodb()
    logger.info("Digital Self vectors reloaded: %d", reloaded)
    # Auto-index skills library into MongoDB
    from skills.library import load_and_index_library
    skills_result = await load_and_index_library()
    logger.info("Skills library: %s (%s skills)", skills_result.get("status"), skills_result.get("skills_indexed", 0))
    logger.info("MyndLens BE ready")
    yield
    await close_db()
    logger.info("MyndLens BE shutdown complete")


# ---- App ----
app = FastAPI(
    title="MyndLens Command Plane",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")


# =====================================================
#  REST Endpoints
# =====================================================

# ---- Health ----
@api_router.get("/health")
async def health():
    settings = get_settings()
    stt = get_stt_provider()
    tts = get_tts()
    stt_healthy = await stt.is_healthy()
    tts_healthy = await tts.is_healthy()
    return {
        "status": "healthy",
        "env": settings.ENV,
        "version": "0.2.0",
        "active_sessions": get_active_session_count(),
        "stt_provider": type(stt).__name__,
        "stt_healthy": stt_healthy,
        "mock_stt": settings.MOCK_STT,
        "tts_provider": type(tts).__name__,
        "tts_healthy": tts_healthy,
        "mock_tts": settings.MOCK_TTS,
        "mock_llm": settings.MOCK_LLM,
    }


# =====================================================
#  Proxy Nickname API
# =====================================================

class NicknameRequest(BaseModel):
    user_id: str
    nickname: str


@api_router.get("/nickname/{user_id}")
async def get_nickname(user_id: str):
    db = get_db()
    doc = await db.nicknames.find_one({"user_id": user_id}, {"_id": 0})
    return {"user_id": user_id, "nickname": doc.get("nickname", "MyndLens") if doc else "MyndLens"}


@api_router.put("/nickname")
async def set_nickname(req: NicknameRequest):
    db = get_db()
    nick = req.nickname.strip()[:30] or "MyndLens"
    await db.nicknames.update_one(
        {"user_id": req.user_id},
        {"$set": {"user_id": req.user_id, "nickname": nick}},
        upsert=True,
    )
    return {"user_id": req.user_id, "nickname": nick}


# =====================================================
#  ObeGee Mock Pairing (dev fixture only)
# =====================================================

class PairRequest(BaseModel):
    code: str
    device_id: str
    device_name: str = "Unknown Device"


class PairResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 2592000  # 30 days
    tenant_id: str
    workspace_slug: str
    runtime_endpoint: str
    dispatch_endpoint: str
    session_id: str


# Conditionally register the mock pairing route
_settings_for_route = get_settings()
if _settings_for_route.ENV != "prod" and _settings_for_route.ENABLE_OBEGEE_MOCK_IDP:

    @api_router.post("/sso/myndlens/pair", response_model=PairResponse)
    async def mock_obegee_pair(req: PairRequest):
        """MOCK ObeGee pairing endpoint — DEV ONLY.

        Simulates: ObeGee Dashboard → Generate Pairing Code → User enters in app.
        In prod, this call goes directly to https://obegee.co.uk/api/myndlens/pair.
        This endpoint MUST NOT exist in prod (route not registered).
        """
        settings = get_settings()
        if settings.ENV == "prod":
            raise HTTPException(status_code=404, detail="Not found")

        # In dev, accept any 6-digit code
        if len(req.code) != 6 or not req.code.isdigit():
            raise HTTPException(status_code=400, detail="Invalid pairing code")

        # Use fixed dev tenant if configured — ensures ObeGee can find it.
        # Fall back to per-device tenant for local-only testing.
        dev_tenant_id = getattr(settings, 'OBEGEE_DEV_TENANT_ID', '')
        if dev_tenant_id:
            tenant_id = dev_tenant_id
            user_id = f"user_{req.device_id[-8:]}"
        else:
            from tenants.registry import create_or_get_tenant
            user_id = f"user_{req.device_id[-8:]}"
            tenant = await create_or_get_tenant(user_id)
            tenant_id = tenant.tenant_id

        now = datetime.now(timezone.utc)
        payload = {
            "iss": "obegee",
            "aud": "myndlens",
            "sub": user_id,
            "obegee_user_id": user_id,
            "myndlens_tenant_id": tenant_id,
            "subscription_status": "ACTIVE",
            "iat": now.timestamp(),
            "exp": (now + timedelta(days=30)).timestamp(),
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(payload, settings.OBEGEE_SSO_HS_SECRET, algorithm="HS256")

        session_id = f"mls_{uuid.uuid4().hex[:12]}"

        logger.info(
            "MOCK pair: code=%s device=%s tenant=%s",
            req.code, req.device_id[:12], tenant_id[:12],
        )

        return PairResponse(
            access_token=token,
            tenant_id=tenant_id,
            workspace_slug=f"workspace-{tenant_id[:8]}",
            runtime_endpoint=settings.MYNDLENS_BASE_URL,
            dispatch_endpoint=f"{settings.MYNDLENS_BASE_URL}/api/dispatch",
            session_id=session_id,
        )


# =====================================================
#  S2S Auth Helper (for ObeGee-initiated callbacks)
# =====================================================

def _verify_s2s_token(x_obegee_s2s_token: str = Header(None)) -> None:
    """Verify service-to-service auth token from ObeGee."""
    settings = get_settings()
    if x_obegee_s2s_token != settings.OBEGEE_S2S_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid S2S token")


# NOTE: Tenant lifecycle APIs (activate/suspend/deprovision) REMOVED.
# Per Dev Agent Contract: tenant lifecycle is ObeGee-owned.
# MyndLens is a relying party — reads tenant state, never mutates it.
# ObeGee pushes tenant state via SSO claims + direct DB writes.


# =====================================================
#  Delivery Webhook (ObeGee → MyndLens)
# =====================================================

class DeliveryWebhookPayload(BaseModel):
    execution_id: str
    status: str
    delivered_to: List[str] = []
    summary: str = ""
    completed_at: Optional[str] = None
    error: Optional[str] = None


@api_router.post("/dispatch/delivery-webhook")
async def delivery_webhook(
    payload: DeliveryWebhookPayload,
    x_obegee_s2s_token: str = Header(None),
):
    """Webhook: ObeGee calls this after OpenClaw executes and delivers results.

    Flow: MyndLens sends mandate → ObeGee executes → ObeGee delivers to channels
    → ObeGee calls this webhook → MyndLens updates UI.
    """
    _verify_s2s_token(x_obegee_s2s_token)
    db = get_db()

    # Store delivery record
    doc = {
        "execution_id": payload.execution_id,
        "status": payload.status,
        "delivered_to": payload.delivered_to,
        "summary": payload.summary,
        "completed_at": payload.completed_at,
        "error": payload.error,
        "received_at": datetime.now(timezone.utc),
    }
    await db.delivery_events.insert_one(doc)

    # Broadcast to connected WS clients via pipeline_stage
    from gateway.ws_server import broadcast_to_session
    stage_index = 9 if payload.status == "COMPLETED" else 8
    await broadcast_to_session(
        execution_id=payload.execution_id,
        message_type="pipeline_stage",
        payload={
            "stage_id": "delivered" if payload.status == "COMPLETED" else "executing",
            "stage_index": stage_index,
            "total_stages": 10,
            "status": "done" if payload.status == "COMPLETED" else "active",
            "summary": payload.summary,
            "delivered_to": payload.delivered_to,
        },
    )

    # Trigger Skills Reinforcement Learning — update skill scores from execution outcome
    if payload.status in ("COMPLETED", "FAILED", "PARTIAL"):
        try:
            dispatch_record = await db.mandate_dispatches.find_one(
                {"execution_id": payload.execution_id},
                {"_id": 0, "mandate": 1},
            )
            if dispatch_record:
                mandate = dispatch_record.get("mandate", {})
                # C1 fix: new mandate format uses "skill_slugs", old uses "generated_skills"
                skill_names = mandate.get("skill_slugs", mandate.get("generated_skills", []))
                # C1 fix: new mandate format uses "task", old uses "intent"
                intent = mandate.get("task", mandate.get("intent", ""))
                if skill_names:
                    from skills.reinforcement import record_skill_outcome
                    await record_skill_outcome(
                        skill_names=skill_names,
                        intent=intent,
                        outcome=payload.status,
                    )
                # Post-mandate Digital Self learning — fires only on successful completion
                if payload.status == "COMPLETED" and mandate.get("actions"):
                    user_id = mandate.get("approved_by", "")
                    if user_id:
                        from memory.post_mandate_learning import learn_from_mandate
                        learned = await learn_from_mandate(user_id, mandate)
                        logger.info(
                            "[DS Learn] Delivery hook: exec=%s user=%s learned=%d",
                            payload.execution_id, user_id, learned.get("learned", 0),
                        )
        except Exception as e:
            logger.warning("Skill RL update failed for exec=%s: %s", payload.execution_id, str(e))

    logger.info(
        "Delivery webhook: exec=%s status=%s channels=%s",
        payload.execution_id, payload.status, payload.delivered_to,
    )

    # Log security report if ObeGee includes agentguard data
    agentguard_data = getattr(payload, "agentguard", None)
    if agentguard_data:
        await db.agentguard_reports.insert_one({
            "execution_id": payload.execution_id,
            "reported_at": datetime.now(timezone.utc),
            "report": agentguard_data,
        })
        # Check for HIGH/CRITICAL alerts
        alerts = (agentguard_data or {}).get("alerts", [])
        high_alerts = [a for a in alerts if a.get("severity") in ("HIGH", "CRITICAL")]
        if high_alerts:
            logger.warning(
                "[AgentGuard] HIGH/CRITICAL alerts for exec=%s: %s",
                payload.execution_id, high_alerts,
            )

    return {"received": True, "execution_id": payload.execution_id}


# =====================================================
#  Mandate Execution API
# =====================================================

class MandateExecuteRequest(BaseModel):
    session_id: str
    mandate_id: str = ""
    tenant_id: str = ""
    intent: str = ""
    dimensions: dict = {}
    generated_skills: List[dict] = []
    delivery_channels: List[str] = []
    channel_details: dict = {}
    mio_signature: str = ""


@api_router.post("/mandate/execute")
async def api_execute_mandate(req: MandateExecuteRequest):
    """Execute an approved mandate — sends to ObeGee and tracks progress."""
    from dispatcher.mandate_dispatch import dispatch_mandate
    mandate = {
        "mandate_id": req.mandate_id or f"mio_{req.session_id[:8]}",
        "tenant_id": req.tenant_id,
        "intent": req.intent,
        "dimensions": req.dimensions,
        "generated_skills": req.generated_skills,
        "delivery_channels": req.delivery_channels,
        "channel_details": req.channel_details,
        "mio_signature": req.mio_signature,
    }
    return await dispatch_mandate(req.session_id, mandate)


@api_router.get("/mandate/progress/{session_id}")
async def api_mandate_progress(session_id: str):
    """Get current pipeline progress for a session."""
    db = get_db()
    doc = await db.pipeline_progress.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        return {"session_id": session_id, "current_stage": -1, "stages": {}}
    return doc


# ---- Session Status ----
class SessionStatus(BaseModel):
    session_id: str
    active: bool
    presence_ok: bool
    last_heartbeat_age_info: str


@api_router.get("/session/{session_id}", response_model=SessionStatus)
async def get_session_status(session_id: str):
    """Get session status including presence check."""
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    presence_ok = await check_presence(session_id)

    return SessionStatus(
        session_id=session_id,
        active=session.active,
        presence_ok=presence_ok,
        last_heartbeat_age_info="fresh" if presence_ok else "stale",
    )


# =====================================================
#  Digital Self APIs (Batch 5)
# =====================================================

class StoreFactRequest(BaseModel):
    user_id: str
    text: str
    fact_type: str = "FACT"
    provenance: str = "EXPLICIT"

class RegisterEntityRequest(BaseModel):
    user_id: str
    entity_type: str
    name: str
    aliases: List[str] = []

class RecallRequest(BaseModel):
    user_id: str
    query: str
    n_results: int = 3


@api_router.post("/memory/store")
async def api_store_fact(req: StoreFactRequest):
    """Store a fact in the Digital Self."""
    from memory.write_policy import can_write
    if not can_write("user_confirmation"):
        raise HTTPException(status_code=403, detail="Write not allowed")
    node_id = await digital_self.store_fact(
        user_id=req.user_id, text=req.text,
        fact_type=req.fact_type, provenance=req.provenance,
    )
    return {"node_id": node_id, "status": "stored"}


@api_router.post("/memory/entity")
async def api_register_entity(req: RegisterEntityRequest):
    """Register an entity in the Digital Self."""
    entity_id = await digital_self.register_entity(
        user_id=req.user_id, entity_type=req.entity_type,
        name=req.name, aliases=req.aliases,
    )
    return {"entity_id": entity_id, "status": "registered"}


@api_router.post("/memory/recall")
async def api_recall(req: RecallRequest):
    """Recall memories from the Digital Self."""
    results = await digital_self.recall(
        user_id=req.user_id, query_text=req.query, n_results=req.n_results,
    )
    stats = digital_self.get_memory_stats(req.user_id)
    return {"results": results, "stats": stats}


# =====================================================
#  Digital Self Vector Sync (Device → Backend)
#  Receives node text, generates ONNX vector, stores
#  vector only — text is NEVER persisted.
# =====================================================

class DSSyncNode(BaseModel):
    node_id: str
    text: str   # Used to generate embedding only. Discarded after.

class DSSyncRequest(BaseModel):
    user_id: str
    nodes: List[DSSyncNode]

class DSTombstoneRequest(BaseModel):
    user_id: str
    deleted_node_ids: List[str]


@api_router.post("/digital-self/sync")
async def api_ds_sync(req: DSSyncRequest, request: Request):
    """Receive PKG node texts from device, embed via ONNX, store vectors only.

    The text payload is used ONCE to generate a 384-dim ONNX vector.
    Only the vector + node_id + user_id metadata is stored in ChromaDB/MongoDB.
    The text is never written to any database.
    """
    from memory.client.vector import add_document
    from memory.client.embedder import embed

    if not req.nodes:
        return {"synced": 0}

    texts = [n.text for n in req.nodes]
    vectors = embed(texts)

    synced = 0
    for node, vector in zip(req.nodes, vectors):
        add_document(
            doc_id=node.node_id,
            text="",           # Intentionally empty — text is NOT stored
            metadata={
                "user_id": req.user_id,
                "node_id": node.node_id,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        synced += 1

    logger.info("[DS Sync] user=%s synced=%d nodes", req.user_id, synced)
    return {"synced": synced}


@api_router.delete("/digital-self/sync")
async def api_ds_tombstone(req: DSTombstoneRequest):
    """Remove vectors for deleted PKG nodes."""
    from memory.client.vector import delete_document

    deleted = 0
    for node_id in req.deleted_node_ids:
        try:
            delete_document(node_id)
            deleted += 1
        except Exception:
            pass

    logger.info("[DS Sync] user=%s tombstoned=%d nodes", req.user_id, deleted)
    return {"deleted": deleted}




class CreateCommitRequest(BaseModel):
    session_id: str
    draft_id: str
    intent_summary: str
    intent: str
    dimensions: Optional[dict] = None


class TransitionCommitRequest(BaseModel):
    commit_id: str
    to_state: str
    reason: str = ""


@api_router.post("/commit/create")
async def api_create_commit(req: CreateCommitRequest):
    """Create a new commit in DRAFT state."""
    return await create_commit(
        session_id=req.session_id,
        draft_id=req.draft_id,
        intent_summary=req.intent_summary,
        intent=req.intent,
        dimensions=req.dimensions,
    )


@api_router.post("/commit/transition")
async def api_transition_commit(req: TransitionCommitRequest):
    """Transition a commit to a new state."""
    try:
        state = CommitState(req.to_state)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid state: {req.to_state}")
    try:
        return await commit_transition(req.commit_id, state, req.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@api_router.get("/commit/{commit_id}")
async def api_get_commit(commit_id: str):
    """Get a commit by ID."""
    doc = await get_commit(commit_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Commit not found")
    return doc


@api_router.get("/commits/session/{session_id}")
async def api_get_session_commits(session_id: str):
    """Get all commits for a session."""
    return await get_session_commits(session_id)


@api_router.get("/commits/recover")
async def api_recover_pending():
    """Recovery: list commits in non-terminal states."""
    return await recover_pending()


# =====================================================
#  L2 Sentry + QC Sentry Diagnostic APIs (Batch 7)
# =====================================================

class L2RunRequest(BaseModel):
    session_id: str = "diagnostic"
    user_id: str = "diagnostic"
    transcript: str
    l1_intent: str = ""
    l1_confidence: float = 0.0


class QCRunRequest(BaseModel):
    session_id: str = "diagnostic"
    user_id: str = "diagnostic"
    transcript: str
    intent: str
    intent_summary: str


@api_router.post("/l2/run")
async def api_run_l2(req: L2RunRequest):
    """Diagnostic: run L2 Sentry on a transcript."""
    verdict = await run_l2_sentry(
        session_id=req.session_id,
        user_id=req.user_id,
        transcript=req.transcript,
        l1_intent=req.l1_intent,
        l1_confidence=req.l1_confidence,
    )
    return {
        "verdict_id": verdict.verdict_id,
        "intent": verdict.intent,
        "confidence": verdict.confidence,
        "risk_tier": verdict.risk_tier,
        "chain_of_logic": verdict.chain_of_logic,
        "shadow_agrees_with_l1": verdict.shadow_agrees_with_l1,
        "conflicts": verdict.conflicts,
        "latency_ms": verdict.latency_ms,
        "is_mock": verdict.is_mock,
    }


@api_router.post("/qc/run")
async def api_run_qc(req: QCRunRequest):
    """Diagnostic: run QC Sentry on an intent."""
    verdict = await run_qc_sentry(
        session_id=req.session_id,
        user_id=req.user_id,
        transcript=req.transcript,
        intent=req.intent,
        intent_summary=req.intent_summary,
    )
    return {
        "verdict_id": verdict.verdict_id,
        "passes": [
            {"name": p.pass_name, "passed": p.passed, "severity": p.severity, "reason": p.reason, "spans": p.cited_spans}
            for p in verdict.passes
        ],
        "overall_pass": verdict.overall_pass,
        "block_reason": verdict.block_reason,
        "latency_ms": verdict.latency_ms,
        "is_mock": verdict.is_mock,
    }


# =====================================================
#  MIO Signing + Verification APIs (Batch 8)
# =====================================================

class MIOSignRequest(BaseModel):
    mio_dict: dict


class MIOVerifyRequest(BaseModel):
    mio_dict: dict
    signature: str
    session_id: str
    device_id: str
    tier: int = 0
    touch_token: Optional[str] = None


@api_router.post("/mio/sign")
async def api_sign_mio(req: MIOSignRequest):
    """Sign a MIO with ED25519."""
    signature = sign_mio(req.mio_dict)
    return {"signature": signature, "public_key": get_public_key_hex()}


@api_router.post("/mio/verify")
async def api_verify_mio(req: MIOVerifyRequest):
    """Full MIO verification pipeline."""
    valid, reason = await verify_mio_for_execution(
        mio_dict=req.mio_dict,
        signature=req.signature,
        session_id=req.session_id,
        device_id=req.device_id,
        tier=req.tier,
        touch_token=req.touch_token,
    )
    return {"valid": valid, "reason": reason}


@api_router.get("/mio/public-key")
async def api_mio_public_key():
    """Get the MIO signing public key."""
    return {"public_key": get_public_key_hex(), "algorithm": "ED25519"}


# =====================================================
#  Dispatcher API (Batch 9)
# =====================================================

class DispatchRequest(BaseModel):
    mio_dict: dict
    signature: str
    session_id: str
    device_id: str
    tenant_id: str


@api_router.post("/dispatch")
async def api_dispatch(req: DispatchRequest):
    """Dispatch a signed MIO to OpenClaw via the Dispatcher."""
    from dispatcher.dispatcher import dispatch
    try:
        result = await dispatch(
            mio_dict=req.mio_dict,
            signature=req.signature,
            session_id=req.session_id,
            device_id=req.device_id,
            tenant_id=req.tenant_id,
        )
        return result
    except DispatchBlockedError as e:
        raise HTTPException(status_code=403, detail=str(e))


# =====================================================
#  Observability + Rate Limits (Batch 11)
# =====================================================

@api_router.get("/metrics")
async def api_metrics():
    """System metrics dashboard."""
    return await get_system_metrics()


class RateLimitCheckRequest(BaseModel):
    key: str
    limit_type: str


@api_router.post("/rate-limit/check")
async def api_check_rate_limit(req: RateLimitCheckRequest):
    """Check a rate limit."""
    allowed, reason = await check_rate_limit(req.key, req.limit_type)
    status = await get_rate_status(req.key, req.limit_type)
    return {"allowed": allowed, "reason": reason, "status": status}


@api_router.get("/circuit-breakers")
async def api_circuit_breakers():
    """Get all circuit breaker statuses."""
    return {"breakers": get_all_breaker_statuses()}


# =====================================================
#  Data Governance + Backup/Restore (Batch 12)
# =====================================================

class BackupRequest(BaseModel):
    user_id: str
    include_audit: bool = True


class RestoreRequest(BaseModel):
    backup_id: str


@api_router.post("/governance/backup")
async def api_create_backup(req: BackupRequest, x_obegee_s2s_token: str = Header(None)):
    """Create a backup snapshot. Requires S2S auth."""
    _verify_s2s_token(x_obegee_s2s_token)
    from governance.backup import create_backup
    return await create_backup(req.user_id, req.include_audit)


@api_router.get("/governance/backups/{user_id}")
async def api_list_backups(user_id: str, x_obegee_s2s_token: str = Header(None)):
    """List backups for a user. Requires S2S auth."""
    _verify_s2s_token(x_obegee_s2s_token)
    from governance.backup import list_backups
    return await list_backups(user_id)


@api_router.post("/governance/restore")
async def api_restore_backup(req: RestoreRequest, x_obegee_s2s_token: str = Header(None)):
    """Restore from a backup. Requires S2S auth."""
    _verify_s2s_token(x_obegee_s2s_token)
    from governance.restore import restore_from_backup
    try:
        return await restore_from_backup(req.backup_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@api_router.get("/governance/retention")
async def api_retention_status():
    """Get retention policy status."""
    from governance.retention import get_retention_status
    return await get_retention_status()


@api_router.post("/governance/retention/cleanup")
async def api_retention_cleanup(x_obegee_s2s_token: str = Header(None)):
    """Run retention cleanup. Requires S2S auth."""
    _verify_s2s_token(x_obegee_s2s_token)
    from governance.retention import run_retention_cleanup
    return await run_retention_cleanup()


# =====================================================
#  Soul Management APIs (Batch 13)
# =====================================================

@api_router.get("/soul/status")
async def api_soul_status():
    """Get soul status: version, integrity, drift check."""
    from soul.store import retrieve_soul
    from soul.versioning import get_current_version, verify_integrity
    from soul.drift_controls import check_drift

    version = await get_current_version()
    integrity = await verify_integrity()
    drift = check_drift()
    fragments = retrieve_soul()

    return {
        "version": version,
        "integrity": integrity,
        "drift": drift,
        "fragments": len(fragments),
    }


class UserSoulRequest(BaseModel):
    user_id: str
    text: str
    category: str


@api_router.post("/soul/personalize")
async def api_personalize_soul(req: UserSoulRequest):
    """Add a user-specific soul fragment (requires explicit user signal)."""
    from soul.store import add_user_soul_fragment
    frag_id = await add_user_soul_fragment(req.user_id, req.text, req.category)
    return {"fragment_id": frag_id, "category": req.category}


# ---- Prompt System Diagnostic (no behavior change) ----
class PromptBuildRequest(BaseModel):
    purpose: str  # PromptPurpose value
    transcript: str = ""
    task_description: str = ""


@api_router.post("/prompt/build")
async def build_prompt(req: PromptBuildRequest):
    """Diagnostic: build a prompt artifact + report without calling LLM.
    
    No behavior change. Tests the prompt system infrastructure.
    """
    try:
        purpose = PromptPurpose(req.purpose)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid purpose: {req.purpose}")

    ctx = PromptContext(
        purpose=purpose,
        mode=PromptMode.INTERACTIVE,
        session_id="diagnostic",
        user_id="diagnostic",
        transcript=req.transcript or None,
        task_description=req.task_description or None,
    )

    orchestrator = PromptOrchestrator()
    artifact, report = orchestrator.build(ctx)

    # Persist snapshot
    await save_prompt_snapshot(report)

    return {
        "prompt_id": artifact.prompt_id,
        "purpose": artifact.purpose.value,
        "sections_included": [s.value for s in artifact.sections_included],
        "sections_excluded": [s.value for s in artifact.sections_excluded],
        "messages": artifact.messages,
        "stable_hash": artifact.stable_hash,
        "volatile_hash": artifact.volatile_hash,
        "total_tokens_est": artifact.total_tokens_est,
        "report": report.to_doc(),
    }


# ---- Prompt Compliance Report (Truth Endpoint) ----

@api_router.get("/prompt/compliance")
async def prompt_compliance():
    """Truth endpoint: prompt system compliance report.
    
    Returns: call sites, last snapshots per purpose, stable hashes,
    bypass attempts, rogue prompt scan results.
    No prompt bodies — hashes only.
    """
    from prompting.call_sites import list_all as list_call_sites
    from prompting.types import PromptPurpose

    db = get_db()

    # Call site registry
    call_sites = list_call_sites()

    # Last N snapshots per purpose
    snapshots_by_purpose = {}
    for purpose in PromptPurpose:
        cursor = db.prompt_snapshots.find(
            {"purpose": purpose.value},
            {"_id": 0, "prompt_id": 1, "purpose": 1, "stable_hash": 1, "volatile_hash": 1, "budget_used": 1, "created_at": 1},
        ).sort("created_at", -1).limit(3)
        snapshots_by_purpose[purpose.value] = await cursor.to_list(3)

    # Stable hashes per purpose (from latest snapshot)
    stable_hashes = {}
    for purpose, snaps in snapshots_by_purpose.items():
        if snaps:
            stable_hashes[purpose] = snaps[0].get("stable_hash", "none")

    # Bypass attempts
    bypass_cursor = db.audit_events.find(
        {"event_type": "prompt_bypass_attempt"},
        {"_id": 0, "event_id": 1, "timestamp": 1, "details": 1},
    ).sort("timestamp", -1).limit(10)
    bypass_events = await bypass_cursor.to_list(10)
    bypass_count = await db.audit_events.count_documents({"event_type": "prompt_bypass_attempt"})

    # Rogue prompt scan (static analysis)
    rogue_scan = _scan_for_rogue_prompts()

    return {
        "call_sites": call_sites,
        "snapshots_by_purpose": {k: [_serialize_snap(s) for s in v] for k, v in snapshots_by_purpose.items()},
        "stable_hashes": stable_hashes,
        "bypass_attempts": {
            "total_count": bypass_count,
            "recent": bypass_events,
        },
        "rogue_prompt_scan": rogue_scan,
    }


def _serialize_snap(snap: dict) -> dict:
    """Serialize a snapshot for JSON output."""
    result = {}
    for k, v in snap.items():
        if hasattr(v, 'isoformat'):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


def _scan_for_rogue_prompts() -> dict:
    """Static scan for rogue prompt patterns in the codebase."""
    import os
    import re

    violations = []
    allowed_dirs = {"prompting/sections", "tests"}
    scan_dir = Path(__file__).parent

    patterns = [
        (re.compile(r'LlmChat\s*\('), "LlmChat( import outside llm_gateway"),
        (re.compile(r'from emergentintegrations\.llm'), "Direct emergentintegrations.llm import"),
        # Ownership violations (Dev Agent Contract)
        (re.compile(r'call_openclaw\s*\('), "Direct OpenClaw call (must use ObeGee adapter)"),
        (re.compile(r'activate_tenant\s*\('), "Tenant lifecycle (ObeGee-owned) in MyndLens code"),
        (re.compile(r'suspend_tenant\s*\('), "Tenant lifecycle (ObeGee-owned) in MyndLens code"),
        (re.compile(r'deprovision_tenant\s*\('), "Tenant lifecycle (ObeGee-owned) in MyndLens code"),
        (re.compile(r'rotate_tenant_key\s*\('), "Tenant key mgmt (ObeGee-owned) in MyndLens code"),
        (re.compile(r'subprocess\..*ssh'), "SSH attempt (MyndLens has no infra access)"),
        (re.compile(r'os\.system.*restart'), "Service restart (MyndLens has no deployment authority)"),
    ]

    for root, dirs, files in os.walk(scan_dir):
        rel_root = os.path.relpath(root, scan_dir)
        # Skip allowed dirs and non-python files
        if any(rel_root.startswith(a) for a in allowed_dirs):
            continue
        if "__pycache__" in rel_root:
            continue

        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, scan_dir)

            # Skip the gateway itself and the scanner function
            if rel_path == "prompting/llm_gateway.py":
                continue

            try:
                with open(fpath, "r") as f:
                    content = f.read()

                # Skip scanner function in server.py (self-reference)
                if rel_path == "server.py":
                    content_lines = content.split("\n")
                    in_scanner = False
                    filtered = []
                    for line in content_lines:
                        if "def _scan_for_rogue_prompts" in line:
                            in_scanner = True
                        elif in_scanner and (line and not line[0].isspace() and line[0] != "#"):
                            in_scanner = False
                        if not in_scanner:
                            filtered.append(line)
                    content = "\n".join(filtered)

                for pattern, desc in patterns:
                    matches = pattern.findall(content)
                    if matches:
                        violations.append({
                            "file": rel_path,
                            "pattern": desc,
                            "count": len(matches),
                        })
            except Exception:
                pass

    return {
        "clean": len(violations) == 0,
        "violations": violations,
        "files_scanned": sum(1 for _ in scan_dir.rglob("*.py")),
    }


# =====================================================
#  Prompt Outcome Tracking & Analytics (Phase 1)
# =====================================================

class TrackOutcomeRequest(BaseModel):
    prompt_id: str
    purpose: str
    session_id: str = "diagnostic"
    user_id: str = "diagnostic"
    result: str = "SUCCESS"
    accuracy_score: float = 0.0
    execution_success: bool = True
    user_corrected: bool = False
    latency_ms: float = 0.0
    tokens_used: int = 0
    sections_used: List[str] = []
    model_name: str = ""


@api_router.post("/prompt/track-outcome")
async def api_track_outcome(req: TrackOutcomeRequest):
    """Track the outcome of a prompt execution."""
    from prompting.outcomes import PromptOutcome, OutcomeResult, track_outcome
    outcome = PromptOutcome(
        prompt_id=req.prompt_id,
        purpose=req.purpose,
        session_id=req.session_id,
        user_id=req.user_id,
        result=OutcomeResult(req.result),
        accuracy_score=req.accuracy_score,
        execution_success=req.execution_success,
        user_corrected=req.user_corrected,
        latency_ms=req.latency_ms,
        tokens_used=req.tokens_used,
        sections_used=req.sections_used,
        model_name=req.model_name,
    )
    await track_outcome(outcome)
    return {"status": "tracked", "prompt_id": req.prompt_id}


class UserCorrectionRequest(BaseModel):
    session_id: str
    user_id: str
    original_intent: str
    corrected_intent: str
    prompt_id: Optional[str] = None


@api_router.post("/prompt/user-correction")
async def api_user_correction(req: UserCorrectionRequest):
    """Record a user correction for learning."""
    from prompting.outcomes import track_user_correction
    await track_user_correction(
        session_id=req.session_id,
        user_id=req.user_id,
        original_intent=req.original_intent,
        corrected_intent=req.corrected_intent,
        prompt_id=req.prompt_id,
    )
    return {"status": "recorded"}


@api_router.get("/prompt/analytics/{purpose}")
async def api_purpose_analytics(purpose: str, days: int = 30):
    """Get accuracy analytics for a specific purpose."""
    from prompting.analytics import get_purpose_accuracy
    return await get_purpose_accuracy(purpose, days)


@api_router.get("/prompt/analytics")
async def api_all_analytics(days: int = 30):
    """Get optimization insights across all purposes."""
    from prompting.analytics import get_optimization_insights
    return await get_optimization_insights(days)


@api_router.get("/prompt/section-effectiveness")
async def api_section_effectiveness(days: int = 30):
    """Get section effectiveness scores."""
    from prompting.analytics import get_section_effectiveness
    return await get_section_effectiveness(days)


# =====================================================
#  Dimension Extraction API (Phase 1)
# =====================================================

class DimensionExtractRequest(BaseModel):
    session_id: str = "diagnostic"
    user_id: str = "diagnostic"
    transcript: str
    l1_suggestions: Optional[dict] = None


@api_router.post("/dimensions/extract")
async def api_extract_dimensions(req: DimensionExtractRequest):
    """Dedicated dimension extraction using DIMENSIONS_EXTRACT purpose."""
    from dimensions.extractor import extract_dimensions_via_llm
    result = await extract_dimensions_via_llm(
        session_id=req.session_id,
        user_id=req.user_id,
        transcript=req.transcript,
        l1_suggestions=req.l1_suggestions,
    )
    return result


# =====================================================
#  Experiment Framework APIs (Phase 2)
# =====================================================

@api_router.get("/prompt/experiments")
async def api_list_experiments():
    """List all prompt experiments."""
    from prompting.experiments import list_experiments
    return await list_experiments()


@api_router.post("/prompt/experiments")
async def api_create_experiment(request: Request):
    """Create a new prompt experiment."""
    from prompting.experiments import create_experiment
    data = await request.json()
    return await create_experiment(data)


@api_router.get("/prompt/experiments/{experiment_id}/results")
async def api_experiment_results(experiment_id: str):
    """Get experiment results."""
    from prompting.experiments import get_experiment_results
    return await get_experiment_results(experiment_id)


# =====================================================
#  Adaptive Policy Engine (Phase 3)
# =====================================================

@api_router.get("/prompt/adaptive-insights")
async def api_adaptive_insights():
    """Get adaptive policy insights and recommendations."""
    from prompting.policy.adaptive import get_adaptive_insights
    return await get_adaptive_insights()


@api_router.get("/prompt/policy-recommendations")
async def api_policy_recommendations(days: int = 30):
    """Get policy adjustment recommendations based on outcome data."""
    from prompting.policy.adaptive import generate_policy_recommendations
    return await generate_policy_recommendations(days)


# =====================================================
#  Agent Builder APIs (Phase 4)
# =====================================================

@api_router.post("/agents/create")
async def api_create_agent(request: Request):
    """Create a new OpenClaw agent from structured intent."""
    from agents.builder import AgentBuilder
    data = await request.json()
    builder = AgentBuilder()
    return await builder.create_agent(data)


@api_router.post("/agents/modify")
async def api_modify_agent(request: Request):
    """Modify an existing agent."""
    from agents.builder import AgentBuilder
    data = await request.json()
    builder = AgentBuilder()
    return await builder.modify_agent(data)


@api_router.post("/agents/retire")
async def api_retire_agent(request: Request):
    """Retire an agent (soft or hard)."""
    from agents.builder import AgentBuilder
    data = await request.json()
    builder = AgentBuilder()
    return await builder.retire_agent(data)


@api_router.post("/agents/delete")
async def api_delete_agent(request: Request):
    """Delete an agent (admin-only, irreversible)."""
    from agents.builder import AgentBuilder
    data = await request.json()
    builder = AgentBuilder()
    return await builder.delete_agent(data)


@api_router.post("/agents/unretire")
async def api_unretire_agent(request: Request):
    """Restore a retired agent to active."""
    from agents.builder import AgentBuilder
    data = await request.json()
    builder = AgentBuilder()
    return await builder.unretire_agent(data)


@api_router.get("/agents/list/{tenant_id}")
async def api_list_agents(tenant_id: str, include_retired: bool = False):
    """List agents for a tenant."""
    from agents.builder import AgentBuilder
    builder = AgentBuilder()
    return await builder.list_agents(tenant_id, include_retired)


@api_router.get("/agents/{agent_id}")
async def api_get_agent(agent_id: str):
    """Get a single agent by ID."""
    from agents.builder import AgentBuilder
    builder = AgentBuilder()
    agent = await builder.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


# =====================================================
#  Unhinged Demo Agent APIs (Phase 4 - DEMO_UNHINGED)
# =====================================================

@api_router.post("/agents/unhinged/create")
async def api_create_unhinged_agent(request: Request):
    """Create an unhinged demo agent.

    Required fields: tenant.tenant_id, demo_sender (E.164 phone).
    Optional: sandbox_mode (off/recommended/required), approved (bool), agent_id.
    First call without approved=true returns an approval prompt.
    """
    from agents.builder import AgentBuilder
    data = await request.json()
    builder = AgentBuilder()
    return await builder.create_unhinged_demo_agent(data)


@api_router.post("/agents/unhinged/teardown")
async def api_teardown_unhinged_agent(request: Request):
    """Teardown an unhinged demo agent.

    Required: agent_id.
    Optional: mode (quick/full). Default: quick.
    """
    from agents.builder import AgentBuilder
    data = await request.json()
    builder = AgentBuilder()
    return await builder.teardown_demo_agent(
        agent_id=data.get("agent_id", ""),
        mode=data.get("mode", "quick"),
    )


@api_router.get("/agents/unhinged/teardown-options")
async def api_teardown_options():
    """Get available teardown options for demo agents."""
    from agents.unhinged import get_teardown_options
    return get_teardown_options()


@api_router.get("/agents/unhinged/test-suite/{agent_id}")
async def api_unhinged_test_suite(agent_id: str, demo_sender: str = "+15555550123"):
    """Get the 8-test validation suite for an unhinged agent."""
    from agents.unhinged import get_test_suite
    return {"agent_id": agent_id, "tests": get_test_suite(agent_id, demo_sender)}


# =====================================================
#  Skills Library APIs (Spec 7)
# =====================================================

@api_router.post("/skills/index")
async def api_index_skills():
    """Load and index the skills library from JSON."""
    from skills.library import load_and_index_library
    return await load_and_index_library()


@api_router.get("/skills/search")
async def api_search_skills(q: str, limit: int = 10):
    """Search skills by keyword."""
    from skills.library import search_skills
    return await search_skills(q, limit)


@api_router.get("/skills/match")
async def api_match_skills(intent: str, top_n: int = 5):
    """Match skills to a user intent."""
    from skills.library import match_skills_to_intent
    return await match_skills_to_intent(intent, top_n)


@api_router.post("/skills/build")
async def api_build_skill(request: Request):
    """Build a custom skill from matched skills + device data."""
    from skills.library import match_skills_to_intent, build_skill
    data = await request.json()
    intent = data.get("intent", "")
    device_data = data.get("device_data", {})
    matched = await match_skills_to_intent(intent)
    return await build_skill(matched, intent, device_data)


@api_router.get("/skills/stats")
async def api_skills_stats():
    """Get skills library statistics."""
    from skills.library import get_library_stats
    return await get_library_stats()


@api_router.get("/skills/classify-risk")
async def api_classify_risk(description: str):
    """Classify risk level of a skill description."""
    from skills.library import classify_risk
    return {"description": description, "risk": classify_risk(description)}


# =====================================================
#  Prompt Versioning APIs
# =====================================================

class CreateVersionRequest(BaseModel):
    purpose: str
    config: dict
    author: str = "system"
    change_description: str = ""


@api_router.post("/prompt/versions")
async def api_create_version(req: CreateVersionRequest):
    """Create a new version of a prompt configuration."""
    from prompting.versioning import create_version
    return await create_version(req.purpose, req.config, req.author, req.change_description)


@api_router.get("/prompt/versions/{purpose}")
async def api_list_versions(purpose: str, limit: int = 20):
    """List all versions for a purpose."""
    from prompting.versioning import list_versions
    return await list_versions(purpose, limit)


@api_router.get("/prompt/versions/{purpose}/active")
async def api_active_version(purpose: str):
    """Get the active version for a purpose."""
    from prompting.versioning import get_active_version
    result = await get_active_version(purpose)
    if not result:
        return {"purpose": purpose, "active": False, "message": "No active version"}
    return result


@api_router.get("/prompt/version/{version_id}")
async def api_get_version(version_id: str):
    """Get a specific version by ID."""
    from prompting.versioning import get_version
    result = await get_version(version_id)
    if not result:
        raise HTTPException(status_code=404, detail="Version not found")
    return result


class RollbackRequest(BaseModel):
    version_id: str
    author: str = "system"


@api_router.post("/prompt/versions/rollback")
async def api_rollback_version(req: RollbackRequest):
    """Rollback to a specific version."""
    from prompting.versioning import rollback_to_version
    return await rollback_to_version(req.version_id, req.author)


class CompareRequest(BaseModel):
    version_id_a: str
    version_id_b: str


@api_router.post("/prompt/versions/compare")
async def api_compare_versions(req: CompareRequest):
    """Compare two versions."""
    from prompting.versioning import compare_versions
    return await compare_versions(req.version_id_a, req.version_id_b)


# =====================================================
#  Per-User Optimization Profile APIs
# =====================================================

@api_router.get("/user-profile/{user_id}")
async def api_get_user_profile(user_id: str):
    """Get a user's optimization profile."""
    from prompting.user_profiles import get_user_profile
    return await get_user_profile(user_id)


@api_router.put("/user-profile/{user_id}")
async def api_update_user_profile(user_id: str, request: Request):
    """Update a user's optimization profile."""
    from prompting.user_profiles import update_user_profile
    data = await request.json()
    return await update_user_profile(user_id, data)


@api_router.post("/user-profile/{user_id}/learn")
async def api_learn_user_profile(user_id: str, days: int = 30):
    """Analyze outcomes and generate profile recommendations for a user."""
    from prompting.user_profiles import learn_from_outcomes
    return await learn_from_outcomes(user_id, days)


@api_router.get("/user-profile/{user_id}/adjustments")
async def api_user_adjustments(user_id: str):
    """Get prompt adjustments for a user (used by orchestrator)."""
    from prompting.user_profiles import get_prompt_adjustments
    return await get_prompt_adjustments(user_id)


# =====================================================
#  Optimization Scheduler APIs
# =====================================================

@api_router.post("/optimization/run")
async def api_run_optimization(days: int = 7):
    """Trigger a manual optimization cycle."""
    from prompting.optimizer_job import run_optimization_cycle
    return await run_optimization_cycle(days)


@api_router.post("/optimization/scheduler/start")
async def api_start_scheduler(interval_seconds: int = 3600):
    """Start the background optimization scheduler."""
    from prompting.optimizer_job import start_scheduler
    return start_scheduler(interval_seconds)


@api_router.post("/optimization/scheduler/stop")
async def api_stop_scheduler():
    """Stop the background optimization scheduler."""
    from prompting.optimizer_job import stop_scheduler
    return stop_scheduler()


@api_router.get("/optimization/scheduler/status")
async def api_scheduler_status():
    """Get scheduler status."""
    from prompting.optimizer_job import get_scheduler_status
    return get_scheduler_status()


@api_router.get("/optimization/runs")
async def api_optimization_runs(limit: int = 10):
    """List recent optimization runs."""
    from prompting.optimizer_job import list_runs
    return await list_runs(limit)


# =====================================================
#  Agent Workspace File I/O APIs
# =====================================================

class WorkspaceCreateRequest(BaseModel):
    agent_id: str
    soil: dict


@api_router.post("/workspace/create")
async def api_create_workspace(req: WorkspaceCreateRequest):
    """Create a workspace with soil files."""
    from agents.workspace import create_workspace
    return create_workspace(req.agent_id, req.soil)


@api_router.get("/workspace/{agent_id}/files")
async def api_list_workspace_files(agent_id: str):
    """List files in an agent's workspace."""
    from agents.workspace import list_files
    return list_files(agent_id)


@api_router.get("/workspace/{agent_id}/file/{filename}")
async def api_read_workspace_file(agent_id: str, filename: str):
    """Read a file from an agent's workspace."""
    from agents.workspace import read_file
    content = read_file(agent_id, filename)
    if content is None:
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
    return {"agent_id": agent_id, "filename": filename, "content": content}


class WriteFileRequest(BaseModel):
    content: str


@api_router.put("/workspace/{agent_id}/file/{filename}")
async def api_write_workspace_file(agent_id: str, filename: str, req: WriteFileRequest):
    """Write or overwrite a file in an agent's workspace."""
    from agents.workspace import write_file
    return write_file(agent_id, filename, req.content)


@api_router.delete("/workspace/{agent_id}/file/{filename}")
async def api_delete_workspace_file(agent_id: str, filename: str):
    """Delete a file from an agent's workspace."""
    from agents.workspace import delete_file
    if not delete_file(agent_id, filename):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
    return {"status": "deleted", "agent_id": agent_id, "filename": filename}


@api_router.get("/workspace/{agent_id}/stats")
async def api_workspace_stats(agent_id: str):
    """Get workspace statistics."""
    from agents.workspace import get_workspace_stats
    return get_workspace_stats(agent_id)


@api_router.post("/workspace/{agent_id}/archive")
async def api_archive_workspace(agent_id: str):
    """Archive a workspace."""
    from agents.workspace import archive_workspace
    path = archive_workspace(agent_id)
    if not path:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"status": "archived", "agent_id": agent_id, "archive_path": path}


@api_router.delete("/workspace/{agent_id}")
async def api_delete_workspace(agent_id: str):
    """Permanently delete a workspace."""
    from agents.workspace import delete_workspace
    if not delete_workspace(agent_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"status": "deleted", "agent_id": agent_id}


@api_router.get("/workspace/archives")
async def api_list_archives():
    """List archived workspaces."""
    from agents.workspace import list_archived_workspaces
    return list_archived_workspaces()


# =====================================================
#  Intent RL Test Framework
# =====================================================

@api_router.post("/intent-rl/seed")
async def api_seed_digital_self():
    """Seed the RL test user's Digital Self with mock data (contacts, facts, routines)."""
    from intent_rl.seed_digital_self import seed_digital_self, clear_digital_self
    clear_stats = await clear_digital_self()
    seed_stats = await seed_digital_self()
    return {"status": "seeded", "cleared": clear_stats, "seeded": seed_stats}


@api_router.post("/intent-rl/run")
async def api_start_intent_rl(batch_size: int = 100, seed: bool = True):
    """Start the intent RL test batch. Auto-seeds Digital Self if seed=true."""
    from intent_rl.runner import run_intent_rl_batch, get_current_run
    current = get_current_run()
    if current and current.in_progress:
        return {"status": "already_running", "run_id": current.run_id, "progress": f"{current.completed}/{current.total}"}
    if seed:
        from intent_rl.seed_digital_self import seed_digital_self, clear_digital_self
        await clear_digital_self()
        seed_stats = await seed_digital_self()
    else:
        seed_stats = None
    run_id = await run_intent_rl_batch(batch_size=min(batch_size, 100))
    return {"status": "started", "run_id": run_id, "total_cases": min(batch_size, 100), "digital_self_seeded": seed_stats}


@api_router.get("/intent-rl/status")
async def api_intent_rl_status():
    """Get current RL batch status and live accuracy."""
    from intent_rl.runner import get_current_run
    run = get_current_run()
    if not run:
        return {"status": "no_run", "message": "No RL run active. POST /api/intent-rl/run to start."}
    return {
        "run_id": run.run_id, "in_progress": run.in_progress,
        "progress": f"{run.completed}/{run.total}",
        "class_accuracy": round(run.class_accuracy * 100, 1),
        "class_correct": run.class_correct,
        "avg_latency_ms": round(run.avg_latency_ms, 1),
        "per_class": run.per_class,
        "failure_count": len(run.failures),
        "corrections_submitted": run.corrections_submitted,
        "started_at": run.started_at, "completed_at": run.completed_at,
    }


@api_router.get("/intent-rl/results")
async def api_intent_rl_results():
    """Get full results including all cases and failures."""
    from intent_rl.runner import get_current_run
    run = get_current_run()
    if not run:
        return {"status": "no_run"}
    return {
        "run_id": run.run_id, "in_progress": run.in_progress,
        "total": run.total, "completed": run.completed,
        "class_accuracy": round(run.class_accuracy * 100, 1),
        "class_correct": run.class_correct, "avg_latency_ms": round(run.avg_latency_ms, 1),
        "per_class": run.per_class, "failures": run.failures, "cases": run.cases,
        "corrections_submitted": run.corrections_submitted,
    }


@api_router.get("/intent-rl/history")
async def api_intent_rl_history(limit: int = 10):
    """Get historical RL run results."""
    from intent_rl.runner import get_historical_runs
    return {"runs": await get_historical_runs(limit)}


# ── Intent RL v2: Broken Thoughts with Main Intent + Sub-Intents ──

@api_router.post("/intent-rl/v2/run")
async def api_start_intent_rl_v2(batch_size: int = 40, seed: bool = True):
    """Start v2 RL test — broken thoughts, main intent, sub-intents, entity resolution."""
    from intent_rl.runner_v2 import run_v2_batch, get_current_v2_run
    current = get_current_v2_run()
    if current and current.in_progress:
        return {"status": "already_running", "run_id": current.run_id, "progress": f"{current.completed}/{current.total}"}
    if seed:
        from intent_rl.seed_digital_self import seed_digital_self, clear_digital_self
        await clear_digital_self()
        seed_stats = await seed_digital_self()
    else:
        seed_stats = None
    run_id = await run_v2_batch(batch_size=min(batch_size, 40))
    return {"status": "started", "run_id": run_id, "total_cases": min(batch_size, 40), "digital_self_seeded": seed_stats}


@api_router.get("/intent-rl/v2/status")
async def api_intent_rl_v2_status():
    """Get v2 batch status — intent accuracy, sub-intent coverage, entity resolution."""
    from intent_rl.runner_v2 import get_current_v2_run
    run = get_current_v2_run()
    if not run:
        return {"status": "no_run"}
    return {
        "run_id": run.run_id, "version": "v2", "in_progress": run.in_progress,
        "progress": f"{run.completed}/{run.total}",
        "intent_accuracy": round(run.intent_accuracy * 100, 1),
        "avg_sub_intent_coverage": round(run.avg_sub_intent_coverage * 100, 1),
        "avg_entity_coverage": round(run.avg_entity_coverage * 100, 1),
        "intent_correct": run.intent_correct,
        "avg_latency_ms": round(run.avg_latency_ms, 1),
        "per_intent": run.per_intent,
        "failure_count": len(run.failures),
        "started_at": run.started_at, "completed_at": run.completed_at,
    }


@api_router.get("/intent-rl/v2/results")
async def api_intent_rl_v2_results():
    """Get full v2 results."""
    from intent_rl.runner_v2 import get_current_v2_run
    run = get_current_v2_run()
    if not run:
        return {"status": "no_run"}
    return {
        "run_id": run.run_id, "version": "v2",
        "in_progress": run.in_progress,
        "total": run.total, "completed": run.completed,
        "intent_accuracy": round(run.intent_accuracy * 100, 1),
        "avg_sub_intent_coverage": round(run.avg_sub_intent_coverage * 100, 1),
        "avg_entity_coverage": round(run.avg_entity_coverage * 100, 1),
        "per_intent": run.per_intent,
        "failures": run.failures, "cases": run.cases,
    }


# ── Intent RL Loop: 10-iteration reinforcement learning ──

@api_router.post("/intent-rl/loop/start")
async def api_start_rl_loop(iterations: int = 10):
    """Start the 10-iteration RL loop with feedback injection."""
    from intent_rl.rl_loop import run_rl_loop, get_rl_loop_state
    from intent_rl.seed_digital_self import seed_digital_self, clear_digital_self
    state = get_rl_loop_state()
    if state["running"]:
        return {"status": "already_running", "iteration": state["current_iteration"], "total": state["total_iterations"]}
    # Fresh seed before loop
    await clear_digital_self()
    seed_stats = await seed_digital_self()
    result = await run_rl_loop(n_iterations=min(iterations, 10))
    return {"status": result, "iterations": min(iterations, 10), "digital_self_seeded": seed_stats}


@api_router.get("/intent-rl/loop/status")
async def api_rl_loop_status():
    """Get live RL loop status — accuracy progression across iterations."""
    from intent_rl.rl_loop import get_rl_loop_state
    state = get_rl_loop_state()
    summary = []
    for it in state.get("iterations", []):
        summary.append({
            "iteration": it["iteration"],
            "accuracy": it["intent_accuracy"],
            "sub_coverage": it["sub_intent_coverage"],
            "entity_coverage": it["entity_coverage"],
            "failures": it["failure_count"],
            "corrections": it.get("corrections_in_engine", it.get("corrections_added", 0)),
        })
    return {
        "running": state["running"],
        "current_iteration": state["current_iteration"],
        "total_iterations": state["total_iterations"],
        "progression": summary,
        "started_at": state.get("started_at"),
        "completed_at": state.get("completed_at"),
    }


@api_router.get("/intent-rl/loop/details")
async def api_rl_loop_details():
    """Get detailed RL loop results with failure breakdown per iteration."""
    from intent_rl.rl_loop import get_rl_loop_state
    return get_rl_loop_state()


# ── Micro-Questions: Test endpoint ──

class MicroQuestionTestRequest(BaseModel):
    transcript: str
    user_id: str = "rl_test_user"

@api_router.post("/intent/micro-questions/test")
async def api_test_micro_questions(req: MicroQuestionTestRequest):
    """Test the full pipeline: L1 Scout → Micro-Question generation.
    
    Runs intent extraction, then generates personalized micro-questions
    using the Digital Self if confidence is low or dimensions are missing.
    """
    from l1.scout import run_l1_scout
    from intent.micro_questions import generate_micro_questions, should_ask_micro_questions
    import uuid

    session_id = f"mq_test_{uuid.uuid4().hex[:8]}"

    # Step 1: Run L1 Scout
    draft = await run_l1_scout(session_id=session_id, user_id=req.user_id, transcript=req.transcript)
    top = draft.hypotheses[0] if draft.hypotheses else None

    hypothesis = top.hypothesis if top else ""
    confidence = top.confidence if top else 0.0
    intent = top.intent if top else ""
    dimensions = top.dimension_suggestions if top else {}

    # Step 2: Check if micro-questions needed
    needs_questions = should_ask_micro_questions(confidence, dimensions)

    # Step 3: Generate micro-questions (always for test endpoint)
    mq_result = await generate_micro_questions(
        session_id=session_id, user_id=req.user_id, transcript=req.transcript,
        hypothesis=hypothesis, confidence=confidence, dimensions=dimensions,
    )

    return {
        "intent_extraction": {
            "hypothesis": hypothesis,
            "intent": intent,
            "confidence": confidence,
            "dimensions": dimensions,
            "latency_ms": round(draft.latency_ms, 1),
        },
        "needs_clarification": needs_questions,
        "micro_questions": {
            "trigger": mq_result.trigger_reason,
            "questions": [
                {"question": q.question, "why": q.why, "options": q.options, "fills": q.dimension_filled}
                for q in mq_result.questions
            ],
            "latency_ms": round(mq_result.latency_ms, 1),
        },
    }


class ClarificationLoopRequest(BaseModel):
    transcript: str
    clarification_response: str
    user_id: str = "rl_test_user"

@api_router.post("/intent/clarification-loop/test")
async def api_test_clarification_loop(req: ClarificationLoopRequest):
    """Test the full loop: original → micro-question → clarification → re-run."""
    from l1.scout import run_l1_scout
    from intent.micro_questions import generate_micro_questions
    import uuid
    session_id = f"cl_test_{uuid.uuid4().hex[:8]}"

    # Pass 1: Original
    draft1 = await run_l1_scout(session_id=f"{session_id}_p1", user_id=req.user_id, transcript=req.transcript)
    top1 = draft1.hypotheses[0] if draft1.hypotheses else None
    hyp1, conf1, dims1 = (top1.hypothesis, top1.confidence, top1.dimension_suggestions) if top1 else ("", 0, {})

    mq = await generate_micro_questions(
        session_id=session_id, user_id=req.user_id, transcript=req.transcript,
        hypothesis=hyp1, confidence=conf1, dimensions=dims1,
    )
    question = mq.questions[0].question if mq.questions else "(no question)"

    # Pass 2: Enriched with clarification
    combined = f"{req.transcript}. Clarification: {req.clarification_response}"
    draft2 = await run_l1_scout(session_id=f"{session_id}_p2", user_id=req.user_id, transcript=combined)
    top2 = draft2.hypotheses[0] if draft2.hypotheses else None
    hyp2, conf2, dims2 = (top2.hypothesis, top2.confidence, top2.dimension_suggestions) if top2 else ("", 0, {})

    return {
        "pass_1": {"hypothesis": hyp1, "intent": top1.intent if top1 else "", "confidence": conf1, "dimensions": dims1},
        "clarification": {"question": question, "response": req.clarification_response},
        "pass_2": {"hypothesis": hyp2, "intent": top2.intent if top2 else "", "confidence": conf2, "dimensions": dims2},
        "improvement": {"confidence_delta": round(conf2 - conf1, 3)},
    }


# ── Full Pipeline Test: L1 → Micro-Q → Dimensions → L2 → QC ──

@api_router.post("/pipeline/test/run")
async def api_run_pipeline_test(batch_size: int = 10, seed: bool = True):
    """Run full pipeline test: L1 → Micro-Q → Dimensions → L2 Sentry → QC Sentry."""
    from intent_rl.full_pipeline_test import run_full_pipeline_test, get_pipeline_state
    state = get_pipeline_state()
    if state["running"]:
        return {"status": "already_running", "progress": f"{state['completed']}/{state['total']}"}
    if seed:
        from intent_rl.seed_digital_self import seed_digital_self, clear_digital_self
        await clear_digital_self()
        await seed_digital_self()
    result = await run_full_pipeline_test(batch_size=min(batch_size, 40))
    return {"status": result, "total_cases": min(batch_size, 40)}


@api_router.get("/pipeline/test/status")
async def api_pipeline_test_status():
    """Get full pipeline test status."""
    from intent_rl.full_pipeline_test import get_pipeline_state
    state = get_pipeline_state()
    return {
        "running": state["running"],
        "progress": f"{state['completed']}/{state['total']}",
        "summary": state.get("summary", {}),
        "started_at": state.get("started_at"),
        "completed_at": state.get("completed_at"),
    }


@api_router.get("/pipeline/test/results")
async def api_pipeline_test_results():
    """Get full pipeline test case-by-case results."""
    from intent_rl.full_pipeline_test import get_pipeline_state
    state = get_pipeline_state()
    return {
        "running": state["running"],
        "summary": state.get("summary", {}),
        "results": state.get("results", []),
    }


# ── Mandate Builder: Intent + Dimensions = Mandate ──

class MandateRequest(BaseModel):
    transcript: str
    user_id: str = "rl_test_user"

@api_router.post("/mandate/build")
async def api_build_mandate(req: MandateRequest):
    """Full mandate pipeline: broken thoughts → Intent → Dimensions → Missing Questions.
    
    Returns the mandate + whisper-questions for every missing dimension.
    No mandate can execute with missing dimensions.
    """
    from l1.scout import run_l1_scout
    from dimensions.extractor import extract_mandate_dimensions
    from intent.mandate_questions import generate_mandate_questions, get_all_missing
    import uuid
    session_id = f"mandate_{uuid.uuid4().hex[:8]}"

    # Step 1: Intent
    draft = await run_l1_scout(session_id=session_id, user_id=req.user_id, transcript=req.transcript)
    top = draft.hypotheses[0] if draft.hypotheses else None
    intent = top.intent if top else "Unknown"
    sub_intents = top.sub_intents if top else []

    # Step 2: Execution-ready dimensions
    mandate = await extract_mandate_dimensions(
        session_id=session_id, user_id=req.user_id, transcript=req.transcript,
        intent=intent, sub_intents=sub_intents,
        l1_dimensions=top.dimension_suggestions if top else None,
    )

    # Step 3: Questions for ALL missing dimensions
    all_missing = get_all_missing(mandate)
    questions_batch = await generate_mandate_questions(
        session_id=session_id, user_id=req.user_id, transcript=req.transcript,
        mandate=mandate, batch_size=len(all_missing),  # ask ALL
    )

    # Build definitive status
    definitive = len(all_missing) == 0

    return {
        "intent": intent,
        "summary": top.hypothesis if top else "",
        "sub_intents": sub_intents,
        "confidence": top.confidence if top else 0,
        "mandate": {k: v for k, v in mandate.items() if k != "_meta"},
        "mandate_id": session_id,
        "status": "DEFINITIVE" if definitive else "INCOMPLETE",
        "missing_count": len(all_missing),
        "questions": [
            {"question": q.question, "action": q.fills_action,
             "dimension": q.fills_dimension, "options": q.options}
            for q in questions_batch.questions
        ],
    }


class MandateCompleteRequest(BaseModel):
    mandate_id: str
    transcript: str              # original broken thoughts
    answers: str                 # user's combined answers to the 3 questions
    user_id: str = "rl_test_user"

@api_router.post("/mandate/complete")
async def api_complete_mandate(req: MandateCompleteRequest):
    """Mandate completion loop:
    1. Combine original transcript + user's answers
    2. Re-extract intent + dimensions with enriched context
    3. Check if DEFINITIVE (zero missing)
    4. If yes → learn from mandate → store in DS → done
    5. If no → generate next round of questions (max 3 rounds total)
    """
    from l1.scout import run_l1_scout
    from dimensions.extractor import extract_mandate_dimensions
    from intent.mandate_questions import generate_mandate_questions, get_all_missing
    from memory.post_mandate_learning import learn_from_mandate
    import uuid

    session_id = req.mandate_id or f"mandate_{uuid.uuid4().hex[:8]}"

    # Combine original + answers into enriched transcript
    combined = f"{req.transcript}. User confirmed: {req.answers}"

    # Re-extract with full context
    draft = await run_l1_scout(
        session_id=f"{session_id}_complete", user_id=req.user_id, transcript=combined,
    )
    top = draft.hypotheses[0] if draft.hypotheses else None
    intent = top.intent if top else "Unknown"
    sub_intents = top.sub_intents if top else []

    mandate = await extract_mandate_dimensions(
        session_id=f"{session_id}_complete", user_id=req.user_id, transcript=combined,
        intent=intent, sub_intents=sub_intents,
        l1_dimensions=top.dimension_suggestions if top else None,
    )

    all_missing = get_all_missing(mandate)
    definitive = len(all_missing) == 0

    # If definitive → learn from mandate into Digital Self
    ds_learned = None
    if definitive:
        ds_learned = await learn_from_mandate(req.user_id, mandate)

    # If still incomplete → one more round of questions
    questions = []
    if not definitive:
        batch = await generate_mandate_questions(
            session_id=f"{session_id}_q2", user_id=req.user_id,
            transcript=combined, mandate=mandate,
        )
        questions = [
            {"question": q.question, "action": q.fills_action,
             "dimension": q.fills_dimension, "options": q.options}
            for q in batch.questions
        ]

    return {
        "intent": intent,
        "mandate": {k: v for k, v in mandate.items() if k != "_meta"},
        "mandate_id": session_id,
        "status": "DEFINITIVE" if definitive else "INCOMPLETE",
        "missing_count": len(all_missing),
        "questions": questions,
        "ds_learned": ds_learned,
    }


class SkillDetermineRequest(BaseModel):
    transcript: str
    user_id: str = "rl_test_user"

@api_router.post("/mandate/skills")
async def api_determine_skills(req: SkillDetermineRequest):
    """Full pipeline: broken thoughts → mandate → skill determination.
    LLM reads the 73-skill library and decides what's needed."""
    from l1.scout import run_l1_scout
    from dimensions.extractor import extract_mandate_dimensions
    from skills.determine import determine_skills
    import uuid
    session_id = f"skills_{uuid.uuid4().hex[:8]}"

    draft = await run_l1_scout(session_id=session_id, user_id=req.user_id, transcript=req.transcript)
    top = draft.hypotheses[0] if draft.hypotheses else None
    intent = top.intent if top else "Unknown"
    sub_intents = top.sub_intents if top else []

    mandate = await extract_mandate_dimensions(
        session_id=session_id, user_id=req.user_id, transcript=req.transcript,
        intent=intent, sub_intents=sub_intents,
        l1_dimensions=top.dimension_suggestions if top else None,
    )

    skills = await determine_skills(session_id=session_id, user_id=req.user_id, mandate=mandate)

    return {
        "intent": intent,
        "mandate_summary": mandate.get("mandate_summary", ""),
        "actions_count": len(mandate.get("actions", [])),
        "skill_plan": skills.get("skill_plan", []),
        "execution_strategy": skills.get("execution_strategy", ""),
        "risk_assessment": skills.get("risk_assessment", ""),
        "estimated_complexity": skills.get("estimated_complexity", ""),
    }



# Include REST router
app.include_router(api_router)

# Include onboarding API router
from api.onboarding import router as onboarding_router
app.include_router(onboarding_router, prefix="/api")

# Include mock dashboard and setup wizard routers — DEV ONLY
# These MUST NOT be active in production (ENV=prod)
_settings_for_mock = get_settings()
if _settings_for_mock.ENV != "prod":
    from api.dashboard_mock import router as dashboard_router
    app.include_router(dashboard_router, prefix="/api")

    from api.setup_wizard import router as setup_router
    app.include_router(setup_router, prefix="/api")

# Digital Self sync — email, audit log, snapshot (Category B)
from api.digital_self_sync import router as ds_sync_router
app.include_router(ds_sync_router, prefix="/api")





# =====================================================
#  WebSocket Endpoint
# =====================================================

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for mobile app."""
    await handle_ws_connection(websocket)
