"""WebSocket message schemas — canonical contract between mobile and BE.

Version: v1
All WS communication flows through these typed envelopes.

FROZEN: Any changes require an ADR + schema compatibility test.
All message types and payload models MUST be defined here.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid


# ---- Enums ----

class WSMessageType(str, Enum):
    # Client → Server
    AUTH = "auth"
    HEARTBEAT = "heartbeat"
    AUDIO_CHUNK = "audio_chunk"
    EXECUTE_REQUEST = "execute_request"
    CANCEL = "cancel"
    TEXT_INPUT = "text_input"
    DS_CONTEXT = "ds_context"       # Device → Backend: readable text for resolved node IDs

    # Server → Client
    AUTH_OK = "auth_ok"
    AUTH_FAIL = "auth_fail"
    HEARTBEAT_ACK = "heartbeat_ack"
    TRANSCRIPT_PARTIAL = "transcript_partial"
    TRANSCRIPT_FINAL = "transcript_final"
    DRAFT_UPDATE = "draft_update"
    TTS_AUDIO = "tts_audio"
    EXECUTE_BLOCKED = "execute_blocked"
    EXECUTE_OK = "execute_ok"
    PIPELINE_STAGE = "pipeline_stage"
    CLARIFICATION_QUESTION = "clarification_question"
    ERROR = "error"
    SESSION_TERMINATED = "session_terminated"
    DS_RESOLVE = "ds_resolve"       # Backend → Device: "resolve these node IDs for me"


# ---- Base Envelope ----

class WSEnvelope(BaseModel):
    """Every WS message is wrapped in this envelope."""
    type: WSMessageType
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict = Field(default_factory=dict)


# =====================================================
#  Client → Server Payloads
# =====================================================

class AuthPayload(BaseModel):
    token: str
    device_id: str
    client_version: str = "1.0.0"


class HeartbeatPayload(BaseModel):
    session_id: str
    seq: int  # monotonic sequence number
    client_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AudioChunkPayload(BaseModel):
    """Audio chunk from client — ~250ms of audio, base64-encoded."""
    session_id: str
    audio: str  # base64-encoded audio data
    seq: int  # monotonic chunk sequence number
    timestamp: Optional[float] = None  # client-side timestamp (epoch ms)
    duration_ms: int = 250  # nominal chunk duration


class ExecuteRequestPayload(BaseModel):
    session_id: str
    draft_id: str
    touch_token: Optional[str] = None  # for Tier ≥2
    biometric_proof: Optional[str] = None  # for Tier 3


class CancelPayload(BaseModel):
    """Cancel/stream-end signal from client."""
    session_id: str
    reason: str = "user_cancel"  # user_cancel | vad_end_of_utterance


class TextInputPayload(BaseModel):
    """Text input as STT fallback.

    context_capsule: optional Digital Self context from the device PKG.
    Backend uses this instead of querying server-side memory.
    """
    session_id: str
    text: str
    context_capsule: Optional[str] = None  # JSON-serialised ContextCapsule from device PKG


# =====================================================
#  Server → Client Payloads
# =====================================================

class AuthOkPayload(BaseModel):
    session_id: str
    user_id: str
    heartbeat_interval_ms: int
    server_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuthFailPayload(BaseModel):
    reason: str
    code: str = "AUTH_FAIL"


class HeartbeatAckPayload(BaseModel):
    seq: int
    server_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TranscriptPayload(BaseModel):
    """Transcript partial or final from server."""
    text: str
    is_final: bool = False
    fragment_count: int = 0
    confidence: float = 0.0
    span_ids: List[str] = Field(default_factory=list)


class TTSAudioPayload(BaseModel):
    """TTS response from server. Format=text for local TTS, audio for streamed."""
    text: str
    session_id: str
    format: str = "text"  # "text" (local TTS) | "audio" (binary stream)
    is_mock: bool = False


class ExecuteBlockedPayload(BaseModel):
    reason: str
    code: str  # PRESENCE_STALE | ENV_GUARD | GUARDRAIL_VIOLATION | PIPELINE_NOT_READY
    draft_id: Optional[str] = None


class ExecuteOkPayload(BaseModel):
    draft_id: str
    mio_id: Optional[str] = None
    dispatch_status: str = "pending"


class ErrorPayload(BaseModel):
    message: str
    code: str
    recoverable: bool = True
