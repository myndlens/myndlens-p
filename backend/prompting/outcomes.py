"""Prompt Outcome Tracking — records results of LLM calls for analytics.

Enables the feedback loop: prompt -> execution -> outcome -> improvement.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from core.database import get_db

logger = logging.getLogger(__name__)


class OutcomeResult(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILURE = "FAILURE"
    CORRECTED = "CORRECTED"
    ABANDONED = "ABANDONED"


@dataclass
class PromptOutcome:
    prompt_id: str
    purpose: str
    session_id: str
    user_id: str
    result: OutcomeResult
    accuracy_score: float = 0.0
    execution_success: bool = False
    user_corrected: bool = False
    correction_type: Optional[str] = None
    latency_ms: float = 0.0
    tokens_used: int = 0
    sections_used: List[str] = field(default_factory=list)
    model_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


async def track_outcome(outcome: PromptOutcome) -> str:
    db = get_db()
    doc = {
        "prompt_id": outcome.prompt_id,
        "purpose": outcome.purpose,
        "session_id": outcome.session_id,
        "user_id": outcome.user_id,
        "result": outcome.result.value,
        "accuracy_score": outcome.accuracy_score,
        "execution_success": outcome.execution_success,
        "user_corrected": outcome.user_corrected,
        "correction_type": outcome.correction_type,
        "latency_ms": outcome.latency_ms,
        "tokens_used": outcome.tokens_used,
        "sections_used": outcome.sections_used,
        "model_name": outcome.model_name,
        "metadata": outcome.metadata,
        "created_at": outcome.created_at,
    }
    result = await db.prompt_outcomes.insert_one(doc)
    logger.info(
        "Outcome tracked: prompt=%s purpose=%s result=%s accuracy=%.2f",
        outcome.prompt_id, outcome.purpose, outcome.result.value, outcome.accuracy_score,
    )
    return str(result.inserted_id)


async def track_user_correction(
    session_id: str,
    user_id: str,
    original_intent: str,
    corrected_intent: str,
    prompt_id: Optional[str] = None,
) -> None:
    db = get_db()
    doc = {
        "session_id": session_id,
        "user_id": user_id,
        "original_intent": original_intent,
        "corrected_intent": corrected_intent,
        "prompt_id": prompt_id,
        "created_at": datetime.now(timezone.utc),
    }
    await db.user_corrections.insert_one(doc)
    logger.info("User correction tracked: session=%s", session_id)
