"""Session schemas — user-device-session binding models."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class Session(BaseModel):
    """Represents an authenticated user-device-session binding."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    device_id: str
    env: str = "dev"  # dev | staging | prod
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat_at: Optional[datetime] = None
    heartbeat_seq: int = 0
    active: bool = True
    client_version: str = "1.0.0"

    def to_doc(self) -> dict:
        """Convert to MongoDB document."""
        return self.model_dump()


class SessionCreate(BaseModel):
    user_id: str
    device_id: str
    client_version: str = "1.0.0"
