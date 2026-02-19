"""MIO (Master Intent Object) canonical schema.

No execution without valid MIO. Defined here for schema-first contracts.
Implementation in Batch 8, but schema frozen now.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


class ActionClass(str, Enum):
    COMM_SEND = "COMM_SEND"
    SCHED_MODIFY = "SCHED_MODIFY"
    INFO_RETRIEVE = "INFO_RETRIEVE"
    DOC_EDIT = "DOC_EDIT"
    FIN_TRANS = "FIN_TRANS"
    SYS_CONFIG = "SYS_CONFIG"
    DRAFT_ONLY = "DRAFT_ONLY"


class RiskTier(int, Enum):
    NO_LATCH = 0
    VOICE_LATCH = 1
    PHYSICAL_LATCH = 2
    BIOMETRIC = 3


class MIOHeader(BaseModel):
    mio_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    signer_id: str = "MYNDLENS_BE_01"
    ttl_seconds: int = 120


class MIOConstraints(BaseModel):
    tier: RiskTier
    physical_latch_required: bool = False
    biometric_required: bool = False


class MIOIntentEnvelope(BaseModel):
    action: str  # e.g. "openclaw.v1.whatsapp.send"
    action_class: ActionClass
    params: Dict[str, Any] = Field(default_factory=dict)
    constraints: MIOConstraints


class MIOGrounding(BaseModel):
    transcript_hash: str  # SHA-256
    l1_hash: str  # SHA-256
    l2_audit_hash: str  # SHA-256
    memory_node_ids: List[str] = Field(default_factory=list)
    provenance_flags: Dict[str, str] = Field(default_factory=dict)


class MIOSecurityProof(BaseModel):
    touch_event_token: Optional[str] = None
    signature: Optional[str] = None  # ED25519


class MasterIntentObject(BaseModel):
    """The canonical MIO schema. Frozen from Batch 0."""
    header: MIOHeader = Field(default_factory=MIOHeader)
    intent_envelope: MIOIntentEnvelope
    grounding: MIOGrounding
    security_proof: MIOSecurityProof = Field(default_factory=MIOSecurityProof)
