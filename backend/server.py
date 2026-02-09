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
from typing import Optional

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
    """Pair a device and return a JWT for WebSocket auth.
    
    In production, this would require prior user authentication.
    For Batch 1, we use a simplified flow.
    """
    settings = get_settings()
    session_id = str(uuid.uuid4())

    token = generate_token(
        user_id=req.user_id,
        device_id=req.device_id,
        session_id=session_id,
        env=settings.ENV,
    )

    logger.info(
        "Device paired: user=%s device=%s",
        req.user_id, req.device_id,
    )

    return PairResponse(
        token=token,
        user_id=req.user_id,
        device_id=req.device_id,
        env=settings.ENV,
    )


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


# Include REST router
app.include_router(api_router)


# =====================================================
#  WebSocket Endpoint
# =====================================================

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for mobile app."""
    await handle_ws_connection(websocket)
