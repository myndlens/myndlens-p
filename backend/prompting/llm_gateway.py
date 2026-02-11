"""LLM Gateway — the ONLY allowed path to call an LLM.

Hard gate: requires PromptArtifact with prompt_id.
Rejects raw message arrays. Throws PromptBypassError.
Audit logs every bypass attempt.

LlmChat import lives HERE ONLY. No other module may import it.
"""
import logging
import uuid
from typing import Optional

from config.settings import get_settings
from core.exceptions import MyndLensError
from observability.audit_log import log_audit_event
from schemas.audit import AuditEventType
from prompting.types import PromptArtifact, PromptPurpose
from prompting.call_sites import get_call_site, validate_purpose

logger = logging.getLogger(__name__)


class PromptBypassError(MyndLensError):
    """Raised when someone attempts to call LLM without PromptArtifact."""
    def __init__(self, message: str = "LLM call attempted without PromptArtifact"):
        super().__init__(message, code="PROMPT_BYPASS")


async def call_llm(
    artifact: PromptArtifact,
    call_site_id: str,
    model_provider: str = "gemini",
    model_name: str = "gemini-2.0-flash",
    session_id: Optional[str] = None,
) -> str:
    """The ONLY allowed way to call an LLM in MyndLens.

    Args:
        artifact: PromptArtifact from PromptOrchestrator.build()
        call_site_id: Registered call site ID (from call_sites.py)
        model_provider: LLM provider (gemini, openai, anthropic)
        model_name: Model name
        session_id: Optional session ID for chat context

    Returns:
        LLM response text.

    Raises:
        PromptBypassError: If artifact is invalid or call site unregistered.
    """
    settings = get_settings()

    # ---- Hard Gate 1: Artifact must exist with prompt_id ----
    if artifact is None:
        await _log_bypass("null_artifact", call_site_id)
        raise PromptBypassError("PromptArtifact is None")

    if not artifact.prompt_id:
        await _log_bypass("missing_prompt_id", call_site_id)
        raise PromptBypassError("PromptArtifact.prompt_id is missing")

    if not artifact.messages:
        await _log_bypass("empty_messages", call_site_id)
        raise PromptBypassError("PromptArtifact.messages is empty")

    # ---- Hard Gate 2: Call site must be registered ----
    try:
        get_call_site(call_site_id)
    except ValueError as e:
        await _log_bypass(f"unregistered_site:{call_site_id}", call_site_id)
        raise PromptBypassError(str(e))

    # ---- Hard Gate 3: Purpose must be allowed for this call site ----
    try:
        validate_purpose(call_site_id, artifact.purpose)
    except ValueError as e:
        await _log_bypass(f"purpose_violation:{artifact.purpose.value}", call_site_id)
        raise PromptBypassError(str(e))

    # ---- Gate passed: make the LLM call ----
    if not settings.EMERGENT_LLM_KEY:
        raise PromptBypassError("EMERGENT_LLM_KEY not configured")

    # LlmChat import lives HERE ONLY
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    system_msg = ""
    user_msg = ""
    for m in artifact.messages:
        if m.get("role") == "system":
            system_msg = m["content"]
        elif m.get("role") == "user":
            user_msg = m["content"]

    chat_session_id = session_id or f"{call_site_id}-{artifact.prompt_id[:8]}"

    chat = LlmChat(
        api_key=settings.EMERGENT_LLM_KEY,
        session_id=chat_session_id,
        system_message=system_msg,
    ).with_model(model_provider, model_name)

    response = await chat.send_message(UserMessage(text=user_msg))

    logger.info(
        "[LLMGateway] Call: site=%s purpose=%s prompt=%s model=%s/%s",
        call_site_id, artifact.purpose.value, artifact.prompt_id[:12],
        model_provider, model_name,
    )

    return response


async def _log_bypass(reason: str, call_site_id: str) -> None:
    """Audit log a bypass attempt. Never logs prompt text (hash only)."""
    logger.critical(
        "PROMPT_BYPASS_ATTEMPT: site=%s reason=%s",
        call_site_id, reason,
    )
    try:
        await log_audit_event(
            AuditEventType.PROMPT_BYPASS_ATTEMPT,
            details={"call_site_id": call_site_id, "reason": reason},
        )
    except Exception:
        pass  # Don't let audit failure mask the bypass
