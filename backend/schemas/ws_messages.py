"""WebSocket message schemas — canonical contract between mobile and BE.

Version: v1
All WS communication flows through these typed envelopes.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
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
    ERROR = "error"
    SESSION_TERMINATED = "session_terminated"


# ---- Base Envelope ----

class WSEnvelope(BaseModel):
    """Every WS message is wrapped in this envelope."""
    type: WSMessageType
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict = Field(default_factory=dict)


# ---- Client Payloads ----

class AuthPayload(BaseModel):
    token: str
    device_id: str
    client_version: str = "1.0.0"


class HeartbeatPayload(BaseModel):
    session_id: str
    seq: int  # monotonic sequence number
    client_ts: datetime = Field(default_factory=datetime.utcnow)


class ExecuteRequestPayload(BaseModel):
    session_id: str
    draft_id: str
    touch_token: Optional[str] = None  # for Tier ≥2
    biometric_proof: Optional[str] = None  # for Tier 3


# ---- Server Payloads ----

class AuthOkPayload(BaseModel):
    session_id: str
    user_id: str
    heartbeat_interval_ms: int
    server_ts: datetime = Field(default_factory=datetime.utcnow)


class AuthFailPayload(BaseModel):
    reason: str
    code: str = "AUTH_FAIL"


class HeartbeatAckPayload(BaseModel):
    seq: int
    server_ts: datetime = Field(default_factory=datetime.utcnow)


class ExecuteBlockedPayload(BaseModel):
    reason: str
    code: str  # PRESENCE_STALE | ENV_GUARD | GUARDRAIL_VIOLATION | etc.
    draft_id: Optional[str] = None


class ErrorPayload(BaseModel):
    message: str
    code: str
    recoverable: bool = True
