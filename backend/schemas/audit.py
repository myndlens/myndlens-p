"""Audit event schemas."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
import uuid


class AuditEventType(str, Enum):
    SESSION_CREATED = "session_created"
    SESSION_TERMINATED = "session_terminated"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    HEARTBEAT_RECEIVED = "heartbeat_received"
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    EXECUTE_REQUESTED = "execute_requested"
    EXECUTE_BLOCKED = "execute_blocked"
    EXECUTE_COMPLETED = "execute_completed"
    ENV_GUARD_VIOLATION = "env_guard_violation"
    PRESENCE_STALE = "presence_stale"
    # SSO + Tenant lifecycle
    SSO_AUTH_SUCCESS = "sso_auth_success"
    SSO_AUTH_FAILURE = "sso_auth_failure"
    SUBSCRIPTION_INACTIVE_BLOCK = "subscription_inactive_block"
    TENANT_ACTIVATED = "tenant_activated"
    TENANT_SUSPENDED = "tenant_suspended"
    TENANT_DEPROVISIONED = "tenant_deprovisioned"
    # Prompt compliance
    PROMPT_BYPASS_ATTEMPT = "prompt_bypass_attempt"
    PROMPT_SNAPSHOT_SAVED = "prompt_snapshot_saved"


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: AuditEventType
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = Field(default_factory=dict)
    env: str = "dev"

    def to_doc(self) -> dict:
        d = self.model_dump()
        d["event_type"] = d["event_type"].value if hasattr(d["event_type"], "value") else d["event_type"]
        return d
