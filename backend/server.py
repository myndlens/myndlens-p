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
from pydantic import BaseModel, Field
from typing import List, Optional

# Load env before anything else
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from config.settings import get_settings
from core.logging_config import setup_logging
from core.database import get_db, init_indexes, close_db
from core.exceptions import AuthError, MyndLensError
from auth.tokens import generate_token
from auth.sso_validator import get_sso_validator, SSOClaims
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
from l2.sentry import run_l2_sentry, check_l1_l2_agreement
from qc.sentry import run_qc_sentry

# ---- Setup logging ----
setup_logging()
logger = logging.getLogger(__name__)


# ---- Lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("MyndLens BE starting — env=%s", settings.ENV)
    await init_indexes()
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
        "status": "ok",
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


# ---- Device Pairing / Auth ----
class PairRequest(BaseModel):
    user_id: str
    device_id: str
    client_version: str = "1.0.0"


class PairResponse(BaseModel):
    token: str
    user_id: str
    device_id: str
    env: str


@api_router.post("/auth/pair", response_model=PairResponse)
async def pair_device(req: PairRequest):
    """DEV ONLY: Pair a device with a simple JWT.
    
    Deprecated in favor of SSO login. Kept for dev/testing only.
    """
    settings = get_settings()
    if settings.ENV == "prod":
        raise HTTPException(status_code=404, detail="Not found")

    session_id = str(uuid.uuid4())
    token = generate_token(
        user_id=req.user_id,
        device_id=req.device_id,
        session_id=session_id,
        env=settings.ENV,
    )

    logger.info("DEV pair: user=%s device=%s", req.user_id, req.device_id)

    return PairResponse(
        token=token,
        user_id=req.user_id,
        device_id=req.device_id,
        env=settings.ENV,
    )


# =====================================================
#  ObeGee SSO Mock IDP (dev fixture only)
# =====================================================

class SSOLoginRequest(BaseModel):
    username: str
    password: str
    device_id: str


class SSOLoginResponse(BaseModel):
    token: str
    obegee_user_id: str
    myndlens_tenant_id: str
    subscription_status: str


# Conditionally register the mock IDP route
_settings_for_route = get_settings()
if _settings_for_route.ENV != "prod" and _settings_for_route.ENABLE_OBEGEE_MOCK_IDP:

    @api_router.post("/sso/myndlens/token", response_model=SSOLoginResponse)
    async def mock_obegee_sso_token(req: SSOLoginRequest):
        """MOCK ObeGee SSO endpoint — DEV ONLY.
        
        Issues SSO tokens with correct claims for testing.
        This endpoint MUST NOT exist in prod (route not registered).
        """
        settings = get_settings()
        # Hard guard (belt + suspenders)
        if settings.ENV == "prod":
            raise HTTPException(status_code=404, detail="Not found")

        # Auto-activate tenant for dev convenience
        from tenants.lifecycle import activate_tenant
        result = await activate_tenant(req.username)
        tenant_id = result["tenant_id"]

        now = datetime.now(timezone.utc)
        payload = {
            "iss": "obegee",
            "aud": "myndlens",
            "obegee_user_id": req.username,
            "myndlens_tenant_id": tenant_id,
            "subscription_status": "ACTIVE",
            "iat": now.timestamp(),
            "exp": (now + timedelta(hours=24)).timestamp(),
        }
        token = jwt.encode(payload, settings.OBEGEE_SSO_HS_SECRET, algorithm="HS256")

        logger.info("MOCK SSO token issued: user=%s tenant=%s", req.username, tenant_id)

        return SSOLoginResponse(
            token=token,
            obegee_user_id=req.username,
            myndlens_tenant_id=tenant_id,
            subscription_status="ACTIVE",
        )


# =====================================================
#  Tenant Lifecycle APIs (S2S auth)
# =====================================================

def _verify_s2s_token(x_obegee_s2s_token: str = Header(None)) -> None:
    """Verify service-to-service auth token."""
    settings = get_settings()
    if x_obegee_s2s_token != settings.OBEGEE_S2S_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid S2S token")


class TenantActivateReq(BaseModel):
    obegee_user_id: str
    openclaw_endpoint: Optional[str] = None


class TenantActionReq(BaseModel):
    tenant_id: str
    reason: str = ""


@api_router.post("/tenants/activate")
async def api_activate_tenant(req: TenantActivateReq, x_obegee_s2s_token: str = Header(None)):
    """Activate a tenant. Idempotent. Requires S2S auth."""
    _verify_s2s_token(x_obegee_s2s_token)
    from tenants.lifecycle import activate_tenant
    return await activate_tenant(req.obegee_user_id, req.openclaw_endpoint)


@api_router.post("/tenants/suspend")
async def api_suspend_tenant(req: TenantActionReq, x_obegee_s2s_token: str = Header(None)):
    """Suspend a tenant. Requires S2S auth."""
    _verify_s2s_token(x_obegee_s2s_token)
    from tenants.lifecycle import suspend_tenant
    return await suspend_tenant(req.tenant_id, req.reason)


@api_router.post("/tenants/deprovision")
async def api_deprovision_tenant(req: TenantActionReq, x_obegee_s2s_token: str = Header(None)):
    """Deprovision a tenant. Requires S2S auth."""
    _verify_s2s_token(x_obegee_s2s_token)
    from tenants.lifecycle import deprovision_tenant
    return await deprovision_tenant(req.tenant_id, req.reason)


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
#  Commit State Machine APIs (Batch 6)
# =====================================================

class CreateCommitRequest(BaseModel):
    session_id: str
    draft_id: str
    intent_summary: str
    action_class: str
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
        action_class=req.action_class,
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
    l1_action_class: str = ""
    l1_confidence: float = 0.0


class QCRunRequest(BaseModel):
    session_id: str = "diagnostic"
    user_id: str = "diagnostic"
    transcript: str
    action_class: str
    intent_summary: str


@api_router.post("/l2/run")
async def api_run_l2(req: L2RunRequest):
    """Diagnostic: run L2 Sentry on a transcript."""
    verdict = await run_l2_sentry(
        session_id=req.session_id,
        user_id=req.user_id,
        transcript=req.transcript,
        l1_action_class=req.l1_action_class,
        l1_confidence=req.l1_confidence,
    )
    return {
        "verdict_id": verdict.verdict_id,
        "action_class": verdict.action_class,
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
        action_class=req.action_class,
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


# Include REST router
app.include_router(api_router)


# =====================================================
#  WebSocket Endpoint
# =====================================================

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for mobile app."""
    await handle_ws_connection(websocket)
