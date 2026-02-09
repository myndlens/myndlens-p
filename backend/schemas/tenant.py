"""Tenant schemas — tenant lifecycle models."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid


class TenantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    DEPROVISIONED = "DEPROVISIONED"


class Tenant(BaseModel):
    """Tenant record in MongoDB."""
    tenant_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    obegee_user_id: str
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    openclaw_endpoint: Optional[str] = None
    key_refs: Dict[str, Any] = Field(default_factory=dict)

    def to_doc(self) -> dict:
        d = self.model_dump()
        d["status"] = d["status"].value if hasattr(d["status"], "value") else d["status"]
        return d


class TenantActivateRequest(BaseModel):
    obegee_user_id: str
    openclaw_endpoint: Optional[str] = None


class TenantSuspendRequest(BaseModel):
    tenant_id: str
    reason: str = "subscription_suspended"


class TenantDeprovisionRequest(BaseModel):
    tenant_id: str
    reason: str = "subscription_cancelled"
